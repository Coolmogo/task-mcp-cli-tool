from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AddTaskCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class TaskCommentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    task_id: str
    author_type: Literal["user", "mogo", "system"]
    author_id: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


class AddTaskCommentResponse(BaseModel):
    success: bool
    user_comment: TaskCommentResponse
    spark_comment: TaskCommentResponse | None = None


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


class SparkTaskReply(BaseModel):
    response_type: Literal["answer", "summary", "suggestion", "clarification"]
    message: str
    confidence: float = Field(ge=0.0, le=1.0)
