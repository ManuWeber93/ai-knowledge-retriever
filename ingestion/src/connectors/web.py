import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import AsyncIterator
from .base import BaseConnector

_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "iframe")
_REQUEST_DELAY_SECONDS = 1.0


class WebConnector(BaseConnector):
    """Fetches a manually specified list of URLs and extracts their text content."""

    async def fetch_documents(self) -> AsyncIterator[dict]:
        urls = self.config.get("urls", [])
        user_agent = self.config.get("user_agent", "ai-knowledge-retriever/1.0 (educational project)")
        headers = {"User-Agent": user_agent}

        async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
            for url in urls:
                print(f"  Fetching: {url}")
                try:
                    yield await self._fetch_page(client, url)
                except Exception as e:
                    print(f"  Error fetching {url}: {e}")
                await asyncio.sleep(_REQUEST_DELAY_SECONDS)

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> dict:
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup.find_all(_NOISE_TAGS):
            tag.decompose()

        title = self._extract_title(soup, url)
        body = soup.find("main") or soup.find("article") or soup.find("body") or soup
        lines = [line for line in body.get_text(separator="\n", strip=True).splitlines() if line.strip()]

        return {
            "external_id": url,
            "title": title,
            "content": "\n".join(lines),
            "url": url,
            "metadata": {},
        }

    def _extract_title(self, soup: BeautifulSoup, fallback: str) -> str:
        if tag := soup.find("h1"):
            return tag.get_text(strip=True)
        if tag := soup.find("title"):
            return tag.get_text(strip=True)
        return fallback
