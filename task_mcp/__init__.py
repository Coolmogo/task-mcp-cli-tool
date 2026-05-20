"""MCP server consumer of the task_program library.

This package is intentionally separate from `task_program` itself: `task_program`
is the execution layer, and `task_mcp` is one of potentially many clients that
wrap it (alongside `task_cli`).
"""

__version__ = "0.1.0"
