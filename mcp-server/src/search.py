from db import get_pool
from embedder import get_embedding


async def search_chunks(source_slug: str, query: str, top_k: int = 5) -> list[dict]:
    """Embed the query and find the top-k most similar chunks from the given source.

    When a chunk belongs to an attachment document, the result includes parent_title
    and parent_url so the LLM can provide accurate citations.
    """
    embedding = await get_embedding(query)
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.text,
                c.chunk_index,
                d.title,
                d.url,
                parent.title AS parent_title,
                parent.url   AS parent_url,
                1 - (c.embedding <=> $1::vector) AS score
            FROM chunks c
            JOIN documents d      ON c.document_id          = d.id
            LEFT JOIN documents parent ON d.parent_document_id = parent.id
            JOIN sources s        ON d.source_id             = s.id
            WHERE s.slug = $2
            ORDER BY c.embedding <=> $1::vector
            LIMIT $3
            """,
            embedding,
            source_slug,
            top_k,
        )

    results = []
    for row in rows:
        result = {
            "text": row["text"],
            "title": row["title"],
            "url": row["url"],
            "score": round(float(row["score"]), 4),
        }
        if row["parent_title"] is not None:
            result["parent_title"] = row["parent_title"]
            result["parent_url"] = row["parent_url"]
        results.append(result)

    return results
