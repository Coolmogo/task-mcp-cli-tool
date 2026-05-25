from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from task_api.app import app, get_api
from task_program import TaskCLIError


class StubTaskAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def list_projects(self) -> list[dict]:
        self.calls.append(("list_projects", (), {}))
        return [
            {
                "id": 1,
                "title": "Launch v1",
                "description": "Q3",
                "start_date": "2026-06-01",
                "end_date": "2026-09-30",
                "no_of_stages": 4,
            }
        ]

    def get_project(self, project_id: int) -> dict:
        self.calls.append(("get_project", (project_id,), {}))
        return {
            "id": project_id,
            "title": "Launch v1",
            "description": "Q3",
            "start_date": "2026-06-01",
            "end_date": "2026-09-30",
            "no_of_stages": 4,
        }

    def add_project(self, **kwargs) -> dict:
        self.calls.append(("add_project", (), kwargs))
        return {
            "id": 1,
            "title": kwargs["title"],
            "description": kwargs["description"],
            "start_date": kwargs["start"].isoformat(),
            "end_date": kwargs["end"].isoformat(),
            "no_of_stages": kwargs["stages"],
        }

    def update_project(self, project_id: int, **kwargs) -> dict:
        self.calls.append(("update_project", (project_id,), kwargs))
        start_value = kwargs.get("start")
        end_value = kwargs.get("end")
        return {
            "id": project_id,
            "title": kwargs.get("title") or "Launch v1",
            "description": kwargs.get("description") or "Q3",
            "start_date": start_value.isoformat() if start_value is not None else "2026-06-01",
            "end_date": end_value.isoformat() if end_value is not None else "2026-09-30",
            "no_of_stages": kwargs.get("stages") or 4,
        }

    def delete_project(self, project_id: int) -> None:
        self.calls.append(("delete_project", (project_id,), {}))

    def list_tasks(self, **kwargs) -> list[dict]:
        self.calls.append(("list_tasks", (), kwargs))
        return [
            {
                "id": 5,
                "project_id": kwargs.get("project") or 1,
                "title": "Wireframes",
                "description": "",
                "status": kwargs.get("status") or "todo",
                "assigned_to": "Aarav",
                "stage": 1,
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            }
        ]

    def get_task(self, task_id: int) -> dict:
        self.calls.append(("get_task", (task_id,), {}))
        return {
            "id": task_id,
            "project_id": 1,
            "title": "Wireframes",
            "description": "",
            "status": "todo",
            "assigned_to": "Aarav",
            "stage": 1,
            "start_date": "2026-06-01",
            "end_date": "2026-06-15",
        }

    def add_task(self, **kwargs) -> dict:
        self.calls.append(("add_task", (), kwargs))
        return {
            "id": 5,
            "project_id": kwargs["project"],
            "title": kwargs["title"],
            "description": kwargs["description"],
            "status": kwargs["status"],
            "assigned_to": kwargs["assigned_to"],
            "stage": kwargs["stage"],
            "start_date": kwargs["start"].isoformat(),
            "end_date": kwargs["end"].isoformat(),
        }

    def update_task(self, task_id: int, **kwargs) -> dict:
        self.calls.append(("update_task", (task_id,), kwargs))
        start_value = kwargs.get("start")
        end_value = kwargs.get("end")
        return {
            "id": task_id,
            "project_id": 1,
            "title": kwargs.get("title") or "Wireframes",
            "description": kwargs.get("description") or "",
            "status": kwargs.get("status") or "todo",
            "assigned_to": kwargs.get("assigned_to") or "Aarav",
            "stage": kwargs.get("stage") or 1,
            "start_date": start_value.isoformat() if start_value is not None else "2026-06-01",
            "end_date": end_value.isoformat() if end_value is not None else "2026-06-15",
        }

    def delete_task(self, task_id: int) -> None:
        self.calls.append(("delete_task", (task_id,), {}))


class ErrorTaskAPI(StubTaskAPI):
    def __init__(self, error: TaskCLIError) -> None:
        super().__init__()
        self.error = error

    def get_project(self, project_id: int) -> dict:
        raise self.error

    def update_project(self, project_id: int, **kwargs) -> dict:
        raise self.error


class TaskAPITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = StubTaskAPI()
        app.dependency_overrides[get_api] = lambda: self.stub
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_list_projects(self) -> None:
        response = self.client.get("/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], 1)
        self.assertEqual(self.stub.calls[0], ("list_projects", (), {}))

    def test_create_project_maps_request_fields(self) -> None:
        response = self.client.post(
            "/projects",
            json={
                "title": "Launch v1",
                "description": "Q3",
                "start_date": "2026-06-01",
                "end_date": "2026-09-30",
                "no_of_stages": 4,
            },
        )

        self.assertEqual(response.status_code, 201)
        name, _, kwargs = self.stub.calls[0]
        self.assertEqual(name, "add_project")
        self.assertEqual(kwargs["stages"], 4)
        self.assertEqual(kwargs["start"].isoformat(), "2026-06-01")
        self.assertEqual(kwargs["end"].isoformat(), "2026-09-30")

    def test_update_project_forwards_partial_fields(self) -> None:
        response = self.client.patch(
            "/projects/9",
            json={"description": "Updated", "no_of_stages": 6},
        )

        self.assertEqual(response.status_code, 200)
        name, args, kwargs = self.stub.calls[0]
        self.assertEqual(name, "update_project")
        self.assertEqual(args, (9,))
        self.assertIsNone(kwargs["title"])
        self.assertEqual(kwargs["description"], "Updated")
        self.assertEqual(kwargs["stages"], 6)

    def test_delete_project_returns_204(self) -> None:
        response = self.client.delete("/projects/3")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.stub.calls[0], ("delete_project", (3,), {}))

    def test_list_tasks_forwards_filters(self) -> None:
        response = self.client.get("/tasks", params={"project_id": 1, "status": "todo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stub.calls[0], ("list_tasks", (), {"project": 1, "status": "todo"}))

    def test_create_task_maps_request_fields(self) -> None:
        response = self.client.post(
            "/tasks",
            json={
                "project_id": 1,
                "title": "Wireframes",
                "description": "",
                "status": "todo",
                "assigned_to": "Aarav",
                "stage": 1,
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )

        self.assertEqual(response.status_code, 201)
        name, _, kwargs = self.stub.calls[0]
        self.assertEqual(name, "add_task")
        self.assertEqual(kwargs["project"], 1)
        self.assertEqual(kwargs["status"], "todo")
        self.assertEqual(kwargs["start"].isoformat(), "2026-06-01")

    def test_update_task_maps_partial_fields(self) -> None:
        response = self.client.patch(
            "/tasks/5",
            json={"status": "in_progress", "assigned_to": "Sam"},
        )

        self.assertEqual(response.status_code, 200)
        name, args, kwargs = self.stub.calls[0]
        self.assertEqual(name, "update_task")
        self.assertEqual(args, (5,))
        self.assertEqual(kwargs["status"], "in_progress")
        self.assertEqual(kwargs["assigned_to"], "Sam")
        self.assertIsNone(kwargs["stage"])

    def test_not_found_errors_become_404(self) -> None:
        app.dependency_overrides[get_api] = lambda: ErrorTaskAPI(
            TaskCLIError("Project #999 not found")
        )

        response = self.client.get("/projects/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Project #999 not found")

    def test_validation_errors_become_400(self) -> None:
        app.dependency_overrides[get_api] = lambda: ErrorTaskAPI(
            TaskCLIError("end date must be on or after start date")
        )

        response = self.client.patch(
            "/projects/1",
            json={"end_date": "2026-05-01"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "end date must be on or after start date",
        )

    def test_invalid_status_is_rejected(self) -> None:
        response = self.client.post(
            "/tasks",
            json={
                "project_id": 1,
                "title": "Wireframes",
                "stage": 1,
                "status": "blocked",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_task_program_imports_still_work_after_rename(self) -> None:
        from task_program import TaskCLI, TaskCLIError as ExportedTaskCLIError
        from task_program.program import TaskCLI as ProgramTaskCLI

        self.assertIs(TaskCLI, ProgramTaskCLI)
        self.assertIs(TaskCLIError, ExportedTaskCLIError)


if __name__ == "__main__":
    unittest.main()
