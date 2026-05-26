from __future__ import annotations

from datetime import date
from typing import Optional, Union

from supabase import create_client, Client

from .db import client as _default_client
from .models import DEFAULT_STATUS


DateLike = Union[date, str]


class TaskCLIError(Exception):
    """Raised by TaskCLI methods on validation or lookup failures."""


def _to_date(value: DateLike) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _validate_dates(start: date, end: date) -> None:
    if end < start:
        raise TaskCLIError("end date must be on or after start date")


# Maps a task column to the (Dart camelCase) activity field name and the action
# used when that column changes. A change to None becomes a "removed" action.
_ACTIVITY_FIELDS: dict[str, tuple[str, str]] = {
    "title": ("title", "updated"),
    "description": ("description", "updated"),
    "due_date": ("dueDate", "updated"),
    "assignee_id": ("assignee", "assigned"),
    "status": ("status", "moved"),
    "stage_id": ("stageId", "moved"),
}


class TaskCLI:
    """Programmatic API for taskcli. Methods return raw row dicts and raise
    TaskCLIError on validation or lookup failures."""

    PROJECTS = "projects"
    TASKS = "tasks"
    ACTIVITIES = "activities"
    COMMENTS = "comments"

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        if supabase_url and supabase_key:
            self._client: Client = create_client(supabase_url, supabase_key)
        else:
            self._client = _default_client()

    # ---- internal helpers ---------------------------------------------------

    def _get_task_row(self, task_id: int) -> dict:
        res = self._client.table(self.TASKS).select("*").eq("id", task_id).execute()
        if not res.data:
            raise TaskCLIError(f"Task #{task_id} not found")
        return res.data[0]

    @staticmethod
    def _stringify(value) -> Optional[str]:
        """Render an activity old/new value as text (ISO for dates, str otherwise)."""
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def _log_activity(self, task_id: int, column: str, old, new) -> None:
        field, action = _ACTIVITY_FIELDS[column]
        if new is None and old is not None:
            action = "removed"
        payload = {
            "task_id": task_id,
            "type": "history",
            "action": action,
            "field": field,
            "old_value": self._stringify(old),
            "new_value": self._stringify(new),
            "author_id": None,
            "legacy_author_name": None,
        }
        self._client.table(self.ACTIVITIES).insert(payload).execute()

    # ---- tasks --------------------------------------------------------------

    def add_task(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        status: str = DEFAULT_STATUS,
        assignee_id: Optional[int] = None,
        stage_id: Optional[str] = None,
        due: Optional[DateLike] = None,
        project: Optional[int] = None,
    ) -> dict:
        payload = {
            "title": title,
            "description": description,
            "status": status,
            "assignee_id": assignee_id,
            "stage_id": stage_id,
            "due_date": _to_date(due).isoformat() if due is not None else None,
            "project_id": project,
        }
        res = self._client.table(self.TASKS).insert(payload).execute()
        return res.data[0]

    def list_tasks(
        self,
        status: Optional[str] = None,
        project: Optional[int] = None,
    ) -> list[dict]:
        q = self._client.table(self.TASKS).select("*")
        if status is not None:
            q = q.eq("status", status)
        if project is not None:
            q = q.eq("project_id", project)
        res = q.order("id").execute()
        return res.data or []

    def get_task(self, id: int) -> dict:
        """Fetch a task with its embedded activity feed and comments."""
        row = self._get_task_row(id)
        row["activities"] = self.list_activities(id)
        row["comments"] = self.list_comments(id)
        return row

    def update_task(
        self,
        id: int,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assignee_id: Optional[int] = None,
        stage_id: Optional[str] = None,
        due: Optional[DateLike] = None,
    ) -> dict:
        current = self._get_task_row(id)

        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if assignee_id is not None:
            payload["assignee_id"] = assignee_id
        if stage_id is not None:
            payload["stage_id"] = stage_id
        if due is not None:
            payload["due_date"] = _to_date(due).isoformat()

        if not payload:
            raise TaskCLIError("Nothing to update. Provide at least one field.")

        # Record one history entry per field that actually changed.
        for column, new in payload.items():
            old = current.get(column)
            if old != new:
                self._log_activity(id, column, old, new)

        res = self._client.table(self.TASKS).update(payload).eq("id", id).execute()
        return res.data[0] if res.data else {**current, **payload}

    def delete_task(self, id: int) -> None:
        self._get_task_row(id)
        self._client.table(self.TASKS).delete().eq("id", id).execute()

    # ---- comments -----------------------------------------------------------

    def add_comment(self, task_id: int, text: str) -> dict:
        self._get_task_row(task_id)  # validate the task exists
        payload = {
            "task_id": task_id,
            "text": text,
            "author_id": None,
            "legacy_author_name": None,
        }
        res = self._client.table(self.COMMENTS).insert(payload).execute()
        return res.data[0]

    def list_comments(self, task_id: int) -> list[dict]:
        res = (
            self._client.table(self.COMMENTS)
            .select("*")
            .eq("task_id", task_id)
            .order("created_at")
            .execute()
        )
        return res.data or []

    # ---- activities ---------------------------------------------------------

    def list_activities(self, task_id: int) -> list[dict]:
        res = (
            self._client.table(self.ACTIVITIES)
            .select("*")
            .eq("task_id", task_id)
            .order("created_at")
            .execute()
        )
        return res.data or []

    # ---- projects (dead: reintroduce later) ---------------------------------
    # Projects are shelved. These methods still target the surviving `projects`
    # table but are not wired into the CLI or MCP clients. Kept verbatim so they
    # can be re-enabled when projects come back.

    def _get_project_row(self, project_id: int) -> dict:
        res = self._client.table(self.PROJECTS).select("*").eq("id", project_id).execute()
        if not res.data:
            raise TaskCLIError(f"Project #{project_id} not found")
        return res.data[0]

    def add_project(
        self,
        title: str,
        description: str,
        start: DateLike,
        end: DateLike,
        stages: int,
    ) -> dict:
        start_d = _to_date(start)
        end_d = _to_date(end)
        _validate_dates(start_d, end_d)
        if stages < 1:
            raise TaskCLIError("--stages must be >= 1")
        payload = {
            "title": title,
            "description": description,
            "start_date": start_d.isoformat(),
            "end_date": end_d.isoformat(),
            "no_of_stages": stages,
        }
        res = self._client.table(self.PROJECTS).insert(payload).execute()
        return res.data[0]

    def list_projects(self) -> list[dict]:
        res = self._client.table(self.PROJECTS).select("*").order("id").execute()
        return res.data or []

    def get_project(self, id: int) -> dict:
        return self._get_project_row(id)

    def update_project(
        self,
        id: int,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        start: Optional[DateLike] = None,
        end: Optional[DateLike] = None,
        stages: Optional[int] = None,
    ) -> dict:
        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if start is not None:
            payload["start_date"] = _to_date(start).isoformat()
        if end is not None:
            payload["end_date"] = _to_date(end).isoformat()
        if stages is not None:
            if stages < 1:
                raise TaskCLIError("--stages must be >= 1")
            payload["no_of_stages"] = stages

        if not payload:
            raise TaskCLIError("Nothing to update. Provide at least one field.")

        existing = self._get_project_row(id)
        merged = {**existing, **payload}
        _validate_dates(_to_date(merged["start_date"]), _to_date(merged["end_date"]))

        res = self._client.table(self.PROJECTS).update(payload).eq("id", id).execute()
        return res.data[0] if res.data else {**existing, **payload}

    def delete_project(self, id: int) -> None:
        self._get_project_row(id)
        self._client.table(self.PROJECTS).delete().eq("id", id).execute()
