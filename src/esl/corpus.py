"""Build the schema-workbook corpus and load it into Postgres.

One passage per documentation row. Locators are stable so an ontology can cite them.

    python -m esl.corpus index
    python -m esl.corpus search "final order value"
"""

import math
import sys
from collections.abc import Mapping

import pandas as pd

from esl.ontology import DOC_SHEETS
from esl.retrieval import CORPUS, Passage

_BUILDERS = {
    "Table Index": lambda row: (
        _text(row.get("Table Name")),
        " ".join(
            [
                "Table Index",
                _text(row.get("Table Name")),
                _text(row.get("Component")),
                _text(row.get("Module")),
                "primary key",
                _text(row.get("Primary Key")),
                _text(row.get("Table Category")),
            ]
        ),
    ),
    "Dependency Register": lambda row: (
        _text(row.get("Table Name")),
        " ".join(
            [
                "Dependency Register",
                _text(row.get("Table Name")),
                _text(row.get("Component Name")),
                "depends on",
                _text(row.get("Dependency Tables Name")),
                _text(row.get("Table Category Notes")),
            ]
        ),
    ),
    "Complexity Rules": lambda row: (
        _text(row.get("Complexity")),
        " ".join(
            [
                "Complexity Rules",
                _text(row.get("Complexity")),
                _text(row.get("Rule")),
                "weight",
                _text(row.get("Weight")),
            ]
        ),
    ),
    "Column Dictionary": lambda row: (
        f"{_text(row.get('Table'))}.{_text(row.get('Column Name'))}".strip("."),
        " ".join(
            [
                "Column Dictionary",
                _text(row.get("Table")),
                _text(row.get("Column Name")),
                _text(row.get("Data Type")),
                _text(row.get("Description / Notes")),
            ]
        ),
    ),
    "Relationships": lambda row: (
        (
            f"{_text(row.get('Child Table'))}.{_text(row.get('Child Column'))} -> "
            f"{_text(row.get('Parent Table'))}.{_text(row.get('Parent Key'))}"
        ),
        " ".join(
            [
                "Relationships",
                _text(row.get("Child Table")),
                _text(row.get("Child Column")),
                "references",
                _text(row.get("Parent Table")),
                _text(row.get("Parent Key")),
                "child",
                _text(row.get("Child Component")),
                "parent",
                _text(row.get("Parent Component")),
                _text(row.get("Optional?")),
            ]
        ),
    ),
    "Load Order": lambda row: (
        _text(row.get("Table")),
        " ".join(
            [
                "Load Order",
                _text(row.get("Order")),
                _text(row.get("Table")),
                _text(row.get("Component")),
                "depends on",
                _text(row.get("Depends On (parents)")),
            ]
        ),
    ),
}


def passages_from_docs(docs: Mapping[str, pd.DataFrame], corpus: str = CORPUS) -> list[Passage]:
    missing = [sheet for sheet in DOC_SHEETS if sheet not in docs]
    if missing:
        raise ValueError(f"schema workbook is missing: {', '.join(missing)}")
    passages: list[Passage] = []
    seen: dict[tuple[str, str], int] = {}
    for sheet in DOC_SHEETS:
        frame = docs[sheet]
        build = _BUILDERS[sheet]
        for record in frame.to_dict(orient="records"):
            locator, body = build(record)
            locator = locator.strip()
            body = " ".join(body.split())
            if not _complete(sheet, locator):
                continue
            key = (sheet, locator)
            count = seen.get(key, 0) + 1
            seen[key] = count
            if count > 1:
                locator = f"{locator} #{count}"
            passages.append(Passage(corpus=corpus, sheet=sheet, locator=locator, body=body))
    return passages


def _complete(sheet: str, locator: str) -> bool:
    if sheet == "Column Dictionary":
        table, dot, column = locator.partition(".")
        return bool(dot and table and column)
    if sheet == "Relationships":
        if " -> " not in locator:
            return False
        left, right = locator.split(" -> ", 1)
        child, left_dot, child_col = left.partition(".")
        parent, right_dot, parent_key = right.partition(".")
        return bool(left_dot and right_dot and child and child_col and parent and parent_key)
    return bool(locator)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        return text[:-2]
    return "" if text.lower() == "nan" else text


def index_workbook(database_url: str, schema_path: str) -> int:
    from pathlib import Path

    from esl.db import connect
    from esl.retrieval import FastEmbedder, replace_passages
    from esl.sources.erp_mtdd import read_docs

    passages = passages_from_docs(read_docs(Path(schema_path)))
    embedder = FastEmbedder()
    vectors: list[list[float]] = []
    batch = 256
    for start in range(0, len(passages), batch):
        chunk = passages[start : start + batch]
        vectors.extend(embedder.embed([passage.body for passage in chunk]))
        print(f"embedded {len(vectors)}/{len(passages)}", flush=True)
    with connect(database_url) as conn:
        written = replace_passages(conn, passages, vectors)
        conn.commit()
    print(f"indexed {written} passages into {CORPUS}")
    return written


def search_cli(database_url: str, query: str) -> list[dict]:
    from esl.db import connect
    from esl.retrieval import FastEmbedder, search_passages

    with connect(database_url) as conn:
        return search_passages(
            conn, corpus=CORPUS, query=query, embedder=FastEmbedder(), limit=5
        )


def main(argv: list[str] | None = None) -> int:
    import os
    from pathlib import Path

    from esl.settings import Settings
    from esl.sources.erp_mtdd import SourceFiles, download

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"index", "search"}:
        print("usage: python -m esl.corpus index | search <query>", file=sys.stderr)
        return 2
    settings = Settings.from_env()
    if args[0] == "index":
        directory = os.environ.get("ERP_MTDD_DIR", "")
        files = SourceFiles.in_directory(Path(directory)) if directory else download()
        index_workbook(settings.database_url, str(files.schema))
        return 0
    if len(args) < 2:
        print("usage: python -m esl.corpus search <query>", file=sys.stderr)
        return 2
    for hit in search_cli(settings.database_url, " ".join(args[1:])):
        print(f"{hit['score']:.4f}  {hit['sheet']}  {hit['locator']}")
        print(f"  {hit['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
