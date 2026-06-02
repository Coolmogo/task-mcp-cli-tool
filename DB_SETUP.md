# Database setup — connecting `task` to SurrealDB

This is the focused guide for wiring the program to its **SurrealDB** backend. For the
broader install flows (CLI on your PATH, MCP server in Claude Desktop) see
[`SETUP.md`](./SETUP.md); for the full command reference see [`README.md`](./README.md).

---

## 1. How the program connects

All database access lives in the execution layer. [`task_program/db.py`](./task_program/db.py)
builds **one** SurrealDB client per process (`@lru_cache`d) like this:

```python
from surrealdb import Surreal

db = Surreal(SURREALDB_URL)                              # pick engine by URL scheme
db.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})  # root auth
db.use(SURREALDB_NS, SURREALDB_DB)                       # namespace + database
```

`TaskCLI` then runs every operation against that client (`create` / `merge` / `delete` /
`query`). The CLI, MCP, and REST clients never connect themselves — they all go through
`TaskCLI`, so this is the **only** place a connection is configured.

The connection signs in as **root**, which has full access and bypasses table
permissions — the single-user analog of "RLS off". No per-table permission setup is needed.

---

## 2. Environment variables

| Variable          | Required | Default | Description                                            |
|-------------------|:--------:|---------|--------------------------------------------------------|
| `SURREALDB_URL`   | ✅       | —       | Connection URL (see schemes in §4), e.g. `wss://your-instance.surreal.cloud` |
| `SURREALDB_USER`  | ✅       | —       | Root username                                          |
| `SURREALDB_PASS`  | ✅       | —       | Root password                                          |
| `SURREALDB_NS`    | ❌       | `main`  | Namespace                                              |
| `SURREALDB_DB`    | ❌       | `main`  | Database                                               |

If `SURREALDB_URL`, `SURREALDB_USER`, or `SURREALDB_PASS` is missing, the program exits with:

```
SURREALDB_URL, SURREALDB_USER and SURREALDB_PASS must be set (see .env.example)
```

### Where to put them

Copy the template and fill it in:

```bash
cp .env.example .env
```

```dotenv
SURREALDB_URL=wss://your-instance.surreal.cloud
SURREALDB_USER=root
SURREALDB_PASS=your-root-password
SURREALDB_NS=main
SURREALDB_DB=main
```

`db.py` discovers `.env` by walking **up from the current working directory**
(`find_dotenv(usecwd=True)`), then falls back to `~/.config/taskcli/.env`. The fallback
matters when the working directory is undefined — e.g. when Claude Desktop launches the MCP
server (see `SETUP.md` Track B3). The fallback folder is the legacy name `taskcli` (not
`task`) for back-compat; don't rename it.

```powershell
# Windows PowerShell — put creds at the fallback location
New-Item -ItemType Directory -Force "$HOME\.config\taskcli" | Out-Null
Copy-Item .env "$HOME\.config\taskcli\.env"
```

```bash
# macOS / Linux
mkdir -p ~/.config/taskcli && cp .env ~/.config/taskcli/.env
```

> `.env` holds root credentials — it is git-ignored. Keep it out of version control.

---

## 3. Getting the values (Surreal Cloud)

This project uses a **Surreal Cloud** instance (e.g. *Coolmogo DB*), namespace and database
both `main`. To find the connection details:

1. Open **[Surrealist](https://surrealist.app/)** and select your instance.
2. The connection URL (`wss://<id>.<region>.surreal.cloud`) and root credentials are in the
   connection's settings — copy them into `.env` exactly as shown.
3. Namespace and database are shown in the top breadcrumb (`main` / `main`).

> **`/rpc` suffix:** the SDK normalizes this for you — it strips any trailing `/rpc` and
> re-appends it internally. So `wss://host` and `wss://host/rpc` both work; use whatever
> Surrealist shows.

---

## 4. Connection URL schemes

`Surreal(url)` selects the engine from the URL scheme:

| Scheme(s)                       | Use                                   | Signin needed? |
|---------------------------------|---------------------------------------|:--------------:|
| `wss://`                        | **Surreal Cloud** (this project)      | yes (root)     |
| `ws://`                         | Self-hosted server over WebSocket     | yes            |
| `https://` / `http://`          | Server over HTTP                      | yes            |
| `mem://`                        | In-process, in-memory (ephemeral)     | no             |
| `surrealkv://<path>` / `file://`| In-process, on-disk (embedded)        | no             |

The default `db.py` path always calls `signin(...)`, so it targets the **server** schemes
(`wss`/`ws`/`http`/`https`). The embedded schemes are useful for offline dev/tests — see §7.

---

## 5. Import the schema

A connection alone isn't enough — the tables must exist. Import
[`schema.surql`](./schema.surql) **once** into your instance (namespace/database `main`):

- **Surrealist:** open a new query, paste the contents of `schema.surql`, click **Run query**.
- **CLI:** `surreal import --endpoint <URL> --username root --password <pass> --namespace main --database main schema.surql`

Every statement uses `IF NOT EXISTS`, so re-running is safe. To wipe all records while
keeping the schema, run [`reset.surql`](./reset.surql) the same way.

---

## 6. Test the connection

With `.env` in place and the schema imported:

```bash
# Round-trips connect -> signin -> use -> a real query. Prints [] on a fresh DB.
python -c "from task_program import TaskCLI; print(TaskCLI().list_tasks())"
```

```bash
# Or via the installed CLI:
task task list      # prints "No tasks." on a fresh DB
```

A clean `[]` / `No tasks.` means the URL, credentials, namespace/database, and schema are
all good.

---

## 7. Alternatives

### Local SurrealDB server (development)

Run a server locally instead of using the cloud:

```bash
# on-disk store, root user root/root, listening on :8000
surreal start --user root --pass root surrealkv://./task.db
```

```dotenv
SURREALDB_URL=ws://localhost:8000
SURREALDB_USER=root
SURREALDB_PASS=root
SURREALDB_NS=main
SURREALDB_DB=main
```

Then import `schema.surql` against it and test as in §6.

### Embedded, no server (offline tests)

The embedded engines (`mem://`, `surrealkv://`) run in-process and need **no signin**, so
they don't fit the default `db.py` path. Construct `TaskCLI` with an injected client instead:

```python
from surrealdb import Surreal
from task_program import TaskCLI

db = Surreal("mem://")            # or surrealkv://./task.db for persistence
db.use("main", "main")
db.query(open("schema.surql", encoding="utf-8").read())

api = TaskCLI(client=db)          # bypasses .env / signin entirely
api.add_task("local task")
```

`TaskCLI(client=...)` is the dependency-injection seam used by the test suite.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `SURREALDB_URL, SURREALDB_USER and SURREALDB_PASS must be set` | `.env` not found or incomplete. Run from inside the project tree, or place it at `~/.config/taskcli/.env` (§2). |
| Authentication / signin error | Wrong username/password, or the URL points at a different instance. Confirm against the connection Surrealist uses. |
| Queries return empty / "table not found"-style errors | Schema not imported into this namespace/database. Re-run §5 against `main`/`main`. |
| `ValueError: '<scheme>' is not a valid UrlScheme` | Unsupported URL scheme. Use one from §4 (likely you meant `wss://`). |
| Wrong data / wrong environment | `SURREALDB_NS`/`SURREALDB_DB` point at the wrong namespace/database. They default to `main`. |
