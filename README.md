# taskcli

A command-line tool for managing **Projects** and the **Tasks** that belong to them, persisted in a Supabase Postgres database. Install once with `pipx`, run `taskcli` from anywhere.

## Data model

**Project**
- `title`, `description`
- `start_date`, `end_date`
- `no_of_stages` — how many phases the project goes through

**Task** (belongs to a project)
- `project_id`
- `title`, `description`
- `status` — `todo` | `in_progress` | `done`
- `assigned_to` — free-text name or handle
- `stage` — integer in `1..project.no_of_stages`
- `start_date`, `end_date`

Deleting a project cascades to its tasks.

## Prerequisites

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/) — `python -m pip install --user pipx && python -m pipx ensurepath`
- A Supabase project (free tier works) with its URL and an API key

## Install

```bash
git clone <this-repo>
cd task-mcp-cli-tool
pipx install .
```

`pipx` puts a `taskcli` executable on your PATH; you can run it from any directory.

## Configure

### 1. Create the database schema

Open the **SQL Editor** in your Supabase dashboard and run the contents of [`schema.sql`](./schema.sql). It creates the `projects` and `tasks` tables plus the `task_status` enum (idempotent — safe to re-run).

### 2. Provide credentials

Copy the template and fill in real values:

```bash
cp .env.example .env
```

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
```

- The **anon key** works if Row-Level Security is off (default for new tables).
- Use the **service role key** if you've enabled RLS without writing policies.

`.env` is gitignored. The CLI looks for it in the current working directory and walks up parent directories, so you can run `taskcli` from anywhere inside the project tree.

To run `taskcli` from **any** directory (e.g. `C:\` or your home folder), also place a copy at `~/.config/taskcli/.env` — the CLI falls back to that location when no `.env` is found by walking up from the cwd.

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$HOME\.config\taskcli" | Out-Null
Copy-Item .env "$HOME\.config\taskcli\.env"
```

```bash
# macOS / Linux
mkdir -p ~/.config/taskcli && cp .env ~/.config/taskcli/.env
```

## Usage

### Projects

```bash
taskcli project add --title "Launch v1" --description "Q3 release" --start 2026-06-01 --end 2026-09-30 --stages 4

taskcli project list
taskcli project show 1
taskcli project update 1 --description "Pushed to Q4" --end 2026-12-15
taskcli project delete 1     # cascades to its tasks
```

### Tasks

```bash
taskcli task add --project 1 --title "Wireframes" --description "First-pass mockups" --status todo --assigned-to "Aarav" --stage 1 --start 2026-06-01 --end 2026-06-15

taskcli task list                          # all tasks
taskcli task list --project 1              # tasks in project 1
taskcli task list --status in_progress     # filter by status
taskcli task show 1
taskcli task update 1 --status in_progress --assigned-to "Sam"
taskcli task delete 1
```

### Defaults and required flags

For `task add`, `--description` defaults to `""`, `--status` defaults to `todo`, and `--assigned-to` defaults to `""`. All other fields are required.

For `project add`, `--description` defaults to `""`. All other fields are required.

For both `update` verbs, every field is optional — pass only what changes.

## Validation

The CLI rejects bad input with a clear message (no Python tracebacks):

| Input | Result |
|---|---|
| `--end` before `--start` | "end date must be on or after start date" |
| `--stage 99` on a 4-stage project | "Stage must be 1..4 for project #N" |
| `--project 999` (nonexistent) | "Project #999 not found" |
| `--status weird` | argparse rejects with allowed choices |
| Missing `SUPABASE_URL` / `SUPABASE_KEY` | "SUPABASE_URL and SUPABASE_KEY must be set (see .env.example)" |

## Development

Run without installing:

```bash
pip install -e .
python -m taskcli --help
```

Or install in a venv with `pipx install --editable .` to keep `taskcli` on PATH while you iterate.

## Project layout

```
taskcli/
├── cli.py              # argparse dispatch
├── __main__.py         # `python -m taskcli` entry
├── db.py               # cached Supabase client (loads .env)
├── models.py           # Project, Task dataclasses + Status enum
└── commands/
    ├── project.py      # project CRUD
    └── task.py         # task CRUD + cross-table validation
schema.sql              # one-shot Supabase DDL
pyproject.toml          # build + `taskcli` entry point
.env.example            # credentials template
```
