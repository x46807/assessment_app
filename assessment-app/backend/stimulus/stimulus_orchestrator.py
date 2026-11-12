import os
from pydantic import BaseModel, Field
from typing import Literal, Optional
from google import genai
from google.genai import types
from stimulus.wikimedia import WikimediaProvider
from stimulus.diagrams import DiagramProvider
from generation_schemas import StimulusContext

class StimulusPlan(BaseModel):
    stimulus_modality: Literal["map_or_illustration", "primary_source_text", "diagram_flowchart", "data_table"]
    search_query_or_theme: str
    synthetic_content_draft: Optional[str] = None
    attribution_context: Optional[str] = None

class StimulusOrchestrator:
    def __init__(self, api_key: Optional[str] = None):
        self.client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    def plan_and_fetch_stimulus(self, source_text: str, preferred_modality: Optional[str] = None) -> StimulusContext:
        plan_prompt = (
            "Plan an external stimulus (primary source text, map query, diagram, or data table) that pairs with this source text.\n\n"
            f"SOURCE:\n{source_text[:2500]}\n"
        )
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=plan_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=StimulusPlan, temperature=0.3)
        )
        plan = StimulusPlan.model_validate_json(response.text)

        if plan.stimulus_modality == "map_or_illustration":
            media = WikimediaProvider.search_media(plan.search_query_or_theme)
            if media:
                return StimulusContext(stimulus_type="map", content=media["media_url"], attribution_or_context=media["attribution"])

        if plan.stimulus_modality == "diagram_flowchart":
            diagram = DiagramProvider.format_mermaid_diagram(plan.synthetic_content_draft or "graph TD; A-->B;", plan.search_query_or_theme)
            return StimulusContext(stimulus_type="diagram", content=diagram["content"], attribution_or_context=diagram["attribution"])

        return StimulusContext(
            stimulus_type="historical_passage",
            content=plan.synthetic_content_draft or "Primary source passage for assessment review.",
            attribution_or_context=plan.attribution_context or f"Historical Record: {plan.search_query_or_theme}"
        )
