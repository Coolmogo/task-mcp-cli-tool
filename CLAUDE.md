# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`taskcli` is a pipx-installable CLI that manages **Projects** and the **Tasks** that belong to them, persisted in a Supabase Postgres database. User-facing setup, install, and full command reference live in [`README.md`](./README.md) — read it for context the first time you touch this repo, but don't duplicate it here.

## Run during development

```bash
pip install -e .            # editable install
python -m taskcli --help    # invoke without going through pipx
```

`taskcli` (installed via pipx or `pip install -e .`) and `python -m taskcli` both dispatch through `taskcli/cli.py:main`.

`pipx install .` snapshots the source — re-run with `pipx install --force --editable .` (or `pipx reinstall taskcli`) after code changes. Prefer `pipx install --editable .` from the start so edits take effect without reinstalling.

## Architecture

```
taskcli/
├── cli.py              # argparse: entity (project|task) -> verb -> args.func dispatch
├── __main__.py         # `python -m taskcli` shim
├── db.py               # cached Supabase client; reads SUPABASE_URL/KEY from .env
├── models.py           # Project, Task dataclasses + Status enum
└── commands/
    ├── project.py      # CRUD on `projects`
    └── task.py         # CRUD on `tasks` + cross-table validation
schema.sql              # one-shot Supabase DDL (idempotent)
```

**Dispatch flow:** `cli.py` builds nested argparse subparsers (entity → verb), attaches a `func` default per verb pointing at the matching `commands/*.py` function, and `main()` calls `args.func(args)`. Command functions read `args.*` directly — they don't reconstruct dataclasses from argparse output.

**DB access:** every command calls `client().table("...").<op>().execute()` directly. `client()` is `lru_cache`d so the Supabase client is built once per process. There is intentionally no ORM/repository layer.

## Conventions and gotchas

- **`task_status` Postgres enum mirrors `Status` in `models.py`.** Adding/renaming a status means a SQL migration *and* a Python enum change — keep them in sync.
- **`tasks.stage` upper bound (`<= projects.no_of_stages`) is enforced in the CLI**, not in SQL. Postgres CHECK can't reference another table without a trigger, and the CLI gives a friendlier error. Validation lives in `commands/task.py::_validate_stage`.
- **Date handling:** argparse parses with the `_date` type adapter in `cli.py` (returns `datetime.date`). Insert payloads call `.isoformat()`. When merging existing rows for re-validation on `update`, fields come back as ISO strings — convert with `date.fromisoformat()` before comparing.
- **Errors exit with `sys.exit("message")`**, not raised exceptions. This produces a clean message with no traceback, matching the validation table in the README. Don't replace these with `raise`.
- **`assigned_to` arrives from argparse via `dest="assigned_to"`** because the flag is `--assigned-to`. Other multi-word fields use the same pattern.
- **`schema.sql` is idempotent** (`if not exists` + `do $$ ... $$` for the enum). Re-running it must be safe.
- **`.env` discovery walks up from cwd** via `find_dotenv(usecwd=True)` in `db.py`. The CLI works from any subdirectory of the project but *not* from unrelated dirs (e.g. `C:\Windows\System32`). If you add a fallback location (e.g. `~/.config/taskcli/.env`), update the README too.
- **RLS is disabled on `projects` and `tasks`** in `schema.sql` because this is a single-user local CLI using a publishable/anon key. Any new table added to `schema.sql` needs its own `alter table ... disable row level security;` line, or callers will hit `42501 row-level security` errors.

## Adding a new field

1. Edit `schema.sql` and run an `ALTER TABLE` in Supabase (the SQL editor accepts ad-hoc `ALTER`s — `schema.sql` itself just needs to reflect the new shape for fresh installs).
2. Update the dataclass in `models.py`.
3. Add the argparse argument in `cli.py` to **both** the `add` and `update` verbs for that entity. Required on `add`, optional on `update`.
4. Add the field to the payload dict in the matching `commands/*.py` function (insert path *and* the conditional update path).
5. If the README's command examples reference the new field, update them too.

## Keep the README in sync

After any significant change — new command, new field, changed flag, changed validation rule, changed install/config flow, or anything else that alters user-facing behavior — update [`README.md`](./README.md) in the same change. The README is the user-facing source of truth; if it drifts, users get wrong instructions. Trivial refactors and internal-only changes don't require a README update.

## What NOT to add

- No ORM, no repository pattern — the codebase is small enough that direct `client().table()` calls win on readability.
- No interactive prompts — every command must be scriptable.
- No colored / table output — keep stdout plain text so it pipes cleanly.
- No offline mode — Supabase is the source of truth; local caching would diverge.
