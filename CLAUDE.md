# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`task` is a pipx-installable CLI plus MCP server that manages **Projects** and the **Tasks** that belong to them, persisted in a Supabase Postgres database. User-facing setup, install, and full command reference live in [`README.md`](./README.md) — read it for context the first time you touch this repo, but don't duplicate it here.

The codebase is split into one execution layer and three clients:

- `task_program/` — execution layer. `TaskCLI` class + Supabase access. No CLI or MCP code.
- `task_cli/` — CLI client. Imports `TaskCLI` from `task_program`.
- `task_mcp/` — MCP server client. Imports `TaskCLI` from `task_program`.
- `task_api/` — REST API client. Imports `TaskCLI` from `task_program`.

`task_cli`, `task_mcp`, and `task_api` are peers; all consume the same execution-layer API. Adding another client (web service, alternative MCP variant) means a new sibling package, not changes to `task_program`.

## Run during development

```bash
pip install -e .              # editable install — registers the `task` command
python -m task_cli --help     # invoke without going through pipx
python -m task_mcp            # launch the MCP server
python -m task_api            # launch the REST API
```

`task` (installed via pipx or `pip install -e .`) and `python -m task_cli` both dispatch through `task_cli/cli.py:main`, which calls `TaskCLI` methods from `task_program`.

`pipx install .` snapshots the source — re-run with `pipx install --force --editable .` after code changes. Prefer `pipx install --editable .` from the start so edits take effect without reinstalling.

## Architecture

```
task_program/           # execution layer (library only)
├── __init__.py         #   exports TaskCLI, TaskCLIError
├── program.py          #   TaskCLI class — validation + Supabase calls
├── db.py               #   cached Supabase client; reads SUPABASE_URL/KEY from .env
└── models.py           #   Project, Task dataclasses + Status enum

task_cli/               # CLI client
├── cli.py              #   argparse: entity (project|task) -> verb -> args.func dispatch
├── __main__.py         #   `python -m task_cli` shim
└── commands/
    ├── project.py      #   CLI adapters for project verbs (formatting + sys.exit)
    └── task.py         #   CLI adapters for task verbs

task_mcp/               # MCP server client (optional [mcp] extra)
├── __main__.py         #   `python -m task_mcp` shim
└── server.py           #   FastMCP server; one tool per TaskCLI method

task_api/               # REST API client
├── __main__.py         #   `python -m task_api` shim
├── app.py              #   FastAPI routes + TaskCLI error mapping
└── schemas.py          #   Pydantic request/response models

schema.sql              # one-shot Supabase DDL (idempotent)
```

**CLI dispatch flow:** `task_cli/cli.py` builds nested argparse subparsers (entity → verb), attaches a `func` default per verb pointing at a function in `task_cli/commands/*.py`, and `main()` calls `args.func(args)`. Each command function instantiates `TaskCLI()` from `task_program`, calls the matching method inside a `try`, catches `TaskCLIError`, and either `sys.exit(str(e))` or prints a confirmation. Command functions read `args.*` directly — they don't reconstruct dataclasses.

**MCP wiring:** `task_mcp/server.py` registers one `@mcp.tool()` per `TaskCLI` method via a `_api()` singleton. On `TaskCLIError`, it returns `f"Error: {e}"` instead of exiting.

**DB access:** every `TaskCLI` method calls `self._client.table("...").<op>().execute()` directly. The shared `client()` from `task_program/db.py` is `lru_cache`d so the Supabase client is built once per process. There is intentionally no ORM/repository layer.

## Conventions and gotchas

- **`task_status` Postgres enum mirrors `Status` in `task_program/models.py`.** Adding/renaming a status means a SQL migration _and_ a Python enum change — keep them in sync.
- **`tasks.stage` upper bound (`<= projects.no_of_stages`) is enforced in `TaskCLI`**, not in SQL. Postgres CHECK can't reference another table without a trigger, and the in-code message is friendlier. Validation lives in `task_program/program.py::TaskCLI._validate_stage`.
- **Date handling:** argparse parses with the `_date` type adapter in `task_cli/cli.py` (returns `datetime.date`). `TaskCLI` methods accept either `date` or ISO strings and normalize via `_to_date`. Insert payloads call `.isoformat()`.
- **CLI errors exit with `sys.exit("message")`**, not raised exceptions, so users see one clean line with no traceback. The execution layer raises `TaskCLIError`; the CLI adapter is what translates that into `sys.exit`. Don't replace these patterns.
- **MCP errors return `f"Error: {e}"`** strings. The MCP layer never raises out to Claude Desktop.
- **`assigned_to` arrives from argparse via `dest="assigned_to"`** because the flag is `--assigned-to`. Other multi-word fields use the same pattern.
- **`schema.sql` is idempotent** (`if not exists` + `do $$ ... $$` for the enum). Re-running it must be safe.
- **`.env` discovery** in `task_program/db.py` walks up from cwd via `find_dotenv(usecwd=True)`, then falls back to `~/.config/taskcli/.env`. The fallback dir name is the legacy `taskcli` (not `task`) so existing user configs continue to work — if you change it, update the README and warn existing users.
- **RLS is disabled on `projects` and `tasks`** in `schema.sql` because this is a single-user local tool using a publishable/anon key. Any new table added to `schema.sql` needs its own `alter table ... disable row level security;` line, or callers will hit `42501 row-level security` errors.

## Adding a new field

1. Edit `schema.sql` and run an `ALTER TABLE` in Supabase (the SQL editor accepts ad-hoc `ALTER`s — `schema.sql` itself just needs to reflect the new shape for fresh installs).
2. Update the dataclass in `task_program/models.py`.
3. Update the relevant `TaskCLI` method(s) in `task_program/program.py` — add the parameter to `add_*` and to the keyword-only block on `update_*`, and include it in the payload dict on both paths.
4. Add the argparse argument in `task_cli/cli.py` to **both** the `add` and `update` verbs for that entity. Required on `add`, optional on `update`. Wire the new arg into the matching call in `task_cli/commands/*.py`.
5. Add the parameter to the matching MCP tool in `task_mcp/server.py` (with a sensible `Optional[...] = None` default for update).
6. If the REST API exposes the field, add it to `task_api/schemas.py` and the relevant route adapter in `task_api/app.py`.
7. If the README's command examples reference the new field, update them too.

## Keep the README in sync

After any significant change — new command, new field, changed flag, changed validation rule, changed install/config flow, or anything else that alters user-facing behavior — update [`README.md`](./README.md) in the same change. The README is the user-facing source of truth; if it drifts, users get wrong instructions. Trivial refactors and internal-only changes don't require a README update.

## What NOT to add

- No ORM, no repository pattern — the codebase is small enough that direct `self._client.table()` calls inside `TaskCLI` win on readability.
- No interactive prompts — every command must be scriptable.
- No colored / table output — keep stdout plain text so it pipes cleanly.
- No offline mode — Supabase is the source of truth; local caching would diverge.
- No CLI or MCP imports inside `task_program/` — the execution layer must stay client-agnostic.
