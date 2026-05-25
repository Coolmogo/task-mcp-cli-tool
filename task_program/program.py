from __future__ import annotations

from datetime import date
from typing import Optional, Union

from supabase import Client, create_client

from .db import client as _default_client


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


class TaskCLI:
    """Programmatic API for taskcli. Methods return raw row dicts and raise
    TaskCLIError on validation or lookup failures."""

    PROJECTS = "projects"
    TASKS = "tasks"

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        if supabase_url and supabase_key:
            self._client: Client = create_client(supabase_url, supabase_key)
        else:
            self._client = _default_client()

    def _get_project_row(self, project_id: int) -> dict:
        res = self._client.table(self.PROJECTS).select("*").eq("id", project_id).execute()
        if not res.data:
            raise TaskCLIError(f"Project #{project_id} not found")
        return res.data[0]

    def _get_task_row(self, task_id: int) -> dict:
        res = self._client.table(self.TASKS).select("*").eq("id", task_id).execute()
        if not res.data:
            raise TaskCLIError(f"Task #{task_id} not found")
        return res.data[0]

    @staticmethod
    def _validate_stage(stage: int, project: dict) -> None:
        if stage < 1 or stage > project["no_of_stages"]:
            raise TaskCLIError(
                f"Stage must be 1..{project['no_of_stages']} for project #{project['id']}"
            )

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

    def add_task(
        self,
        project: int,
        title: str,
        description: str,
        status: str,
        assigned_to: str,
        stage: int,
        start: DateLike,
        end: DateLike,
    ) -> dict:
        project_row = self._get_project_row(project)
        self._validate_stage(stage, project_row)
        start_d = _to_date(start)
        end_d = _to_date(end)
        _validate_dates(start_d, end_d)

        payload = {
            "project_id": project,
            "title": title,
            "description": description,
            "status": status,
            "assigned_to": assigned_to,
            "stage": stage,
            "start_date": start_d.isoformat(),
            "end_date": end_d.isoformat(),
        }
        res = self._client.table(self.TASKS).insert(payload).execute()
        return res.data[0]

    def list_tasks(
        self,
        project: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        q = self._client.table(self.TASKS).select("*")
        if project is not None:
            q = q.eq("project_id", project)
        if status is not None:
            q = q.eq("status", status)
        res = q.order("id").execute()
        return res.data or []

    def get_task(self, id: int) -> dict:
        return self._get_task_row(id)

    def update_task(
        self,
        id: int,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
        stage: Optional[int] = None,
        start: Optional[DateLike] = None,
        end: Optional[DateLike] = None,
    ) -> dict:
        current = self._get_task_row(id)

        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if assigned_to is not None:
            payload["assigned_to"] = assigned_to
        if stage is not None:
            project = self._get_project_row(current["project_id"])
            self._validate_stage(stage, project)
            payload["stage"] = stage
        if start is not None:
            payload["start_date"] = _to_date(start).isoformat()
        if end is not None:
            payload["end_date"] = _to_date(end).isoformat()

        if not payload:
            raise TaskCLIError("Nothing to update. Provide at least one field.")

        merged = {**current, **payload}
        _validate_dates(_to_date(merged["start_date"]), _to_date(merged["end_date"]))

        res = self._client.table(self.TASKS).update(payload).eq("id", id).execute()
        return res.data[0] if res.data else {**current, **payload}

    def delete_task(self, id: int) -> None:
        self._get_task_row(id)
        self._client.table(self.TASKS).delete().eq("id", id).execute()
