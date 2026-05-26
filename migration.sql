-- Migration: reshape an EXISTING database to the new task model.
-- Paste into the Supabase SQL editor. Safe to re-run (idempotent where practical).
--
-- DESTRUCTIVE: drops tasks.start_date, tasks.end_date and tasks.assigned_to.
-- Back up first if you need that data. Projects are NOT touched (kept as dead
-- structure to reincorporate later).

-- 1. Users (dead structure: stays empty until user management is reintroduced).
create table if not exists users (
  id     bigserial primary key,
  name   text not null,
  email  text
);
alter table users disable row level security;

-- 2. tasks.status: enum -> free text, default 'To Do', remap legacy values.
alter table tasks alter column status drop default;
alter table tasks alter column status type text using status::text;
update tasks set status = 'To Do'        where status = 'todo';
update tasks set status = 'In Progress'  where status = 'in_progress';
update tasks set status = 'Done'         where status = 'done';
alter table tasks alter column status set default 'To Do';

-- 3. New task columns.
alter table tasks add column if not exists due_date    date;
alter table tasks add column if not exists assignee_id bigint references users(id) on delete set null;
alter table tasks add column if not exists created_at  timestamptz not null default now();

-- 4. project_id: now optional, FK relaxed to ON DELETE SET NULL.
alter table tasks alter column project_id drop not null;
alter table tasks drop constraint if exists tasks_project_id_fkey;
alter table tasks add constraint tasks_project_id_fkey
  foreign key (project_id) references projects(id) on delete set null;

-- 5. stage (int, checked) -> stage_id (free text, nullable).
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'tasks' and column_name = 'stage'
  ) then
    alter table tasks rename column stage to stage_id;
  end if;
end$$;
alter table tasks drop constraint if exists tasks_stage_check;
alter table tasks alter column stage_id type text using stage_id::text;
alter table tasks alter column stage_id drop not null;

-- 6. Drop columns that left the model.
alter table tasks drop column if exists start_date;
alter table tasks drop column if exists end_date;
alter table tasks drop column if exists assigned_to;
alter table tasks alter column description drop not null;
alter table tasks alter column description drop default;

-- 7. The old enum type is no longer referenced.
drop type if exists task_status;

-- 8. Activity feed + comments.
create table if not exists activities (
  id                  bigserial primary key,
  task_id             bigint not null references tasks(id) on delete cascade,
  type                text not null default 'history',
  action              text not null,
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

create index if not exists activities_task_id_idx on activities(task_id);
create index if not exists comments_task_id_idx   on comments(task_id);

-- 9. RLS off on every table (single-user tool with a publishable/anon key).
--    tasks/projects are included in case they were created with RLS on.
alter table tasks      disable row level security;
alter table projects   disable row level security;
alter table activities disable row level security;
alter table comments   disable row level security;
