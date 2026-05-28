from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from surrealdb import RecordID, Surreal

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


# Maps a (client-facing) task field to the (Dart camelCase) activity field name and
# the action used when that field changes. A change to None becomes a "removed" action.
_ACTIVITY_FIELDS: dict[str, tuple[str, str]] = {
    "title": ("title", "updated"),
    "description": ("description", "updated"),
    "due_date": ("dueDate", "updated"),
    "assignee_id": ("assignee", "assigned"),
    "status": ("status", "moved"),
    "stage_id": ("stageId", "moved"),
}


# ---- result normalization ---------------------------------------------------
# SurrealDB returns RecordID/datetime objects and stores links under bare names
# (`assignee`, `project`, `task`, `author`). SCHEMAFULL also omits null option<>
# fields entirely. These helpers reproduce the original Supabase dict shape:
# string ids, `*_id` link keys, ISO strings for dates, and the full key set with
# missing values filled as None so clients can `.get(...)` safely.

_LINK_RENAMES = {
    "assignee": "assignee_id",
    "project": "project_id",
    "task": "task_id",
    "author": "author_id",
}

_TASK_KEYS = (
    "id", "title", "description", "status", "due_date",
    "assignee_id", "stage_id", "project_id", "created_at",
)
_ACTIVITY_KEYS = (
    "id", "task_id", "type", "action", "field",
    "old_value", "new_value", "text", "author_id", "legacy_author_name", "created_at",
)
_COMMENT_KEYS = (
    "id", "task_id", "text", "content", "author_id", "author_type",
    "legacy_author_name", "created_at", "metadata",
)
_PROJECT_KEYS = (
    "id", "title", "description", "start_date", "end_date", "no_of_stages",
)


def _scalar(value):
    if isinstance(value, RecordID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _normalize(raw: dict, keys: tuple[str, ...]) -> dict:
    renamed: dict = {}
    for key, value in raw.items():
        normalized_key = _LINK_RENAMES.get(key, key)
        renamed[normalized_key] = _scalar(value)
    return {k: renamed.get(k) for k in keys}


def _normalize_comment(raw: dict) -> dict:
    row = _normalize(raw, _COMMENT_KEYS)
    if "author_id" in raw:
        row["author_id"] = _scalar(raw.get("author_id"))
    if "author_type" in raw:
        row["author_type"] = _scalar(raw.get("author_type"))
    if "metadata" in raw:
        row["metadata"] = raw.get("metadata")
    content = row.get("content") or row.get("text")
    row["content"] = content
    row["text"] = row.get("text") or content
    row["author_type"] = row.get("author_type") or "user"
    row["author_id"] = row.get("author_id") or "current_user"
    return row


def _normalize_task_context_status(status: Optional[str]) -> str:
    normalized = (status or "").strip().lower().replace("-", " ").replace("_", " ")
    if normalized in {"todo", "to do", "backlog"}:
        return "todo"
    if normalized in {"in progress", "inprogress", "doing"}:
        return "in_progress"
    if normalized in {"blocked", "on hold", "stuck"}:
        return "blocked"
    if normalized in {"done", "complete", "completed"}:
        return "done"
    return "todo"


def _normalize_task_context_priority(priority: Optional[str]) -> str:
    normalized = (priority or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "medium"


class TaskCLI:
    """Programmatic API for taskcli. Methods return raw row dicts and raise
    TaskCLIError on validation or lookup failures."""

    PROJECTS = "project"
    TASKS = "task"
    ACTIVITIES = "activity"
    COMMENTS = "comment"
    USERS = "user"

    def __init__(
        self,
        *,
        client: Optional[Surreal] = None,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        namespace: str = "main",
        database: str = "main",
    ) -> None:
        if client is not None:
            self._client = client
        elif url and username and password:
            db = Surreal(url)
            db.signin({"username": username, "password": password})
            db.use(namespace, database)
            self._client = db
        else:
            self._client = _default_client()

    # ---- internal helpers ---------------------------------------------------

    def _rid(self, id) -> RecordID:
        """Coerce a record-id string ('task:abc') into a RecordID, or raise."""
        if isinstance(id, RecordID):
            return id
        try:
            return RecordID.parse(str(id))
        except Exception:
            raise TaskCLIError(f"Task #{id} not found")

    def _optional_rid(self, id) -> Optional[RecordID]:
        if not id:
            return None
        try:
            return self._rid(id)
        except TaskCLIError:
            return None

    def _get_task_row(self, id) -> dict:
        res = self._client.query("SELECT * FROM $t", {"t": self._rid(id)})
        if not res:
            raise TaskCLIError(f"Task #{id} not found")
        return _normalize(res[0], _TASK_KEYS)

    def _get_user_row(self, id) -> Optional[dict]:
        try:
            rid = id if isinstance(id, RecordID) else RecordID.parse(str(id))
        except Exception:
            return None
        res = self._client.query("SELECT * FROM $u", {"u": rid})
        if not res:
            return None
        return res[0]

    @staticmethod
    def _stringify(value) -> Optional[str]:
        """Render an activity old/new value as text (already normalized scalars)."""
        if value is None:
            return None
        return str(value)

    def _log_activity(self, task_rid: RecordID, field_key: str, old, new) -> None:
        field, action = _ACTIVITY_FIELDS[field_key]
        if new is None and old is not None:
            action = "removed"
        self._client.create(self.ACTIVITIES, {
            "task": task_rid,
            "type": "history",
            "action": action,
            "field": field,
            "old_value": self._stringify(old),
            "new_value": self._stringify(new),
            "author": None,
            "legacy_author_name": None,
        })

    # ---- tasks --------------------------------------------------------------

    def add_task(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        status: str = DEFAULT_STATUS,
        assignee_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        due: Optional[DateLike] = None,
        project: Optional[str] = None,
    ) -> dict:
        if assignee_id:
            self.ensure_user(assignee_id)
        payload = {
            "title": title,
            "description": description,
            "status": status,
            "assignee": self._rid(assignee_id) if assignee_id else None,
            "stage_id": stage_id,
            "due_date": _to_date(due).isoformat() if due is not None else None,
            "project": self._rid(project) if project else None,
        }
        row = self._client.create(self.TASKS, payload)
        return _normalize(row, _TASK_KEYS)

    def list_tasks(
        self,
        status: Optional[str] = None,
        project: Optional[str] = None,
    ) -> list[dict]:
        conditions: list[str] = []
        vars: dict = {}
        if status is not None:
            conditions.append("status = $status")
            vars["status"] = status
        if project is not None:
            conditions.append("project = $project")
            vars["project"] = self._rid(project)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._client.query(
            f"SELECT * FROM {self.TASKS}{where} ORDER BY created_at", vars or None
        )
        return [_normalize(r, _TASK_KEYS) for r in rows]

    def get_task(self, id) -> dict:
        """Fetch a task with its embedded activity feed and comments (one query)."""
        res = self._client.query(
            "SELECT *, "
            "(SELECT * FROM activity WHERE task = $t ORDER BY created_at) AS activities, "
            "(SELECT * FROM comment  WHERE task = $t ORDER BY created_at) AS comments "
            "FROM $t",
            {"t": self._rid(id)},
        )
        if not res:
            raise TaskCLIError(f"Task #{id} not found")
        raw = res[0]
        row = _normalize(raw, _TASK_KEYS)
        row["activities"] = [_normalize(a, _ACTIVITY_KEYS) for a in (raw.get("activities") or [])]
        row["comments"] = [_normalize_comment(c) for c in (raw.get("comments") or [])]
        return row

    def update_task(
        self,
        id,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assignee_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        due: Optional[DateLike] = None,
    ) -> dict:
        current = self._get_task_row(id)  # normalized; raises if missing
        rid = self._rid(id)

        # Provided (non-None) fields, in client-facing form.
        provided: dict = {}
        if title is not None:
            provided["title"] = title
        if description is not None:
            provided["description"] = description
        if status is not None:
            provided["status"] = status
        if assignee_id is not None:
            provided["assignee_id"] = assignee_id
        if stage_id is not None:
            provided["stage_id"] = stage_id
        if due is not None:
            provided["due_date"] = _to_date(due).isoformat()

        if not provided:
            raise TaskCLIError("Nothing to update. Provide at least one field.")

        # Record one history entry per field that actually changed.
        changes = {k: v for k, v in provided.items() if v != current.get(k)}
        for field_key, new in changes.items():
            self._log_activity(rid, field_key, current.get(field_key), new)

        # Translate changed client fields to SurrealDB field names / record links.
        db_payload: dict = {}
        for field_key, new in changes.items():
            if field_key == "assignee_id":
                if new:
                    self.ensure_user(new)
                db_payload["assignee"] = self._rid(new) if new else None
            elif field_key == "project_id":
                db_payload["project"] = self._rid(new) if new else None
            else:
                db_payload[field_key] = new
        if db_payload:
            self._client.merge(rid, db_payload)

        return {**current, **provided}

    # ---- users -------------------------------------------------------------

    def ensure_user(
        self,
        user_id: str,
        *,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict:
        existing = self._get_user_row(user_id)
        if existing:
            return existing
        payload = {
            "name": name or user_id.split(":", 1)[-1].replace("_", " ").title(),
            "email": email,
        }
        return self._client.create(self._rid(user_id), payload)

    def delete_task(self, id) -> None:
        self._get_task_row(id)  # validate it exists
        rid = self._rid(id)
        # SurrealDB has no FK cascade: remove children explicitly, then the task.
        self._client.query("DELETE activity WHERE task = $t", {"t": rid})
        self._client.query("DELETE comment WHERE task = $t", {"t": rid})
        self._client.delete(rid)

    # ---- comments -----------------------------------------------------------

    def add_comment(
        self,
        task_id,
        text: str,
        *,
        author_type: str = "user",
        author_id: str = "current_user",
        metadata: Optional[dict] = None,
        legacy_author_name: Optional[str] = None,
    ) -> dict:
        self._get_task_row(task_id)  # validate the task exists
        row = self._client.create(self.COMMENTS, {
            "task": self._rid(task_id),
            "text": text,
            "author_id": author_id,
            "author_type": author_type,
            "author": self._optional_rid(author_id),
            "legacy_author_name": legacy_author_name,
            "metadata": metadata,
        })
        return _normalize_comment(row)

    def create_comment(
        self,
        task_id,
        content: str,
        *,
        author_type: str = "user",
        author_id: str = "current_user",
        metadata: Optional[dict] = None,
        legacy_author_name: Optional[str] = None,
    ) -> dict:
        return self.add_comment(
            task_id,
            content,
            author_type=author_type,
            author_id=author_id,
            metadata=metadata,
            legacy_author_name=legacy_author_name,
        )

    def list_comments(self, task_id) -> list[dict]:
        rows = self._client.query(
            "SELECT * FROM comment WHERE task = $t ORDER BY created_at",
            {"t": self._rid(task_id)},
        )
        return [_normalize_comment(r) for r in rows]

    def get_recent_comments_for_task(self, task_id, *, limit: int = 10) -> list[dict]:
        rows = self._client.query(
            "SELECT * FROM comment WHERE task = $t ORDER BY created_at DESC LIMIT $limit",
            {"t": self._rid(task_id), "limit": limit},
        )
        normalized = [_normalize_comment(r) for r in rows]
        normalized.reverse()
        return normalized

    # ---- activities ---------------------------------------------------------

    def list_activities(self, task_id) -> list[dict]:
        rows = self._client.query(
            "SELECT * FROM activity WHERE task = $t ORDER BY created_at",
            {"t": self._rid(task_id)},
        )
        return [_normalize(r, _ACTIVITY_KEYS) for r in rows]

    def get_recent_activity_logs_for_task(self, task_id, *, limit: int = 10) -> list[dict]:
        rows = self._client.query(
            "SELECT * FROM activity WHERE task = $t ORDER BY created_at DESC LIMIT $limit",
            {"t": self._rid(task_id), "limit": limit},
        )
        normalized = [_normalize(r, _ACTIVITY_KEYS) for r in rows]
        normalized.reverse()
        return normalized

    def get_task_by_id(self, task_id) -> dict:
        return self._get_task_row(task_id)

    def build_task_context(
        self,
        task_id,
        *,
        comment_limit: int = 10,
        activity_limit: int = 10,
    ) -> dict:
        task = self.get_task_by_id(task_id)
        comments = self.get_recent_comments_for_task(task_id, limit=comment_limit)
        activities = self.get_recent_activity_logs_for_task(task_id, limit=activity_limit)
        return {
            "task_id": task["id"],
            "title": task["title"],
            "description": task.get("description"),
            "status": _normalize_task_context_status(task.get("status")),
            "priority": _normalize_task_context_priority(task.get("priority")),
            "assignee_name": None,
            "comments": [
                {
                    "author_type": comment.get("author_type") or "user",
                    "author_name": comment.get("legacy_author_name"),
                    "content": comment.get("content") or "",
                    "created_at": comment.get("created_at"),
                }
                for comment in comments
            ],
            "activity_logs": [
                {
                    "event_type": activity.get("action") or activity.get("type") or "history",
                    "description": activity.get("text")
                    or (
                        f"{activity.get('field')} changed from "
                        f"{activity.get('old_value')!r} to {activity.get('new_value')!r}"
                        if activity.get("field")
                        else None
                    ),
                    "created_at": activity.get("created_at"),
                }
                for activity in activities
            ],
        }

    # ---- projects (dead: reintroduce later) ---------------------------------
    # Projects are shelved. These methods still target the surviving `project`
    # table but are not wired into the CLI or MCP clients. Kept so they can be
    # re-enabled when projects come back.

    def _get_project_row(self, id) -> dict:
        try:
            prid = id if isinstance(id, RecordID) else RecordID.parse(str(id))
        except Exception:
            raise TaskCLIError(f"Project #{id} not found")
        res = self._client.query("SELECT * FROM $p", {"p": prid})
        if not res:
            raise TaskCLIError(f"Project #{id} not found")
        return _normalize(res[0], _PROJECT_KEYS)

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
        row = self._client.create(self.PROJECTS, {
            "title": title,
            "description": description,
            "start_date": start_d.isoformat(),
            "end_date": end_d.isoformat(),
            "no_of_stages": stages,
        })
        return _normalize(row, _PROJECT_KEYS)

    def list_projects(self) -> list[dict]:
        rows = self._client.query(f"SELECT * FROM {self.PROJECTS} ORDER BY created_at")
        return [_normalize(r, _PROJECT_KEYS) for r in rows]

    def get_project(self, id) -> dict:
        return self._get_project_row(id)

    def update_project(
        self,
        id,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        start: Optional[DateLike] = None,
        end: Optional[DateLike] = None,
        stages: Optional[int] = None,
    ) -> dict:
        provided: dict = {}
        if title is not None:
            provided["title"] = title
        if description is not None:
            provided["description"] = description
        if start is not None:
            provided["start_date"] = _to_date(start).isoformat()
        if end is not None:
            provided["end_date"] = _to_date(end).isoformat()
        if stages is not None:
            if stages < 1:
                raise TaskCLIError("--stages must be >= 1")
            provided["no_of_stages"] = stages

        if not provided:
            raise TaskCLIError("Nothing to update. Provide at least one field.")

        existing = self._get_project_row(id)
        merged = {**existing, **provided}
        _validate_dates(_to_date(merged["start_date"]), _to_date(merged["end_date"]))

        self._client.merge(RecordID.parse(str(id)), provided)
        return merged

    def delete_project(self, id) -> None:
        self._get_project_row(id)
        self._client.delete(RecordID.parse(str(id)))
