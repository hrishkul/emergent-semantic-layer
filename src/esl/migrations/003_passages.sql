-- Schema-workbook passages. 384 dimensions is the local BAAI/bge-small-en-v1.5 model.
-- The debate model is a different choice and stays unset.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE passages (
    id uuid PRIMARY KEY,
    corpus text NOT NULL,
    sheet text NOT NULL,
    locator text NOT NULL,
    body text NOT NULL,
    embedding vector(384) NOT NULL,
    UNIQUE (corpus, sheet, locator)
);

CREATE INDEX passages_corpus_idx ON passages (corpus);

CREATE INDEX passages_embedding_idx ON passages USING hnsw (embedding vector_cosine_ops);
