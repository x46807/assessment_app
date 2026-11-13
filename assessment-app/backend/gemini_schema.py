"""Response schemas for the Gemini Developer API.

The Gemini Developer API rejects ``additionalProperties`` in response
schemas (it is only supported in Gemini Enterprise / Agent Platform mode).
Pydantic emits ``additionalProperties`` for ``Dict[...]`` fields -- e.g.
``PsychometricItem.distractor_rationales: Dict[str, str]`` becomes
``{"type": "object", "additionalProperties": {"type": "string"}}`` -- so
passing a Pydantic model directly as ``response_schema`` makes the API
reject the call with:
"additionalProperties is only supported in Gemini Enterprise Agent
Platform mode, not in Gemini Developer API mode."

``gemini_response_schema`` returns the model's JSON schema with every
``additionalProperties`` entry removed (recursively, including ``$defs``).
The affected fields become plain ``{"type": "object"}``; the model is
still free to return an object there, and the response is validated
against the full Pydantic model afterwards, so nothing is lost.
"""

from typing import Any


def _strip_additional_properties(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("additionalProperties", None)
        for value in node.values():
            _strip_additional_properties(value)
    elif isinstance(node, list):
        for item in node:
            _strip_additional_properties(item)


def gemini_response_schema(model_cls) -> dict:
    """JSON schema for ``model_cls`` with ``additionalProperties`` removed."""
    schema = model_cls.model_json_schema()
    _strip_additional_properties(schema)
    return schema
