import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import yaml
from dotenv import load_dotenv
from fastmcp import FastMCP
from search import search_chunks

load_dotenv()

SOURCES_PATH = os.getenv("SOURCES_PATH", "/app/sources.yaml")
DEFAULT_TOP_K = int(os.getenv("MCP_DEFAULT_TOP_K", "5"))

mcp = FastMCP("knowledge-retriever")


def _register_source_tool(slug: str, display_name: str, description: str) -> None:
    async def search(query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
        return await search_chunks(slug, query, top_k)

    search.__name__ = f"search_{slug}"
    search.__qualname__ = f"search_{slug}"
    search.__doc__ = description
    mcp.tool()(search)


def _default_description(display_name: str) -> str:
    return (
        f"Search '{display_name}' for relevant text passages matching the query. "
        "Returns the most semantically similar excerpts with their source title and URL."
    )


def _register_source_tools() -> None:
    with open(SOURCES_PATH) as sources_file:
        sources_config = yaml.safe_load(sources_file)
    for source in sources_config.get("sources", []):
        description = source.get("description") or _default_description(source["display_name"])
        _register_source_tool(source["slug"], source["display_name"], description)


_register_source_tools()

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
