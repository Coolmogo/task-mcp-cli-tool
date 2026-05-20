from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class Status(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass
class Project:
    id: Optional[int]
    title: str
    description: str
    start_date: date
    end_date: date
    no_of_stages: int


@dataclass
class Task:
    id: Optional[int]
    project_id: int
    title: str
    description: str
    status: Status
    assigned_to: str
    stage: int
    start_date: date
    end_date: date
