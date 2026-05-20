# taskcli

A command-line tool and Python library for managing **Projects** and the **Tasks** that belong to them, persisted in a Supabase Postgres database.

---

## Part 1 — How the system works

### 1.1 High-level architecture

`taskcli` is a thin client over a Supabase Postgres database. There are three layers, top to bottom:

1. **CLI layer** (`taskcli/cli.py`, `taskcli/commands/*.py`) — an argparse dispatcher that turns shell invocations like `taskcli project add ...` into Python function calls. Output is plain text; errors exit cleanly with no traceback.
2. **API layer** (`taskcli/api.py`) — a `TaskCLI` class that exposes the same CRUD surface as the CLI but as ordinary Python methods. It owns all validation and all Supabase calls. This is the layer other Python programs import.
3. **Database layer** (`taskcli/db.py` + `schema.sql`) — a `lru_cache`d Supabase client built once per process, plus the SQL DDL that creates the two tables and the `task_status` enum.

The CLI does not talk to Supabase directly anymore; CLI command functions are now thin adapters that call `TaskCLI` methods, catch `TaskCLIError`, and translate it into `sys.exit(message)` so the user still sees a clean one-line error.

```
shell  ──▶  cli.py (argparse)  ──▶  commands/*.py (adapters)  ──▶  api.py (TaskCLI)  ──▶  db.py (Supabase client)
                                                                       ▲
                                            other Python programs ─────┘
```

### 1.2 Data model

Two tables, one enum. The full DDL lives in [`schema.sql`](./schema.sql).

**`projects`**

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | auto |
| `title` | text | required |
| `description` | text | required, may be empty string |
| `start_date` | date | required |
| `end_date` | date | must be `>= start_date` (enforced in the API layer) |
| `no_of_stages` | int | number of phases the project moves through; must be `>= 1` |

**`tasks`**

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | auto |
| `project_id` | int FK → `projects.id` | `ON DELETE CASCADE` — deleting a project deletes its tasks |
| `title`, `description` | text | required (description may be empty) |
| `status` | `task_status` enum | one of `todo`, `in_progress`, `done` |
| `assigned_to` | text | free-form, may be empty |
| `stage` | int | must be in `1..projects.no_of_stages` (enforced in the API layer, not in SQL) |
| `start_date`, `end_date` | date | `end_date >= start_date` |

The `task_status` Postgres enum mirrors the `Status` enum in `taskcli/models.py`. They must stay in sync — adding a status requires both a SQL migration and a Python enum change.

### 1.3 Dispatch flow (CLI)

`taskcli/cli.py` builds two layers of argparse subparsers: **entity** (`project` | `task`) → **verb** (`add` | `list` | `show` | `update` | `delete`). Each verb subparser sets `func=<command_function>` as a default. `main()` parses argv and then simply calls `args.func(args)`.

Each command function in `taskcli/commands/project.py` and `taskcli/commands/task.py` does three things:

1. Reads the relevant attributes off `args` (e.g. `args.title`, `args.start`).
2. Calls the matching `TaskCLI` method inside a `try` block.
3. On `TaskCLIError`, calls `sys.exit(str(e))`. On success, prints a one-line confirmation (`[+] Created project #5: Launch v1`) or, for `list`/`show`, the formatted rows.

Formatting helpers (`_format`) live in the command modules because formatting is a CLI-only concern. The API layer returns raw dicts.

### 1.4 The `TaskCLI` class

`taskcli/api.py` defines:

- `TaskCLIError(Exception)` — raised on any validation or not-found failure. Programmatic callers catch this.
- `TaskCLI` — one method per CLI verb:
  - `add_project`, `list_projects`, `get_project`, `update_project`, `delete_project`
  - `add_task`, `list_tasks`, `get_task`, `update_task`, `delete_task`

Methods return raw row dicts (or `list[dict]` for the list variants). Date arguments accept either `datetime.date` or ISO strings (`"2026-06-01"`); the API normalizes both with `date.fromisoformat`. `status` is a plain string matching one of the enum values.

The constructor optionally accepts `supabase_url` / `supabase_key` overrides. When omitted, it falls back to the shared cached `client()` from `taskcli/db.py`, which means the same `.env` discovery rules apply to both CLI and library callers.

### 1.5 Validation, error handling, and where it lives

All cross-cutting validation is centralized in `TaskCLI`:

| Check | Triggered by | Error message |
|---|---|---|
| `end_date >= start_date` | every add/update with both dates | `"end date must be on or after start date"` |
| `stages >= 1` | project add/update | `"--stages must be >= 1"` |
| `1 <= stage <= no_of_stages` | task add/update with `stage` | `"Stage must be 1..N for project #M"` |
| Project exists | task add, task update changing stage, project show/update/delete | `"Project #N not found"` |
| Task exists | task show/update/delete | `"Task #N not found"` |
| At least one update field | project/task update | `"Nothing to update. Provide at least one field."` |
| Credentials present | first Supabase call | `"SUPABASE_URL and SUPABASE_KEY must be set (see .env.example)"` |

The API raises `TaskCLIError` for all of these. The CLI adapters catch it and `sys.exit` with the same string, so users see one clean line — no traceback. The stage upper bound is enforced in code rather than SQL because a Postgres `CHECK` can't reference another table without a trigger and the in-code message is friendlier.

### 1.6 `.env` discovery and credentials

`taskcli/db.py` looks for `.env` in two places:

1. **Walk up from cwd** via `find_dotenv(usecwd=True)`. This is what makes `taskcli` work anywhere inside the project tree.
2. **Fallback to `~/.config/taskcli/.env`** if no `.env` is found by walking up. This is what makes `taskcli` work from unrelated directories (e.g. your home folder).

Either the anon key or the service role key works. RLS is disabled on both tables in `schema.sql` because this is a single-user local tool — if you re-enable RLS, you'll need policies or you'll get `42501 row-level security` errors.

### 1.7 What `taskcli` deliberately does *not* do

- No ORM, no repository pattern — `client().table("...").<op>().execute()` is called directly. The codebase is small enough that this wins on readability.
- No interactive prompts — every command is scriptable.
- No colored or tabular output — stdout is plain text so it pipes cleanly.
- No offline mode or local cache — Supabase is the single source of truth.

### 1.8 Repository layout

```
taskcli/
├── cli.py              # argparse: entity → verb → args.func dispatch
├── __main__.py         # `python -m taskcli` entry point
├── api.py              # TaskCLI class + TaskCLIError (business logic + Supabase calls)
├── db.py               # cached Supabase client; loads .env
├── models.py           # Project, Task dataclasses + Status enum
└── commands/
    ├── project.py      # CLI adapters for project verbs (formatting + sys.exit)
    └── task.py         # CLI adapters for task verbs
schema.sql              # idempotent Postgres DDL
pyproject.toml          # build config + `taskcli` console script entry point
.env.example            # credentials template
```

---

## Part 2 — How to use it

### 2.1 Prerequisites

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/) — `python -m pip install --user pipx && python -m pipx ensurepath`
- A Supabase project (free tier is fine) and its URL + an API key

### 2.2 Install

```bash
git clone <this-repo>
cd task-mcp-cli-tool
pipx install .
```

`pipx` puts a `taskcli` executable on your PATH that you can run from any directory.

For active development, install editable so source edits take effect without reinstalling:

```bash
pipx install --editable .
# or, without pipx:
pip install -e .
python -m taskcli --help
```

### 2.3 One-time setup

**Step 1 — create the schema.** Open the **SQL Editor** in your Supabase dashboard and paste the contents of [`schema.sql`](./schema.sql). It's idempotent, so re-running is safe.

**Step 2 — provide credentials.** Copy the template:

```bash
cp .env.example .env
```

Fill in real values:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
```

- The **anon key** works if RLS is off (the default for new tables and what `schema.sql` sets).
- Use the **service role key** if you've turned RLS on without writing policies.

**Step 3 (optional) — make it work from anywhere.** The CLI walks up parent directories from cwd to find `.env`. To also make it work outside the project tree (e.g. from `C:\` or your home folder), copy `.env` to `~/.config/taskcli/.env`:

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$HOME\.config\taskcli" | Out-Null
Copy-Item .env "$HOME\.config\taskcli\.env"
```

```bash
# macOS / Linux
mkdir -p ~/.config/taskcli && cp .env ~/.config/taskcli/.env
```

### 2.4 CLI — project commands

```bash
# Create
taskcli project add \
  --title "Launch v1" \
  --description "Q3 release" \
  --start 2026-06-01 \
  --end 2026-09-30 \
  --stages 4

# List all
taskcli project list

# Show one
taskcli project show 1

# Update (every field optional; pass only what changes)
taskcli project update 1 --description "Pushed to Q4" --end 2026-12-15

# Delete (cascades to all tasks in this project)
taskcli project delete 1
```

**Required flags for `project add`:** `--title`, `--start`, `--end`, `--stages`. `--description` defaults to `""`.

### 2.5 CLI — task commands

```bash
# Create
taskcli task add \
  --project 1 \
  --title "Wireframes" \
  --description "First-pass mockups" \
  --status todo \
  --assigned-to "Aarav" \
  --stage 1 \
  --start 2026-06-01 \
  --end 2026-06-15

# List
taskcli task list                          # all tasks
taskcli task list --project 1              # only tasks in project 1
taskcli task list --status in_progress     # filter by status
taskcli task list --project 1 --status done

# Show one
taskcli task show 1

# Update
taskcli task update 1 --status in_progress --assigned-to "Sam"

# Delete
taskcli task delete 1
```

**Required flags for `task add`:** `--project`, `--title`, `--stage`, `--start`, `--end`. `--description` defaults to `""`, `--status` defaults to `todo`, `--assigned-to` defaults to `""`.

### 2.6 Validation behavior

The CLI rejects bad input with a clean one-line message — no Python tracebacks:

| Input | Result |
|---|---|
| `--end` before `--start` | `end date must be on or after start date` |
| `--stages 0` | `--stages must be >= 1` |
| `--stage 99` on a 4-stage project | `Stage must be 1..4 for project #N` |
| `--project 999` (nonexistent) | `Project #999 not found` |
| `update` with no fields | `Nothing to update. Provide at least one field.` |
| `--status weird` | argparse rejects with the allowed choices |
| Missing `SUPABASE_URL` / `SUPABASE_KEY` | `SUPABASE_URL and SUPABASE_KEY must be set (see .env.example)` |

### 2.7 Library use — `TaskCLI` from Python

Other Python programs can import `TaskCLI` directly instead of shelling out. Credentials use the same `.env` discovery as the CLI.

```python
from datetime import date
from taskcli import TaskCLI, TaskCLIError

api = TaskCLI()
# or explicit: TaskCLI(supabase_url="...", supabase_key="...")

# Create a project
project = api.add_project(
    title="Launch v1",
    description="Q3 release",
    start=date(2026, 6, 1),
    end=date(2026, 9, 30),
    stages=4,
)
print(project["id"], project["title"])

# Create a task — dates accept date objects or ISO strings
task = api.add_task(
    project=project["id"],
    title="Wireframes",
    description="First-pass mockups",
    status="todo",
    assigned_to="Aarav",
    stage=1,
    start="2026-06-01",
    end="2026-06-15",
)

# List + filter
for t in api.list_tasks(project=project["id"], status="todo"):
    print(t["title"], t["status"])

# Update (keyword-only optional fields)
api.update_task(task["id"], status="in_progress", assigned_to="Sam")

# Lookup by id
print(api.get_project(project["id"]))
print(api.get_task(task["id"]))

# Delete
api.delete_task(task["id"])
api.delete_project(project["id"])

# Errors raise TaskCLIError instead of exiting
try:
    api.add_task(
        project=999, title="x", description="",
        status="todo", assigned_to="",
        stage=1, start="2026-01-01", end="2026-01-02",
    )
except TaskCLIError as e:
    print("rejected:", e)
```

**Method summary:**

```python
# Projects
api.add_project(title, description, start, end, stages) -> dict
api.list_projects() -> list[dict]
api.get_project(id) -> dict
api.update_project(id, *, title=None, description=None,
                   start=None, end=None, stages=None) -> dict
api.delete_project(id) -> None

# Tasks
api.add_task(project, title, description, status, assigned_to,
             stage, start, end) -> dict
api.list_tasks(project=None, status=None) -> list[dict]
api.get_task(id) -> dict
api.update_task(id, *, title=None, description=None, status=None,
                assigned_to=None, stage=None, start=None, end=None) -> dict
api.delete_task(id) -> None
```

All methods return raw row dicts (or `list[dict]`) and raise `TaskCLIError` on the same conditions the CLI exits on. `status` is the string value (`"todo"`, `"in_progress"`, `"done"`). Date arguments accept either `datetime.date` or ISO `"YYYY-MM-DD"` strings.

### 2.8 Troubleshooting

- **`SUPABASE_URL and SUPABASE_KEY must be set`** — no `.env` was found walking up from cwd and `~/.config/taskcli/.env` doesn't exist either. Create one of the two.
- **`42501 row-level security`** — RLS got turned on in Supabase without policies. Either turn it off for `projects`/`tasks` or use the service role key.
- **Edits don't take effect after `pipx install .`** — that snapshots the source. Reinstall with `pipx install --force --editable .` (or use `--editable` from the start).
