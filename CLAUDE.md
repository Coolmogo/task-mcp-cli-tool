# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`task` is a pipx-installable CLI plus MCP server that manages **Tasks**, each with an auto-recorded **activity history** and free-text **comments**, persisted in a Supabase Postgres database. **Projects are shelved** — the project table, dataclass, `TaskCLI` methods, CLI parser, and MCP tools are all kept as clearly-labeled *dead code* to reintroduce later, but nothing wires them into the active CLI/MCP surface. User-facing setup, install, and full command reference live in [`README.md`](./README.md) — read it for context the first time you touch this repo, but don't duplicate it here.

The codebase is split into one execution layer and two clients:

- `task_program/` — execution layer. `TaskCLI` class + Supabase access. No CLI or MCP code.
- `task_cli/` — CLI client. Imports `TaskCLI` from `task_program`.
- `task_mcp/` — MCP server client. Imports `TaskCLI` from `task_program`.

`task_cli` and `task_mcp` are peers; both consume the same execution-layer API. Adding another client (web service, alternative MCP variant) means a new sibling package, not changes to `task_program`.

## Run during development

```bash
pip install -e .              # editable install — registers the `task` command
python -m task_cli --help     # invoke without going through pipx
python -m task_mcp            # launch the MCP server
```

`task` (installed via pipx or `pip install -e .`) and `python -m task_cli` both dispatch through `task_cli/cli.py:main`, which calls `TaskCLI` methods from `task_program`.

`pipx install .` snapshots the source — re-run with `pipx install --force --editable .` after code changes. Prefer `pipx install --editable .` from the start so edits take effect without reinstalling.

## Architecture

```
task_program/           # execution layer (library only)
├── __init__.py         #   exports TaskCLI, TaskCLIError (from .program)
├── program.py          #   TaskCLI class — validation, activity logging + Supabase calls
├── db.py               #   cached Supabase client; reads SUPABASE_URL/KEY from .env
└── models.py           #   Task, ActivityLog, Comment, User dataclasses; Status/ActivityType/ActivityAction enums; Project (dead)

task_cli/               # CLI client
├── cli.py              #   argparse: entity (task|comment|activity) -> verb -> args.func dispatch
├── __main__.py         #   `python -m task_cli` shim
└── commands/
    ├── task.py         #   CLI adapters for task verbs
    ├── comment.py      #   CLI adapters for comment verbs
    ├── activity.py     #   CLI adapter for `activity list`
    └── project.py      #   CLI adapters for project verbs (dead: not dispatched)

task_mcp/               # MCP server client (optional [mcp] extra)
├── __main__.py         #   `python -m task_mcp` shim
└── server.py           #   FastMCP server; one tool per active TaskCLI method (project tools dead)

schema.sql              # fresh-install Supabase DDL (idempotent)
migration.sql           # ad-hoc ALTERs to reshape an existing DB to the current model
```

**CLI dispatch flow:** `task_cli/cli.py` builds nested argparse subparsers (entity → verb), attaches a `func` default per verb pointing at a function in `task_cli/commands/*.py`, and `main()` calls `args.func(args)`. `main()` registers the `task`, `comment`, and `activity` entities; `_build_project_parser` is defined but intentionally **not called** (dead). Each command function instantiates `TaskCLI()` from `task_program`, calls the matching method inside a `try`, catches `TaskCLIError`, and either `sys.exit(str(e))` or prints a confirmation. Command functions read `args.*` directly — they don't reconstruct dataclasses.

**MCP wiring:** `task_mcp/server.py` registers one `@mcp.tool()` per active `TaskCLI` method via a `_api()` singleton. On `TaskCLIError`, it returns `f"Error: {e}"` instead of exiting. The `*_project` functions are kept with their `@mcp.tool()` decorators **commented out**, so they don't appear to Claude Desktop.

**DB access:** every `TaskCLI` method calls `self._client.table("...").<op>().execute()` directly. The shared `client()` from `task_program/db.py` is `lru_cache`d so the Supabase client is built once per process. There is intentionally no ORM/repository layer.

## Conventions and gotchas

- **`status` is free text** (`tasks.status text not null default 'To Do'`). There is no longer a `task_status` Postgres enum. `Status` in `task_program/models.py` is just a set of *suggested* values + `DEFAULT_STATUS`; it is not enforced and the CLI/MCP accept any string. Don't reintroduce `choices=`/`Literal` constraints on status.
- **History is auto-logged.** `update_task` diffs the current row against the update payload and inserts one `activities` row per changed field via `TaskCLI._log_activity`. The `_ACTIVITY_FIELDS` map in `program.py` decides the activity `field` (Dart camelCase, e.g. `dueDate`, `stageId`) and `action` (`updated`/`assigned`/`moved`); clearing a field to `NULL` becomes `removed`. Comments are NOT auto-logged — they go through `add_comment` only.
- **`get_task` assembles embedded lists.** It returns the task row plus `activities` and `comments` keys (separate selects), so the shape matches the Dart `Task` model. `list_tasks` does not embed them.
- **`users` / `assignee_id` / `author_id` are dead structure.** The `users` table exists and is referenced by `tasks.assignee_id` and the `author_id` columns on `activities`/`comments`, but user management isn't built yet — these are always `NULL`. Task assignment is non-functional until users are reintroduced. Don't add user CRUD without revisiting this.
- **Date handling:** argparse parses with the `_date` type adapter in `task_cli/cli.py` (returns `datetime.date`). `TaskCLI` methods accept either `date` or ISO strings and normalize via `_to_date`. Insert payloads call `.isoformat()`. Tasks now have a single nullable `due_date` (no start/end); the old `end >= start` validation only survives in the dead project methods.
- **CLI errors exit with `sys.exit("message")`**, not raised exceptions, so users see one clean line with no traceback. The execution layer raises `TaskCLIError`; the CLI adapter is what translates that into `sys.exit`. Don't replace these patterns.
- **MCP errors return `f"Error: {e}"`** strings. The MCP layer never raises out to Claude Desktop.
- **Multi-word flags use `dest=`** — e.g. `--stage-id` arrives as `args.stage_id`, `--assignee` maps to `dest="assignee_id"`.
- **`schema.sql` is idempotent** (`if not exists`); `migration.sql` is the path for reshaping an existing DB and is destructive (drops `start_date`/`end_date`/`assigned_to`). `schema.sql` creates referenced tables (`users`, `projects`) before `tasks` because of FKs.
- **`.env` discovery** in `task_program/db.py` walks up from cwd via `find_dotenv(usecwd=True)`, then falls back to `~/.config/taskcli/.env`. The fallback dir name is the legacy `taskcli` (not `task`) so existing user configs continue to work — if you change it, update the README and warn existing users.
- **RLS is disabled on every table** (`users`, `tasks`, `activities`, `comments`, and dead `projects`) in `schema.sql` because this is a single-user local tool using a publishable/anon key. Any new table needs its own `alter table ... disable row level security;` line, or callers will hit `42501 row-level security` errors.

## Adding a new field

1. Edit `schema.sql` (fresh installs) and add the `ALTER TABLE` to `migration.sql`, then run it in the Supabase SQL editor.
2. Update the dataclass in `task_program/models.py`.
3. Update the relevant `TaskCLI` method(s) in `task_program/program.py` — add the parameter to `add_*` and to the keyword-only block on `update_*`, and include it in the payload dict on both paths. If the new field should appear in the task's history, add it to `_ACTIVITY_FIELDS`.
4. Add the argparse argument in `task_cli/cli.py` to **both** the `add` and `update` verbs for that entity. Wire the new arg into the matching call in `task_cli/commands/*.py`.
5. Add the parameter to the matching MCP tool in `task_mcp/server.py` (with a sensible `Optional[...] = None` default for update).
6. If the README's command examples reference the new field, update them too.

## Keep the README in sync

After any significant change — new command, new field, changed flag, changed validation rule, changed install/config flow, or anything else that alters user-facing behavior — update [`README.md`](./README.md) in the same change. The README is the user-facing source of truth; if it drifts, users get wrong instructions. Trivial refactors and internal-only changes don't require a README update.

## What NOT to add

- No ORM, no repository pattern — the codebase is small enough that direct `self._client.table()` calls inside `TaskCLI` win on readability.
- No interactive prompts — every command must be scriptable.
- No colored / table output — keep stdout plain text so it pipes cleanly.
- No offline mode — Supabase is the source of truth; local caching would diverge.
- No CLI or MCP imports inside `task_program/` — the execution layer must stay client-agnostic.
