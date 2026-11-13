import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Literal

from gemini_schema import gemini_response_schema, make_gemini_client

class ClassifiedSample(BaseModel):
    detected_typology: Literal[
        "SCENARIO_VIGNETTE",
        "STIMULUS_INTERPRETATION",
        "DATA_EVALUATION",
        "ASSERTION_REASON",
        "COMPARATIVE_PAIRED",
        "CONCEPT_APPLICATION"
    ]
    detected_bloom_level: Literal["Level 3: Apply", "Level 4: Analyze", "Level 5: Evaluate"]
    structural_features: List[str]
    recommended_prompt_guidance: str

class SampleClassifier:
    def __init__(self, api_key: str = None):
        self.client = make_gemini_client(api_key)

    def analyze_samples(self, raw_sample_text: str) -> ClassifiedSample:
        prompt = (
            "You are an expert psychometrician. Analyze the following sample assessment questions.\n"
            "Identify their core typology from our catalog, their cognitive depth (Bloom's Taxonomy), and structural mechanics.\n\n"
            "SAMPLE QUESTIONS:\n"
            + raw_sample_text
        )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",  # was gemini-2.5-flash, retired 2026-11-02
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(ClassifiedSample),
                temperature=0.1
            )
        )
        return ClassifiedSample.model_validate_json(response.text)
