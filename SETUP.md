# Setup

Two setup tracks — one for the CLI tool, one for the MCP server. Both share the same prerequisites and Supabase schema, so do those once first.

## Prerequisites (shared)

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/) — `python -m pip install --user pipx && python -m pipx ensurepath`
- A Supabase project (free tier works). Grab its URL and either the anon key or the service-role key.

## Step 0 — Supabase schema + credentials (shared)

1. **Create the schema.** Open the **SQL Editor** in your Supabase dashboard and paste the contents of [`schema.sql`](./schema.sql). It's idempotent — re-run safely.
2. **Add credentials.** Copy the template and fill it in:
   ```bash
   cp .env.example .env
   ```
   ```dotenv
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-or-service-role-key
   ```
   The anon key works when RLS is off (the default — `schema.sql` disables RLS on both tables). Use the service-role key only if you've turned RLS on without writing policies.

Done with the shared prep. Now pick a track below.

---

## Track A — CLI tool

### A1. Install

From the repo root:

```bash
pipx install --editable .
```

`pipx` puts a `task` executable on your PATH that runs from any directory. The `--editable` flag means source edits take effect without reinstalling.

(For development without pipx: `pip install -e .`, then use `python -m task_cli` instead of `task`.)

### A2. Verify

```bash
task --help
task project list      # should print "No projects." or your existing list
```

If you get `SUPABASE_URL and SUPABASE_KEY must be set`, the CLI couldn't find your `.env` — see A3.

### A3. (Optional) Make it work from outside the project tree

By default the CLI walks up parent directories from cwd to find `.env`. If you want `task` to work from `C:\` or your home folder too, copy `.env` to the fallback location:

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$HOME\.config\taskcli" | Out-Null
Copy-Item .env "$HOME\.config\taskcli\.env"
```

```bash
# macOS / Linux
mkdir -p ~/.config/taskcli && cp .env ~/.config/taskcli/.env
```

(The directory is named `taskcli` rather than `task` for back-compat with the pre-rename layout.)

### A4. Smoke test

```bash
task project add --title "Test" --description "" \
                 --start 2026-06-01 --end 2026-09-30 --stages 4
task project list
task project delete <id_from_above>
```

See the README for the full command reference.

### A5. Troubleshooting

- **`SUPABASE_URL and SUPABASE_KEY must be set`** — `.env` not found. Either run from inside the project tree or do A3.
- **`42501 row-level security`** — you turned RLS on in Supabase without policies. Either turn it off for `projects`/`tasks` or switch to the service-role key.
- **Edits don't take effect** — you used `pipx install .` (snapshot) instead of `pipx install --editable .`. Reinstall: `pipx install --force --editable .`.

---

## Track B — MCP server (Claude Desktop)

### B1. Install with the MCP extra

The MCP SDK is an optional dependency. From the repo root:

```bash
pipx install --editable ".[mcp]"
```

This gets you both the `task` CLI command **and** the ability to run `python -m task_mcp`. If you already installed via Track A, reinstall with the extra:

```bash
pipx uninstall task
pipx install --editable ".[mcp]"
```

(The `pipx install --force` flag has a known bug with the uv backend — uninstall first instead.)

### B2. Locate your Python interpreter

Claude Desktop needs the absolute path to the Python that has the `task` package installed.

- **Windows + pipx:** `C:\Users\<you>\pipx\venvs\task\Scripts\python.exe`
  Find the parent dir with `pipx environment --value PIPX_LOCAL_VENVS`, then append `\task\Scripts\python.exe`.
- **macOS / Linux + pipx:** `~/.local/pipx/venvs/task/bin/python`

Verify it works (should start silently and block on stdin — that's the MCP server waiting; Ctrl+C to exit):

```powershell
# PowerShell (the & is required for quoted paths)
& "C:\Users\<you>\pipx\venvs\task\Scripts\python.exe" -m task_mcp
```

```bash
# bash / zsh
"<that python path>" -m task_mcp
```

If you see `ModuleNotFoundError`, you have the wrong interpreter, or you forgot the `[mcp]` extra.

### B3. Put credentials at the fallback location

Claude Desktop launches the MCP server with an **undefined working directory**, so the cwd-walking `.env` discovery from Track A is unreliable. Copy `.env` to the fallback path:

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$HOME\.config\taskcli" | Out-Null
Copy-Item .env "$HOME\.config\taskcli\.env"
```

```bash
# macOS / Linux
mkdir -p ~/.config/taskcli && cp .env ~/.config/taskcli/.env
```

### B4. Edit `claude_desktop_config.json`

The config file lives at:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Open it (create if missing) and add a `task` entry under `mcpServers`. Use the Python path from B2. **Double-backslash all Windows paths in JSON.**

```json
{
  "mcpServers": {
    "task": {
      "command": "C:\\Users\\<you>\\pipx\\venvs\\task\\Scripts\\python.exe",
      "args": ["-m", "task_mcp"]
    }
  }
}
```

If you already have other `mcpServers` entries, merge — don't replace.

### B5. Restart Claude Desktop and verify

Fully quit Claude Desktop (tray icon → Quit on Windows, ⌘Q on macOS — not just close the window). Relaunch. In a new chat, click the tools icon (🔌 / hammer); you should see ten tools registered under the `task` server (`add_project`, `list_projects`, `add_task`, …).

Smoke tests inside Claude:

- *"List my projects."* → calls `list_projects`.
- *"Create a project titled 'Test' from 2026-06-01 to 2026-09-30 with 4 stages, blank description."* → calls `add_project`.
- *"Show project 999999."* → returns `Error: Project #999999 not found` (no traceback).

### B6. (Optional) Interactive inspector during development

```bash
mcp dev task_mcp/server.py
```

Opens a browser UI listing all tools with their schemas and a form to invoke each. Useful when iterating on the server.

### B7. Troubleshooting

- **Tools don't appear after restart.** Check the MCP logs:
  - Windows: `%APPDATA%\Claude\logs\mcp-server-task.log`
  - macOS: `~/Library/Logs/Claude/mcp-server-task.log`
- **`ModuleNotFoundError: No module named 'task_program'`** in the log — wrong Python in B4. Redo B2.
- **`ModuleNotFoundError: No module named 'mcp'`** — you installed without the `[mcp]` extra. Redo B1.
- **`SUPABASE_URL and SUPABASE_KEY must be set`** — `.env` missing at the fallback path. Redo B3.
- **Server crashes silently on launch.** Run the B2 verify command manually — any stack trace prints to your terminal.
- **Data looks stale.** CLI and MCP share the same Supabase tables; re-call `list_*` to refresh.
