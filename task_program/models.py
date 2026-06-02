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


class ActivityVerb(str, Enum):
    UPDATE = "update"
    ASK = "ask"
    INSTRUCT = "instruct"
    PROPOSE = "propose"
    DECIDE = "decide"
    DISMISS = "dismiss"


@dataclass
class User:
    """Minimal user record. Dead structure for now — no rows are created until
    user management is reincorporated."""

    id: Optional[str]
    name: str
    email: Optional[str] = None


@dataclass
class Activity:
    """Base activity class. Represents an action (verb) on a task.
    The audit log format is: (verb) → (to_actor) → (message)"""
    id: Optional[str]
    task_id: str
    verb: str           # what action (update/ask/instruct/propose)
    created_at: datetime
    from_actor: Optional[str] = None   # who initiated it
    to_actor: Optional[str] = None     # who it's directed at
    content: Optional[str] = None      # the message/text
    # Legacy fields for backward compat with old DB records
    author_id: Optional[str] = None
    author_type: Optional[str] = None
    legacy_author_name: Optional[str] = None
    metadata: Optional[dict] = None


@dataclass
class Update(Activity):
    """Field-change audit entry. Maps to type='update' verb."""
    action: Optional[str] = None       # updated / removed / assigned / moved
    field: Optional[str] = None        # dueDate, status, stageId, title, ...
    old_value: Optional[str] = None
    new_value: Optional[str] = None


@dataclass
class Ask(Activity):
    """Question directed at an actor. Maps to type='ask' verb.
    to_actor = who is being asked; content = the question."""
    pass


@dataclass
class Instruct(Activity):
    """Directive/instruction directed at an actor. Maps to type='instruct' verb.
    to_actor = who is being instructed; content = the instruction."""
    pass


@dataclass
class Proposal(Activity):
    """Proposed action pending approval. Maps to type='propose' verb."""
    proposal_status: Optional[str] = None
    proposal_title: Optional[str] = None
    proposal_description: Optional[str] = None
    proposal_assignee_id: Optional[str] = None
    proposal_stage_id: Optional[str] = None
    proposal_created_task_id: Optional[str] = None
    proposal_activity_id: Optional[str] = None


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


# ---- dead: reintroduce with projects later ---------------------------------


@dataclass
class Project:
    id: Optional[str]
    title: str
    description: str
    start_date: date
    end_date: date
    no_of_stages: int
