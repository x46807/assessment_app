import os
import random
import re
from typing import List, Optional
from google import genai
from google.genai import types
from models import IngestionResult
from gemini_schema import gemini_response_schema, make_gemini_client
from generation_schemas import GenerationBatchOutput, PsychometricItem, QuestionOption, StimulusContext
from stimulus.stimulus_orchestrator import StimulusOrchestrator


# A single quote, passage, map, or illustration is shared by at most
# three questions in one generation (John, 2026-11-15): a 10-question
# set generated from one stimulus came back with all ten items built
# around the same quote. Batches are therefore generated in chunks of
# at most this size, each chunk with its own stimulus.
MAX_QUESTIONS_PER_STIMULUS = 3


def _image_part(content: str):
    """Build a Gemini image Part for a stimulus: a data URI (source
    material's own embedded image) becomes inline bytes, a web URL
    becomes a file reference the API fetches itself."""
    import base64
    if content.startswith("data:"):
        header, b64 = content.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1] or "image/jpeg"
        return types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
    mime = "image/png" if content.lower().split("?")[0].endswith(".png") else "image/jpeg"
    return types.Part.from_uri(file_uri=content, mime_type=mime)


OPTION_LABELS = ("A", "B", "C", "D")


def _shuffle_item_options(item: PsychometricItem) -> PsychometricItem:
    """Randomise the position of the correct answer (John, 2026-11-16).

    The model writes the options in order and systematically favours
    putting the correct answer first, and nothing in the pipeline ever
    reordered them, so generated sets came out biased toward A. Shuffling
    here -- after the model has finished, before the items are stored --
    makes the correct answer equally likely to sit at any position no
    matter what the model did. The option texts, the correct answer, and
    the per-option distractor rationales all move together; only the
    labels change. Multiple choice only: true/false keeps its
    conventional True-then-False order and short answer has no options.
    Items that do not look like a normal 4-option multiple-choice item
    are left untouched rather than risk corrupting them.
    """
    if item.question_type != "multiple_choice":
        return item
    if len(item.options) != 4 or item.correct_option not in OPTION_LABELS:
        return item
    order = list(range(len(item.options)))
    random.shuffle(order)
    new_options = []
    new_rationales = {}
    new_correct = item.correct_option
    for new_idx, old_idx in enumerate(order):
        old = item.options[old_idx]
        new_label = OPTION_LABELS[new_idx]
        new_options.append(QuestionOption(label=new_label, text=old.text))
        if old.label == item.correct_option:
            new_correct = new_label
        if old.label in (item.distractor_rationales or {}):
            new_rationales[new_label] = item.distractor_rationales[old.label]
    item.options = new_options
    item.correct_option = new_correct
    item.distractor_rationales = new_rationales
    return item


class QuestionGeneratorEngine:
    def __init__(self, api_key: str = None):
        self.client = make_gemini_client(api_key)
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
            "   - Vary the position of the correct answer across items: it must be equally likely to be A, B, C, or D. Do not favour putting it first.\n"
            "   - Homogeneity: All options must be syntactically parallel and roughly equal in length.\n"
            "   - NEVER use: 'All of the above', 'None of the above', 'Both A and B'.\n\n"
            "4. CITATION PRECISION:\n"
            "   - Extract the exact anchor (Page number, Section name, or Timestamp interval).\n\n"
            "5. STYLE EXAMPLES ARE NOT CONTENT:\n"
            "   - When example questions are supplied, they define the FORMAT, STRUCTURE, PHRASING, and COGNITIVE LEVEL to imitate. They are the primary style reference.\n"
            "   - NEVER ground an item in an example question, NEVER use an example's facts or answers as question content, and NEVER cite an example question as the grounding quote or citation anchor. Grounding comes only from the ingested source content.\n\n"
            "6. SOURCE REFERENCE IN EVERY ITEM:\n"
            "   - Every chunk in the source content is tagged with its source file (SOURCE: <filename>) and an anchor (page number, line range, timestamp, or section).\n"
            "   - For EVERY item, the citation MUST name the exact source file from that chunk's SOURCE tag (citation.source_file) and the exact anchor (citation.location_type and citation.location_value, e.g. page \"Page 12\", line \"Lines 41-80\", timestamp \"04:32 - 05:10\"). The verbatim_grounding_quote must be an exact snippet from that same chunk.\n"
            "   - The pedagogical_feedback for EVERY item must also name that source file and location, e.g. \"See chapter3.pdf, p. 12\", so a student can find where the correct answer comes from without any other information.\n"
        )

    def _style_context_for(self, target_typology: Optional[str], modality: Optional[str]) -> Optional[str]:
        """The style note that tells the model what kind of stimulus
        the example questions use, for this chunk's modality."""
        if target_typology != "STIMULUS_INTERPRETATION":
            return None
        if modality == "map_or_illustration":
            return (
                "The generated items imitate stimulus-interpretation questions: each item is built "
                "around a stimulus the student must interpret -- in the example questions this is "
                "usually a map or illustration, not a passage of text."
            )
        if modality == "primary_source_text":
            return (
                "The generated items imitate stimulus-interpretation questions: each item is built "
                "around a stimulus the student must interpret -- in the example questions this is "
                "usually a short primary-source passage or quote."
            )
        return None

    def _chunk_modalities(self, n_chunks: int, target_typology: Optional[str],
                          preferred_modality: Optional[str]) -> List[Optional[str]]:
        """One stimulus modality per chunk. An explicitly requested
        modality is honoured for every chunk. For
        stimulus-interpretation sets the 60% text / 40% visual split
        (John, 2026-11-14) is assigned across the chunks, so a set
        lands near the split instead of leaving it to chance; a
        single chunk still rolls 60/40, as before. Other typologies
        leave the modality to the planner, per chunk."""
        if preferred_modality:
            return [preferred_modality] * n_chunks
        if target_typology != "STIMULUS_INTERPRETATION":
            return [None] * n_chunks
        if n_chunks == 1:
            modality = random.choices(
                ["primary_source_text", "map_or_illustration"], weights=[60, 40]
            )[0]
            print(f"[Generate] stimulus modality roll: {modality} (60% text / 40% visual)")
            return [modality]
        n_text = round(0.6 * n_chunks)
        modalities = ["primary_source_text"] * n_text + ["map_or_illustration"] * (n_chunks - n_text)
        random.shuffle(modalities)
        print(f"[Generate] stimulus modalities across {n_chunks} chunks: "
              f"{modalities.count('primary_source_text')} text / {modalities.count('map_or_illustration')} visual")
        return modalities

    def _concept_focus(self, concepts_slice: List[str]) -> str:
        """Per-chunk concept directive: which key concepts this
        chunk's questions should validate, and how many questions
        each one gets. The slice is the round-robin assignment for
        this chunk's questions, so the counts are exact, not a wish."""
        counts = {}
        order = []
        for concept in concepts_slice:
            if concept not in counts:
                counts[concept] = 0
                order.append(concept)
            counts[concept] += 1
        lines = ["CONCEPT FOCUS FOR THIS SET OF %d QUESTION(S):" % len(concepts_slice),
                 "Validate the student's understanding of the key concepts below -- write the number of questions shown for each concept."]
        for concept in order:
            n = counts[concept]
            lines.append("- %s (%d question%s)" % (concept, n, "s" if n != 1 else ""))
        lines.append("The other sets in this assessment cover the remaining key concepts; do not repeat them here.")
        return "\n".join(lines)

    def _fetch_distinct_stimulus(self, source_text: str, preferred_modality: Optional[str],
                                 style_context: Optional[str], source_images: Optional[list],
                                 used_stimuli: List[StimulusContext]) -> Optional[StimulusContext]:
        """Fetch one stimulus that has not been used already in this
        generation. The exclusions are passed to the planner so it
        varies the passage or the image search; if it still repeats
        one, retry once with the repeat added to the exclusions."""
        try:
            stimulus = self.stimulus_orchestrator.plan_and_fetch_stimulus(
                source_text=source_text,
                preferred_modality=preferred_modality,
                style_context=style_context,
                source_images=source_images,
                exclude=list(used_stimuli),
            )
        except Exception as e:
            print(f"[Stimulus Pipeline Warning]: {e}")
            return None
        if stimulus is not None and any(stimulus.content == used.content for used in used_stimuli):
            print("[Stimulus] fetched stimulus repeats one already used; retrying with it excluded")
            try:
                stimulus = self.stimulus_orchestrator.plan_and_fetch_stimulus(
                    source_text=source_text,
                    preferred_modality=preferred_modality,
                    style_context=style_context,
                    source_images=source_images,
                    exclude=list(used_stimuli) + [stimulus],
                )
            except Exception as e:
                print(f"[Stimulus Pipeline Warning]: {e}")
                return None
        return stimulus

    def _stimulus_prompt_section(self, external_stimulus: Optional[StimulusContext]) -> str:
        if not external_stimulus:
            return ""
        if external_stimulus.stimulus_type in ("map", "illustration"):
            return (
                f"\n=== EXTERNAL STIMULUS SUPPLIED FOR THIS ASSESSMENT ===\n"
                f"Type: {external_stimulus.stimulus_type.upper()} -- the image is attached to this request; look at it.\n"
                f"Attribution / Background: {external_stimulus.attribution_or_context}\n"
                f"Image URL: {external_stimulus.content}\n"
                f"Write the stem so the student must interpret what is actually shown in the image, as in the example questions.\n"
                f"======================================================\n"
            )
        return (
            f"\n=== EXTERNAL STIMULUS SUPPLIED FOR THIS ASSESSMENT ===\n"
            f"Type: {external_stimulus.stimulus_type.upper()}\n"
            f"Attribution / Background: {external_stimulus.attribution_or_context}\n\n"
            f"CONTENT / DATA:\n{external_stimulus.content}\n"
            f"======================================================\n"
        )

    def generate_questions(
        self,
        ingested_source: IngestionResult,
        count: int = 5,
        target_typology: Optional[str] = "SCENARIO_VIGNETTE",
        question_type: str = "multiple_choice",
        custom_style_instructions: Optional[str] = None,
        inject_external_stimulus: bool = False,
        preferred_stimulus_modality: Optional[str] = None,
        style_examples: Optional[str] = None,
        source_images: Optional[list] = None,
        concepts: Optional[List[str]] = None,
    ) -> List[PsychometricItem]:
        if count <= 0:
            return []
        source_context_str = ingested_source.to_llm_context()
        needs_stimulus = inject_external_stimulus or target_typology in ["STIMULUS_INTERPRETATION", "DATA_EVALUATION"]

        # Concepts are dealt round-robin, one question at a time, so
        # a set covers them evenly instead of clustering on the
        # first concept the model happens to pick.
        question_concepts = (
            [concepts[i % len(concepts)] for i in range(count)] if concepts else [None] * count
        )
        # Chunking only pays when something varies per chunk: a
        # stimulus to rotate, or concepts to spread. Otherwise the
        # single call is unchanged -- same cost, same behaviour.
        chunked = needs_stimulus or bool(concepts)
        chunk_size = MAX_QUESTIONS_PER_STIMULUS if chunked else count
        chunks = [(i, min(i + chunk_size, count)) for i in range(0, count, chunk_size)]
        modalities = self._chunk_modalities(len(chunks), target_typology, preferred_stimulus_modality) if needs_stimulus else []

        style_examples_section = ""
        if style_examples:
            style_examples_section = (
                "\n=== EXAMPLE QUESTIONS - STYLE REFERENCE ONLY ===\n"
                "The questions below are real example questions from this topic. They are the PRIMARY basis for the style of the items you generate: imitate their format, structure, phrasing, option style, and cognitive level as closely as possible.\n"
                "They are NOT source content: do not test their facts, do not reuse their answers, and never cite them as grounding. Every item you generate must still be grounded exclusively in the INGESTED SOURCE CONTENT above.\n\n"
                f"{style_examples}\n"
                "=== END EXAMPLE QUESTIONS ===\n"
            )

        all_items: List[PsychometricItem] = []
        used_stimuli: List[StimulusContext] = []
        for chunk_idx, (start, end) in enumerate(chunks):
            chunk_count = end - start
            chunk_instructions = custom_style_instructions
            # The per-chunk concept focus only applies when the set
            # is actually split; a single chunk covers what it can
            # under the overall concepts directive as before.
            if len(chunks) > 1 and concepts:
                focus = self._concept_focus(question_concepts[start:end])
                chunk_instructions = (chunk_instructions + "\n" + focus if chunk_instructions else focus)
            external_stimulus = None
            if needs_stimulus:
                modality = modalities[chunk_idx] if modalities else preferred_stimulus_modality
                external_stimulus = self._fetch_distinct_stimulus(
                    source_context_str,
                    modality,
                    self._style_context_for(target_typology, modality),
                    source_images,
                    used_stimuli,
                )
                if external_stimulus is not None:
                    used_stimuli.append(external_stimulus)

            task_prompt = (
                f"SOURCE DOCUMENT: \"{ingested_source.source_title}\" ({ingested_source.source_type.upper()})\n\n"
                f"--- INGESTED SOURCE CONTENT (WITH CITATION ANCHORS) ---\n"
                f"{source_context_str}\n"
                f"--- END SOURCE CONTENT ---\n\n"
                f"{style_examples_section}\n"
                f"{self._stimulus_prompt_section(external_stimulus)}\n"
                f"TASK:\n"
                f"Generate {chunk_count} assessment items following these specifications:\n"
                f"- Item Typology: {target_typology}\n"
                f"- Question Format: {question_type}\n"
                f"- Cognitive Level: Bloom's Level 3 (Apply) or Level 4 (Analyze)\n"
                f"- Source Reference: every item's citation.source_file and citation location must match the SOURCE tag and anchor of the chunk the answer comes from; the pedagogical_feedback must name that same file and location.\n\n"
                f"ADDITIONAL DIRECTIVES:\n"
                f"{chunk_instructions or 'Adhere to strict psychometric guidelines.'}\n"
            )

            contents = task_prompt
            if external_stimulus and external_stimulus.stimulus_type in ("map", "illustration"):
                # The model cannot see an image from a URL in the text prompt.
                # Attach it as a multimodal part; if that fails, fall back
                # to the text-only prompt rather than failing generation.
                try:
                    contents = [task_prompt, _image_part(external_stimulus.content)]
                except Exception as e:
                    print(f"[Generate] could not attach stimulus image, text-only prompt: {e}")

            response = self.client.models.generate_content(
                model="gemini-3.1-pro-preview",  # was gemini-2.5-pro, retired 2026-11-02
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self._build_system_instruction(),
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(GenerationBatchOutput),
                    temperature=0.2,
                )
            )

            batch = GenerationBatchOutput.model_validate_json(response.text)
            for item in batch.items:
                if item.stimulus and item.stimulus.stimulus_type in ("map", "illustration"):
                    # A map/illustration stimulus is only real if it is the
                    # URL we fetched. The model may invent one; a broken
                    # image is worse than no image, so replace it with the
                    # verified stimulus, or drop it when there is none.
                    if not external_stimulus or item.stimulus.content != external_stimulus.content:
                        print(f"[Generate] dropping model-invented visual stimulus: {str(item.stimulus.content)[:100]}")
                        item.stimulus = external_stimulus
                elif external_stimulus and not item.stimulus:
                    item.stimulus = external_stimulus
                # Randomise the answer position (see _shuffle_item_options).
                _shuffle_item_options(item)
            all_items.extend(batch.items)
        return all_items
