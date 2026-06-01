import sys

from task_program import TaskCLI, TaskCLIError


def _format(row: dict) -> str:
    accepted = row.get("created_task_id")
    return (
        f"[{row['status']:<12}] #{row['id']}: {row['title']}\n"
        f"  description:  {row.get('description') or '-'}\n"
        f"  stage:        {row.get('stage_id') or '-'}\n"
        f"  assignee:     {row.get('assignee_id') or '-'}\n"
        f"  created task: {accepted or '-'}"
    )


def add(args) -> None:
    try:
        row = TaskCLI().add_proposal(
            args.task,
            args.title,
            description=args.description,
            status=args.status,
            stage_id=args.stage_id,
            assignee_id=args.assignee_id,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Added proposal #{row['id']} to task #{args.task}")


def list_(args) -> None:
    try:
        rows = TaskCLI().list_proposals(args.task)
    except TaskCLIError as e:
        sys.exit(str(e))
    if not rows:
        print("No proposals.")
        return
    for row in rows:
        print(_format(row))
        print()


def show(args) -> None:
    try:
        row = TaskCLI().get_proposal(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(_format(row))


def accept(args) -> None:
    try:
        task = TaskCLI().accept_proposal(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Accepted proposal #{args.id} -> created task #{task['id']}")


def delete(args) -> None:
    try:
        TaskCLI().delete_proposal(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[-] Deleted proposal #{args.id}")
