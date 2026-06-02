from __future__ import annotations

import unittest
from unittest.mock import patch

from task_program.spark_agent import SPARK_USER_ID, is_spark_assignee
from task_program.schemas import SparkCreateTaskProposal, SparkTaskAction, TaskContext
from task_program.spark_service import generate_spark_reply
from task_program.settings import SparkSettings
from task_program import TaskCLIError
from task_program.program import (
    _normalize_task_context_priority,
    _normalize_task_context_status,
)


class FakeTaskProgram:
    def __init__(
        self,
        *,
        fail_user_comment: bool = False,
        fail_spark_comment: bool = False,
        fail_add_task: bool = False,
    ) -> None:
        self.fail_user_comment = fail_user_comment
        self.fail_spark_comment = fail_spark_comment
        self.fail_add_task = fail_add_task
        self.comments: list[dict] = []
        self.created_tasks: list[dict] = []
        self.users: dict[str, dict] = {}
        self.task = {
            "id": "task:1",
            "title": "Plan Spark",
            "description": "Implement Spark comment replies",
            "status": "In Progress",
            "assignee_id": None,
            "stage_id": None,
            "project_id": None,
            "created_at": "2026-05-28T09:00:00Z",
        }

    def ensure_user(self, user_id: str, *, name: str | None = None, email: str | None = None) -> dict:
        row = {"id": user_id, "name": name or user_id, "email": email}
        self.users[user_id] = row
        return row

    def get_task_by_id(self, task_id: str) -> dict:
        if task_id != self.task["id"]:
            raise TaskCLIError("Task not found")
        return dict(self.task)

    def update_task(self, task_id: str, **changes) -> dict:
        current = self.get_task_by_id(task_id)
        self.task.update(changes)
        return {**current, **changes}

    def add_task(
        self,
        title: str,
        *,
        description: str | None = None,
        status: str = "To Do",
        assignee_id: str | None = None,
        stage_id: str | None = None,
        due: str | None = None,
        project: str | None = None,
    ) -> dict:
        if self.fail_add_task:
            raise RuntimeError("task creation failed")
        row = {
            "id": f"task:created{len(self.created_tasks) + 1}",
            "title": title,
            "description": description,
            "status": status,
            "assignee_id": assignee_id,
            "stage_id": stage_id,
            "project_id": project,
            "created_at": "2026-05-28T10:01:00Z",
        }
        self.created_tasks.append(row)
        return row

    def create_comment(
        self,
        task_id: str,
        content: str,
        *,
        author_type: str = "user",
        author_id: str = "current_user",
        metadata: dict | None = None,
        legacy_author_name: str | None = None,
    ) -> dict:
        if author_type == "user" and self.fail_user_comment:
            raise TaskCLIError("comment save failed")
        if author_type == "mogo" and self.fail_spark_comment:
            raise RuntimeError("spark save failed")

        row = {
            "id": f"task_comment:{len(self.comments) + 1}",
            "task_id": task_id,
            "author_type": author_type,
            "author_id": author_id,
            "content": content,
            "created_at": "2026-05-28T10:00:00Z",
            "metadata": metadata,
        }
        self.comments.append(row)
        return row

    def build_task_context(self, task_id: str) -> dict:
        return {
            "task_id": task_id,
            "title": self.task["title"],
            "description": self.task["description"],
            "status": "in_progress",
            "priority": "medium",
            "assignee_name": None,
            "comments": [],
            "activity_logs": [],
        }


class SparkUtilityTests(unittest.TestCase):
    def test_is_spark_assignee(self) -> None:
        self.assertTrue(is_spark_assignee(SPARK_USER_ID))
        self.assertFalse(is_spark_assignee("user:alex"))
        self.assertFalse(is_spark_assignee(None))

    def test_status_and_priority_normalization(self) -> None:
        self.assertEqual(_normalize_task_context_status("To Do"), "todo")
        self.assertEqual(_normalize_task_context_status("In Progress"), "in_progress")
        self.assertEqual(_normalize_task_context_status("Blocked"), "blocked")
        self.assertEqual(_normalize_task_context_status("Done"), "done")
        self.assertEqual(_normalize_task_context_priority(None), "medium")
        self.assertEqual(_normalize_task_context_priority("high"), "high")

    def test_generate_spark_reply_returns_fallback_when_no_api_key(self) -> None:
        context = TaskContext(
            task_id="task:1",
            title="Task",
            description=None,
            status="todo",
            priority="medium",
            assignee_name=None,
            comments=[],
            activity_logs=[],
        )

        reply = generate_spark_reply(
            context,
            "Summarize this task",
            settings=SparkSettings(openrouter_api_key=None),
        )

        self.assertEqual(reply.action_type, "update")
        self.assertEqual(reply.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
