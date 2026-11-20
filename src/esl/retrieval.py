"""Hybrid search over schema-workbook passages: pgvector plus BM25.

Embeddings are local. The debate model is chosen later and is not used here.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

EMBEDDING_DIM = 384
CORPUS = "erp_mtdd_schema"
_BM25_K1 = 1.5
_BM25_B = 0.75
_RRF_K = 60
_POOL = 50
_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Passage:
    corpus: str
    sheet: str
    locator: str
    body: str


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashEmbedder:
    """Deterministic stand-in so tests do not download a model."""

    dimension = EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = tokenize(text) or ["empty"]
            for token in tokens:
                digest = hashlib.sha256(token.encode()).digest()
                bucket = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[bucket] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class FastEmbedder:
    """Local BAAI/bge-small-en-v1.5. Same width as the passages column."""

    dimension = EMBEDDING_DIM
    model_name = "BAAI/bge-small-en-v1.5"

    def __init__(self) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError("install the index extra: pip install -e '.[index]'") from exc
        self._model = TextEmbedding(self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(value) for value in vector] for vector in self._model.embed(texts)]


def bm25_ranking(query: str, documents: list[tuple[str, str]]) -> list[str]:
    """Document ids with a positive score, best first."""

    query_tokens = tokenize(query)
    if not query_tokens or not documents:
        return []
    tokenized = [(doc_id, tokenize(text)) for doc_id, text in documents]
    lengths = [len(tokens) for _, tokens in tokenized]
    avgdl = sum(lengths) / len(lengths) if lengths else 0.0
    if avgdl == 0:
        return []
    df: dict[str, int] = {}
    for _, tokens in tokenized:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    n_docs = len(tokenized)
    scored: list[tuple[float, str]] = []
    for doc_id, tokens in tokenized:
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for token in set(query_tokens):
            freq = counts.get(token, 0)
            if freq == 0:
                continue
            idf = math.log(1 + (n_docs - df[token] + 0.5) / (df[token] + 0.5))
            denom = freq + _BM25_K1 * (1 - _BM25_B + _BM25_B * len(tokens) / avgdl)
            score += idf * (freq * (_BM25_K1 + 1)) / denom
        if score > 0:
            scored.append((score, doc_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [doc_id for _, doc_id in scored]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = _RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking[:_POOL], start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def vector_literal(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"embedding must have {EMBEDDING_DIM} dimensions")
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def replace_passages(conn, passages: list[Passage], vectors: list[list[float]]) -> int:
    if len(passages) != len(vectors):
        raise ValueError("one embedding per passage")
    corpora = {passage.corpus for passage in passages}
    if len(corpora) != 1:
        raise ValueError("replace one corpus at a time")
    corpus = corpora.pop()
    rows = [
        (
            uuid4(),
            passage.corpus,
            passage.sheet,
            passage.locator,
            passage.body,
            vector_literal(vector),
        )
        for passage, vector in zip(passages, vectors, strict=True)
    ]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM passages WHERE corpus = %s", (corpus,))
        cur.executemany(
            """
            INSERT INTO passages (id, corpus, sheet, locator, body, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            """,
            rows,
        )
    return len(passages)


def search_passages(conn, *, corpus: str, query: str, embedder: Embedder, limit: int) -> list[dict]:
    if not query.strip():
        raise ValueError("query is empty")
    if embedder.dimension != EMBEDDING_DIM:
        raise ValueError(f"embedder dimension must be {EMBEDDING_DIM}")
    rows = conn.execute(
        """
        SELECT id, sheet, locator, body
        FROM passages
        WHERE corpus = %s
        ORDER BY sheet, locator
        """,
        (corpus,),
    ).fetchall()
    if not rows:
        return []
    by_id = {str(row["id"]): row for row in rows}
    lexical = bm25_ranking(query, [(str(row["id"]), row["body"]) for row in rows])
    query_vector = embedder.embed([query])[0]
    neighbors = conn.execute(
        """
        SELECT id
        FROM passages
        WHERE corpus = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (corpus, vector_literal(query_vector), _POOL),
    ).fetchall()
    semantic = [str(row["id"]) for row in neighbors]
    fused = reciprocal_rank_fusion([lexical, semantic])
    hits = []
    for doc_id, score in fused[:limit]:
        row = by_id[doc_id]
        hits.append(
            {
                "sheet": row["sheet"],
                "locator": row["locator"],
                "text": row["body"],
                "score": round(score, 6),
            }
        )
    return hits
