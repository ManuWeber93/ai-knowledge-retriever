import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import AsyncIterator
from .base import BaseConnector

_NOISE_TAGS = ("table", "figure", "sup")
_NOISE_CLASSES = ("reflist", "navbox", "sistersitebox", "mw-references-wrap")
_HEADERS = {"User-Agent": "ai-knowledge-retriever/1.0 (https://github.com/; educational project)"}
_REQUEST_DELAY_SECONDS = 2.0
_MAX_RETRIES = 4
_RETRY_BACKOFF_SECONDS = 30.0


class WikipediaConnector(BaseConnector):
    async def fetch_documents(self) -> AsyncIterator[dict]:
        language = self.config.get("language", "en")
        pages = self.config.get("pages", [])

        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
            for title in pages:
                print(f"  Fetching: {title}")
                try:
                    yield await self._fetch_page(client, language, title)
                except Exception as e:
                    print(f"  Error fetching {title}: {e}")
                await asyncio.sleep(_REQUEST_DELAY_SECONDS)

    async def _fetch_page(self, client: httpx.AsyncClient, language: str, title: str) -> dict:
        for attempt in range(_MAX_RETRIES):
            response = await client.get(
                f"https://{language}.wikipedia.org/api/rest_v1/page/html/{title}",
                follow_redirects=True,
            )
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", _RETRY_BACKOFF_SECONDS * (attempt + 1)))
                print(f"    Rate limited — waiting {wait:.0f}s before retry {attempt + 1}/{_MAX_RETRIES}...")
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            break

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup.find_all(_NOISE_TAGS):
            tag.decompose()
        for tag in soup.find_all(class_=_NOISE_CLASSES):
            tag.decompose()

        body = soup.find("body") or soup
        lines = [line for line in body.get_text(separator="\n", strip=True).splitlines() if line.strip()]

        return {
            "external_id": title,
            "title": title.replace("_", " "),
            "content": "\n".join(lines),
            "url": f"https://{language}.wikipedia.org/wiki/{title}",
            "metadata": {"language": language, "page_title": title},
        }
