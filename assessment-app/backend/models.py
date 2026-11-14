from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class SourceChunk(BaseModel):
    chunk_index: int
    locator_type: Literal["page", "timestamp", "section", "slide", "line"]
    locator_value: str = Field(..., description="Verifiable reference: e.g. 'Page 5', '00:12:15 - 00:12:45', 'Lines 41-80'")
    content: str = Field(..., description="The raw clean text content within this chunk")
    source_file: Optional[str] = Field(default=None, description="Unique identifier of the source this chunk came from, e.g. the uploaded filename")
    raw_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class IngestionResult(BaseModel):
    source_title: str
    source_type: Literal["pdf", "docx", "text", "web", "youtube", "audio_video", "gdoc", "image"]
    total_chunks: int
    chunks: List[SourceChunk]

    def to_llm_context(self) -> str:
        formatted_blocks = []
        for c in self.chunks:
            source_tag = f"SOURCE: {c.source_file} | " if c.source_file else ""
            formatted_blocks.append(
                f"--- [{source_tag}ANCHOR: {c.locator_type.upper()} {c.locator_value}] ---\n{c.content}\n"
            )
        return "\n".join(formatted_blocks)
