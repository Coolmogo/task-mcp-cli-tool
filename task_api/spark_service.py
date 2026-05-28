from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .schemas import SparkTaskReply, TaskContext
from .settings import SparkSettings, get_settings

if TYPE_CHECKING:  # pragma: no cover
    from google.genai import Client as GoogleGenAIClient
    from openai import OpenAI


logger = logging.getLogger(__name__)

_FALLBACK_REPLY = SparkTaskReply(
    response_type="clarification",
    message="I could not generate a reliable response for this task yet.",
    confidence=0.0,
)


def get_fallback_spark_reply() -> SparkTaskReply:
    return _FALLBACK_REPLY.model_copy()


def _build_spark_prompt(context: TaskContext, latest_comment: str) -> str:
    context_payload = context.model_dump(mode="json")
    return (
        "You are Spark, an MVP task assistant that only replies as a task comment.\n"
        "Use only the provided task context.\n"
        "Do not claim you updated status, assigned users, created tasks, or deleted tasks.\n"
        "Keep the reply short, useful, and grounded in the context.\n"
        "Return strict JSON with keys response_type, message, confidence.\n"
        f"Latest user comment: {latest_comment}\n"
        f"Task context JSON: {json.dumps(context_payload, ensure_ascii=True)}"
    )


def _extract_openai_text_content(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
    raise ValueError("OpenAI response did not include text content")


@lru_cache(maxsize=4)
def _openai_client(api_key: str) -> "OpenAI":
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    return OpenAI(api_key=api_key)


@lru_cache(maxsize=4)
def _google_client(api_key: str) -> "GoogleGenAIClient":
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    from google import genai

    return genai.Client(api_key=api_key)


def _extract_google_text_content(response: Any) -> str:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, SparkTaskReply):
            return parsed.model_dump_json()
        if isinstance(parsed, dict):
            return json.dumps(parsed)

    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    raise ValueError("Google AI response did not include text content")


def _generate_openai_reply(
    active_settings: SparkSettings,
    prompt: str,
) -> SparkTaskReply:
    if not active_settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    response = _openai_client(active_settings.openai_api_key).chat.completions.create(
        model=active_settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are Spark. Reply with JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )
    raw_content = _extract_openai_text_content(response)
    return SparkTaskReply.model_validate(json.loads(raw_content))


def _generate_google_reply(
    active_settings: SparkSettings,
    prompt: str,
) -> SparkTaskReply:
    if not active_settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    from google.genai import types

    response = _google_client(active_settings.google_api_key).models.generate_content(
        model=active_settings.google_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SparkTaskReply,
        ),
    )
    raw_content = _extract_google_text_content(response)
    return SparkTaskReply.model_validate(json.loads(raw_content))


def generate_spark_reply(
    context: TaskContext,
    latest_comment: str,
    *,
    settings: SparkSettings | None = None,
) -> SparkTaskReply:
    active_settings = settings or get_settings()
    prompt = _build_spark_prompt(context, latest_comment)

    try:
        if active_settings.spark_llm_provider == "google":
            return _generate_google_reply(active_settings, prompt)
        return _generate_openai_reply(active_settings, prompt)
    except (json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
        logger.exception(
            "Spark returned an invalid response using provider %s",
            active_settings.spark_llm_provider,
            exc_info=exc,
        )
        return get_fallback_spark_reply()
    except Exception as exc:  # pragma: no cover - defensive API failure guard
        logger.exception(
            "Spark request failed using provider %s",
            active_settings.spark_llm_provider,
            exc_info=exc,
        )
        return get_fallback_spark_reply()
