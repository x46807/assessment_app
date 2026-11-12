import re
import requests
import trafilatura
from typing import List, Optional
from models import SourceChunk, IngestionResult

class WebParser:
    @staticmethod
    def parse_website(url: str, title: Optional[str] = None) -> IngestionResult:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise ValueError(f"Failed to fetch content from URL: {url}")
        text = trafilatura.extract(downloaded) or ""
        meta = trafilatura.extract_metadata(downloaded)
        page_title = title or (meta.title if meta and meta.title else url)

        chunks = [SourceChunk(chunk_index=1, locator_type="section", locator_value="Main Content", content=text)]
        return IngestionResult(source_title=page_title, source_type="web", total_chunks=1, chunks=chunks)

    @staticmethod
    def parse_google_doc(gdoc_url: str, title: Optional[str] = None) -> IngestionResult:
        match = re.search(r"/document/d/([a-zA-Z0-9-_]+)", gdoc_url)
        if not match:
            raise ValueError("Invalid Google Docs URL structure.")
        doc_id = match.group(1)
        res = requests.get(f"https://docs.google.com/document/d/{doc_id}/export?format=txt", timeout=15)
        if res.status_code != 200:
            raise PermissionError("Could not access Google Doc. Verify it is set to 'Anyone with link can view'.")

        chunks = [SourceChunk(chunk_index=1, locator_type="section", locator_value="Full Document", content=res.text)]
        return IngestionResult(source_title=title or f"Google Doc ({doc_id[:8]})", source_type="gdoc", total_chunks=1, chunks=chunks)
