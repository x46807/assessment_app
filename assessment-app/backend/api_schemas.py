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

class GenerateRequest(BaseModel):
    count: int = 5
    target_typology: Optional[str] = "SCENARIO_VIGNETTE"
    question_type: Optional[str] = "multiple_choice"
    inject_external_stimulus: bool = False
    preferred_stimulus_modality: Optional[str] = None
    custom_style_instructions: Optional[str] = None
