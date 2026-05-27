"""MCP server exposing the TaskCLI class as tools for Claude Desktop.

Launch with: ``python -m task_mcp``
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from task_program import TaskCLI, TaskCLIError
from task_program.models import DEFAULT_STATUS


mcp = FastMCP("task")

_api_singleton: Optional[TaskCLI] = None


def _api() -> TaskCLI:
    global _api_singleton
    if _api_singleton is None:
        _api_singleton = TaskCLI()
    return _api_singleton


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
        return _api().add_task(
            title=title,
            description=description,
            status=status,
            assignee_id=assignee_id,
            stage_id=stage_id,
            due=due,
        )
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
    """Fetch a single task by id, with its embedded activity history and comments."""
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
        return _api().update_task(
            id,
            title=title,
            description=description,
            status=status,
            assignee_id=assignee_id,
            stage_id=stage_id,
            due=due,
        )
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def delete_task(id: str) -> str:
    """Delete a task by id. Its activity history and comments are cascaded."""
    try:
        _api().delete_task(id)
        return f"Deleted task #{id}"
    except TaskCLIError as e:
        return f"Error: {e}"


# ---- comment / activity tools ----------------------------------------------


@mcp.tool()
def add_comment(task_id: str, text: str) -> dict | str:
    """Add a comment to a task."""
    try:
        return _api().add_comment(task_id, text)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def list_comments(task_id: str) -> list[dict] | str:
    """List a task's comments, oldest first."""
    try:
        return _api().list_comments(task_id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def list_activities(task_id: str) -> list[dict] | str:
    """List a task's activity history (auto-recorded field changes), oldest first."""
    try:
        return _api().list_activities(task_id)
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
