import os
import re
from typing import List, Optional
from google import genai
from google.genai import types
from models import IngestionResult
from generation_schemas import GenerationBatchOutput, PsychometricItem
from stimulus.stimulus_orchestrator import StimulusOrchestrator

class QuestionGeneratorEngine:
    def __init__(self, api_key: str = None):
        self.client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        self.stimulus_orchestrator = StimulusOrchestrator(api_key=api_key)

    def _build_system_instruction(self) -> str:
        return (
            "You are a master psychometrician and standardized test developer (ETS, NBME, AP/SAT standards).\n"
            "Your mission is to generate test items grounded EXCLUSIVELY in the provided source material.\n\n"
            "### MANDATORY PSYCHOMETRIC PRINCIPLES:\n"
            "1. ABSOLUTE SOURCE GROUNDING:\n"
            "   - Every tested concept and correct rationale must originate directly from the source text.\n"
            "   - The verbatim_grounding_quote must be an exact text snippet from the supplied context.\n\n"
            "2. COGNITIVE DEMAND (Bloom's Level 3 & 4):\n"
            "   - Items must evaluate application, synthesis, or analysis. Use scenario-based stems.\n\n"
            "3. DISTRACTOR INTEGRITY:\n"
            "   - Exactly 4 options for Multiple Choice (A, B, C, D).\n"
            "   - Homogeneity: All options must be syntactically parallel and roughly equal in length.\n"
            "   - NEVER use: 'All of the above', 'None of the above', 'Both A and B'.\n\n"
            "4. CITATION PRECISION:\n"
            "   - Extract the exact anchor (Page number, Section name, or Timestamp interval).\n"
        )

    def generate_questions(
        self,
        ingested_source: IngestionResult,
        count: int = 5,
        target_typology: Optional[str] = "SCENARIO_VIGNETTE",
        question_type: str = "multiple_choice",
        custom_style_instructions: Optional[str] = None,
        inject_external_stimulus: bool = False,
        preferred_stimulus_modality: Optional[str] = None
    ) -> List[PsychometricItem]:
        source_context_str = ingested_source.to_llm_context()
        external_stimulus = None

        if inject_external_stimulus or target_typology in ["STIMULUS_INTERPRETATION", "DATA_EVALUATION"]:
            try:
                external_stimulus = self.stimulus_orchestrator.plan_and_fetch_stimulus(
                    source_text=source_context_str,
                    preferred_modality=preferred_stimulus_modality
                )
            except Exception as e:
                print(f"[Stimulus Pipeline Warning]: {e}")
                external_stimulus = None

        stimulus_prompt_section = ""
        if external_stimulus:
            stimulus_prompt_section = (
                f"\n=== EXTERNAL STIMULUS SUPPLIED FOR THIS ASSESSMENT ===\n"
                f"Type: {external_stimulus.stimulus_type.upper()}\n"
                f"Attribution / Background: {external_stimulus.attribution_or_context}\n\n"
                f"CONTENT / DATA:\n{external_stimulus.content}\n"
                f"======================================================\n"
            )

        task_prompt = (
            f"SOURCE DOCUMENT: \"{ingested_source.source_title}\" ({ingested_source.source_type.upper()})\n\n"
            f"--- INGESTED SOURCE CONTENT (WITH CITATION ANCHORS) ---\n"
            f"{source_context_str}\n"
            f"--- END SOURCE CONTENT ---\n\n"
            f"{stimulus_prompt_section}\n"
            f"TASK:\n"
            f"Generate {count} assessment items following these specifications:\n"
            f"- Item Typology: {target_typology}\n"
            f"- Question Format: {question_type}\n"
            f"- Cognitive Level: Bloom's Level 3 (Apply) or Level 4 (Analyze)\n\n"
            f"ADDITIONAL DIRECTIVES:\n"
            f"{custom_style_instructions or 'Adhere to strict psychometric guidelines.'}\n"
        )

        response = self.client.models.generate_content(
            model="gemini-2.5-pro",
            contents=task_prompt,
            config=types.GenerateContentConfig(
                system_instruction=self._build_system_instruction(),
                response_mime_type="application/json",
                response_schema=GenerationBatchOutput,
                temperature=0.2,
            )
        )

        batch = GenerationBatchOutput.model_validate_json(response.text)
        for item in batch.items:
            if external_stimulus and not item.stimulus:
                item.stimulus = external_stimulus
        return batch.items
