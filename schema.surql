-- Fresh-install schema for the `task` tool on SurrealDB.
-- Import once into your instance (namespace + database = main) via the Surrealist
-- query editor (paste -> Run query) or `surreal import`. Safe to re-run: every
-- statement uses IF NOT EXISTS.
--
-- We connect as root, so no table PERMISSIONS are needed (root bypasses them) --
-- this is the SurrealDB analog of "RLS off everywhere" under the old Postgres schema.

-- Users. Dead structure for now: no records created until user management is
-- reintroduced. task.assignee and the *.author links below reference it.
DEFINE TABLE IF NOT EXISTS user SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name  ON user TYPE string;
DEFINE FIELD IF NOT EXISTS email ON user TYPE option<string>;

-- Projects are shelved (dead). Kept so they can be reincorporated later;
-- task.project links here but is currently unused. Dates are stored as plain
-- 'YYYY-MM-DD' strings to match the client contract (see task.due_date below).
DEFINE TABLE IF NOT EXISTS project SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS title        ON project TYPE string;
DEFINE FIELD IF NOT EXISTS description  ON project TYPE string DEFAULT '';
DEFINE FIELD IF NOT EXISTS start_date   ON project TYPE string;
DEFINE FIELD IF NOT EXISTS end_date     ON project TYPE string;
DEFINE FIELD IF NOT EXISTS no_of_stages ON project TYPE int ASSERT $value > 0;

-- Tasks. status is free text (default 'To Do'); any string is accepted.
-- due_date is a 'YYYY-MM-DD' string (not a datetime) so it round-trips to clients
-- unchanged with no timezone games. created_at is a real datetime for ordering.
DEFINE TABLE IF NOT EXISTS task SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS title       ON task TYPE string;
DEFINE FIELD IF NOT EXISTS description ON task TYPE option<string>;
DEFINE FIELD IF NOT EXISTS status      ON task TYPE string DEFAULT 'To Do';
DEFINE FIELD IF NOT EXISTS due_date    ON task TYPE option<string>;
DEFINE FIELD IF NOT EXISTS assignee    ON task TYPE option<record<user>>;
DEFINE FIELD IF NOT EXISTS stage_id    ON task TYPE option<string>;
DEFINE FIELD IF NOT EXISTS project     ON task TYPE option<record<project>>;
DEFINE FIELD IF NOT EXISTS created_at  ON task TYPE datetime DEFAULT time::now();

-- Unified activity feed. Every event on a task is one row; `type` is the discriminator.
-- Types: update | ask | instruct | delegate | propose | decide | dismiss
DEFINE TABLE IF NOT EXISTS activity SCHEMALESS;
DEFINE FIELD IF NOT EXISTS task                          ON activity TYPE record<task>;
DEFINE FIELD IF NOT EXISTS type                          ON activity TYPE string;
DEFINE FIELD IF NOT EXISTS created_at                    ON activity TYPE datetime DEFAULT time::now();

-- Allow NULL for all optional fields (override old definitions)
DEFINE FIELD action                        ON activity TYPE none | string;
DEFINE FIELD field                         ON activity TYPE none | string;
DEFINE FIELD old_value                     ON activity TYPE none | string;
DEFINE FIELD new_value                     ON activity TYPE none | string;
DEFINE FIELD text                          ON activity TYPE none | string;
DEFINE FIELD author                        ON activity TYPE none | record<user>;
DEFINE FIELD author_id                     ON activity TYPE none | string;
DEFINE FIELD author_type                   ON activity TYPE none | string;
DEFINE FIELD legacy_author_name            ON activity TYPE none | string;
DEFINE FIELD metadata                      ON activity TYPE none | object;
DEFINE FIELD proposal_status               ON activity TYPE none | string;
DEFINE FIELD proposal_title                ON activity TYPE none | string;
DEFINE FIELD proposal_description          ON activity TYPE none | string;
DEFINE FIELD proposal_assignee_id          ON activity TYPE none | string;
DEFINE FIELD proposal_stage_id             ON activity TYPE none | string;
DEFINE FIELD proposal_created_task_id      ON activity TYPE none | string;
DEFINE FIELD proposal_activity_id          ON activity TYPE none | string;
DEFINE FIELD IF NOT EXISTS from_actor    ON activity TYPE none | string;
DEFINE FIELD IF NOT EXISTS to_actor      ON activity TYPE none | string;

DEFINE INDEX IF NOT EXISTS activity_task ON activity FIELDS task;
DEFINE INDEX IF NOT EXISTS activity_type ON activity FIELDS task, type;
