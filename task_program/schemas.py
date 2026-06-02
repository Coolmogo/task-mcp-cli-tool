from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


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
