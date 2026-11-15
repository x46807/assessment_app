"""Two further tiers of feedback for the student.

Tier 1 -- detailed per-question feedback: a paragraph connecting the
correct answer to the key concept(s) it tests, plus a test-taking tip
for that question.

Tier 2 -- topic evaluation: once enough questions in a topic have been
answered, an evaluation of strengths and weaknesses by concept and by
test-taking strategy.

The strategy guidance is grounded in the AP World MCQ playbook from
Fiveable (https://fiveable.me/ap-world/ap-world-history-modern-exam/
ap-world-mcq/study-guide/ap-world-mcq): 55 questions in 55 minutes
(~1 min per question, 40% of the exam score, no penalty for guessing);
read the stimulus first (15-20 seconds) before the options; match the
scale (local vs regional vs global); eliminate with historical logic --
anachronisms, geographic mismatches, "what could have happened but
didn't" options, and too-tidy single-cause answers; "most directly"
means the next link in the causal chain, not the eventual one;
comparison questions want a deeper structural parallel, not a surface
similarity; sourcing / point of view shapes what an author says;
change-over-time signals ("by the end of the period") name a timeframe
the answer must fit; skip a stuck question after ~45 seconds and return
to it (the 40-15 timing plan); never leave a question blank.
"""

from typing import List, Literal, Optional

from google.genai import types
from pydantic import BaseModel, Field

from gemini_schema import gemini_response_schema, make_gemini_client


STRATEGY_PLAYBOOK = (
    "Test-taking strategies for multiple-choice history questions "
    "(AP World MCQ playbook): read the stimulus first (15-20 seconds) "
    "before looking at the options; match the scale -- a local explanation "
    "does not answer a global question and vice versa; eliminate with "
    "historical logic -- anachronisms (an option from the wrong era), "
    "geographic mismatches (a true statement about the wrong region), "
    "plausible-but-didn't-happen options, and too-tidy single-cause "
    "answers for multicausal processes; 'most directly' means the next "
    "link in the causal chain, not the eventual consequence; comparison "
    "questions want a deeper structural parallel, not a surface "
    "similarity; sourcing matters -- the author's position, identity and "
    "moment shape what they say; change-over-time wording ('by the end of "
    "the period') names a timeframe the answer must fit; if a question is "
    "not clicking after ~45 seconds, skip it and return later; there is "
    "no penalty for guessing, so never leave a question blank."
)


class DetailedFeedback(BaseModel):
    """Tier 1: the deeper explanation for one question."""
    concept_paragraph: str = Field(
        description="A paragraph connecting the correct answer to the key "
        "concept(s) it tests, and why understanding that concept leads to "
        "this answer."
    )
    key_concepts: List[str] = Field(
        default_factory=list,
        description="The key concepts this question tests, as short names.",
    )
    strategy_tip: str = Field(
        description="One concrete test-taking tip for this specific "
        "question: which strategy applies, and which trap in the "
        "distractors it guards against."
    )


class ConceptAssessment(BaseModel):
    """One concept's verdict inside a topic evaluation."""
    concept: str
    verdict: Literal["strength", "weakness", "developing"]
    correct: int = 0
    total: int = 0
    evidence: str = Field(
        description="What the student's answers on this concept show."
    )
    recommendation: str = Field(
        description="What to study or practise for this concept."
    )


class TopicEvaluation(BaseModel):
    """Tier 2: the evaluation of one topic, once enough questions have
    been answered."""
    summary: str = Field(
        description="Two to three sentences: overall, what the student "
        "knows well and where they struggle."
    )
    concepts: List[ConceptAssessment] = Field(default_factory=list)
    strategy_observations: List[str] = Field(
        default_factory=list,
        description="What the student's answering patterns show about "
        "their test-taking strategy (pacing, stimulus use, traps fallen "
        "for, question types)."
    )
    strategy_recommendations: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


class FeedbackAnalyzer:
    def __init__(self, api_key: str = None):
        self.client = make_gemini_client(api_key)

    def detailed_feedback(
        self,
        question_text: str,
        source_context: str,
        concepts_context: str = "",
    ) -> DetailedFeedback:
        """Tier 1: explain one question in depth -- the concept behind
        the correct answer, and the test-taking tip for this question."""
        prompt = (
            "You are an expert history teacher explaining one practice "
            "question to a student who has just answered it.\\n\\n"
            "Write (1) a paragraph that connects the correct answer to "
            "the key concept(s) it tests -- explain the concept and why "
            "understanding it leads to this answer, grounding everything "
            "in the source material below; (2) the key concepts as short "
            "names; (3) one concrete test-taking tip for THIS question, "
            "drawn from the strategy playbook below, naming the trap in "
            "the wrong options it guards against.\\n\\n"
            "STRATEGY PLAYBOOK:\\n" + STRATEGY_PLAYBOOK + "\\n\\n"
            + ("KEY CONCEPTS AND OBJECTIVES FOR THIS TOPIC:\\n" + concepts_context[:2000] + "\\n\\n"
               if concepts_context.strip() else "")
            + "SOURCE MATERIAL (for grounding -- the question's facts come "
            "from here):\\n" + source_context[:4000] + "\\n\\n"
            + "QUESTION:\\n" + question_text[:4000] + "\\n"
        )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(DetailedFeedback),
                temperature=0.3,
            ),
        )
        return DetailedFeedback.model_validate_json(response.text)

    def evaluate_topic(
        self,
        attempts_text: str,
        concepts_context: str = "",
    ) -> TopicEvaluation:
        """Tier 2: evaluate a topic from the student's answered
        questions -- strengths and weaknesses by concept, and by
        test-taking strategy. The attempt lines state, for each
        question, the type, the options, the correct answer, what the
        student answered, and how long they took from first choice to
        submit."""
        prompt = (
            "You are an expert history teacher evaluating a student's "
            "practice in one topic. Below are the questions they "
            "answered, what they chose, whether it was right, and how "
            "long each took.\\n\\n"
            "Assess (1) their understanding of the core concepts and "
            "objectives -- group the questions by the concept each "
            "tests, judge each concept a strength, a weakness, or "
            "developing, and say what to study for it; (2) their "
            "test-taking strategy, using the playbook below: pacing "
            "(fast-and-wrong suggests rushing; slow-and-wrong suggests "
            "being stuck), whether they use the stimulus, which traps "
            "they fall for, and which question types are weakest. Be "
            "specific and honest: name the actual questions and options "
            "as evidence, and do not invent a pattern the data does not "
            "show. If a concept has only one or two attempts, say so "
            "rather than overstating it.\\n\\n"
            "STRATEGY PLAYBOOK:\\n" + STRATEGY_PLAYBOOK + "\\n\\n"
            + ("KEY CONCEPTS AND OBJECTIVES FOR THIS TOPIC:\\n" + concepts_context[:2000] + "\\n\\n"
               if concepts_context.strip() else "")
            + "ANSWERED QUESTIONS:\\n" + attempts_text[:12000] + "\\n"
        )
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(TopicEvaluation),
                temperature=0.3,
            ),
        )
        return TopicEvaluation.model_validate_json(response.text)
