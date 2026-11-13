"""Gemini Developer API compatibility helpers.

Response schemas for the Gemini Developer API.

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

import os
from typing import Any

from google import genai


def make_gemini_client(api_key=None):
    """Build a Gemini Developer API client pinned to API version v1beta.

    The google-genai 3.x SDK defaults to API version v1, where preview
    models such as gemini-3.1-pro-preview do not exist ("not found for
    API version v1"). They are served on v1beta, so pin the client
    there. All client construction in this backend goes through here.
    """
    return genai.Client(
        api_key=api_key or os.environ.get("GEMINI_API_KEY"),
        http_options={"api_version": "v1beta"},
    )


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
