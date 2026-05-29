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
    AcceptProposalResponse,
    AddTaskCommentRequest,
    AddTaskCommentResponse,
    ProposalResponse,
    TaskCommentResponse,
    TaskContext,
)
from .spark_service import generate_spark_reply


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
    spark_comments: list[TaskCommentResponse] = []
    if is_spark_assignee(created.get("assignee_id")):
        spark_comments = _run_spark_sequence(created["id"], build_assignment_trigger(created["id"]))
    return {**created, "spark_comments": [c.model_dump(mode="json") for c in spark_comments]}


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
    spark_comments: list[TaskCommentResponse] = []
    if not is_spark_assignee(before.get("assignee_id")) and is_spark_assignee(updated.get("assignee_id")):
        spark_comments = _run_spark_sequence(id, build_assignment_trigger(id))
    return {
        **updated,
        "spark_comments": [c.model_dump(mode="json") for c in spark_comments],
    }


@app.delete("/tasks/{id}")
def delete_task(id: str) -> dict:
    """Delete a task by id. Its activity history and comments are cascaded."""
    _api().delete_task(id)
    return {"detail": f"Deleted task #{id}"}


# ---- comment / activity routes ---------------------------------------------


def _to_task_comment_response(row: dict) -> TaskCommentResponse:
    return TaskCommentResponse.model_validate(row)


def _normalize_proposed_assignee_id(assignee_id: str | None) -> str | None:
    if not assignee_id:
        return None
    if ":" not in assignee_id:
        return None
    return assignee_id


def _create_pending_proposal(task_id: str, spark_reply) -> dict:
    proposal = spark_reply.proposal
    if proposal is None or proposal.proposal_type != "create_task":
        raise ValueError("Unsupported Spark proposal")
    return _api().create_proposal(
        task_id,
        proposal.title,
        proposal.description,
        assignee_id=_normalize_proposed_assignee_id(proposal.assignee_id),
        stage_id=proposal.stage_id,
    )


def _post_spark_comment(task_id: str, content: str, metadata: dict | None = None) -> TaskCommentResponse:
    row = _api().create_comment(
        task_id,
        content,
        author_type=SPARK_AUTHOR_TYPE,
        author_id=SPARK_AUTHOR_ID,
        metadata=metadata,
        legacy_author_name=SPARK_USER_NAME,
    )
    return _to_task_comment_response(row)


def _run_spark_sequence(task_id: str, trigger: SparkTrigger) -> list[TaskCommentResponse]:
    try:
        _api().ensure_user(SPARK_USER_ID, name=SPARK_USER_NAME)
        context = TaskContext.model_validate(_api().build_task_context(task_id))
        if not is_spark_assignee(_api().get_task_by_id(task_id).get("assignee_id")):
            return []

        logger.info("Generating Spark reply for task %s with trigger: %s", task_id, trigger.kind)
        spark_reply = generate_spark_reply(context, trigger.prompt)
        logger.info(
            "Spark reply generated: action_type=%s, confidence=%s, message=%s...",
            spark_reply.action_type,
            spark_reply.confidence,
            spark_reply.message[:50] if spark_reply.message else "N/A"
        )
        if spark_reply.confidence <= 0.0:
            logger.warning("Spark returned fallback reply for task %s", task_id)
            fallback_comment = _post_spark_comment(
                task_id,
                "I need more context to respond effectively. Can you clarify what you're asking?",
                metadata={**trigger.metadata, "action_type": "update", "confidence": 0.0},
            )
            return [fallback_comment]

        base_metadata = {
            **trigger.metadata,
            "action_type": spark_reply.action_type,
            "confidence": spark_reply.confidence,
        }

        if spark_reply.action_type == "propose":
            # Step 1: acknowledge
            ack = _post_spark_comment(
                task_id,
                "On it — researching now and will create an implementation task.",
                metadata={**base_metadata, "action_type": "update"},
            )

            # Step 2: create proposal + post the proposal comment
            pending = _create_pending_proposal(task_id, spark_reply)
            proposal_metadata = {
                **base_metadata,
                "proposal_type": spark_reply.proposal.proposal_type if spark_reply.proposal else None,
                "proposal_id": pending["id"],
            }
            proposal_comment = _post_spark_comment(task_id, spark_reply.message, metadata=proposal_metadata)

            # Step 3: confirm
            confirm = _post_spark_comment(
                task_id,
                f"Done — I've created \"{pending['title']}\" with full implementation details. Accept the proposal above to add it to the board.",
                metadata={**base_metadata, "action_type": "update"},
            )

            return [ack, proposal_comment, confirm]

        # Single update comment
        update_comment = _post_spark_comment(task_id, spark_reply.message, metadata=base_metadata)
        return [update_comment]

    except Exception as exc:
        logger.exception("Spark failed for task %s: %s", task_id, str(exc))
        fallback_comment = _post_spark_comment(
            task_id,
            f"I ran into an issue: {str(exc)[:100]}. Please check the logs.",
            metadata={**trigger.metadata, "error": True, "action_type": "update", "error_detail": str(exc)},
        )
        return [fallback_comment]


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

    spark_comments: list[TaskCommentResponse] = []
    task = _api().get_task_by_id(task_id)
    if is_spark_assignee(task.get("assignee_id")):
        spark_comments = _run_spark_sequence(
            task_id,
            build_comment_trigger(task_id, user_comment.id, body.content),
        )
    return AddTaskCommentResponse(success=True, user_comment=user_comment, spark_comments=spark_comments)


@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: str) -> list[dict]:
    """List a task's comments, oldest first."""
    return _api().list_comments(task_id)


@app.get("/tasks/{task_id}/activities")
def list_activities(task_id: str) -> list[dict]:
    """List a task's activity history (auto-recorded field changes), oldest first."""
    return _api().list_activities(task_id)


# ---- proposal routes -------------------------------------------------------


@app.get("/proposals/{proposal_id}", response_model=ProposalResponse)
def get_proposal(proposal_id: str) -> ProposalResponse:
    """Fetch a pending or resolved proposal by id."""
    return ProposalResponse.model_validate(_api().get_proposal(proposal_id))


@app.post("/proposals/{proposal_id}/accept", response_model=AcceptProposalResponse)
def accept_proposal(proposal_id: str) -> AcceptProposalResponse:
    """Accept a pending proposal: creates the task and marks the proposal accepted."""
    result = _api().accept_proposal(proposal_id)
    return AcceptProposalResponse(
        proposal=ProposalResponse.model_validate(result),
        created_task=result["created_task"],
    )


@app.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
def reject_proposal(proposal_id: str) -> ProposalResponse:
    """Reject a pending proposal without creating a task."""
    return ProposalResponse.model_validate(_api().reject_proposal(proposal_id))


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

