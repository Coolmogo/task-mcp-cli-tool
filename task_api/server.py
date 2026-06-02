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
from task_program.spark_service import generate_spark_reply
from task_program.settings import SparkSettings, get_settings

from .schemas import (
    AcceptProposalResponse,
    AddTaskCommentRequest,
    AddTaskCommentResponse,
    DecideProposalRequest,
    ProposalResponse,
    TaskActivityResponse,
    TaskCommentResponse,
    TaskContext,
)


app = FastAPI(title="task")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flutter-task-beta.vercel.app"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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


# ---- spark helpers ---------------------------------------------------------


def _post_spark_comment(task_id: str, content: str, verb: str = "instruct", metadata: dict | None = None) -> dict:
    """Post a Spark-authored comment to a task."""
    return _api().add_comment(
        task_id,
        content,
        verb=verb,
        author_type=SPARK_AUTHOR_TYPE,
        author_id=SPARK_AUTHOR_ID,
        to_actor="current_user",
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
        proposal.title,
        proposal.description,
        assignee_id=proposal.assignee_id,
        stage_id=proposal.stage_id,
        author_id=SPARK_AUTHOR_ID,
        author_type=SPARK_AUTHOR_TYPE,
        legacy_author_name=SPARK_USER_NAME,
        metadata={"spark_message": spark_reply.message, "spark_confidence": spark_reply.confidence},
    )


def _run_spark_sequence(task_id: str, trigger: SparkTrigger) -> list[dict]:
    """Run Spark orchestration: handle ask, instruct, update, propose, decide, dismiss."""
    spark_comments = []
    try:
        context_dict = _api().build_task_context(task_id)
        context = TaskContext(**context_dict)

        spark_reply = generate_spark_reply(context, trigger.prompt)
        logger.info("Spark reply for task %s: action_type=%s, confidence=%.2f", task_id, spark_reply.action_type, spark_reply.confidence)

        if spark_reply.action_type == "ask":
            comment = _post_spark_comment(task_id, spark_reply.message, verb="ask", metadata={"spark_confidence": spark_reply.confidence})
            spark_comments.append(comment)
        elif spark_reply.action_type == "instruct":
            comment = _post_spark_comment(task_id, spark_reply.message, verb="instruct", metadata={"spark_confidence": spark_reply.confidence})
            spark_comments.append(comment)
        elif spark_reply.action_type == "update":
            # Auto-update task fields based on Spark's analysis
            if spark_reply.update_fields:
                updated_task = _api().update_task(task_id, **spark_reply.update_fields)
                logger.info("Spark auto-updated task %s: %s", task_id, spark_reply.update_fields)
        elif spark_reply.action_type == "propose":
            proposal = _create_pending_proposal(task_id, spark_reply)
            spark_comments.append(proposal)
    except Exception as exc:
        logger.exception("Spark sequence failed for task %s: %s", task_id, exc)
        # Post a fallback message so user knows Spark tried but failed
        try:
            fallback_comment = _post_spark_comment(
                task_id,
                "I encountered an error processing your request. Please try again in a moment.",
                verb="instruct",
                metadata={"spark_confidence": 0.0, "spark_error": True}
            )
            spark_comments.append(fallback_comment)
        except Exception as fallback_exc:
            logger.exception("Failed to post fallback comment for task %s: %s", task_id, fallback_exc)

    return spark_comments


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
    created = _api().add_task(**body.model_dump())

    if is_spark_assignee(created.get("assignee_id")):
        _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)

    return created


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
    before = _api().get_task(id)
    updated = _api().update_task(id, **body.model_dump(exclude_unset=True))

    if not is_spark_assignee(before.get("assignee_id")) and is_spark_assignee(updated.get("assignee_id")):
        _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)

    return updated


@app.delete("/tasks/{id}")
def delete_task(id: str) -> dict:
    """Delete a task by id. Its activity history and comments are cascaded."""
    _api().delete_task(id)
    return {"detail": f"Deleted task #{id}"}


# ---- comment / activity routes ---------------------------------------------


def _to_task_activity_response(row: dict) -> TaskActivityResponse:
    row["content"] = row.get("text") or row.get("content")
    return TaskActivityResponse.model_validate(row)


def _to_task_comment_response(row: dict) -> TaskCommentResponse:
    """Deprecated: use _to_task_activity_response instead."""
    return _to_task_activity_response(row)


@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: str) -> list[TaskActivityResponse]:
    """List all comments (activities with ask/instruct/update verbs) on a task."""
    rows = _api().list_comments(task_id)
    return [_to_task_activity_response(row) for row in rows]


@app.post("/tasks/{task_id}/comments", status_code=201, response_model=AddTaskCommentResponse)
def add_comment(task_id: str, body: AddTaskCommentRequest) -> AddTaskCommentResponse:
    """Add a comment to a task."""
    user_comment_row = _api().add_comment(
        task_id,
        body.content,
        verb="ask",
        author_type="user",
        author_id="current_user",
    )
    user_comment = _to_task_activity_response(user_comment_row)

    spark_comments_rows = []
    task = _api().get_task(task_id)
    if is_spark_assignee(task.get("assignee_id")):
        _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
        spark_comments_rows = _run_spark_sequence(task_id, build_comment_trigger(task_id, user_comment_row["id"], body.content))

    spark_comments = [_to_task_activity_response(row) for row in spark_comments_rows]
    return AddTaskCommentResponse(success=True, user_comment=user_comment, spark_comments=spark_comments)


@app.get("/tasks/{task_id}/activities")
def list_activities(task_id: str) -> list[dict]:
    """List all activity on a task (field changes, comments, proposals), oldest first."""
    return _api().list_activities(task_id)


@app.get("/activities/{activity_id}", response_model=TaskActivityResponse)
def get_activity(activity_id: str) -> TaskActivityResponse:
    """Fetch a single activity by its ID."""
    return _to_task_activity_response(_api().get_activity(activity_id))


# ---- proposal routes -------------------------------------------------------


@app.get("/proposals/{activity_id}", response_model=ProposalResponse)
def get_proposal(activity_id: str) -> ProposalResponse:
    """Fetch a proposal activity by its ID."""
    activity = _api().get_proposal(activity_id)
    return ProposalResponse.model_validate({
        "id": activity["id"],
        "task_id": activity["task_id"],
        "proposal_status": activity.get("proposal_status"),
        "proposal_title": activity.get("proposal_title"),
        "proposal_description": activity.get("proposal_description"),
        "proposal_assignee_id": activity.get("proposal_assignee_id"),
        "proposal_stage_id": activity.get("proposal_stage_id"),
        "proposal_created_task_id": activity.get("proposal_created_task_id"),
        "created_at": activity.get("created_at"),
    })


@app.post("/proposals/{activity_id}/accept", response_model=AcceptProposalResponse)
def accept_proposal(activity_id: str, request: DecideProposalRequest) -> AcceptProposalResponse:
    """Accept a proposal: creates the task and marks the proposal accepted."""
    result = _api().accept_proposal(activity_id, message=request.message)
    return AcceptProposalResponse(
        proposal=ProposalResponse.model_validate({
            "id": result["id"],
            "task_id": result["task_id"],
            "proposal_status": result.get("proposal_status"),
            "proposal_title": result.get("proposal_title"),
            "proposal_description": result.get("proposal_description"),
            "proposal_assignee_id": result.get("proposal_assignee_id"),
            "proposal_stage_id": result.get("proposal_stage_id"),
            "proposal_created_task_id": result.get("proposal_created_task_id"),
            "created_at": result.get("created_at"),
        }),
        created_task=result["created_task"],
    )


@app.post("/proposals/{activity_id}/reject", response_model=ProposalResponse)
def reject_proposal(activity_id: str, request: DecideProposalRequest) -> ProposalResponse:
    """Reject a proposal without creating a task."""
    result = _api().reject_proposal(activity_id, message=request.message)
    return ProposalResponse.model_validate({
        "id": result["id"],
        "task_id": result["task_id"],
        "proposal_status": result.get("proposal_status"),
        "proposal_title": result.get("proposal_title"),
        "proposal_description": result.get("proposal_description"),
        "proposal_assignee_id": result.get("proposal_assignee_id"),
        "proposal_stage_id": result.get("proposal_stage_id"),
        "proposal_created_task_id": result.get("proposal_created_task_id"),
        "created_at": result.get("created_at"),
    })


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

