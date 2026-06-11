from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseConnector(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def fetch_documents(self) -> AsyncIterator[dict]:
        """Yield document dicts for ingestion.

        Required keys:
            external_id  -- unique ID within the source (page title, UNID, filename)
            title        -- human-readable title
            content      -- extracted plaintext
            url          -- link back to the source (for LLM citations)
            metadata     -- dict with source-specific fields (author, tags, …)

        Optional keys:
            parent_external_id  -- external_id of the parent document; set this for
                                   attachments (PDFs, DOCX, …) so the ingestion pipeline
                                   can establish the parent_document_id FK relationship.
                                   The parent document MUST be yielded before its attachments.
        """
        ...
