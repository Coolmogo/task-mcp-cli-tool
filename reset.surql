-- Wipes all records from the task tables, preserving the schema (table/field
-- definitions and indexes from schema.surql). Run in the Surrealist query editor.
-- DELETE with no WHERE clears every record in the table but keeps its definition.
-- There are no id sequences to reset: SurrealDB record ids are not auto-increment.

DELETE comment;
DELETE activity;
DELETE proposal;
DELETE task;
DELETE project;
DELETE user;
