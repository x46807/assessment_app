from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class SourceChunk(BaseModel):
    chunk_index: int
    locator_type: Literal["page", "timestamp", "section", "slide"]
    locator_value: str = Field(..., description="Verifiable reference: e.g. 'Page 5', '00:12:15 - 00:12:45'")
    content: str = Field(..., description="The raw clean text content within this chunk")
    raw_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class IngestionResult(BaseModel):
    source_title: str
    source_type: Literal["pdf", "docx", "text", "web", "youtube", "audio_video", "gdoc"]
    total_chunks: int
    chunks: List[SourceChunk]

    def to_llm_context(self) -> str:
        formatted_blocks = []
        for c in self.chunks:
            formatted_blocks.append(
                f"--- [ANCHOR: {c.locator_type.upper()} {c.locator_value}] ---\n{c.content}\n"
            )
        return "\n".join(formatted_blocks)
