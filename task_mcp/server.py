"""MCP server exposing the TaskCLI class as tools for Claude Desktop.

Launch with: ``python -m task_mcp``
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from task_program import TaskCLI, TaskCLIError
from task_program.models import DEFAULT_STATUS
from task_program.schemas import TaskContext
from task_program.spark_agent import (
    SPARK_AUTHOR_ID,
    SPARK_AUTHOR_TYPE,
    SPARK_USER_ID,
    SPARK_USER_NAME,
    SparkTrigger,
    build_assignment_trigger,
    build_comment_trigger,
    is_spark_assignee,
)
from task_program.spark_service import generate_spark_reply, _strip_markdown


logger = logging.getLogger(__name__)


mcp = FastMCP("task")

_api_singleton: Optional[TaskCLI] = None


def _api() -> TaskCLI:
    global _api_singleton
    if _api_singleton is None:
        _api_singleton = TaskCLI()
    return _api_singleton


# ---- spark helpers ---------------------------------------------------------


def _post_spark_comment(task_id: str, content: str, verb: str = "instruct", metadata: dict | None = None) -> dict:
    """Post a Spark-authored comment to a task."""
    return _api().add_comment(
        task_id,
        content,
        verb=verb,
        author_type=SPARK_AUTHOR_TYPE,
        author_id=SPARK_AUTHOR_ID,
        metadata=metadata,
        legacy_author_name=SPARK_USER_NAME,
    )


def _create_pending_proposal(task_id: str, spark_reply) -> dict:
    """Create a proposal from a Spark reply."""
    proposal = spark_reply.proposal
    if proposal is None or proposal.proposal_type != "create_task":
        raise ValueError("Invalid Spark proposal")

    return _api().create_proposal(
        task_id,
        _strip_markdown(proposal.title),
        _strip_markdown(proposal.description),
        assignee_id=proposal.assignee_id,
        stage_id=proposal.stage_id,
        author_id=SPARK_AUTHOR_ID,
        author_type=SPARK_AUTHOR_TYPE,
        legacy_author_name=SPARK_USER_NAME,
        metadata={"spark_message": spark_reply.message, "spark_confidence": spark_reply.confidence},
    )


def _run_spark_sequence(task_id: str, trigger: SparkTrigger) -> None:
    """Run Spark orchestration: get reply, handle update vs propose."""
    try:
        context_dict = _api().build_task_context(task_id)
        context = TaskContext(**context_dict)

        spark_reply = generate_spark_reply(context, trigger.prompt)
        logger.info("Spark reply for task %s: action_type=%s, confidence=%.2f", task_id, spark_reply.action_type, spark_reply.confidence)

        if spark_reply.action_type == "update":
            _post_spark_comment(task_id, spark_reply.message, verb="instruct", metadata={"spark_confidence": spark_reply.confidence})
        elif spark_reply.action_type == "propose":
            _create_pending_proposal(task_id, spark_reply)
    except Exception as exc:
        logger.exception("Spark sequence failed for task %s: %s", task_id, exc)


# ---- task tools ------------------------------------------------------------


@mcp.tool()
def add_task(
    title: str,
    description: Optional[str] = None,
    status: str = DEFAULT_STATUS,
    assignee_id: Optional[str] = None,
    stage_id: Optional[str] = None,
    due: Optional[str] = None,
) -> dict | str:
    """Create a task. status is free text (default 'To Do'). due is ISO (YYYY-MM-DD).
    assignee_id references a user (user management is not wired up yet, leave null)."""
    try:
        created = _api().add_task(
            title=title,
            description=description,
            status=status,
            assignee_id=assignee_id,
            stage_id=stage_id,
            due=due,
        )

        if is_spark_assignee(created.get("assignee_id")):
            _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
            _run_spark_sequence(created["id"], build_assignment_trigger(created["id"]))

        return created
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def list_tasks(status: Optional[str] = None) -> list[dict] | str:
    """List tasks. Optionally filter by status."""
    try:
        return _api().list_tasks(status=status)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def get_task(id: str) -> dict | str:
    """Fetch a single task by id, with its unified activity feed."""
    try:
        return _api().get_task(id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def update_task(
    id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    stage_id: Optional[str] = None,
    due: Optional[str] = None,
) -> dict | str:
    """Update one or more fields on a task. Pass only the fields you want to change.
    Each changed field is recorded automatically in the task's activity history."""
    try:
        before = _api().get_task(id)
        updated = _api().update_task(
            id,
            title=title,
            description=description,
            status=status,
            assignee_id=assignee_id,
            stage_id=stage_id,
            due=due,
        )

        if not is_spark_assignee(before.get("assignee_id")) and is_spark_assignee(updated.get("assignee_id")):
            _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
            _run_spark_sequence(id, build_assignment_trigger(id))

        return updated
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def delete_task(id: str) -> str:
    """Delete a task by id. Its activity feed is cascaded."""
    try:
        _api().delete_task(id)
        return f"Deleted task #{id}"
    except TaskCLIError as e:
        return f"Error: {e}"


# ---- activity / comment tools -----------------------------------------------


@mcp.tool()
def add_comment(task_id: str, text: str) -> dict | str:
    """Add a human comment (ask) to a task."""
    try:
        row = _api().add_comment(task_id, text, verb="ask")
        task = _api().get_task(task_id)

        if is_spark_assignee(task.get("assignee_id")):
            _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
            _run_spark_sequence(task_id, build_comment_trigger(task_id, row["id"], text))

        return row
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def add_instruction(task_id: str, text: str) -> dict | str:
    """Post an instruction to a task (directive to Spark)."""
    try:
        row = _api().add_comment(task_id, text, verb="instruct")
        task = _api().get_task(task_id)

        if is_spark_assignee(task.get("assignee_id")):
            _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
            _run_spark_sequence(task_id, build_comment_trigger(task_id, row["id"], text))

        return row
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def list_activities(task_id: str) -> list[dict] | str:
    """List all activity on a task (field changes, comments, proposals), oldest first."""
    try:
        return _api().list_activities(task_id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def get_proposal(activity_id: str) -> dict | str:
    """Fetch a proposal activity by its ID."""
    try:
        return _api().get_proposal(activity_id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def accept_proposal(activity_id: str, message: Optional[str] = None) -> dict | str:
    """Accept a proposal and create the task."""
    try:
        return _api().accept_proposal(activity_id, message=message)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def decide(activity_id: str, message: Optional[str] = None) -> dict | str:
    """Accept a proposal and create the task (human-approved decide verb)."""
    try:
        return _api().accept_proposal(activity_id, message=message)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def reject_proposal(activity_id: str, message: Optional[str] = None) -> dict | str:
    """Reject a proposal with no action."""
    try:
        return _api().reject_proposal(activity_id, message=message)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def dismiss(activity_id: str, message: Optional[str] = None) -> dict | str:
    """Reject a proposal (human-rejected dismiss verb)."""
    try:
        return _api().reject_proposal(activity_id, message=message)
    except TaskCLIError as e:
        return f"Error: {e}"


# ---- project tools (dead: reintroduce later) -------------------------------
# Projects are shelved. The functions are kept but their @mcp.tool() decorators
# are commented out so they are NOT exposed to Claude Desktop. Re-add the
# decorators to bring projects back.


# @mcp.tool()
def add_project(
    title: str,
    description: str,
    start: str,
    end: str,
    stages: int,
) -> dict | str:
    """Create a new project. Dates are ISO format (YYYY-MM-DD). stages is the number of phases (>= 1)."""
    try:
        return _api().add_project(
            title=title,
            description=description,
            start=start,
            end=end,
            stages=stages,
        )
    except TaskCLIError as e:
        return f"Error: {e}"


# @mcp.tool()
def list_projects() -> list[dict] | str:
    """List every project."""
    try:
        return _api().list_projects()
    except TaskCLIError as e:
        return f"Error: {e}"


# @mcp.tool()
def get_project(id: str) -> dict | str:
    """Fetch a single project by id."""
    try:
        return _api().get_project(id)
    except TaskCLIError as e:
        return f"Error: {e}"


# @mcp.tool()
def update_project(
    id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    stages: Optional[int] = None,
) -> dict | str:
    """Update one or more fields on a project. Pass only the fields you want to change."""
    try:
        return _api().update_project(
            id,
            title=title,
            description=description,
            start=start,
            end=end,
            stages=stages,
        )
    except TaskCLIError as e:
        return f"Error: {e}"


# @mcp.tool()
def delete_project(id: str) -> str:
    """Delete a project. All its tasks are cascaded."""
    try:
        _api().delete_project(id)
        return f"Deleted project #{id} (and its tasks)"
    except TaskCLIError as e:
        return f"Error: {e}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
