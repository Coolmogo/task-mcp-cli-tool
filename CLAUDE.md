# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`task` is a pipx-installable CLI plus MCP server that manages **Tasks**, each with an auto-recorded **activity history**, free-text **comments**, and AI-suggested **proposals**, persisted in a **SurrealDB** database (Surreal Cloud; namespace/database `main`). The `activity` table is the **parent/wrapper** over its subtypes: each `comment` and each `proposal` has a 1:1 parent `activity` row and points up to it via an `activity` link (see the activity-as-parent gotcha below). **Projects are shelved** — the project table, dataclass, `TaskCLI` methods, CLI parser, and MCP tools are all kept as clearly-labeled *dead code* to reintroduce later, but nothing wires them into the active CLI/MCP surface. User-facing setup, install, and full command reference live in [`README.md`](./README.md) — read it for context the first time you touch this repo, but don't duplicate it here.

The codebase is split into one execution layer and two clients:

- `task_program/` — execution layer. `TaskCLI` class + SurrealDB access. No CLI or MCP code.
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
├── program.py          #   TaskCLI class — validation, activity logging, _normalize + SurrealDB calls
├── db.py               #   cached Surreal client; reads SURREALDB_URL/USER/PASS/NS/DB from .env, signs in as root
└── models.py           #   Task, ActivityLog, Comment, Proposal, User dataclasses (string ids); Status/ActivityType/ActivityAction enums; Project (dead)

task_cli/               # CLI client
├── cli.py              #   argparse: entity (task|comment|activity) -> verb -> args.func dispatch
├── __main__.py         #   `python -m task_cli` shim
└── commands/
    ├── task.py         #   CLI adapters for task verbs
    ├── comment.py      #   CLI adapters for comment verbs
    ├── proposal.py     #   CLI adapters for proposal verbs (add/list/show/accept/delete)
    ├── activity.py     #   CLI adapter for `activity list`
    └── project.py      #   CLI adapters for project verbs (dead: not dispatched)

task_mcp/               # MCP server client (optional [mcp] extra)
├── __main__.py         #   `python -m task_mcp` shim
└── server.py           #   FastMCP server; one tool per active TaskCLI method (project tools dead)

schema.surql            # fresh-install SurrealDB schema (DEFINE TABLE/FIELD, IF NOT EXISTS — idempotent)
reset.surql             # wipes all records, keeps the schema (DELETE per table)
```

**CLI dispatch flow:** `task_cli/cli.py` builds nested argparse subparsers (entity → verb), attaches a `func` default per verb pointing at a function in `task_cli/commands/*.py`, and `main()` calls `args.func(args)`. `main()` registers the `task`, `comment`, `proposal`, and `activity` entities; `_build_project_parser` is defined but intentionally **not called** (dead). Each command function instantiates `TaskCLI()` from `task_program`, calls the matching method inside a `try`, catches `TaskCLIError`, and either `sys.exit(str(e))` or prints a confirmation. Command functions read `args.*` directly — they don't reconstruct dataclasses.

**MCP wiring:** `task_mcp/server.py` registers one `@mcp.tool()` per active `TaskCLI` method via a `_api()` singleton. On `TaskCLIError`, it returns `f"Error: {e}"` instead of exiting. The `*_project` functions are kept with their `@mcp.tool()` decorators **commented out**, so they don't appear to Claude Desktop.

**DB access:** every `TaskCLI` method calls the SurrealDB SDK directly — `self._client.create(table, payload)`, `.merge(rid, payload)`, `.delete(rid)`, and `.query(surql, vars)`. The shared `client()` from `task_program/db.py` is `lru_cache`d so the Surreal client is connected and signed in once per process. There is intentionally no ORM/repository layer.

**Record ids are strings.** SurrealDB ids look like `task:8f3k` (a `RecordID`), **not** auto-increment integers — `add_task` lets SurrealDB assign them (`create("task", ...)`), there is no counter. The CLI/MCP/REST clients accept and emit these id strings. Inside `TaskCLI`, `self._rid(id)` coerces a string id into a `RecordID` (raising `TaskCLIError` on a malformed id) for every lookup/merge/delete; pass `RecordID` params into `query` via `vars`, never string-interpolate them.

**Results are normalized.** SurrealDB returns `RecordID`/`datetime` objects, stores links under bare names (`assignee`, `project`, `task`, `author`), and SCHEMAFULL **omits null `option<>` fields**. `_normalize(raw, keys)` in `program.py` reproduces the original dict contract: `RecordID`→str, `datetime`→ISO string, links renamed to `*_id`, and the full key set filled (missing → `None`) so clients can `.get(...)` safely. Every method returns `_normalize(...)` output, never raw SDK rows. The `_TASK_KEYS`/`_ACTIVITY_KEYS`/`_COMMENT_KEYS`/`_PROPOSAL_KEYS`/`_PROJECT_KEYS` tuples define those contracts — update them when you add a field. The `activity` bare-name link (the comment/proposal up-link to their parent wrapper) is renamed to `activity_id` by `_LINK_RENAMES`.

## Conventions and gotchas

- **`status` is free text** (`DEFINE FIELD status ON task TYPE string DEFAULT 'To Do'`). There is no enum. `Status` in `task_program/models.py` is just a set of *suggested* values + `DEFAULT_STATUS`; it is not enforced and the CLI/MCP accept any string. Don't reintroduce `choices=`/`Literal` constraints on status.
- **History is auto-logged.** `update_task` diffs the current row against the update payload and inserts one `activities` row per changed field via `TaskCLI._log_activity`. The `_ACTIVITY_FIELDS` map in `program.py` decides the activity `field` (Dart camelCase, e.g. `dueDate`, `stageId`) and `action` (`updated`/`assigned`/`moved`); clearing a field to `NULL` becomes `removed`. Comments and proposals are NOT diff-logged, but each one still creates a parent `activity` row (see next bullet).
- **`activity` is the parent/wrapper feed.** Three subtypes share the table via `type`: `history` (auto-logged field changes), `comment`, and `proposal`. `add_comment` and `add_proposal` each first create a parent `activity` row through `TaskCLI._create_activity_wrapper(task_rid, type_, action)` (action `commented`/`proposed`), then create the child row with its `activity` link pointing **up** to that wrapper (the child also keeps its own `task` link — intentional duplication, kept additive). Subtype detail (comment `text`, proposal `title`/fields) lives on the child, **not** on the wrapper, so wrapper rows have null `text`/`field`. `list_activities` therefore returns the full feed (history + comment + proposal wrappers); `get_task` embeds `activities`, `comments`, **and** `proposals`. The `update` subtype is deferred — there is no `update` child table yet.
- **Proposals are AI-suggested tasks.** A `proposal` mirrors a creatable task (`title`/`description`/`status`/`stage_id`/`assignee_id`). `accept_proposal(id)` calls `add_task(...)` from those fields and merges the new task id into the proposal's `created_task_id`. `assignee_id`/`created_task_id` are plain id **strings** on the proposal row (not record links), matching the client contract. `delete_proposal` removes the proposal's parent `activity` wrapper too; `delete_task` cascades `DELETE proposal WHERE task = $t` (the comment/proposal wrappers are already cleared by the existing `DELETE activity WHERE task = $t`).
- **`get_task` embeds via one query.** A single SurrealQL `SELECT *, (SELECT … WHERE task = $t) AS activities, (SELECT … WHERE task = $t) AS comments, (SELECT … WHERE task = $t) AS proposals FROM $t` returns the task row with embedded `activities`, `comments`, and `proposals`, matching the Dart `Task` model. `list_tasks` does not embed them.
- **`user` / `assignee` / `author` are dead structure.** The `user` table exists and is referenced by the `task.assignee` and `activity.author`/`comment.author` record links, but user management isn't built yet — these are always `NULL` (and SCHEMAFULL omits them from results, so `_normalize` fills `assignee_id`/`author_id` as `None`). Task assignment is non-functional until users are reintroduced. Don't add user CRUD without revisiting this.
- **Date handling:** argparse parses with the `_date` type adapter in `task_cli/cli.py` (returns `datetime.date`). `TaskCLI` methods accept either `date` or ISO strings and normalize via `_to_date`. `due_date` is stored as a `'YYYY-MM-DD'` **string** field in SurrealDB (not a `datetime`) so it round-trips to clients unchanged with no timezone games; payloads call `.isoformat()`. `created_at` is a real `datetime DEFAULT time::now()` (used for `ORDER BY`), normalized to an ISO string on read. The old `end >= start` validation only survives in the dead project methods.
- **CLI errors exit with `sys.exit("message")`**, not raised exceptions, so users see one clean line with no traceback. The execution layer raises `TaskCLIError`; the CLI adapter is what translates that into `sys.exit`. Don't replace these patterns.
- **MCP errors return `f"Error: {e}"`** strings. The MCP layer never raises out to Claude Desktop.
- **Multi-word flags use `dest=`** — e.g. `--stage-id` arrives as `args.stage_id`, `--assignee` maps to `dest="assignee_id"`.
- **`schema.surql` is idempotent** (every statement is `DEFINE ... IF NOT EXISTS`); import it via the Surrealist query editor or `surreal import`. `reset.surql` wipes all records while keeping the schema (`DELETE` per table). Record links are loose references, so table definition order doesn't matter the way Postgres FK ordering did. There is no FK cascade — `delete_task` removes child `activity`/`comment`/`proposal` records explicitly before deleting the task.
- **`.env` discovery** in `task_program/db.py` walks up from cwd via `find_dotenv(usecwd=True)`, then falls back to `~/.config/taskcli/.env`. The fallback dir name is the legacy `taskcli` (not `task`) so existing user configs continue to work — if you change it, update the README and warn existing users.
- **No table permissions / RLS.** The connection signs in as **root** (`db.py`), which bypasses table `PERMISSIONS` entirely — this is the single-user analog of "RLS off everywhere". `schema.surql` therefore needs no per-table permission lines, and new tables need nothing special. Don't add `DEFINE ACCESS`/record-user auth without revisiting `db.py`.

## Adding a new field

1. Edit `schema.surql` — add a `DEFINE FIELD <name> ON <table> TYPE ... IF NOT EXISTS` line, then re-run the file in the Surrealist query editor (or `surreal import`). On an existing instance the new `DEFINE FIELD` just adds the field.
2. Update the dataclass in `task_program/models.py`.
3. Update the relevant `TaskCLI` method(s) in `task_program/program.py` — add the parameter to `add_*` and to the keyword-only block on `update_*`, and include it in the payload dict on both paths. Add the field's client-facing key to the matching `_TASK_KEYS`/`_ACTIVITY_KEYS`/`_COMMENT_KEYS` tuple so `_normalize` returns it. If it's a **record link**, store it in the payload under the bare DB name (e.g. `assignee`) wrapped via `self._rid(...)`, and add the `bare_name -> name_id` entry to `_LINK_RENAMES`. If the new field should appear in the task's history, add it to `_ACTIVITY_FIELDS` (keyed by the client-facing field name).
4. Add the argparse argument in `task_cli/cli.py` to **both** the `add` and `update` verbs for that entity. Wire the new arg into the matching call in `task_cli/commands/*.py`.
5. Add the parameter to the matching MCP tool in `task_mcp/server.py` (with a sensible `Optional[...] = None` default for update).
6. If the README's command examples reference the new field, update them too.

## Keep the README in sync

After any significant change — new command, new field, changed flag, changed validation rule, changed install/config flow, or anything else that alters user-facing behavior — update [`README.md`](./README.md) in the same change. The README is the user-facing source of truth; if it drifts, users get wrong instructions. Trivial refactors and internal-only changes don't require a README update.

## What NOT to add

- No ORM, no repository pattern — the codebase is small enough that direct `self._client.create()/merge()/query()` calls inside `TaskCLI` win on readability.
- No interactive prompts — every command must be scriptable.
- No colored / table output — keep stdout plain text so it pipes cleanly.
- No offline mode — SurrealDB is the source of truth; local caching would diverge.
- No CLI or MCP imports inside `task_program/` — the execution layer must stay client-agnostic.
