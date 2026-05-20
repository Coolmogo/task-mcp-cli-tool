"""MCP server exposing the TaskCLI class as tools for Claude Desktop.

Launch with: ``python -m task_mcp``
"""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from task_program import TaskCLI, TaskCLIError


StatusLiteral = Literal["todo", "in_progress", "done"]


mcp = FastMCP("task")

_api_singleton: Optional[TaskCLI] = None


def _api() -> TaskCLI:
    global _api_singleton
    if _api_singleton is None:
        _api_singleton = TaskCLI()
    return _api_singleton


# ---- project tools ---------------------------------------------------------


@mcp.tool()
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


@mcp.tool()
def list_projects() -> list[dict] | str:
    """List every project."""
    try:
        return _api().list_projects()
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def get_project(id: int) -> dict | str:
    """Fetch a single project by id."""
    try:
        return _api().get_project(id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def update_project(
    id: int,
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


@mcp.tool()
def delete_project(id: int) -> str:
    """Delete a project. All its tasks are cascaded."""
    try:
        _api().delete_project(id)
        return f"Deleted project #{id} (and its tasks)"
    except TaskCLIError as e:
        return f"Error: {e}"


# ---- task tools ------------------------------------------------------------


@mcp.tool()
def add_task(
    project: int,
    title: str,
    description: str,
    status: StatusLiteral,
    assigned_to: str,
    stage: int,
    start: str,
    end: str,
) -> dict | str:
    """Create a task inside a project. stage must be 1..project.no_of_stages. Dates are ISO (YYYY-MM-DD)."""
    try:
        return _api().add_task(
            project=project,
            title=title,
            description=description,
            status=status,
            assigned_to=assigned_to,
            stage=stage,
            start=start,
            end=end,
        )
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def list_tasks(
    project: Optional[int] = None,
    status: Optional[StatusLiteral] = None,
) -> list[dict] | str:
    """List tasks. Optionally filter by project id and/or status."""
    try:
        return _api().list_tasks(project=project, status=status)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def get_task(id: int) -> dict | str:
    """Fetch a single task by id."""
    try:
        return _api().get_task(id)
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def update_task(
    id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[StatusLiteral] = None,
    assigned_to: Optional[str] = None,
    stage: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict | str:
    """Update one or more fields on a task. Pass only the fields you want to change."""
    try:
        return _api().update_task(
            id,
            title=title,
            description=description,
            status=status,
            assigned_to=assigned_to,
            stage=stage,
            start=start,
            end=end,
        )
    except TaskCLIError as e:
        return f"Error: {e}"


@mcp.tool()
def delete_task(id: int) -> str:
    """Delete a task by id."""
    try:
        _api().delete_task(id)
        return f"Deleted task #{id}"
    except TaskCLIError as e:
        return f"Error: {e}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
