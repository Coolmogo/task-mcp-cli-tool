import sys

from task_program import TaskCLI, TaskCLIError


def _format(row: dict) -> str:
    return (
        f"[{row['status']:<11}] #{row['id']} (proj {row['project_id']}, stage {row['stage']}): {row['title']}\n"
        f"  description: {row['description']}\n"
        f"  assigned:    {row['assigned_to'] or '-'}\n"
        f"  dates:       {row['start_date']} -> {row['end_date']}"
    )


def add(args) -> None:
    try:
        row = TaskCLI().add_task(
            project=args.project,
            title=args.title,
            description=args.description,
            status=args.status,
            assigned_to=args.assigned_to,
            stage=args.stage,
            start=args.start,
            end=args.end,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Created task #{row['id']}: {args.title}")


def list_(args) -> None:
    rows = TaskCLI().list_tasks(project=args.project, status=args.status)
    if not rows:
        print("No tasks.")
        return
    for row in rows:
        print(_format(row))
        print()


def show(args) -> None:
    try:
        row = TaskCLI().get_task(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(_format(row))


def update(args) -> None:
    try:
        TaskCLI().update_task(
            args.id,
            title=args.title,
            description=args.description,
            status=args.status,
            assigned_to=args.assigned_to,
            stage=args.stage,
            start=args.start,
            end=args.end,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Updated task #{args.id}")


def delete(args) -> None:
    try:
        TaskCLI().delete_task(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[-] Deleted task #{args.id}")
