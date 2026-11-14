from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class SourceChunk(BaseModel):
    chunk_index: int
    locator_type: Literal["page", "timestamp", "section", "slide", "line"]
    locator_value: str = Field(..., description="Verifiable reference: e.g. 'Page 5', '00:12:15 - 00:12:45', 'Lines 41-80'")
    content: str = Field(..., description="The raw clean text content within this chunk")
    source_file: Optional[str] = Field(default=None, description="Unique identifier of the source this chunk came from, e.g. the uploaded filename")
    raw_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class SourceImage(BaseModel):
    """An image embedded in a source document, extracted for use as a
    visual stimulus. The image bytes travel as a data URI because
    Render's free tier has no persistent disk to serve files from,
    and the frontend renders a data URI in an <img> directly.
    Kept out of the text chunks so to_llm_context() stays text-only."""
    image_id: str
    page: int
    source_file: Optional[str] = None
    mime_type: str = "image/jpeg"
    data_uri: str
    width: int
    height: int


class IngestionResult(BaseModel):
    source_title: str
    source_type: Literal["pdf", "docx", "text", "web", "youtube", "audio_video", "gdoc", "image"]
    total_chunks: int
    chunks: List[SourceChunk]
    images: List[SourceImage] = Field(default_factory=list)

    def to_llm_context(self) -> str:
        formatted_blocks = []
        for c in self.chunks:
            source_tag = f"SOURCE: {c.source_file} | " if c.source_file else ""
            formatted_blocks.append(
                f"--- [{source_tag}ANCHOR: {c.locator_type.upper()} {c.locator_value}] ---\n{c.content}\n"
            )
        return "\n".join(formatted_blocks)
