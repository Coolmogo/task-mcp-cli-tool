import sys

from task_program import TaskCLI, TaskCLIError


def add(args) -> None:
    try:
        row = TaskCLI().add_comment(args.task, args.text)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Added comment #{row['id']} to task #{args.task}")


def list_(args) -> None:
    try:
        rows = TaskCLI().list_comments(args.task)
    except TaskCLIError as e:
        sys.exit(str(e))
    if not rows:
        print("No comments.")
        return
    for row in rows:
        print(f"#{row['id']}: {row['text']} ({row.get('created_at')})")
