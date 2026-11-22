-- Phase 4E: scheduled refresh of live forecasts.

-- Configurable checkpoints (minutes before kickoff) and a switch for automatic forecasting, per workspace.
create table if not exists football_live_settings (
  workspace_id       uuid primary key references workspaces(id) on delete cascade,
  checkpoint_minutes integer[] not null default '{2880,1440,360,60}'
                     check (cardinality(checkpoint_minutes) between 1 and 8),
  auto_forecast      boolean not null default true,
  updated_by         uuid references users(id) on delete set null,
  updated_at         timestamptz not null default now()
);

-- Which checkpoint has been handled for which kickoff time. The unique key is what makes the scheduler idempotent:
-- two overlapping runs cannot both claim a checkpoint, and a rescheduled match (new kickoff time) gets its checkpoints again.
create table if not exists football_refresh_runs (
  id                 uuid primary key default gen_random_uuid(),
  workspace_id       uuid not null references workspaces(id) on delete cascade,
  fixture_id         uuid not null references football_fixtures(id) on delete cascade,
  kickoff_utc        timestamptz not null,
  checkpoint_minutes integer not null check (checkpoint_minutes between 1 and 14400),
  outcome            text not null check (outcome in ('claimed', 'created', 'unchanged', 'ineligible', 'skipped_late', 'failed')),
  attempts           integer not null default 1,
  version_no         integer,
  detail             text check (detail is null or char_length(detail) <= 300),
  handled_at         timestamptz not null default now(),
  unique (fixture_id, kickoff_utc, checkpoint_minutes)
);
create index if not exists football_refresh_runs_ws_idx on football_refresh_runs (workspace_id, handled_at desc);

-- A checkpoint set by a person is not always one of the four named ones.
alter table football_prediction_versions drop constraint if exists football_prediction_versions_checkpoint_check;
alter table football_prediction_versions add constraint football_prediction_versions_checkpoint_check
  check (checkpoint in ('discovery', 'h48', 'h24', 'h6', 'h1', 'scheduled', 'reschedule', 'lineup', 'manual'));

-- Light scheduled ticks are recorded as their own kind of job run.
alter table football_job_runs drop constraint if exists football_job_runs_kind_check;
alter table football_job_runs add constraint football_job_runs_kind_check check (kind in ('scheduled', 'monitor', 'retrain', 'live'));
