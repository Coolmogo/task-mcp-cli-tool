"""FastAPI server exposing the TaskCLI class as a REST API.

Launch with: ``python -m task_api`` (serves on http://127.0.0.1:8000).
Interactive docs at /docs.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from task_program import TaskCLI, TaskCLIError
from task_program.models import DEFAULT_STATUS

from .spark_agent import (
    SPARK_AUTHOR_ID,
    SPARK_AUTHOR_TYPE,
    SPARK_USER_ID,
    SPARK_USER_NAME,
    SparkTrigger,
    build_assignment_trigger,
    build_comment_trigger,
    is_spark_assignee,
)
from .schemas import (
    AddTaskCommentRequest,
    AddTaskCommentResponse,
    TaskCommentResponse,
    TaskContext,
)
from .spark_service import generate_spark_reply


app = FastAPI(title="task")
logger = logging.getLogger(__name__)

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
    before = _api().get_task_by_id(id)
    updated = _api().update_task(id, **body.model_dump(exclude_unset=True))
    spark_comment: TaskCommentResponse | None = None
    if not is_spark_assignee(before.get("assignee_id")) and is_spark_assignee(updated.get("assignee_id")):
        spark_comment = _maybe_generate_spark_comment(id, build_assignment_trigger(id))
    return {
        **updated,
        "spark_comment": spark_comment.model_dump(mode="json") if spark_comment else None,
    }


@app.delete("/tasks/{id}")
def delete_task(id: str) -> dict:
    """Delete a task by id. Its activity history and comments are cascaded."""
    _api().delete_task(id)
    return {"detail": f"Deleted task #{id}"}


# ---- comment / activity routes ---------------------------------------------


def _to_task_comment_response(row: dict) -> TaskCommentResponse:
    return TaskCommentResponse.model_validate(row)


def _maybe_generate_spark_comment(task_id: str, trigger: SparkTrigger) -> TaskCommentResponse | None:
    try:
        _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
        context = TaskContext.model_validate(_api().build_task_context(task_id))
        if not is_spark_assignee(_api().get_task_by_id(task_id).get("assignee_id")):
            return None

        spark_reply = generate_spark_reply(context, trigger.prompt)
        if spark_reply.confidence <= 0.0:
            logger.warning("Spark returned fallback reply for task %s", task_id)
            return None

        row = _api().create_comment(
            task_id,
            spark_reply.message,
            author_type=SPARK_AUTHOR_TYPE,
            author_id=SPARK_AUTHOR_ID,
            metadata={
                **trigger.metadata,
                "response_type": spark_reply.response_type,
                "confidence": spark_reply.confidence,
            },
            legacy_author_name=SPARK_USER_NAME,
        )
        return _to_task_comment_response(row)
    except Exception:
        logger.exception("Spark failed for task %s", task_id)
        return None


@app.post("/tasks/{task_id}/comments", status_code=201, response_model=AddTaskCommentResponse)
def add_comment(task_id: str, body: AddTaskCommentRequest) -> AddTaskCommentResponse:
    """Add a comment to a task and optionally trigger Spark when assigned."""
    user_comment = _to_task_comment_response(
        _api().create_comment(
            task_id,
            body.content,
            author_type="user",
            author_id="current_user",
        )
    )

    spark_comment: TaskCommentResponse | None = None
    task = _api().get_task_by_id(task_id)
    if is_spark_assignee(task.get("assignee_id")):
        spark_comment = _maybe_generate_spark_comment(
            task_id,
            build_comment_trigger(task_id, user_comment.id, body.content),
        )
    return AddTaskCommentResponse(success=True, user_comment=user_comment, spark_comment=spark_comment)


@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: str) -> list[dict]:
    """List a task's comments, oldest first."""
    return _api().list_comments(task_id)


@app.get("/tasks/{task_id}/activities")
def list_activities(task_id: str) -> list[dict]:
    """List a task's activity history (auto-recorded field changes), oldest first."""
    return _api().list_activities(task_id)


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

