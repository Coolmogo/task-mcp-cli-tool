import sys

from ..api import TaskCLI, TaskCLIError


def _format(row: dict) -> str:
    return (
        f"#{row['id']}: {row['title']}\n"
        f"  description: {row['description']}\n"
        f"  dates:       {row['start_date']} -> {row['end_date']}\n"
        f"  stages:      {row['no_of_stages']}"
    )


def add(args) -> None:
    api = TaskCLI()
    try:
        row = api.add_project(
            title=args.title,
            description=args.description,
            start=args.start,
            end=args.end,
            stages=args.stages,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Created project #{row['id']}: {args.title}")


def list_(args) -> None:
    rows = TaskCLI().list_projects()
    if not rows:
        print("No projects.")
        return
    for row in rows:
        print(_format(row))
        print()


def show(args) -> None:
    try:
        row = TaskCLI().get_project(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(_format(row))


def update(args) -> None:
    try:
        TaskCLI().update_project(
            args.id,
            title=args.title,
            description=args.description,
            start=args.start,
            end=args.end,
            stages=args.stages,
        )
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[+] Updated project #{args.id}")


def delete(args) -> None:
    try:
        TaskCLI().delete_project(args.id)
    except TaskCLIError as e:
        sys.exit(str(e))
    print(f"[-] Deleted project #{args.id} (and its tasks)")
