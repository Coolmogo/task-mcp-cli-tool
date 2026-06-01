"""FastAPI server exposing the TaskCLI class as a REST API.

Launch with: ``python -m task_api`` (serves on http://127.0.0.1:8000).
Interactive docs at /docs.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from task_program import TaskCLI, TaskCLIError
from task_program.models import DEFAULT_STATUS


app = FastAPI(title="task")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:8000",
        "https://flutter-task-beta.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_api_singleton: Optional[TaskCLI] = None


def _api() -> TaskCLI:
    global _api_singleton
    if _api_singleton is None:
        _api_singleton = TaskCLI()
    return _api_singleton


@app.exception_handler(TaskCLIError)
def _handle_taskcli_error(request: Request, exc: TaskCLIError) -> JSONResponse:
    """Translate execution-layer errors into HTTP responses. Lookups that miss
    become 404; everything else (validation) is 400. This is the API equivalent
    of the CLI's sys.exit and the MCP layer's "Error: ..." string."""
    status = 404 if "not found" in str(exc).lower() else 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


# ---- request models (write endpoints only) ---------------------------------


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = DEFAULT_STATUS
    assignee_id: Optional[str] = None
    stage_id: Optional[str] = None
    due: Optional[str] = None  # ISO YYYY-MM-DD


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[str] = None
    stage_id: Optional[str] = None
    due: Optional[str] = None  # ISO YYYY-MM-DD


class CommentCreate(BaseModel):
    text: str


class ProposalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = DEFAULT_STATUS
    stage_id: Optional[str] = None
    assignee_id: Optional[str] = None


# ---- task routes -----------------------------------------------------------


@app.post("/tasks", status_code=201)
def add_task(body: TaskCreate) -> dict:
    """Create a task. status is free text (default 'To Do'); due is ISO (YYYY-MM-DD)."""
    return _api().add_task(**body.model_dump())


@app.get("/tasks")
def list_tasks(status: Optional[str] = None, project: Optional[str] = None) -> list[dict]:
    """List tasks, optionally filtered by status and/or project."""
    return _api().list_tasks(status=status, project=project)


@app.get("/tasks/{id}")
def get_task(id: str) -> dict:
    """Fetch a single task with its embedded activity history and comments."""
    return _api().get_task(id)


@app.patch("/tasks/{id}")
def update_task(id: str, body: TaskUpdate) -> dict:
    """Update one or more fields. Only the fields present in the body change;
    each changed field is auto-recorded in the task's activity history."""
    return _api().update_task(id, **body.model_dump(exclude_unset=True))


@app.delete("/tasks/{id}")
def delete_task(id: str) -> dict:
    """Delete a task by id. Its activity history and comments are cascaded."""
    _api().delete_task(id)
    return {"detail": f"Deleted task #{id}"}


# ---- comment / activity routes ---------------------------------------------


@app.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: str, body: CommentCreate) -> dict:
    """Add a comment to a task."""
    return _api().add_comment(task_id, body.text)


@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: str) -> list[dict]:
    """List a task's comments, oldest first."""
    return _api().list_comments(task_id)


@app.get("/tasks/{task_id}/activities")
def list_activities(task_id: str) -> list[dict]:
    """List a task's activity feed (auto-recorded field changes plus comment and
    proposal wrapper entries), oldest first."""
    return _api().list_activities(task_id)


# ---- proposal routes -------------------------------------------------------
# A proposal is an AI agent's suggested task; accepting one spawns a real task.


@app.post("/tasks/{task_id}/proposals", status_code=201)
def add_proposal(task_id: str, body: ProposalCreate) -> dict:
    """Propose a task for an existing task. status is free text (default 'To Do')."""
    return _api().add_proposal(task_id, **body.model_dump())


@app.get("/tasks/{task_id}/proposals")
def list_proposals(task_id: str) -> list[dict]:
    """List a task's proposals, oldest first."""
    return _api().list_proposals(task_id)


@app.get("/proposals/{id}")
def get_proposal(id: str) -> dict:
    """Fetch a single proposal by id."""
    return _api().get_proposal(id)


@app.post("/proposals/{id}/accept")
def accept_proposal(id: str) -> dict:
    """Accept a proposal: create a real task from its fields and record the new
    task's id on the proposal (created_task_id). Returns the created task."""
    return _api().accept_proposal(id)


@app.delete("/proposals/{id}")
def delete_proposal(id: str) -> dict:
    """Delete a proposal by id. Its activity wrapper is removed too."""
    _api().delete_proposal(id)
    return {"detail": f"Deleted proposal #{id}"}


def main() -> None:
    import os

    import uvicorn

    # Hosting platforms (Render, etc.) inject $PORT and probe 0.0.0.0; bind there
    # when PORT is set. Locally (no PORT) keep the loopback-only default.
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    uvicorn.run("task_api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

