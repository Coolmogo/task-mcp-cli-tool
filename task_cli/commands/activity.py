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
        activity_type = row.get("type", "unknown")
        line = f"#{row['id']} [{activity_type}]"

        # Audit log format: (verb) -> (to_actor) -> (message)
        if row.get("target_name"):
            line += f" -> {row.get('target_name')}"

        if activity_type == "update":
            if row.get("action"):
                line += f" {row['action']}"
            if row.get("field"):
                line += f" {row['field']}"
            if row.get("old_value") is not None or row.get("new_value") is not None:
                line += f": {row.get('old_value')!r} -> {row.get('new_value')!r}"
        elif activity_type in ("ask", "instruct", "propose"):
            if row.get("content"):
                line += f" -> {row.get('content')!r}"
            elif row.get("proposal_title"):
                line += f" -> {row.get('proposal_title')!r}"
        elif activity_type == "decide":
            proposal_id = row.get("proposal_activity_id")
            line += f" -> accepted {proposal_id}"
            if row.get("content"):
                line += f": {row.get('content')!r}"
        elif activity_type == "dismiss":
            proposal_id = row.get("proposal_activity_id")
            line += f" -> rejected {proposal_id}"
            if row.get("content"):
                line += f": {row.get('content')!r}"

        line += f" ({row.get('created_at')})"
        print(line)


def decide_proposal(args) -> None:
    try:
        message = getattr(args, "message", None)
        result = TaskCLI().accept_proposal(args.activity_id, message=message)
        print(f"Proposal accepted. Task created: {result['proposal_created_task_id']}")
    except TaskCLIError as e:
        sys.exit(str(e))


def reject_proposal(args) -> None:
    try:
        message = getattr(args, "message", None)
        result = TaskCLI().reject_proposal(args.activity_id, message=message)
        print(f"Proposal rejected.")
    except TaskCLIError as e:
        sys.exit(str(e))
