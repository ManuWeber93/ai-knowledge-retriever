CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS sources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         VARCHAR(100) UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    type         VARCHAR(50) NOT NULL,
    config       JSONB,
    last_sync    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id          UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    parent_document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    external_id        TEXT NOT NULL,
    title              TEXT NOT NULL,
    content            TEXT NOT NULL,
    url                TEXT,
    metadata           JSONB,
    content_hash       TEXT,
    indexed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_id, external_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    text         TEXT NOT NULL,
    embedding    vector(768),
    token_count  INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS documents_source_id_idx
    ON documents(source_id);

CREATE INDEX IF NOT EXISTS documents_parent_id_idx
    ON documents(parent_document_id);
