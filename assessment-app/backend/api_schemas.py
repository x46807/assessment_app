from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

class GoogleAuthRequest(BaseModel):
    id_token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class TopicBucketCreate(BaseModel):
    title: str
    description: Optional[str] = None

class TopicBucketResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    created_at: datetime
    sources_count: int = 0
    items_count: int = 0

    class Config:
        from_attributes = True

class SourceResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    purpose: str = "source"
    # True when the user flagged this source as holding the
    # high-level concepts / objectives for the topic.
    is_concepts_source: bool = False
    source_url: Optional[str] = None
    chunks: int = 0
    images: int = 0
    created_at: datetime
    # True when this source reused an already-parsed upload;
    # ingested_at is when that content was first parsed.
    reused: bool = False
    ingested_at: Optional[datetime] = None
    # The pages in scope for generation, as typed ("1-3, 5"),
    # or None for all pages; page_count is the source's total
    # pages (None for non-paginated sources).
    page_range: Optional[str] = None
    page_count: Optional[int] = None

    class Config:
        from_attributes = True

class ReferenceSetCreate(BaseModel):
    title: str
    description: Optional[str] = None

class QuestionBankResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    question_count: int = 0


class QuestionBankRename(BaseModel):
    title: str


class SourceFlagRequest(BaseModel):
    # Each field is applied only when present in the request,
    # so the same endpoint flags a concepts source and/or sets
    # a page range. page_range "" clears it back to all pages.
    is_concepts_source: Optional[bool] = None
    page_range: Optional[str] = None


class AttemptCreate(BaseModel):
    question_id: UUID
    selected_option: str
    # Seconds from the student's first choice on the question to
    # submit; None when the frontend did not measure it.
    time_spent_seconds: Optional[float] = None
    bank_id: Optional[UUID] = None


class AttemptResponse(BaseModel):
    id: UUID
    question_id: UUID
    is_correct: bool
    created_at: datetime


class ReferenceSetResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    created_at: datetime
    examples_count: int = 0
    # Files uploaded as source material (not example questions).
    source_count: int = 0
    # True when the set has source material: the designator that
    # marks a source-enriched reference set.
    is_source_enriched: bool = False

    class Config:
        from_attributes = True

class ReferenceExampleResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    purpose: str = "example"
    source_url: Optional[str] = None
    chunks: int = 0
    created_at: datetime
    reused: bool = False
    ingested_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class GenerateRequest(BaseModel):
    count: int = 5
    target_typology: Optional[str] = "SCENARIO_VIGNETTE"
    question_type: Optional[str] = "multiple_choice"
    inject_external_stimulus: bool = False
    preferred_stimulus_modality: Optional[str] = None
    custom_style_instructions: Optional[str] = None
    # Use this reference set's example questions as the style for
    # this generation. Takes precedence over the topic's own examples.
    reference_set_id: Optional[UUID] = None
    # When False, ignore the topic's own example questions and use
    # only the typology picker (ignored when reference_set_id is set).
    use_topic_examples: bool = True
    # Add the new questions to this existing bank instead of creating
    # a new one. Must belong to the same topic; omitted = new bank.
    bank_id: Optional[UUID] = None
    # When True, guide generation by the topic's key concepts and
    # objectives: from a source flagged as holding them, or -- when
    # none is flagged -- identified automatically from the source
    # material. Questions should validate understanding of those
    # concepts, not just recall.
    conceptual_understanding: bool = False
