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
    source_url: Optional[str] = None
    chunks: int = 0
    images: int = 0
    created_at: datetime

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


class ReferenceSetResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    created_at: datetime
    examples_count: int = 0

    class Config:
        from_attributes = True

class ReferenceExampleResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    source_url: Optional[str] = None
    chunks: int = 0
    created_at: datetime

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
