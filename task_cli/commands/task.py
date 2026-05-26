import sys

from task_program import TaskCLI, TaskCLIError


def _format(row: dict) -> str:
    return (
        f"[{row['status']:<12}] #{row['id']}: {row['title']}\n"
        f"  description: {row.get('description') or '-'}\n"
        f"  due:         {row.get('due_date') or '-'}\n"
        f"  assignee:    {row.get('assignee_id') or '-'}\n"
        f"  stage:       {row.get('stage_id') or '-'}"
    )


def _format_activity(row: dict) -> str:
    parts = [f"  - [{row['action']}]"]
    if row.get("field"):
        parts.append(row["field"])
    if row.get("old_value") is not None or row.get("new_value") is not None:
        parts.append(f"{row.get('old_value')!r} -> {row.get('new_value')!r}")
    if row.get("text"):
        parts.append(row["text"])
    parts.append(f"({row.get('created_at')})")
    return " ".join(parts)


def add(args) -> None:
    try:
        row = TaskCLI().add_task(
            title=args.title,
            description=args.description,
            status=args.status,
            assignee_id=args.assignee_id,
            stage_id=args.stage_id,
            due=args.due,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Created task #{row['id']}: {args.title}")


def list_(args) -> None:
    rows = TaskCLI().list_tasks(status=args.status)
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

    activities = row.get("activities") or []
    print(f"  activity:    {len(activities)} entr{'y' if len(activities) == 1 else 'ies'}")
    for act in activities:
        print(_format_activity(act))

    comments = row.get("comments") or []
    print(f"  comments:    {len(comments)}")
    for c in comments:
        print(f"  - {c['text']} ({c.get('created_at')})")


def update(args) -> None:
    try:
        TaskCLI().update_task(
            args.id,
            title=args.title,
            description=args.description,
            status=args.status,
            assignee_id=args.assignee_id,
            stage_id=args.stage_id,
            due=args.due,
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
