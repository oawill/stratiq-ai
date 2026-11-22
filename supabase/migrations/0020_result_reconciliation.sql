-- Phase 4F: verified results, evaluation of the official forecast, and performance reports.

-- What was last reconciled for a fixture, so a later change of the provider's score is noticed and a finished match is not reprocessed forever.
alter table football_fixtures add column if not exists reconciled_home smallint;
alter table football_fixtures add column if not exists reconciled_away smallint;
alter table football_fixtures add column if not exists reconciled_at   timestamptz;
alter table football_fixtures add column if not exists result_note     text check (result_note is null or char_length(result_note) <= 300);
create index if not exists football_fixtures_reconcile_idx on football_fixtures (workspace_id, kickoff_utc) where status = 'finished' or reconciled_at is not null;

-- Every distinct full-time score the provider has given for a fixture. A correction is a new revision, never an overwrite.
create table if not exists football_result_history (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  fixture_id    uuid not null references football_fixtures(id) on delete cascade,
  revision      integer not null check (revision > 0),
  home_goals    smallint not null check (home_goals between 0 and 50),
  away_goals    smallint not null check (away_goals between 0 and 50),
  observed_at   timestamptz not null default now(),
  unique (fixture_id, revision)
);

-- The score of the official pre-kickoff forecast against the verified result. One row per forecast version, so reconciling twice cannot count a match twice.
create table if not exists football_prediction_evaluations (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  fixture_id       uuid not null references football_fixtures(id) on delete cascade,
  version_id       uuid not null unique references football_prediction_versions(id),
  model_name       text not null,
  home_goals       smallint not null,
  away_goals       smallint not null,
  outcome          smallint not null check (outcome in (0, 1, 2)),      -- 0 home win, 1 draw, 2 away win
  p_actual         real not null check (p_actual between 0 and 1),
  log_loss         real not null,
  brier            real not null,
  rps              real not null,
  correct          boolean not null,
  markets          jsonb not null default '{}'::jsonb,
  correction_count integer not null default 0,
  evaluated_at     timestamptz not null default now(),
  voided_at        timestamptz,
  void_reason      text check (void_reason is null or char_length(void_reason) <= 300)
);
create index if not exists football_prediction_evaluations_ws_idx on football_prediction_evaluations (workspace_id, evaluated_at desc) where voided_at is null;
create index if not exists football_prediction_evaluations_fixture_idx on football_prediction_evaluations (fixture_id);

-- Daily summaries and weekly model performance reports, created once per period.
create table if not exists football_performance_reports (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  period        text not null check (period in ('daily', 'weekly')),
  window_start  timestamptz not null,
  window_end    timestamptz not null,
  summary       jsonb not null,
  created_at    timestamptz not null default now(),
  unique (workspace_id, period, window_end)
);
create index if not exists football_performance_reports_ws_idx on football_performance_reports (workspace_id, period, window_end desc);
