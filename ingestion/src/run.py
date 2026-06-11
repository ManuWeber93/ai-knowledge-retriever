import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import yaml
from connectors.wikipedia import WikipediaConnector
from connectors.web import WebConnector
from chunker import chunk_text
from embedder import get_embedding
from db import get_connection, get_or_create_source, upsert_document

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

CONNECTOR_MAP = {
    "wikipedia": WikipediaConnector,
    "web": WebConnector,
}


async def run_ingestion(source_config: dict) -> None:
    slug = source_config["slug"]
    display_name = source_config["display_name"]
    source_type = source_config["type"]
    config = source_config.get("config", {})

    print(f"\n[{slug}] Starting ingestion (type={source_type})")

    connector_class = CONNECTOR_MAP.get(source_type)
    if not connector_class:
        raise ValueError(f"Unknown source type: '{source_type}'. Available: {list(CONNECTOR_MAP)}")

    conn = get_connection()
    source_id = get_or_create_source(conn, slug, display_name, source_type, config)
    connector = connector_class(config)

    inserted_ids: dict[str, str] = {}
    docs_processed = 0
    docs_updated = 0

    async for doc in connector.fetch_documents():
        parent_doc_id: str | None = None
        if parent_external_id := doc.get("parent_external_id"):
            parent_doc_id = inserted_ids.get(parent_external_id)
            if parent_doc_id is None:
                print(f"  Warning: parent '{parent_external_id}' not yet seen for '{doc['external_id']}' — skipping")
                continue

        print(f"  Processing: {doc['title']}")
        chunks = chunk_text(doc["content"], max_chars=CHUNK_SIZE, overlap_chars=CHUNK_OVERLAP)
        print(f"    {len(chunks)} chunks — generating embeddings...")

        chunk_embeddings = [(chunk, get_embedding(chunk)) for chunk in chunks]
        updated, doc_id = upsert_document(conn, source_id, doc, chunk_embeddings,
                                         parent_document_id=parent_doc_id)

        inserted_ids[doc["external_id"]] = doc_id
        docs_processed += 1
        if updated:
            docs_updated += 1
        print(f"    {'updated' if updated else 'unchanged'}")

    conn.close()
    print(f"\n[{slug}] Done: {docs_processed} processed, {docs_updated} updated/inserted")


def main() -> None:
    default_config = os.path.join(os.path.dirname(__file__), "..", "..", "sources.yaml")

    parser = argparse.ArgumentParser(description="Run the knowledge ingestion pipeline")
    parser.add_argument("--source", default=None, help="Source slug to ingest (from sources.yaml); omit to ingest all")
    parser.add_argument("--config", default=default_config, help="Path to sources.yaml")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as sources_file:
        sources_config = yaml.safe_load(sources_file)

    all_sources = sources_config.get("sources", [])

    if args.source:
        sources_to_run = [s for s in all_sources if s["slug"] == args.source]
        if not sources_to_run:
            available = [s["slug"] for s in all_sources]
            print(f"Source '{args.source}' not found. Available: {available}")
            sys.exit(1)
    else:
        sources_to_run = all_sources

    for source in sources_to_run:
        asyncio.run(run_ingestion(source))


if __name__ == "__main__":
    main()
