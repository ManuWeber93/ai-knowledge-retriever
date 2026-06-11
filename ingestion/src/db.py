import hashlib
import os
import psycopg
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def get_or_create_source(conn: psycopg.Connection, slug: str, display_name: str,
                          source_type: str, config: dict) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE slug = %s", (slug,))
        row = cur.fetchone()
        if row:
            return str(row[0])
        cur.execute(
            "INSERT INTO sources (slug, display_name, type, config) VALUES (%s, %s, %s, %s) RETURNING id",
            (slug, display_name, source_type, Jsonb(config)),
        )
        source_id = str(cur.fetchone()[0])
    conn.commit()
    return source_id


def upsert_document(conn: psycopg.Connection, source_id: str, doc: dict,
                    chunks: list[tuple[str, list[float]]],
                    parent_document_id: str | None = None) -> tuple[bool, str]:
    """Insert or update a document and its chunks.

    Returns (was_updated, doc_id). doc_id is always returned so callers can
    use it as parent_document_id when inserting attachment documents.
    """
    content_hash = hashlib.sha256(doc["content"].encode()).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, content_hash FROM documents WHERE source_id = %s AND external_id = %s",
            (source_id, doc["external_id"]),
        )
        row = cur.fetchone()

        if row and row[1] == content_hash:
            return False, str(row[0])  # Unchanged — skip chunk regeneration

        metadata = Jsonb(doc.get("metadata") or {})

        if row:
            doc_id = str(row[0])
            cur.execute(
                """UPDATE documents
                   SET title=%s, content=%s, url=%s, metadata=%s, content_hash=%s,
                       parent_document_id=%s, indexed_at=now()
                   WHERE id=%s""",
                (doc["title"], doc["content"], doc.get("url"), metadata,
                 content_hash, parent_document_id, doc_id),
            )
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
        else:
            cur.execute(
                """INSERT INTO documents
                       (source_id, external_id, title, content, url, metadata,
                        content_hash, parent_document_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (source_id, doc["external_id"], doc["title"], doc["content"],
                 doc.get("url"), metadata, content_hash, parent_document_id),
            )
            doc_id = str(cur.fetchone()[0])

        for i, (text, embedding) in enumerate(chunks):
            cur.execute(
                """INSERT INTO chunks (document_id, chunk_index, text, embedding, token_count)
                   VALUES (%s, %s, %s, %s, %s)""",
                (doc_id, i, text, embedding, len(text.split())),
            )

    conn.commit()
    return True, doc_id
