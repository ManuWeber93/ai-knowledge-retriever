import os
import httpx

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "ollama")


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a batch of texts via OpenAI-compatible API."""
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{EMBEDDING_BASE_URL}/embeddings",
            json={"model": EMBEDDING_MODEL, "input": texts},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
        )
        response.raise_for_status()
    items = response.json()["data"]
    return [item["embedding"] for item in sorted(items, key=lambda x: x["index"])]


def get_embedding(text: str) -> list[float]:
    return get_embeddings([text])[0]
