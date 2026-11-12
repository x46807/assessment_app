from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict

class StimulusContext(BaseModel):
    stimulus_type: Literal["quote", "historical_passage", "case_vignette", "data_table", "map", "illustration", "diagram", "none"]
    content: str
    attribution_or_context: str

class QuestionOption(BaseModel):
    label: Literal["A", "B", "C", "D"]
    text: str

class ItemCitation(BaseModel):
    source_title: str
    location_type: Literal["page", "timestamp", "section"]
    location_value: str
    verbatim_grounding_quote: str

class PsychometricItem(BaseModel):
    catalog_typology: Literal[
        "SCENARIO_VIGNETTE",
        "STIMULUS_INTERPRETATION",
        "DATA_EVALUATION",
        "ASSERTION_REASON",
        "COMPARATIVE_PAIRED",
        "CONCEPT_APPLICATION"
    ]
    bloom_level: Literal["Level 3: Apply", "Level 4: Analyze", "Level 5: Evaluate"]
    question_type: Literal["multiple_choice", "true_false", "short_answer"]
    stimulus: Optional[StimulusContext] = None
    stem: str
    options: List[QuestionOption] = Field(default_factory=list)
    correct_option: str
    pedagogical_feedback: str
    distractor_rationales: Dict[str, str] = Field(default_factory=dict)
    citation: ItemCitation

class GenerationBatchOutput(BaseModel):
    items: List[PsychometricItem]
