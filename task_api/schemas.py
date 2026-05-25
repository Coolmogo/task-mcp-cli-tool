from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from task_program.models import Status


class HealthResponse(BaseModel):
    status: str


class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str
    start_date: date
    end_date: date
    no_of_stages: int

    model_config = ConfigDict(from_attributes=True)


class ProjectCreateRequest(BaseModel):
    title: str
    description: str = ""
    start_date: date
    end_date: date
    no_of_stages: int


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    no_of_stages: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    status: Status
    assigned_to: str
    stage: int
    start_date: date
    end_date: date

    model_config = ConfigDict(from_attributes=True)


class TaskCreateRequest(BaseModel):
    project_id: int
    title: str
    description: str = ""
    status: Status = Status.TODO
    assigned_to: str = ""
    stage: int
    start_date: date
    end_date: date


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Status] = None
    assigned_to: Optional[str] = None
    stage: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
