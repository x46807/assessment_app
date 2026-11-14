import os
from typing import Optional
from models import IngestionResult
from parsers.document_parser import DocumentParser
from parsers.web_parser import WebParser
from parsers.media_parser import MediaParser
from parsers.image_parser import ImageParser

class MasterIngestionPipeline:
    def ingest_url(self, url: str, title: Optional[str] = None) -> IngestionResult:
        if "youtube.com" in url or "youtu.be" in url:
            return MediaParser.parse_youtube(url, title=title)
        elif "docs.google.com/document" in url:
            return WebParser.parse_google_doc(url, title=title)
        else:
            return WebParser.parse_website(url, title=title)

    def ingest_file(self, file_path: str, title: Optional[str] = None) -> IngestionResult:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = os.path.basename(file_path)
        ext = filename.split(".")[-1].lower()
        doc_title = title or filename

        if ext == "pdf":
            return DocumentParser.parse_pdf(file_path, title=doc_title)
        elif ext in ["docx", "doc"]:
            return DocumentParser.parse_docx(file_path, title=doc_title)
        elif ext in ["txt", "md"]:
            return DocumentParser.parse_txt(file_path, title=doc_title)
        elif ext in ["jpg", "jpeg", "png"]:
            return ImageParser.parse_image(file_path, title=doc_title)
        else:
            raise NotImplementedError(f"Unsupported file format: .{ext}")
