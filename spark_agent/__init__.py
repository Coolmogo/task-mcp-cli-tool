"""Spark — the AI agent that works tasks on the board.

`spark_agent` is a standalone client of the task system: it talks to the rest of
the application **only** through the `task_mcp` MCP server (spawned over stdio),
never by importing `task_program` / `TaskCLI` directly. It is launched as a
fire-and-forget subprocess (`python -m spark_agent <task_id> ...`) by whichever
server detected that a Spark turn is due.
"""

__version__ = "0.1.0"
