from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from task_api import server
from task_api.spark_agent import SPARK_USER_ID, is_spark_assignee
from task_api.schemas import SparkTaskReply, TaskContext
from task_api.spark_service import generate_spark_reply
from task_api.settings import SparkSettings
from task_program import TaskCLIError
from task_program.program import (
    _normalize_task_context_priority,
    _normalize_task_context_status,
)


class FakeTaskProgram:
    def __init__(self, *, fail_user_comment: bool = False, fail_spark_comment: bool = False) -> None:
        self.fail_user_comment = fail_user_comment
        self.fail_spark_comment = fail_spark_comment
        self.comments: list[dict] = []
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

    def test_generate_spark_reply_returns_fallback_on_invalid_json(self) -> None:
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

        class FakeResponse:
            output_text = "not json"

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        return FakeResponse()

        with patch("task_api.spark_service._openai_client", return_value=FakeClient()):
            reply = generate_spark_reply(
                context,
                "@Spark summarize",
                settings=SparkSettings(openai_api_key="test-key"),
            )

        self.assertEqual(reply.response_type, "clarification")
        self.assertEqual(reply.confidence, 0.0)

    def test_generate_spark_reply_supports_google_provider(self) -> None:
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

        class FakeResponse:
            text = '{"response_type":"summary","message":"Review the latest task notes.","confidence":0.72}'

        class FakeModels:
            @staticmethod
            def generate_content(**kwargs):
                return FakeResponse()

        class FakeClient:
            models = FakeModels()

        with patch("task_api.spark_service._google_client", return_value=FakeClient()):
            reply = generate_spark_reply(
                context,
                "Summarize this task",
                settings=SparkSettings(
                    spark_llm_provider="google",
                    google_api_key="test-key",
                ),
            )

        self.assertEqual(reply.response_type, "summary")
        self.assertEqual(reply.confidence, 0.72)


class SparkRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(server.app)

    def test_comment_without_spark_returns_only_user_comment(self) -> None:
        fake_program = FakeTaskProgram()
        with patch.object(server, "_api", return_value=fake_program):
            response = self.client.post("/tasks/task:1/comments", json={"content": "Normal comment"})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["user_comment"]["author_type"], "user")
        self.assertIsNone(payload["spark_comment"])
        self.assertEqual(len(fake_program.comments), 1)

    def test_comment_on_spark_assigned_task_returns_both_comments(self) -> None:
        fake_program = FakeTaskProgram()
        fake_program.task["assignee_id"] = SPARK_USER_ID
        spark_reply = SparkTaskReply(
            response_type="suggestion",
            message="Confirm the requirements and move the task to in progress.",
            confidence=0.91,
        )
        with patch.object(server, "_api", return_value=fake_program):
            with patch.object(server, "generate_spark_reply", return_value=spark_reply):
                response = self.client.post(
                    "/tasks/task:1/comments",
                    json={"content": "What should we do next?"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["spark_comment"]["author_id"], SPARK_USER_ID)
        self.assertEqual(payload["spark_comment"]["metadata"]["triggered_by_comment_id"], "task_comment:1")
        self.assertEqual(len(fake_program.comments), 2)
        self.assertIn(SPARK_USER_ID, fake_program.users)

    def test_assigning_task_to_spark_generates_comment(self) -> None:
        fake_program = FakeTaskProgram()
        spark_reply = SparkTaskReply(
            response_type="answer",
            message="I will review the task and suggest the next step.",
            confidence=0.85,
        )
        with patch.object(server, "_api", return_value=fake_program):
            with patch.object(server, "generate_spark_reply", return_value=spark_reply):
                response = self.client.patch(
                    "/tasks/task:1",
                    json={"assignee_id": SPARK_USER_ID},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignee_id"], SPARK_USER_ID)
        self.assertEqual(response.json()["spark_comment"]["author_id"], SPARK_USER_ID)
        self.assertEqual(len(fake_program.comments), 1)
        self.assertEqual(fake_program.comments[0]["author_id"], SPARK_USER_ID)
        self.assertEqual(fake_program.comments[0]["metadata"]["triggered_by_type"], "assignment")

    def test_user_comment_failure_returns_http_error(self) -> None:
        fake_program = FakeTaskProgram(fail_user_comment=True)
        with patch.object(server, "_api", return_value=fake_program):
            response = self.client.post("/tasks/task:1/comments", json={"content": "Normal comment"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "comment save failed"})

    def test_spark_failure_returns_user_comment_only(self) -> None:
        fake_program = FakeTaskProgram()
        fake_program.task["assignee_id"] = SPARK_USER_ID
        with patch.object(server, "_api", return_value=fake_program):
            with patch.object(server, "generate_spark_reply", side_effect=RuntimeError("boom")):
                response = self.client.post(
                    "/tasks/task:1/comments",
                    json={"content": "Summarize this task"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["spark_comment"])
        self.assertEqual(len(fake_program.comments), 1)

    def test_spark_comment_save_failure_returns_user_comment_only(self) -> None:
        fake_program = FakeTaskProgram(fail_spark_comment=True)
        fake_program.task["assignee_id"] = SPARK_USER_ID
        spark_reply = SparkTaskReply(
            response_type="summary",
            message="This task needs a short summary.",
            confidence=0.8,
        )
        with patch.object(server, "_api", return_value=fake_program):
            with patch.object(server, "generate_spark_reply", return_value=spark_reply):
                response = self.client.post(
                    "/tasks/task:1/comments",
                    json={"content": "Summarize this task"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNone(payload["spark_comment"])
        self.assertEqual(len(fake_program.comments), 1)


if __name__ == "__main__":
    unittest.main()
