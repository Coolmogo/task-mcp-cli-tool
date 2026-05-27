from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# Free-text status now (no Postgres enum). These are the suggested values and
# DEFAULT_STATUS seeds new tasks; any string is accepted.
DEFAULT_STATUS = "To Do"


class Status(str, Enum):
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class ActivityType(str, Enum):
    COMMENT = "comment"
    HISTORY = "history"


class ActivityAction(str, Enum):
    COMMENTED = "commented"
    UPDATED = "updated"
    REMOVED = "removed"
    ASSIGNED = "assigned"
    MOVED = "moved"


@dataclass
class User:
    """Minimal user record. Dead structure for now — no rows are created until
    user management is reincorporated."""

    id: Optional[str]
    name: str
    email: Optional[str] = None


@dataclass
class ActivityLog:
    id: Optional[str]
    task_id: str
    type: ActivityType
    action: ActivityAction
    timestamp: datetime
    text: Optional[str] = None
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    author_id: Optional[str] = None
    legacy_author_name: Optional[str] = None


@dataclass
class Comment:
    id: Optional[str]
    task_id: str
    text: str
    created_at: datetime
    author_id: Optional[str] = None
    legacy_author_name: Optional[str] = None


@dataclass
class Task:
    # SurrealDB record ids are strings, e.g. "task:8f3k" (not auto-increment ints).
    id: Optional[str]
    title: str
    status: str = DEFAULT_STATUS
    description: Optional[str] = None
    due_date: Optional[date] = None
    assignee_id: Optional[str] = None
    project_id: Optional[str] = None
    stage_id: Optional[str] = None
    activities: list = field(default_factory=list)
    comments: list = field(default_factory=list)


# ---- dead: reintroduce with projects later ---------------------------------


@dataclass
class Project:
    id: Optional[str]
    title: str
    description: str
    start_date: date
    end_date: date
    no_of_stages: int
