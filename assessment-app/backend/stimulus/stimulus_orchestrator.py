import base64
import os
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from google import genai
from google.genai import types
from stimulus.wikimedia import WikimediaProvider
from stimulus.diagrams import DiagramProvider
from generation_schemas import StimulusContext
from gemini_schema import gemini_response_schema, make_gemini_client

class StimulusPlan(BaseModel):
    stimulus_modality: Literal["map_or_illustration", "primary_source_text", "diagram_flowchart", "data_table"]
    search_query_or_theme: str
    synthetic_content_draft: Optional[str] = None
    attribution_context: Optional[str] = None

class SourceImagePick(BaseModel):
    """Flash's choice among the images embedded in the source material:
    the index of the best stimulus image, or null when none of them
    would make a good stimulus (then the web is tried instead)."""
    image_index: Optional[int] = None
    image_type: Literal["map", "illustration"] = "illustration"
    reason: str = ""


class StimulusOrchestrator:
    def __init__(self, api_key: Optional[str] = None):
        self.client = make_gemini_client(api_key)

    def _pick_source_image(self, source_text: str, source_images: List[dict]) -> Optional[StimulusContext]:
        """Ask Flash to choose the best stimulus among the source
        material's own embedded images. The model sees the images,
        so the choice is by content, not by filename or guesswork.
        Returns None when no image is suitable -- the caller then
        falls back to a text passage."""
        images = source_images[:8]
        parts = [
            "You are choosing a visual stimulus for assessment questions about the source text below. "
            "The images that follow were extracted from the source material itself. "
            "Pick the ONE image that would make the best stimulus -- a map, illustration, chart, or diagram "
            "a student could be asked to interpret. Prefer a map when the questions are about places, routes, "
            "or regions. If none of the images would make a good stimulus (decorative, illegible, or unrelated), "
            "return image_index null.\n\n"
            f"SOURCE TEXT (excerpt):\n{source_text[:1500]}\n"
        ]
        for i, img in enumerate(images):
            data_uri = img.get("data_uri", "")
            try:
                b64 = data_uri.split(",", 1)[1]
                raw = base64.b64decode(b64)
            except Exception:
                continue
            parts.append("Image %d (from %s, p. %s):" % (i, img.get("source_file"), img.get("page")))
            parts.append(types.Part.from_bytes(data=raw, mime_type=img.get("mime_type", "image/jpeg")))
        if len(parts) <= 1:
            return None
        try:
            response = self.client.models.generate_content(
                model="gemini-3.8-flash",
                contents=parts,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=gemini_response_schema(SourceImagePick), temperature=0.2)
            )
            pick = SourceImagePick.model_validate_json(response.text)
        except Exception as e:
            print(f"[Stimulus] source-image pick failed: {e}")
            return None
        if pick.image_index is None or not (0 <= pick.image_index < len(images)):
            print(f"[Stimulus] no source image suitable ({pick.reason[:120]})")
            return None
        chosen = images[pick.image_index]
        print("[Stimulus] using source image %d (%s) from %s, p. %s: %s" % (pick.image_index, pick.image_type, chosen.get("source_file"), chosen.get("page"), pick.reason[:120]))
        return StimulusContext(
            stimulus_type=pick.image_type,
            content=chosen["data_uri"],
            attribution_or_context="From %s, p. %s" % (chosen.get("source_file"), chosen.get("page")),
        )

    def plan_and_fetch_stimulus(self, source_text: str, preferred_modality: Optional[str] = None, style_context: Optional[str] = None, source_images: Optional[List[dict]] = None) -> StimulusContext:
        # preferred_modality was previously accepted and then ignored,
        # so a caller asking for a map got whatever the planner felt
        # like -- usually a text passage. When it is set, the plan is
        # constrained to that modality instead of choosing freely.
        if preferred_modality == "map_or_illustration":
            plan_prompt = (
                "Plan a MAP OR ILLUSTRATION stimulus for this source text. "
                "Give a Wikimedia Commons search query that will find a map, illustration, or image "
                "depicting the people, places, or events in the source text.\n\n"
                + (f"STYLE CONTEXT: {style_context}\n\n" if style_context else "")
                + f"SOURCE:\n{source_text[:2500]}\n"
            )
        elif preferred_modality == "primary_source_text":
            plan_prompt = (
                "Plan a PRIMARY SOURCE TEXT stimulus for this source text. "
                "Give a short passage (a quote or excerpt) that pairs with the source text, "
                "with its attribution, for a student to interpret.\n\n"
                + (f"STYLE CONTEXT: {style_context}\n\n" if style_context else "")
                + f"SOURCE:\n{source_text[:2500]}\n"
            )
        else:
            plan_prompt = (
                "Plan an external stimulus (primary source text, map query, diagram, or data table) that pairs with this source text.\n\n"
                + (f"STYLE CONTEXT: {style_context}\n\n" if style_context else "")
                + f"SOURCE:\n{source_text[:2500]}\n"
            )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",  # was gemini-2.5-flash, retired 2026-11-02
            contents=plan_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=gemini_response_schema(StimulusPlan), temperature=0.3)
        )
        plan = StimulusPlan.model_validate_json(response.text)
        modality = preferred_modality or plan.stimulus_modality
        print(f"[Stimulus] planned modality={plan.stimulus_modality} preferred={preferred_modality} query={plan.search_query_or_theme!r}")

        if modality == "map_or_illustration":
            # Outside sources come first: a curated web image is
            # usually a cleaner stimulus than an image pulled out
            # of a scanned source page. The source material's own
            # images are the fallback when the web has nothing
            # suitable for the question.
            query = plan.search_query_or_theme
            if "map" not in query.lower() and "illustration" not in query.lower():
                query = query + " map"
            media = WikimediaProvider.search_media(query)
            if media:
                return StimulusContext(stimulus_type="map", content=media["media_url"], attribution_or_context=media["attribution"])
            if source_images:
                picked = self._pick_source_image(source_text, source_images)
                if picked:
                    return picked
            print(f"[Stimulus] no web or source image for {query!r}; falling back to a text passage")

        if preferred_modality != "primary_source_text" and plan.stimulus_modality == "diagram_flowchart":
            diagram = DiagramProvider.format_mermaid_diagram(plan.synthetic_content_draft or "graph TD; A-->B;", plan.search_query_or_theme)
            return StimulusContext(stimulus_type="diagram", content=diagram["content"], attribution_or_context=diagram["attribution"])

        return StimulusContext(
            stimulus_type="historical_passage",
            content=plan.synthetic_content_draft or "Primary source passage for assessment review.",
            attribution_or_context=plan.attribution_context or f"Historical Record: {plan.search_query_or_theme}"
        )
