import os
import httpx

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://host.docker.internal:11434/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "ollama")


async def get_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{EMBEDDING_BASE_URL}/embeddings",
            json={"model": EMBEDDING_MODEL, "input": text},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
        )
        response.raise_for_status()
    return response.json()["data"][0]["embedding"]
