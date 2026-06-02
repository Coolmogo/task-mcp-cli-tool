"""The task system's notion of the Spark agent user.

This is identity/routing only — *not* Spark's behavior. The servers use it to
recognise when a task is assigned to the agent and to stamp Spark-authored
writes. Spark's actual logic lives in the standalone ``spark_agent`` package.
"""
from __future__ import annotations


SPARK_USER_ID = "user:spark"
SPARK_AUTHOR_ID = SPARK_USER_ID
SPARK_AUTHOR_TYPE = "mogo"
SPARK_USER_NAME = "Spark"


def is_spark_assignee(assignee_id: str | None) -> bool:
    return assignee_id == SPARK_USER_ID
