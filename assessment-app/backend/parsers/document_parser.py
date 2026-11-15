import base64
import hashlib
import io
import fitz
import docx
from typing import List
from models import SourceChunk, IngestionResult, SourceImage

# Embedded-image extraction limits: keep the stored JSON small enough
# that generation (which re-reads every source) stays fast, and skip
# icons, logos and decorative thumbnails, which make poor stimuli.
MAX_IMAGES_PER_PDF = 4
MIN_IMAGE_DIMENSION = 200
MAX_IMAGE_DIMENSION = 900
IMAGE_JPEG_QUALITY = 75

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
                source_file=title,
                raw_metadata={"page_number": page_num + 1}
            ))
        images = DocumentParser._extract_pdf_images(doc, title)
        doc.close()
        if images:
            print(f"[PDF] {title}: extracted {len(images)} embedded image(s) for stimulus use")
        return IngestionResult(source_title=title, source_type="pdf", total_chunks=len(chunks), chunks=chunks, images=images)

    @staticmethod
    def _extract_pdf_images(doc, title: str) -> List[SourceImage]:
        """Extract embedded images from a PDF as downscaled JPEG data URIs.

        One bad image must never break ingestion, so every image is
        handled defensively and skipped on any error. Duplicates (the
        same image on several pages, or embedded twice) are dropped by
        content hash, and only the largest few are kept.

        Speed matters here: a scanned textbook chapter can hold a
        full-page image per page, and decoding every one just to keep
        four would dominate ingestion -- and, on the free tier's
        tenth of a CPU, push a single upload past the request
        timeout. So the largest candidates are picked from the image
        metadata first (width and height ride along in the
        get_images tuple) and only those are extracted and decoded.
        """
        from PIL import Image

        # Pass 1 -- metadata only: (area, page, xref) for every distinct
        # image big enough to be a useful stimulus. No bytes are read.
        ranked = []
        seen_xrefs = set()
        for page_num in range(len(doc)):
            for img in doc[page_num].get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                width, height = img[2], img[3]
                if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                    continue
                ranked.append((width * height, page_num + 1, xref))
        # Largest first; ties break toward the earlier page.
        ranked.sort(key=lambda c: (-c[0], c[1]))

        # Pass 2 -- extract and decode only until the quota is met. A
        # hash duplicate among the leaders is skipped and the next
        # candidate takes its place, so the quota still fills.
        candidates = []
        seen_hashes = set()
        for _area, page_num, xref in ranked:
            if len(candidates) >= MAX_IMAGES_PER_PDF:
                break
            try:
                raw = doc.extract_image(xref)
                digest = hashlib.sha256(raw["image"]).hexdigest()
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)
                pil = Image.open(io.BytesIO(raw["image"]))
                if pil.mode in ("RGBA", "LA", "PA"):
                    background = Image.new("RGB", pil.size, (255, 255, 255))
                    background.paste(pil, mask=pil.split()[-1])
                    pil = background
                else:
                    pil = pil.convert("RGB")
                pil.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=IMAGE_JPEG_QUALITY)
                data_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
                candidates.append(SourceImage(
                    image_id=f"{title}-p{page_num}-{xref}",
                    page=page_num,
                    source_file=title,
                    mime_type="image/jpeg",
                    data_uri=data_uri,
                    width=pil.width,
                    height=pil.height,
                ))
            except Exception as e:
                print(f"[PDF] skipping unreadable embedded image xref={xref} on p.{page_num}: {e}")
                continue
        # Keep the largest images: maps and full-page illustrations
        # carry the most stimulus value; icons were already filtered.
        candidates.sort(key=lambda im: (im.page, im.image_id))
        return candidates

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
                    chunks.append(SourceChunk(chunk_index=chunk_idx, locator_type="section", locator_value=current_section, content="\n".join(buffer), source_file=title))
                    buffer = []
                current_section = text
            else:
                buffer.append(text)

        if buffer:
            chunk_idx += 1
            chunks.append(SourceChunk(chunk_index=chunk_idx, locator_type="section", locator_value=current_section, content="\n".join(buffer), source_file=title))

        return IngestionResult(source_title=title, source_type="docx", total_chunks=len(chunks), chunks=chunks)

    @staticmethod
    def parse_txt(file_path: str, title: str) -> IngestionResult:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        chunks = []
        for chunk_idx, (first_line, last_line, content) in enumerate(
            DocumentParser._line_windows(text), start=1
        ):
            chunks.append(SourceChunk(
                chunk_index=chunk_idx,
                locator_type="line",
                locator_value=f"Lines {first_line}-{last_line}",
                content=content,
                source_file=title,
            ))
        if not chunks:
            chunks = [SourceChunk(chunk_index=1, locator_type="line", locator_value="Lines 1-1", content="", source_file=title)]
        return IngestionResult(source_title=title, source_type="text", total_chunks=len(chunks), chunks=chunks)

    @staticmethod
    def _line_windows(text: str, lines_per_chunk: int = 40):
        """Split plain text into (first_line, last_line, content) windows."""
        lines = text.splitlines()
        for start in range(0, len(lines), lines_per_chunk):
            window = lines[start:start + lines_per_chunk]
            if not any(line.strip() for line in window):
                continue
            yield start + 1, start + len(window), "\n".join(window)
