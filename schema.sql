-- Fresh-install DDL. Run once in the Supabase SQL editor. Idempotent.
-- For transforming an EXISTING database, use migration.sql instead.

-- Users. Dead structure for now: no rows are created until user management is
-- reincorporated. assignee_id / author_id columns below reference it.
create table if not exists users (
  id     bigserial primary key,
  name   text not null,
  email  text
);

-- Projects are shelved (dead). The table is kept so they can be reincorporated
-- later; tasks.project_id references it but is nullable and currently unused.
-- It is created first only because tasks.project_id has an FK to it.
create table if not exists projects (
  id            bigserial primary key,
  title         text not null,
  description   text not null default '',
  start_date    date not null,
  end_date      date not null,
  no_of_stages  int  not null check (no_of_stages > 0)
);

create table if not exists tasks (
  id           bigserial primary key,
  title        text not null,
  description  text,
  status       text not null default 'To Do',
  due_date     date,
  assignee_id  bigint references users(id) on delete set null,
  stage_id     text,
  project_id   bigint references projects(id) on delete set null,
  created_at   timestamptz not null default now()
);

create table if not exists activities (
  id                  bigserial primary key,
  task_id             bigint not null references tasks(id) on delete cascade,
  type                text not null default 'history',   -- 'history' | 'comment'
  action              text not null,                     -- updated|removed|assigned|moved|commented
  field               text,
  old_value           text,
  new_value           text,
  text                text,
  author_id           bigint references users(id) on delete set null,
  legacy_author_name  text,
  created_at          timestamptz not null default now()
);

create table if not exists comments (
  id                  bigserial primary key,
  task_id             bigint not null references tasks(id) on delete cascade,
  text                text not null,
  author_id           bigint references users(id) on delete set null,
  legacy_author_name  text,
  created_at          timestamptz not null default now()
);

create index if not exists tasks_project_id_idx  on tasks(project_id);
create index if not exists activities_task_id_idx on activities(task_id);
create index if not exists comments_task_id_idx   on comments(task_id);

-- Single-user local tool with a publishable/anon key: RLS off everywhere.
alter table users      disable row level security;
alter table projects   disable row level security;
alter table tasks      disable row level security;
alter table activities disable row level security;
alter table comments   disable row level security;
