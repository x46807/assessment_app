import os
from typing import List

from google.genai import types

from gemini_schema import make_gemini_client
from models import IngestionResult, SourceChunk

_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

_TRANSCRIBE_PROMPT = (
    "Transcribe all text visible in this image exactly, preserving the "
    "reading order and line breaks. Do not summarize, do not add commentary, "
    "do not correct spelling or grammar, and do not describe the image. "
    "If there is no readable text in the image, reply with nothing."
)


class ImageParser:
    @staticmethod
    def parse_image(file_path: str, title: str) -> IngestionResult:
        """Transcribe an image file to text with Gemini vision.

        Render's Python environment has no OCR binary, so the transcription
        uses the same Gemini client as the rest of the backend (Flash is
        fast and cheap for this). The transcription is chunked into
        40-line windows, like plain-text sources, so citations can point
        at exact lines of the transcribed text.
        """
        ext = os.path.splitext(file_path)[1].lstrip(".").lower()
        mime_type = _MIME_TYPES.get(ext)
        if not mime_type:
            raise ValueError(f"Unsupported image format: .{ext}")

        with open(file_path, "rb") as f:
            image_bytes = f.read()

        client = make_gemini_client()
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                _TRANSCRIBE_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError(
                f"No readable text found in {title}. Images used as source "
                "material need visible text (for example, a photo of notes "
                "or a textbook page)."
            )

        chunks: List[SourceChunk] = []
        lines = text.splitlines()
        for chunk_idx, start in enumerate(range(0, len(lines), 40), start=1):
            window = lines[start:start + 40]
            if not any(line.strip() for line in window):
                continue
            chunks.append(SourceChunk(
                chunk_index=chunk_idx,
                locator_type="line",
                locator_value=f"Lines {start + 1}-{start + len(window)}",
                content="\n".join(window),
                source_file=title,
            ))
        if not chunks:
            raise ValueError(f"No readable text found in {title}.")

        return IngestionResult(
            source_title=title, source_type="image",
            total_chunks=len(chunks), chunks=chunks,
        )
