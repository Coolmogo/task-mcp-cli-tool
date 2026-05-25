from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Response, status
from fastapi.responses import JSONResponse

from task_api.schemas import (
    HealthResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from task_program import TaskCLI, TaskCLIError
from task_program.models import Status


@lru_cache
def get_api() -> TaskCLI:
    return TaskCLI()


def _status_for_task_error(exc: TaskCLIError) -> int:
    if "not found" in str(exc).lower():
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST


app = FastAPI(title="Task API")


@app.exception_handler(TaskCLIError)
async def handle_task_cli_error(_, exc: TaskCLIError) -> JSONResponse:
    return JSONResponse(
        status_code=_status_for_task_error(exc),
        content={"detail": str(exc)},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/projects", response_model=list[ProjectResponse])
def list_projects(api: Annotated[TaskCLI, Depends(get_api)]) -> list[dict]:
    return api.list_projects()


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    return api.get_project(project_id)


@app.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    return api.add_project(
        title=payload.title,
        description=payload.description,
        start=payload.start_date,
        end=payload.end_date,
        stages=payload.no_of_stages,
    )


@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    payload: ProjectUpdateRequest,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    return api.update_project(
        project_id,
        title=payload.title,
        description=payload.description,
        start=payload.start_date,
        end=payload.end_date,
        stages=payload.no_of_stages,
    )


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> Response:
    api.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    api: Annotated[TaskCLI, Depends(get_api)],
    project_id: int | None = Query(default=None),
    task_status: Annotated[Status | None, Query(alias="status")] = None,
) -> list[dict]:
    status_filter = task_status.value if task_status is not None else None
    return api.list_tasks(project=project_id, status=status_filter)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    return api.get_task(task_id)


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    return api.add_task(
        project=payload.project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        assigned_to=payload.assigned_to,
        stage=payload.stage,
        start=payload.start_date,
        end=payload.end_date,
    )


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> dict:
    task_status = payload.status.value if payload.status is not None else None
    return api.update_task(
        task_id,
        title=payload.title,
        description=payload.description,
        status=task_status,
        assigned_to=payload.assigned_to,
        stage=payload.stage,
        start=payload.start_date,
        end=payload.end_date,
    )


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    api: Annotated[TaskCLI, Depends(get_api)],
) -> Response:
    api.delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
