import fitz
import docx
from typing import List
from models import SourceChunk, IngestionResult

class DocumentParser:
    @staticmethod
    def parse_pdf(file_path: str, title: str) -> IngestionResult:
        doc = fitz.open(file_path)
        chunks: List[SourceChunk] = []
        chunk_idx = 0
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text").strip()
            if not text:
                continue
            chunk_idx += 1
            chunks.append(SourceChunk(
                chunk_index=chunk_idx,
                locator_type="page",
                locator_value=f"Page {page_num + 1}",
                content=text,
                raw_metadata={"page_number": page_num + 1}
            ))
        doc.close()
        return IngestionResult(source_title=title, source_type="pdf", total_chunks=len(chunks), chunks=chunks)

    @staticmethod
    def parse_docx(file_path: str, title: str) -> IngestionResult:
        doc = docx.Document(file_path)
        chunks: List[SourceChunk] = []
        current_section = "Main Content"
        buffer = []
        chunk_idx = 0

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if para.style.name.startswith("Heading"):
                if buffer:
                    chunk_idx += 1
                    chunks.append(SourceChunk(chunk_index=chunk_idx, locator_type="section", locator_value=current_section, content="\n".join(buffer)))
                    buffer = []
                current_section = text
            else:
                buffer.append(text)

        if buffer:
            chunk_idx += 1
            chunks.append(SourceChunk(chunk_index=chunk_idx, locator_type="section", locator_value=current_section, content="\n".join(buffer)))

        return IngestionResult(source_title=title, source_type="docx", total_chunks=len(chunks), chunks=chunks)

    @staticmethod
    def parse_txt(file_path: str, title: str) -> IngestionResult:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        chunks = [SourceChunk(chunk_index=1, locator_type="section", locator_value="Full Text", content=text)]
        return IngestionResult(source_title=title, source_type="text", total_chunks=1, chunks=chunks)
