from __future__ import annotations

from dataclasses import dataclass


SPARK_USER_ID = "user:spark"
SPARK_AUTHOR_ID = SPARK_USER_ID
SPARK_AUTHOR_TYPE = "mogo"
SPARK_USER_NAME = "Spark"


@dataclass(frozen=True)
class SparkTrigger:
    kind: str
    prompt: str
    metadata: dict


def is_spark_assignee(assignee_id: str | None) -> bool:
    return assignee_id == SPARK_USER_ID


def build_assignment_trigger(task_id: str) -> SparkTrigger:
    return SparkTrigger(
        kind="assignment",
        prompt="You were just assigned this task. Reply with the most useful next step.",
        metadata={
            "triggered_by_type": "assignment",
            "task_id": task_id,
        },
    )


def build_comment_trigger(task_id: str, comment_id: str, content: str) -> SparkTrigger:
    return SparkTrigger(
        kind="comment",
        prompt=content,
        metadata={
            "triggered_by_type": "comment",
            "triggered_by_comment_id": comment_id,
            "task_id": task_id,
        },
    )
