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

class SourceLinkage(BaseModel):
    """How example questions connect to the source material they were
    written about: which features of the source the questions target,
    and what kinds of questions this kind of source gives rise to.
    Meta-guidance only -- it carries no source facts, so it is safe
    to pass to the generator as style guidance."""
    linkage_guidance: str
    question_source_patterns: List[str] = []


class KeyConcept(BaseModel):
    """One key concept / learning objective the student should
    understand, and what that understanding looks like (beyond
    recalling a fact)."""
    concept: str
    understanding: str = ""


class KeyConcepts(BaseModel):
    concepts: List[KeyConcept] = []


class KeyConceptExtractor:
    """Read source material and identify the key concepts and
    learning objectives a student should understand. Used when
    "conceptual understanding" is enabled at generation time and
    no source was manually flagged as holding the concepts."""

    def __init__(self, api_key: str = None):
        self.client = make_gemini_client(api_key)

    def extract_concepts(self, source_text: str) -> KeyConcepts:
        prompt = (
            "You are an expert teacher. Read the source material below and identify the key concepts and "
            "learning objectives a student should understand from it. Aim for 5 to 10 concepts. For each, "
            "state the concept and what it means to understand it -- the understanding a question should "
            "validate -- not just a fact to recall. For example, for a source about trade routes, a concept "
            "might be 'how monsoon winds shaped which routes merchants could use', with understanding "
            "'the student can explain why a route was only usable in certain months'.\n\n"
            "SOURCE MATERIAL:\n" + source_text[:8000] + "\n"
        )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(KeyConcepts),
                temperature=0.3,
            )
        )
        return KeyConcepts.model_validate_json(response.text)


class SampleClassifier:
    def __init__(self, api_key: str = None):
        self.client = make_gemini_client(api_key)

    def analyze_source_linkage(self, example_text: str, source_text: str) -> SourceLinkage:
        """Connect the dots between example questions and the source
        material they were written about, so the generator learns
        what types of questions this kind of source material gives
        rise to. Only the returned guidance (not the source text
        itself) is ever passed on to generation."""
        prompt = (
            "You are an expert psychometrician. Below are example assessment questions AND the source material "
            "they were written about. Explain how the questions connect to the source material, so a question "
            "generator can learn what types of questions this kind of source material gives rise to.\n\n"
            "For each pattern, say which feature of the source the questions target (a map, a timeline, an "
            "argument, data, a passage, a diagram) and what kind of question it produces (e.g. interpreting "
            "the map, sequencing events, evaluating a claim). Then summarise it in a few sentences of guidance "
            "for generating new questions from NEW source material of the same kind. Do not repeat facts from "
            "the source material itself -- describe the relationship, not the content.\n\n"
            "EXAMPLE QUESTIONS:\n" + example_text[:6000] + "\n\n"
            "SOURCE MATERIAL THE QUESTIONS WERE WRITTEN ABOUT:\n" + source_text[:6000] + "\n"
        )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(SourceLinkage),
                temperature=0.3,
            )
        )
        return SourceLinkage.model_validate_json(response.text)

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
