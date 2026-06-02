from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import ValidationError

from .schemas import SparkTaskAction, TaskContext
from .settings import SparkSettings, get_settings

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
except ImportError:
    Agent = None
    OpenAIModel = None


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


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting from text, keeping plain content."""
    if not text:
        return text

    import re
    # Remove bold **text** -> text
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # Remove italic *text* or _text_ -> text
    text = re.sub(r'[*_](.*?)[*_]', r'\1', text)
    # Remove headers (### text -> text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # Remove [link](url) -> link
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # Remove inline code `code` -> code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove code blocks and keep content
    text = re.sub(r'```.*?\n(.*?)\n```', r'\1', text, flags=re.DOTALL)

    return text


def _format_search_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""

    formatted = "RESEARCH FINDINGS:\n"
    for i, result in enumerate(results, 1):
        title = result['title'][:100]
        body = result['body'][:150]
        href = result['href'][:80]
        formatted += f"\n[{i}] {title}\n{body}\n(Source: {href})\n"
    return formatted


def _should_include_research(latest_comment: str) -> bool:
    # Only search for explicit research requests, not generic questions
    explicit_research_keywords = ["research", "find out", "look up", "investigate", "search for"]
    comment_lower = latest_comment.lower()
    return any(keyword in comment_lower for keyword in explicit_research_keywords)


def _should_propose(latest_comment: str) -> bool:
    # Check if user explicitly asks to create a task
    propose_keywords = ["create", "create task", "create a task", "make a task", "propose", "draft", "build"]
    comment_lower = latest_comment.lower()
    return any(keyword in comment_lower for keyword in propose_keywords)


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
        "You may respond with one of six action types:\n"
        "\n"
        "1. action_type='ask'\n"
        "   Use when you need more information or clarification to proceed.\n"
        "   Examples: asking about budget, timeline, technical requirements, or priorities.\n"
        "\n"
        "2. action_type='instruct'\n"
        "   Use when you want to share analysis, give advice, or provide updates.\n"
        "   This is a comment — just dialogue, no external action.\n"
        "   Examples: summarizing findings, giving recommendations, confirming understanding.\n"
        "\n"
        "3. action_type='update'\n"
        "   Use when you want to auto-update task fields based on your analysis.\n"
        "   Include update_fields: {\"status\": \"In Progress\", \"priority\": \"high\", etc}\n"
        "   Examples: moving status to In Progress when work starts, raising priority for urgent items.\n"
        "\n"
        "4. action_type='propose'\n"
        "   Use when the best next step requires creating a follow-up task.\n"
        "   You MUST include a proposal object with proposal_type='create_task', a clear title, and DETAILED description.\n"
        "   IMPORTANT: When you have research findings, embed them directly into the proposal description.\n"
        "   Do NOT use placeholders like '[findings]' or '[details]'. Include the actual research content, sources, and next steps.\n"
        "   The proposal is NOT executed automatically — a human must accept it first.\n"
        "   Examples: user says 'research and create a task', user says 'package findings into actionable work'.\n"
        "\n"
        "5. action_type='decide'\n"
        "   (Human-only) Use when approving a proposal.\n"
        "\n"
        "6. action_type='dismiss'\n"
        "   (Human-only) Use when rejecting a proposal.\n"
        "\n"
        "## Rules\n"
        "- NEVER claim you have updated a status, assigned a user, created a task, sent an email, or taken any real-world action.\n"
        "  You can only propose — a human decides whether to accept.\n"
        "- NEVER return action_type='update' when the user clearly asked for task creation.\n"
        "- NEVER return action_type='propose' without a valid proposal object.\n"
        "- DEFAULT TO 'ask' or 'instruct' (dialogue) UNLESS the user explicitly uses words like 'create', 'make', 'draft', 'propose', or 'build'.\n"
        "- IMPORTANT: If the user is asking a question or asking for analysis, respond with 'ask' or 'instruct'. Do NOT propose a task.\n"
        "- IMPORTANT: Only propose when the user explicitly asks you to CREATE/DRAFT/BUILD/PROPOSE something new.\n"
        "- Do NOT hedge excessively. Pick the single most useful action and commit to it.\n"
        "- Keep messages short and grounded in the task context provided.\n"
        "- If the task context is insufficient to give a useful response, use action_type='ask' to ask for clarification.\n"
        "- confidence should reflect how certain you are that your response is useful (0.0 = not useful, 1.0 = very confident).\n"
        "\n"
        "## Output format\n"
        "Return strict JSON only. No markdown, no asterisks, no preamble, no explanation outside the JSON.\n"
        "In all text fields (message, title, description): use PLAIN TEXT ONLY. Do not use **bold**, *italic*, # headers, - bullets, [links], or any markdown.\n"
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
        "With research findings showing 'AI template tools increase efficiency 20%', 'Popular tools: Talentsoft, BambooHR':\n"
        "-> action_type='propose'\n"
        "   message='Found several AI tools that can streamline onboarding'\n"
        "   proposal.title='Research and implement AI onboarding tools'\n"
        "   proposal.description='Research Summary: We researched AI onboarding solutions to improve our process.\\n\\nFindings:\\n\\n1. AI Template Tools: AI-generated templates increase efficiency by 20%. Key tools include Talentsoft, BambooHR, and others.\\n\\n2. Scheduling Integration: [specific findings without markdown]\\n\\n3. Implementation Approach: [next steps]\\n\\nSources: [actual URLs from research]'\n"
        "\n"
        "User comment: 'what do you need from me to move forward?'\n"
        "-> action_type='update', message asking the specific clarifying question you need, proposal=null\n"
        "\n"
    )

    prompt += f"Latest user comment: {latest_comment}\n"

    # If user explicitly asks to create a task, guide toward proposal
    if _should_propose(latest_comment):
        prompt += "\nThe user is asking you to CREATE or DRAFT a task. You MUST respond with action_type='propose' and include a detailed proposal.\n"
    else:
        prompt += "\nThe user is asking a question or seeking analysis. Respond with 'ask' or 'instruct', NOT 'propose'.\n"

    if research_findings:
        prompt += (
            "\n⚠️ RESEARCH FINDINGS AVAILABLE:\n"
            "You have research findings below. Use them to answer the user's question with action_type='instruct' or 'ask'.\n"
            "ONLY if the user explicitly asked you to CREATE or DRAFT a task, use action_type='propose' and embed these findings VERBATIM in proposal.description.\n"
            "Otherwise, share the findings directly in your message as 'instruct' or ask follow-up questions as 'ask'.\n"
            "DO NOT automatically propose a task just because you have research findings.\n"
            f"\nRESEARCH CONTENT:\n{research_findings}\n"
            "END RESEARCH CONTENT\n"
        )

    prompt += f"Task context JSON: {json.dumps(context_payload, ensure_ascii=True)}"

    return prompt


def generate_spark_reply(
    context: TaskContext,
    latest_comment: str,
    *,
    settings: SparkSettings | None = None,
) -> SparkTaskAction:
    if Agent is None or OpenAIModel is None:
        logger.error("pydantic-ai not installed; Spark unavailable")
        return get_fallback_spark_reply()

    active_settings = settings or get_settings()

    if not active_settings.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY is not configured")
        return get_fallback_spark_reply()

    research_findings = ""
    if _should_include_research(latest_comment):
        logger.info("Detected research request in comment: %s", latest_comment[:100])
        search_results = _search_web(latest_comment, max_results=5)
        if search_results:
            research_findings = _format_search_results(search_results)

    prompt = _build_spark_prompt(context, latest_comment, research_findings)

    # Configure environment for OpenRouter before any model initialization
    os.environ["OPENAI_API_KEY"] = active_settings.openrouter_api_key or ""
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

    try:
        logger.info("Calling Spark LLM: OpenRouter (model: %s)", active_settings.openrouter_model)
        model = OpenAIModel(active_settings.openrouter_model, provider="openai-chat")
        agent: Agent[SparkTaskAction] = Agent(
            model,
            system_prompt=(
                "You are Spark, an AI employee. Return VALID JSON ONLY.\n"
                "CRITICAL: Default to dialogue (ask/instruct). Only propose when the user explicitly asks you to CREATE or DRAFT something.\n"
                "When proposing tasks with research findings:\n"
                "1. The proposal.description will be shown to the user as the actual task body they will read\n"
                "2. MUST include research findings VERBATIM in proposal.description — NOT placeholders or summaries\n"
                "3. Structure: [Overview] → [Detailed Findings with all research content] → [Sources] → [Recommended Actions]\n"
                "4. Copy the actual research content directly; do not abstract or replace with 'see findings' language\n"
                "5. If research was provided in the prompt, embed ALL of it, not just a reference to it\n"
                "6. The user approves based on what they see in the proposal.description, so it must be complete and substantive\n"
                "CRITICAL: All text fields in the JSON MUST use proper JSON escaping (use \\n for newlines, not literal newlines)"
            ),
        )
        result = agent.run_sync(prompt)
        # Extract JSON from response and validate
        messages = result.all_messages()
        if messages:
            last_msg = messages[-1]
            response_text = getattr(last_msg, 'text', '')
            logger.info(f"Raw LLM response: {response_text[:500]}")

            if response_text:
                # Strip markdown code fence if present (```json ... ```)
                response_text = response_text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:]  # Remove ```json
                if response_text.startswith('```'):
                    response_text = response_text[3:]  # Remove ```
                if response_text.endswith('```'):
                    response_text = response_text[:-3]  # Remove trailing ```
                response_text = response_text.strip()

                logger.info(f"Cleaned response: {response_text[:500]}")
                try:
                    response_json = json.loads(response_text)
                except json.JSONDecodeError as parse_err:
                    logger.error(f"JSON parse error at position {parse_err.pos}: {parse_err.msg}")
                    logger.error(f"Near: ...{response_text[max(0, parse_err.pos-50):parse_err.pos+50]}...")

                    # Try fixing common JSON issues: unescaped newlines/quotes in strings
                    logger.info("Attempting to fix JSON with unescaped newlines...")
                    try:
                        import re
                        # More sophisticated: replace newlines only within string values
                        # This regex finds strings and replaces newlines within them
                        def fix_string(match):
                            s = match.group(0)
                            # Escape unescaped newlines and carriage returns within the string
                            s = s.replace('\n', '\\n').replace('\r', '\\r')
                            return s

                        fixed_text = re.sub(r'"[^"]*"', fix_string, response_text, flags=re.DOTALL)
                        response_json = json.loads(fixed_text)
                        logger.info("Fixed JSON by escaping newlines in strings")
                    except json.JSONDecodeError as e2:
                        logger.error(f"Fix failed: {e2}")
                        raise parse_err

                logger.info(f"Parsed JSON successfully")
                return SparkTaskAction(**response_json)
        logger.warning("No response text from LLM or empty messages")
        return get_fallback_spark_reply()
    except (ValidationError, ValueError, RuntimeError) as exc:
        logger.exception("Spark returned an invalid response: %s", str(exc))
        return get_fallback_spark_reply()
    except Exception as exc:
        logger.exception("Spark request failed: %s", str(exc))
        return get_fallback_spark_reply()
