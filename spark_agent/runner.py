"""Entry point for a single Spark turn.

Launched fire-and-forget by whichever server detected a Spark trigger:

    python -m spark_agent <task_id> --trigger assignment
    python -m spark_agent <task_id> --trigger comment --comment-id <id> --text "..."

Flow: read task context via MCP → run the LLM → write Spark's reply back via MCP.
Nothing here touches ``task_program`` directly.
"""
from __future__ import annotations

import argparse
import logging

from .mcp_client import call_tool
from .schemas import TaskContext
from .service import _strip_markdown, generate_spark_reply
from .triggers import build_assignment_trigger, build_comment_trigger

logger = logging.getLogger(__name__)

_FALLBACK_MESSAGE = "I encountered an error processing your request. Please try again in a moment."


def _post_comment(task_id: str, text: str, verb: str, confidence: float | None = None) -> None:
    call_tool("post_spark_comment", task_id=task_id, text=text, verb=verb, confidence=confidence)


def _dispatch(task_id: str, reply) -> None:
    """Write Spark's reply back to the task via the spark-facing MCP tools."""
    if reply.action_type in ("ask", "instruct"):
        _post_comment(task_id, reply.message, verb=reply.action_type, confidence=reply.confidence)
    elif reply.action_type == "update":
        if reply.update_fields:
            call_tool("update_task", id=task_id, **reply.update_fields)
            logger.info("Spark updated task %s: %s", task_id, reply.update_fields)
        elif reply.message:
            # No fields to change (e.g. the fallback reply) — surface the message.
            _post_comment(task_id, reply.message, verb="instruct", confidence=reply.confidence)
    elif reply.action_type == "propose" and reply.proposal is not None:
        call_tool(
            "create_spark_proposal",
            task_id=task_id,
            title=_strip_markdown(reply.proposal.title),
            description=_strip_markdown(reply.proposal.description),
            assignee_id=reply.proposal.assignee_id,
            stage_id=reply.proposal.stage_id,
            message=reply.message,
            confidence=reply.confidence,
        )
    else:
        logger.warning("Unhandled Spark action_type=%s for task %s", reply.action_type, task_id)


def run(task_id: str, *, trigger_kind: str, comment_id: str | None, text: str | None) -> None:
    if trigger_kind == "comment":
        trigger = build_comment_trigger(task_id, comment_id, text or "")
    else:
        trigger = build_assignment_trigger(task_id)

    try:
        context_data = call_tool("get_task_context", task_id=task_id)
        if not isinstance(context_data, dict):
            logger.error("Could not fetch context for task %s: %r", task_id, context_data)
            _post_comment(task_id, _FALLBACK_MESSAGE, verb="instruct", confidence=0.0)
            return

        context = TaskContext(**context_data)
        reply = generate_spark_reply(context, trigger.prompt)
        logger.info(
            "Spark reply for task %s: action_type=%s, confidence=%.2f",
            task_id, reply.action_type, reply.confidence,
        )
        _dispatch(task_id, reply)
    except Exception as exc:  # noqa: BLE001 - last-resort: tell the user Spark tried
        logger.exception("Spark turn failed for task %s: %s", task_id, exc)
        try:
            _post_comment(task_id, _FALLBACK_MESSAGE, verb="instruct", confidence=0.0)
        except Exception as fallback_exc:  # noqa: BLE001
            logger.exception("Failed to post fallback for task %s: %s", task_id, fallback_exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="spark_agent", description="Run a single Spark turn on a task.")
    parser.add_argument("task_id", help="ID of the task Spark should act on")
    parser.add_argument("--trigger", choices=["assignment", "comment"], default="assignment")
    parser.add_argument("--comment-id", dest="comment_id", default=None)
    parser.add_argument("--text", default=None, help="Comment body that triggered Spark (comment trigger)")
    args = parser.parse_args()

    run(args.task_id, trigger_kind=args.trigger, comment_id=args.comment_id, text=args.text)


if __name__ == "__main__":
    main()
