from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .schemas import SparkTaskAction, TaskContext
from .settings import SparkSettings, get_settings

if TYPE_CHECKING:  # pragma: no cover
    from google.genai import Client as GoogleGenAIClient

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


logger = logging.getLogger(__name__)

_FALLBACK_REPLY = SparkTaskAction(
    action_type="update",
    message="I could not generate a reliable response for this task yet.",
    confidence=0.0,
)


def get_fallback_spark_reply() -> SparkTaskAction:
    return _FALLBACK_REPLY.model_copy()


def _search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    if DDGS is None:
        logger.warning("duckduckgo-search not installed; web search unavailable")
        return []

    try:
        results = []
        for result in DDGS().text(query, max_results=max_results):
            results.append({
                "title": result.get("title", ""),
                "body": result.get("body", ""),
                "href": result.get("href", ""),
            })
        logger.info("Web search for '%s' returned %d results", query, len(results))
        return results
    except Exception as exc:
        logger.exception("Web search failed for query '%s': %s", query, str(exc))
        return []


def _format_search_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""

    formatted = "RESEARCH FINDINGS:\n"
    for i, result in enumerate(results, 1):
        # Keep it concise for Google's structured output
        title = result['title'][:100]
        body = result['body'][:150]
        href = result['href'][:80]
        formatted += f"\n[{i}] {title}\n{body}\n(Source: {href})\n"
    return formatted


def _should_include_research(latest_comment: str) -> bool:
    research_keywords = ["research", "find", "look up", "investigate", "explore", "check", "what is", "how to"]
    comment_lower = latest_comment.lower()
    return any(keyword in comment_lower for keyword in research_keywords)


def _build_spark_prompt(context: TaskContext, latest_comment: str, research_findings: str = "") -> str:
    context_payload = context.model_dump(mode="json")
    prompt = (
        "You are Spark, a Sales AI employee (Mogo) on the coolmogo platform.\n"
        "You work alongside humans on a shared task board. You are a thoughtful colleague, not a chatbot.\n"
        "\n"
        "## Your identity\n"
        "- You are assigned to tasks just like a human teammate.\n"
        "- You have a name (Spark), a role (Sales Mogo), and a consistent voice: capable, concise, transparent about uncertainty.\n"
        "- You do NOT greet the user, introduce yourself, or use filler phrases like 'Great question!'.\n"
        "- You write like a colleague giving a quick, useful update — not an assistant completing a request.\n"
        "\n"
        "## What you can do\n"
        "You may only respond with one of two action types:\n"
        "\n"
        "1. action_type='update'\n"
        "   Use this when a concise status update, analysis, recommendation, or clarifying question is the most useful next step.\n"
        "   This is narration — it does NOT trigger any external action.\n"
        "   Examples:\n"
        "   - Summarising what you found after researching the task\n"
        "   - Flagging a blocker or asking a clarifying question\n"
        "   - Confirming you understood the instruction\n"
        "\n"
        "2. action_type='propose'\n"
        "   Use this when the best next step requires creating a follow-up task for someone to act on.\n"
        "   You MUST include a proposal object with proposal_type='create_task', a clear title, and a DETAILED description.\n"
        "   IMPORTANT: When you have research findings (in the Research Context section below), you MUST embed them directly into the proposal description.\n"
        "   Do NOT use placeholders like '[findings]' or '[details]'. Instead, include the actual research content, sources, and next steps.\n"
        "   The proposal is NOT executed automatically — a human must accept it first.\n"
        "   Examples:\n"
        "   - User says 'research this and create an implementation task'\n"
        "   - User says 'package these findings into a task and assign it to me'\n"
        "   - The work is ready to be handed off as a concrete next step\n"
        "\n"
        "## Rules\n"
        "- NEVER claim you have updated a status, assigned a user, created a task, sent an email, or taken any real-world action.\n"
        "  You can only propose — a human decides whether to accept.\n"
        "- NEVER return action_type='update' when the user clearly asked for task creation.\n"
        "- NEVER return action_type='propose' without a valid proposal object.\n"
        "- Do NOT hedge excessively. Pick the single most useful action and commit to it.\n"
        "- Keep messages short and grounded in the task context provided.\n"
        "- If the task context is insufficient to give a useful response, use action_type='update' to ask a clarifying question.\n"
        "- confidence should reflect how certain you are that your response is useful (0.0 = not useful, 1.0 = very confident).\n"
        "\n"
        "## Output format\n"
        "Return strict JSON only. No markdown, no preamble, no explanation outside the JSON.\n"
        "Schema:\n"
        "{\n"
        "  \"action_type\": \"update\" | \"propose\",\n"
        "  \"message\": \"<your concise response as Spark>\",\n"
        "  \"confidence\": <0.0 to 1.0>,\n"
        "  \"proposal\": null | {\n"
        "    \"proposal_type\": \"create_task\",\n"
        "    \"title\": \"<task title>\",\n"
        "    \"description\": \"<detailed implementation instructions or research findings>\",\n"
        "    \"assignee_id\": \"<user id or null>\",\n"
        "    \"stage_id\": \"<stage id or null>\"\n"
        "  }\n"
        "}\n"
        "\n"
        "## Examples\n"
        "\n"
        "User comment: 'research the Henderson deal and tell me what you think'\n"
        "-> action_type='update', message summarising your analysis from context, proposal=null\n"
        "\n"
        "User comment: 'research AI onboarding tools and create a task to improve our onboarding process'\n"
        "With research findings showing 'AI template tools increase efficiency 20%', 'Popular tools: Talentsoft, BambooHR', etc:\n"
        "-> action_type='propose'\n"
        "   message='Found several AI tools that can streamline onboarding'\n"
        "   proposal.title='Research and implement AI onboarding tools'\n"
        "   proposal.description='## Research Summary\\n\\nWe researched AI onboarding solutions to improve our process.\\n\\n## Findings\\n\\n1. **AI Template Tools**\\nAI-generated templates increase efficiency by 20%. Key tools: [tool names from research]...\\n2. **Scheduling Integration**\\n[complete findings from research]...\\n3. **Implementation Approach**\\n[next steps]\\n\\n## Sources\\n[actual URLs from research]'\n"
        "\n"
        "User comment: 'what do you need from me to move forward?'\n"
        "-> action_type='update', message asking the specific clarifying question you need, proposal=null\n"
        "\n"
    )

    prompt += f"Latest user comment: {latest_comment}\n"

    if research_findings:
        prompt += (
            "\n⚠️ CRITICAL INSTRUCTION FOR PROPOSAL:\n"
            "You have research findings below. If you propose a task (action_type='propose'), you MUST include these findings VERBATIM in the proposal.description field.\n"
            "DO NOT use placeholders like '[findings]', '[details]', or '[research]'.\n"
            "DO NOT summarize the findings — copy them directly.\n"
            "The proposal.description will be shown to the user as the task body, so it must contain the full research content, sources, and actionable next steps.\n"
            "Structure the description as:\n"
            "1. Brief overview of what was researched\n"
            "2. Detailed findings (copy the research results verbatim below)\n"
            "3. Sources and links\n"
            "4. Recommended next steps\n"
            f"\nRESEARCH CONTENT TO EMBED:\n{research_findings}\n"
            "END RESEARCH CONTENT\n"
            "\nNow compose the proposal.description to INCLUDE ALL of this research verbatim.\n"
        )

    prompt += f"Task context JSON: {json.dumps(context_payload, ensure_ascii=True)}"

    return prompt


@lru_cache(maxsize=4)
def _google_client(api_key: str) -> "GoogleGenAIClient":
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    from google import genai

    return genai.Client(api_key=api_key)


def _extract_google_text_content(response: Any) -> str:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, SparkTaskAction):
            return parsed.model_dump_json()
        if isinstance(parsed, dict):
            return json.dumps(parsed)

    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    raise ValueError("Google AI response did not include text content")


def _generate_google_reply(
    active_settings: SparkSettings,
    prompt: str,
) -> SparkTaskAction:
    if not active_settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    from google.genai import types

    system_instruction = (
        "You are Spark, an AI employee. When proposing tasks with research findings:\n"
        "1. The proposal.description will be shown to the user as the actual task body they will read\n"
        "2. MUST include research findings VERBATIM in proposal.description — NOT placeholders or summaries\n"
        "3. Structure: [Overview] → [Detailed Findings with all research content] → [Sources] → [Recommended Actions]\n"
        "4. Copy the actual research content directly; do not abstract or replace with 'see findings' language\n"
        "5. If research was provided in the prompt, embed ALL of it, not just a reference to it\n"
        "6. The user approves based on what they see in the proposal.description, so it must be complete and substantive"
    )

    response = _google_client(active_settings.google_api_key).models.generate_content(
        model=active_settings.google_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=SparkTaskAction,
        ),
    )
    raw_content = _extract_google_text_content(response)
    return SparkTaskAction.model_validate(json.loads(raw_content))


def generate_spark_reply(
    context: TaskContext,
    latest_comment: str,
    *,
    settings: SparkSettings | None = None,
) -> SparkTaskAction:
    active_settings = settings or get_settings()

    research_findings = ""
    if _should_include_research(latest_comment):
        logger.info("Detected research request in comment: %s", latest_comment[:100])
        search_results = _search_web(latest_comment, max_results=5)
        if search_results:
            research_findings = _format_search_results(search_results)

    prompt = _build_spark_prompt(context, latest_comment, research_findings)

    try:
        logger.info("Calling Spark LLM: Google AI (model: %s)", active_settings.google_model)
        return _generate_google_reply(active_settings, prompt)
    except (json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
        logger.exception("Spark returned an invalid response: %s", str(exc), exc_info=exc)
        return get_fallback_spark_reply()
    except Exception as exc:  # pragma: no cover - defensive API failure guard
        logger.exception("Spark request failed: %s", str(exc), exc_info=exc)
        return get_fallback_spark_reply()
