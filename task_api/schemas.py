from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AddTaskCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class DecideProposalRequest(BaseModel):
    message: Optional[str] = Field(None, max_length=1000)


class TaskActivityResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    task_id: str
    type: str
    author_type: Optional[Literal["user", "mogo", "system"]] = None
    author_id: Optional[str] = None
    content: Optional[str] = None
    created_at: datetime
    metadata: dict[str, Any] | None = None
    proposal_status: Optional[str] = None
    proposal_title: Optional[str] = None
    proposal_description: Optional[str] = None
    proposal_assignee_id: Optional[str] = None
    proposal_stage_id: Optional[str] = None
    proposal_created_task_id: Optional[str] = None


class TaskCommentResponse(TaskActivityResponse):
    """Deprecated: use TaskActivityResponse instead."""
    pass


class AddTaskCommentResponse(BaseModel):
    success: bool
    user_comment: TaskActivityResponse
    spark_comments: list[TaskActivityResponse] = []


class ProposalResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    task_id: str
    proposal_status: Literal["pending", "accepted", "rejected"]
    proposal_title: str
    proposal_description: Optional[str] = None
    proposal_assignee_id: Optional[str] = None
    proposal_stage_id: Optional[str] = None
    proposal_created_task_id: Optional[str] = None
    created_at: datetime


class AcceptProposalResponse(BaseModel):
    proposal: ProposalResponse
    created_task: dict


class TaskContextComment(BaseModel):
    author_type: Literal["user", "mogo", "system"]
    author_name: str | None = None
    content: str
    created_at: datetime


class TaskActivityLogContext(BaseModel):
    event_type: str
    description: str | None = None
    created_at: datetime


class TaskContext(BaseModel):
    task_id: str
    title: str
    description: str | None = None
    status: Literal["todo", "in_progress", "blocked", "done"]
    priority: Literal["low", "medium", "high"]
    assignee_name: str | None = None
    comments: list[TaskContextComment]
    activity_logs: list[TaskActivityLogContext]


class SparkCreateTaskProposal(BaseModel):
    proposal_type: Literal["create_task"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    assignee_id: str | None = None
    stage_id: str | None = None


class SparkTaskAction(BaseModel):
    action_type: Literal["ask", "instruct", "update", "propose", "decide", "dismiss"]
    message: str
    confidence: float = Field(ge=0.0, le=1.0)
    proposal: SparkCreateTaskProposal | None = None
    # For update action: which fields to update
    update_fields: dict | None = None
