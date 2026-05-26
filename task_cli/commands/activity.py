import sys

from task_program import TaskCLI, TaskCLIError


def list_(args) -> None:
    try:
        rows = TaskCLI().list_activities(args.task)
    except TaskCLIError as e:
        sys.exit(str(e))
    if not rows:
        print("No activity.")
        return
    for row in rows:
        line = f"#{row['id']} [{row['action']}]"
        if row.get("field"):
            line += f" {row['field']}"
        if row.get("old_value") is not None or row.get("new_value") is not None:
            line += f": {row.get('old_value')!r} -> {row.get('new_value')!r}"
        if row.get("text"):
            line += f" {row['text']}"
        line += f" ({row.get('created_at')})"
        print(line)
