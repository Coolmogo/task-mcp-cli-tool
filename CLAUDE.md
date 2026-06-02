# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Python backend for **coolmogo MVP** — a task-centric, approval-driven business AI tool. The core loop: user creates a task → agent runs asynchronously → structured activity output is stored → user reviews proposals and approves or acts.

The MVP demo is the **Gmail inbox flow**: connect Gmail → agent reads inbox → drafts reply per email → user approves → email sent.

The backend has three packages sharing a single execution layer:

- `task_program/` — execution layer. `TaskCLI` class + SurrealDB access. No API, CLI, or MCP code.
- `task_api/` — FastAPI REST server. Imports `TaskCLI`. This is the primary interface for the Flutter app.
- `task_mcp/` — MCP server. **Does NOT import `task_program` directly** — it is an HTTP client that calls `task_api`. Auth via `X-API-Key` header.
- `task_cli/` — CLI client. Imports `TaskCLI`. Development/debugging tool.

`task_api` and `task_mcp` are peers consuming the same REST surface. The Flutter app uses `task_api`; Claude Desktop / Cursor / OpenClaw use `task_mcp`.

**Projects are shelved** — the project table, `TaskCLI` methods, CLI parser, and MCP tools are kept as clearly-labeled dead code.

## Run during development

```bash
pip install -e ".[api]"       # installs FastAPI + uvicorn
python -m task_api            # launch REST API (port 8000)

pip install -e ".[mcp]"       # installs MCP server deps
python -m task_mcp            # launch MCP server (requires API_URL + API_KEY env vars)

pip install -e .              # editable install — registers the `task` CLI command
python -m task_cli --help
```

## Architecture

```
task_program/               # execution layer (library only — no API/MCP/CLI imports)
├── __init__.py             #   exports TaskCLI, TaskCLIError
├── program.py              #   TaskCLI class — verb methods, activity logging, _normalize + SurrealDB calls
├── db.py                   #   cached Surreal client; reads SURREALDB_* from .env, signs in as root
├── models.py               #   Task, Activity dataclasses; ActivityVerb enum; Project (dead)
├── schemas.py              #   Pydantic models: SparkOutput (list), SparkActivityItem, proposal content types
├── settings.py             #   SparkSettings, AuthSettings, GmailSettings — separate classes, each lru_cached
├── proposal_content.py     #   Discriminated union: EmailProposalContent | ReassignProposalContent | NewTaskProposalContent
├── spark_agent.py          #   SparkTrigger; build_assignment_trigger(), build_comment_trigger()
├── spark_service.py        #   generate_spark_reply() — returns list[SparkActivityItem]; LLM + web search
└── gmail_client.py         #   GmailOAuth2Client — OAuth flow, inbox read, email send, AES-256 token storage

task_api/                   # FastAPI REST server
├── __main__.py             #   uvicorn shim
├── server.py               #   FastAPI app; all routes; JWT + API-key auth middleware
├── schemas.py              #   Pydantic request/response models
├── auth.py                 #   create_access_token(), verify_token(), get_current_user() dependency, password hashing
└── routers/
    ├── auth.py             #   POST /auth/register, POST /auth/login
    ├── api_keys.py         #   POST /api-keys; X-API-Key validation dependency
    └── gmail.py            #   GET /gmail/auth, GET /gmail/callback, POST /gmail/sync, POST /proposals/{id}/send-email

task_mcp/                   # MCP server — HTTP client only, no task_program imports
├── __main__.py             #   MCP shim
├── server.py               #   FastMCP tools; each tool calls task_api via httpx with X-API-Key
└── settings.py             #   MCPSettings: api_url, api_key (from env)

task_cli/                   # CLI client (dev/debug)
├── cli.py                  #   argparse dispatch
├── __main__.py
└── commands/
    ├── task.py
    ├── comment.py
    ├── activity.py
    └── project.py          #   dead: not dispatched

schema.surql                # idempotent schema (DEFINE TABLE/FIELD IF NOT EXISTS)
reset.surql                 # wipes records, keeps schema
```

## Verb Taxonomy

All `activity` records carry a `verb` field (stored as `type` in SurrealDB — the column name is `type` but the Python parameter is always called `verb`). This is the authoritative list:

**Shared verbs** (humans and agents):

| Verb | Meaning | Content shape |
|------|---------|---------------|
| `update` | Add context, research output, or a correction | `{ body }` |
| `instruct` | Give a direction or task to another actor | `{ body, target? }` |

**Human-only verbs:**

| Verb | Meaning | Content shape |
|------|---------|---------------|
| `accept` | Accept an agent proposal (fires the proposal's action) | `{ proposal_activity_id }` |
| `dismiss` | Close the task, no further action | `{ note? }` |

**Agent-only verbs** (every agent turn must end with one of these):

| Verb | Meaning | Content shape |
|------|---------|---------------|
| `proposal` | Agent proposes an action for human approval | `{ type, ...type-specific fields }` |
| `ask` | Agent needs clarification before proceeding | `{ body }` |
| `propose_dismiss` | Agent recommends closing the task | `{ reason }` |

**`ActivityVerb` enum values:** `UPDATE`, `INSTRUCT`, `ACCEPT`, `DISMISS`, `PROPOSAL`, `ASK`, `PROPOSE_DISMISS`. `DELEGATE` is not yet implemented.

## Proposals

A `proposal` verb activity stores its content as `proposal_content` (a JSON object) with a `type` discriminator. New proposal types are additive — no schema change required.

| `type` | Key fields |
|--------|-----------|
| `email` | `recipients: list[str]`, `subject`, `body`, `cc?`, `attachments?` |
| `reassign` | `task_id`, `assign_to_user_id`, `reason` |
| `new_task` | `description`, `suggested_verb`, `suggested_project_id?` |

**`proposal_content` is the structured field** — not `content`. The `content` field on normalized activity rows is already taken (it's an alias for the text `body` of comments/instructions). Do not use `content` for proposal data.

**Proposal lifecycle:**
1. Agent emits `proposal` verb → `proposal_status = "pending"`, stored in `proposal_content`
2. Human emits `accept` → `accept_proposal()` fires the action (creates task, sends email, etc.) and logs an `accept` activity
3. Human emits `dismiss` → task closed with no action

**Old flat `proposal_*` fields** (`proposal_title`, `proposal_description`, etc.) are kept for backward compat read-only. New code always writes `proposal_content`.

## Agent Integration (Spark)

**Spark** is the AI agent assigned to tasks. It runs asynchronously when a task is assigned to `user:spark` or when a user comments on a Spark-assigned task.

**Output format**: `generate_spark_reply()` in `spark_service.py` returns `list[SparkActivityItem]`. The list may start with any number of `update` or `instruct` items (narration, research findings), but the **last item must always be `proposal | ask | propose_dismiss`** (enforced by Pydantic validator on `SparkOutput`).

**Example output:**
```python
[
    SparkActivityItem(verb="instruct", text="Research complete. Found 3 competitors..."),
    SparkActivityItem(verb="proposal", proposal_content={"type": "new_task", "description": "..."})
]
```

**`_run_spark_sequence()`** in `task_api/server.py` iterates the list and dispatches each item:
- `update` / `instruct` → `add_comment(verb=...)`
- `proposal` → `create_proposal_v2(content_dict)`
- `ask` → `add_comment(verb="ask")`
- `propose_dismiss` → `add_comment(verb="propose_dismiss")`

**Configuration:** `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`. Web search (DuckDuckGo via `ddgs`) is triggered when comments contain keywords like "research", "find out", "look up".

**Fallback:** On any LLM error, `generate_spark_reply()` returns `[SparkActivityItem(verb="ask", text="I need more context...")]`.

## Auth

All REST endpoints require a JWT bearer token (`Authorization: Bearer <token>`).

- `POST /auth/register` — email + password → creates user, returns JWT
- `POST /auth/login` — email + password → returns JWT
- `get_current_user()` FastAPI dependency — validates JWT, returns `{id, email}`
- Every `TaskCLI` call that touches user data receives `owner_id=current_user["id"]`
- Cross-user access raises `TaskCLIError("not authorized")` → 403

**API key auth** (for MCP / OpenClaw): `X-API-Key` header on all MCP-facing endpoints. Keys are bcrypt-hashed and stored in `user.api_keys`. The `get_api_key_user()` dependency validates the header.

**Settings:** `AuthSettings` in `task_program/settings.py` (separate from `SparkSettings`) — `jwt_secret_key`, `jwt_algorithm`, `jwt_expire_minutes`.

## Gmail Integration

- `GET /gmail/auth` — returns Google OAuth2 redirect URL (requires JWT)
- `GET /gmail/callback` — exchanges code, stores AES-256-encrypted token in `user.gmail_token_enc`
- `POST /gmail/sync` — reads inbox, creates one task per email with an `instruct` opening activity → triggers Spark
- `POST /proposals/{id}/send-email` — accepts an `email`-type proposal, sends via Gmail API, logs `accept` activity

Gmail OAuth token is encrypted at rest (AES-256, `cryptography.fernet`) in `gmail_client.py`. The `GmailSettings` in `task_program/settings.py` holds `google_client_id`, `google_client_secret`, `aes_encryption_key`.

## MCP Server

`task_mcp/server.py` is **an HTTP client only** — it has zero imports from `task_program`. Each `@mcp.tool()` function:
1. Gets an `httpx.Client` configured with `MCPSettings.api_url` and `X-API-Key: MCPSettings.api_key`
2. Makes the corresponding HTTP call to `task_api`
3. On error returns `f"Error: {status} {body}"`

Required env vars: `MCP_API_URL`, `MCP_API_KEY`.

**Never re-introduce direct `task_program` imports in `task_mcp/`** — if the MCP server needs a new operation, add it to `task_api` first, then call it via HTTP.

## DB access and normalization

Every `TaskCLI` method calls the SurrealDB SDK directly — `self._client.create()`, `.merge()`, `.delete()`, `.query()`. No ORM. The shared `client()` from `task_program/db.py` is `lru_cache`d (one connection per process).

**Record ids are strings** like `task:8f3k`. `self._rid(id)` coerces a string to `RecordID` (raises `TaskCLIError` on malformed). Pass `RecordID` params into SurrealQL via `vars={}`, never string-interpolate.

**Results are normalized.** `_normalize(raw, keys)` converts `RecordID`→str, `datetime`→ISO string, renames link fields (`assignee`→`assignee_id`, etc.), and fills the full key set with `None` so callers can `.get(...)` safely. Every method returns `_normalize(...)` output. The `_TASK_KEYS`/`_ACTIVITY_KEYS` tuples define the normalization contract — **add every new DB field to the relevant tuple or it silently disappears from API responses**.

**`_normalize_activity()` naming:** sets `content = row.get("text")` — so `content` is already the text alias. Structured proposal data lives in `proposal_content` (dict), never `content`.

## Conventions and gotchas

- **`status` is free text.** `Status` in `models.py` is suggested values only; not enforced. Don't add `choices=`/`Literal` constraints.
- **History is auto-logged.** `update_task` diffs the current row and inserts one activity per changed field via `_record_update()`. Comments go through `add_comment()` with an explicit verb.
- **`_ACTIVITY_KEYS` is the normalization contract.** Every field written to SurrealDB `activity` must appear in this tuple or it disappears from responses. This is the #1 source of silent bugs.
- **`_lru_cache` isolation for settings.** `AuthSettings`, `GmailSettings`, and `SparkSettings` must be separate classes with separate `@lru_cache` decorators. Do not merge them or cache invalidation becomes unpredictable.
- **`get_task` embeds activities via one query.** `SELECT *, (SELECT … WHERE task = $t) AS activities FROM $t` returns the task with an embedded activity list. `list_tasks` does not embed.
- **`schema.surql` is idempotent** (every statement is `DEFINE ... IF NOT EXISTS`). Run it in Surrealist to apply. `reset.surql` wipes all records while keeping schema.
- **`due_date` is a plain string** `'YYYY-MM-DD'` in SurrealDB, not a `datetime`. `created_at` is a real `datetime DEFAULT time::now()`.
- **CLI errors exit with `sys.exit("message")`** — one clean line, no traceback. Execution layer raises `TaskCLIError`; CLI adapter translates to `sys.exit`.
- **MCP errors return `f"Error: {e}"`** — never raise out to Claude Desktop.
- **`schema.surql` has no table permissions / RLS** — connection signs in as root, which bypasses `PERMISSIONS`. Don't add `DEFINE ACCESS` without revisiting `db.py`.
- **`activity` table is SCHEMALESS** — new verb types and `proposal_content` shapes are additive. Old rows with old verb names survive without migration.

## Adding a new field

1. `schema.surql` — add `DEFINE FIELD IF NOT EXISTS <name> ON <table> TYPE ...`
2. `task_program/models.py` — update dataclass
3. `task_program/program.py` — add to method params, payload dict, and `_TASK_KEYS`/`_ACTIVITY_KEYS` tuple
4. `task_api/server.py` — update route + `task_api/schemas.py` response model
5. `task_mcp/server.py` — update the corresponding HTTP call if the field needs to flow through MCP

## Flutter Task Detail Screen — Backend Contract

The Flutter `task_detail_drawer.dart` renders an activity feed with verb-typed cards and a task header. The Flutter client is at `C:\Users\Koln\task_manager_flutter`. These are the outstanding backend changes required for full feature coverage.

### 1. Task `verb` field — unlocks the header verb badge

The Flutter `Task` model has a `verb` field wired and ready; it currently receives `null` because the backend doesn't write or expose it yet. Four touch points:

1. **`schema.surql`** — `DEFINE FIELD IF NOT EXISTS verb ON task TYPE option<string>;`
2. **`task_program/program.py` `_TASK_KEYS`** — add `"verb"` to the tuple so it flows through `_normalize()` automatically
3. **`task_program/program.py` `add_task()`/`update_task()`** — add `verb: Optional[str] = None` param and include in the DB payload dict
4. **`task_api/schemas.py` `TaskCreate`/`TaskUpdate`** — add `verb: Optional[str] = None` (routes already use `**body.model_dump()`, no route changes needed)

Planned task verb values (different from activity verbs): `propose | draft | research | email | build`.

### 2. `verb` missing from `TaskActivityResponse` — fixes wrong card routing today

`TaskActivityResponse` in `task_api/schemas.py` has `model_config = ConfigDict(extra="ignore")` and no `verb` field. Pydantic strips `verb` from `/tasks/{id}/comments` responses. The Flutter `fromBackendCommentJson` then defaults all comments to `verb='ask'`, so Spark `instruct`/`update` replies incorrectly render as agent question cards instead of plain comment items.

**Fix:** add `verb: Optional[str] = None` to `TaskActivityResponse` in `task_api/schemas.py`.

### 3. `propose_dismiss` verb name — Flutter-side fix needed

The backend emits `verb='propose_dismiss'`. The Flutter `feedKind` getter in `task_activity_model.dart` currently routes to a dismiss card only when `verb == 'dismiss'`. Update that condition to also match `'propose_dismiss'`:

```dart
// task_activity_model.dart — feedKind getter
if (isAgent && (verb == 'dismiss' || verb == 'propose_dismiss' || sparkActionType == 'dismiss')) {
  return 'dismiss';
}
```

### 4. `proposal_content` vs flat fields — keep writing both until Flutter is updated

The backend writes new proposals to `proposal_content` (the `{ type, ...fields }` JSON object). The Flutter `ActivityLog` model currently reads from flat `metadata['proposal_title']`, `metadata['proposal_description']` etc. (the old backward-compat fields).

Until Flutter's `ActivityLog` is updated to parse `proposal_content`, **`create_proposal_v2()` must continue writing the flat backward-compat fields alongside `proposal_content`**. The flat fields are already kept for read-only backward compat per this CLAUDE.md — do not remove them yet.

For the `email` proposal type, the Flutter card additionally reads `proposal_recipients`, `proposal_subject`, `proposal_body` from `metadata`. These need to be present in the normalized activity dict — add them to `_ACTIVITY_KEYS` and write them from `proposal_content` in `_normalize_activity()`.

### 5. `proposal_reason` for `propose_dismiss` cards

The Flutter dismiss card reads `metadata['proposal_reason']`. When Spark emits `propose_dismiss`, store the `reason` field in the activity and ensure `proposal_reason` appears in `_ACTIVITY_KEYS` and `_normalize_activity()` output.

### What the Flutter feed renderer expects per verb

| Flutter `feedKind` | Triggered when | Backend must provide |
|---|---|---|
| `new_task` | proposal with `proposal_type == 'new_task'` | `proposal_title`, `proposal_description`, `proposal_status`, `proposal_created_task_id` |
| `email` | proposal with `proposal_type == 'email'` | `proposal_recipients`, `proposal_subject`, `proposal_body`, `proposal_status` |
| `question` | `verb == 'ask'` + `author_type == 'mogo'` | `content`/`text` body |
| `dismiss` | `verb == 'propose_dismiss'` + `author_type == 'mogo'` | `proposal_reason` |
| `decision` | `verb == 'accept'` or human `verb == 'dismiss'` | `content`/`text` |
| `comment` | human comment | `content`/`text`, `author_type == 'user'` |
| `history` | field-update activity | `verb`, `field`, `old_value`, `new_value` |

Activities are fetched via `GET /tasks/{id}/activities` (all) + `GET /tasks/{id}/comments` (filtered), merged and sorted **ascending by `created_at`** in the Flutter service. The feed renders oldest-first.

---

## What NOT to add

- No ORM or repository pattern — direct SurrealDB SDK calls in `TaskCLI` win on readability.
- No interactive prompts — everything must be scriptable.
- No colored/table output in CLI — plain text pipes cleanly.
- No offline mode — SurrealDB is the source of truth.
- No `task_program` imports in `task_mcp/` — MCP is an HTTP client only.
- No direct DB calls from `task_api` routes — all DB access goes through `TaskCLI`.
