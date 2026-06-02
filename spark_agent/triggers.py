from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SparkTrigger:
    kind: str
    prompt: str
    metadata: dict


def build_assignment_trigger(task_id: str) -> SparkTrigger:
    return SparkTrigger(
        kind="assignment",
        prompt="You were just assigned this task. Analyze the context and emit the most helpful verb: propose a new subtask, instruct the human, ask for clarification, or update the task. Focus on proposing actionable next steps.",
        metadata={
            "triggered_by_type": "assignment",
            "task_id": task_id,
        },
    )


def build_comment_trigger(task_id: str, comment_id: str | None, content: str) -> SparkTrigger:
    return SparkTrigger(
        kind="comment",
        prompt=content,
        metadata={
            "triggered_by_type": "comment",
            "triggered_by_comment_id": comment_id,
            "task_id": task_id,
        },
    )
