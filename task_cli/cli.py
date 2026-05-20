import argparse
from datetime import date

from task_program.models import Status

from .commands import project as project_cmd
from .commands import task as task_cmd


STATUS_CHOICES = [s.value for s in Status]


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")


def _build_project_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("project", help="Manage projects")
    verbs = p.add_subparsers(dest="verb", required=True)

    add = verbs.add_parser("add", help="Create a project")
    add.add_argument("--title", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--start", required=True, type=_date, help="YYYY-MM-DD")
    add.add_argument("--end", required=True, type=_date, help="YYYY-MM-DD")
    add.add_argument("--stages", required=True, type=int)
    add.set_defaults(func=project_cmd.add)

    lst = verbs.add_parser("list", help="List all projects")
    lst.set_defaults(func=project_cmd.list_)

    show = verbs.add_parser("show", help="Show one project")
    show.add_argument("id", type=int)
    show.set_defaults(func=project_cmd.show)

    upd = verbs.add_parser("update", help="Update fields on a project")
    upd.add_argument("id", type=int)
    upd.add_argument("--title")
    upd.add_argument("--description")
    upd.add_argument("--start", type=_date)
    upd.add_argument("--end", type=_date)
    upd.add_argument("--stages", type=int)
    upd.set_defaults(func=project_cmd.update)

    dele = verbs.add_parser("delete", help="Delete a project (cascades to tasks)")
    dele.add_argument("id", type=int)
    dele.set_defaults(func=project_cmd.delete)


def _build_task_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("task", help="Manage tasks")
    verbs = p.add_subparsers(dest="verb", required=True)

    add = verbs.add_parser("add", help="Create a task")
    add.add_argument("--project", required=True, type=int, help="Project ID")
    add.add_argument("--title", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--status", choices=STATUS_CHOICES, default=Status.TODO.value)
    add.add_argument("--assigned-to", dest="assigned_to", default="")
    add.add_argument("--stage", required=True, type=int)
    add.add_argument("--start", required=True, type=_date, help="YYYY-MM-DD")
    add.add_argument("--end", required=True, type=_date, help="YYYY-MM-DD")
    add.set_defaults(func=task_cmd.add)

    lst = verbs.add_parser("list", help="List tasks (optionally filter)")
    lst.add_argument("--project", type=int, default=None)
    lst.add_argument("--status", choices=STATUS_CHOICES, default=None)
    lst.set_defaults(func=task_cmd.list_)

    show = verbs.add_parser("show", help="Show one task")
    show.add_argument("id", type=int)
    show.set_defaults(func=task_cmd.show)

    upd = verbs.add_parser("update", help="Update fields on a task")
    upd.add_argument("id", type=int)
    upd.add_argument("--title")
    upd.add_argument("--description")
    upd.add_argument("--status", choices=STATUS_CHOICES, default=None)
    upd.add_argument("--assigned-to", dest="assigned_to")
    upd.add_argument("--stage", type=int)
    upd.add_argument("--start", type=_date)
    upd.add_argument("--end", type=_date)
    upd.set_defaults(func=task_cmd.update)

    dele = verbs.add_parser("delete", help="Delete a task")
    dele.add_argument("id", type=int)
    dele.set_defaults(func=task_cmd.delete)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="task",
        description="Manage projects and tasks backed by Supabase",
    )
    sub = parser.add_subparsers(dest="entity", required=True)
    _build_project_parser(sub)
    _build_task_parser(sub)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
