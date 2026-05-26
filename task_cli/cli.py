import argparse
from datetime import date

from task_program.models import DEFAULT_STATUS

from .commands import activity as activity_cmd
from .commands import comment as comment_cmd
from .commands import project as project_cmd  # noqa: F401  (dead: reintroduce later)
from .commands import task as task_cmd


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")


# ---- dead: reintroduce with projects later ---------------------------------
# Defined but intentionally NOT registered in main(). Re-add the
# `_build_project_parser(sub)` call to bring projects back.
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
    add.add_argument("--title", required=True)
    add.add_argument("--description", default=None)
    add.add_argument("--status", default=DEFAULT_STATUS, help=f"free text (default {DEFAULT_STATUS!r})")
    add.add_argument("--assignee", dest="assignee_id", type=int, default=None, help="user id")
    add.add_argument("--stage-id", dest="stage_id", default=None)
    add.add_argument("--due", type=_date, default=None, help="YYYY-MM-DD")
    add.set_defaults(func=task_cmd.add)

    lst = verbs.add_parser("list", help="List tasks (optionally filter by status)")
    lst.add_argument("--status", default=None)
    lst.set_defaults(func=task_cmd.list_)

    show = verbs.add_parser("show", help="Show one task with its activity and comments")
    show.add_argument("id", type=int)
    show.set_defaults(func=task_cmd.show)

    upd = verbs.add_parser("update", help="Update fields on a task")
    upd.add_argument("id", type=int)
    upd.add_argument("--title")
    upd.add_argument("--description")
    upd.add_argument("--status", default=None)
    upd.add_argument("--assignee", dest="assignee_id", type=int, default=None, help="user id")
    upd.add_argument("--stage-id", dest="stage_id", default=None)
    upd.add_argument("--due", type=_date, default=None, help="YYYY-MM-DD")
    upd.set_defaults(func=task_cmd.update)

    dele = verbs.add_parser("delete", help="Delete a task (cascades to its activity/comments)")
    dele.add_argument("id", type=int)
    dele.set_defaults(func=task_cmd.delete)


def _build_comment_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("comment", help="Manage task comments")
    verbs = p.add_subparsers(dest="verb", required=True)

    add = verbs.add_parser("add", help="Add a comment to a task")
    add.add_argument("--task", required=True, type=int, help="Task ID")
    add.add_argument("--text", required=True)
    add.set_defaults(func=comment_cmd.add)

    lst = verbs.add_parser("list", help="List a task's comments")
    lst.add_argument("--task", required=True, type=int, help="Task ID")
    lst.set_defaults(func=comment_cmd.list_)


def _build_activity_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("activity", help="View a task's activity history")
    verbs = p.add_subparsers(dest="verb", required=True)

    lst = verbs.add_parser("list", help="List a task's activity history")
    lst.add_argument("--task", required=True, type=int, help="Task ID")
    lst.set_defaults(func=activity_cmd.list_)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="task",
        description="Manage tasks (with activity history and comments) backed by Supabase",
    )
    sub = parser.add_subparsers(dest="entity", required=True)
    _build_task_parser(sub)
    _build_comment_parser(sub)
    _build_activity_parser(sub)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
