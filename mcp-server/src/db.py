import os
import asyncpg
from pgvector.asyncpg import register_vector

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            init=register_vector,
            min_size=2,
            max_size=10,
        )
    return _pool
