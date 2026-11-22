-- Phase 4A: live fixture ingestion from a licensed provider (football-data.org).
-- `football_fixtures` stays the one fixtures table: uploaded rows keep working, and provider rows add kickoff time, status and provider identity.
-- Historical results stay in `match_history`; nothing here is training data.

alter table football_fixtures add column if not exists kickoff_utc          timestamptz;
alter table football_fixtures add column if not exists status               text not null default 'scheduled';
alter table football_fixtures add column if not exists venue                text check (venue is null or char_length(venue) <= 120);
alter table football_fixtures add column if not exists matchday             smallint;
alter table football_fixtures add column if not exists provider             text;
alter table football_fixtures add column if not exists provider_updated_at  timestamptz;
alter table football_fixtures add column if not exists last_synced_at       timestamptz;
alter table football_fixtures add column if not exists home_goals           smallint check (home_goals is null or home_goals between 0 and 50);
alter table football_fixtures add column if not exists away_goals           smallint check (away_goals is null or away_goals between 0 and 50);
alter table football_fixtures drop constraint if exists football_fixtures_status_check;
alter table football_fixtures add constraint football_fixtures_status_check
  check (status in ('scheduled', 'in_play', 'paused', 'finished', 'awarded', 'postponed', 'suspended', 'cancelled'));
create index if not exists football_fixtures_kickoff_idx on football_fixtures (workspace_id, kickoff_utc) where kickoff_utc is not null;
create index if not exists football_fixtures_status_idx on football_fixtures (workspace_id, status, fixture_date);

-- The provider's own id for a fixture. One provider id is one fixture, so a rescheduled match is updated, never duplicated.
create table if not exists football_fixture_provider_mappings (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspaces(id) on delete cascade,
  fixture_id          uuid not null references football_fixtures(id) on delete cascade,
  provider            text not null check (char_length(provider) <= 40),
  provider_fixture_id text not null check (char_length(provider_fixture_id) <= 60),
  raw_home            text not null,
  raw_away            text not null,
  created_at          timestamptz not null default now(),
  unique (workspace_id, provider, provider_fixture_id),
  unique (fixture_id, provider)
);

-- Every change of status or kickoff time that a synchronisation observed.
create table if not exists football_fixture_status_history (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  fixture_id    uuid not null references football_fixtures(id) on delete cascade,
  old_status    text,
  new_status    text not null,
  old_kickoff   timestamptz,
  new_kickoff   timestamptz,
  sync_job_id   uuid,
  observed_at   timestamptz not null default now()
);
create index if not exists football_fixture_status_history_idx on football_fixture_status_history (fixture_id, observed_at desc);

-- One row per synchronisation attempt. A partial unique index allows only one running job per workspace and provider.
create table if not exists football_sync_jobs (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  provider      text not null,
  trigger       text not null check (trigger in ('schedule', 'manual')),
  status        text not null default 'running' check (status in ('running', 'complete', 'failed')),
  window_from   date not null,
  window_to     date not null,
  fetched       integer not null default 0,
  created       integer not null default 0,
  updated       integer not null default 0,
  unchanged     integer not null default 0,
  skipped       integer not null default 0,
  detail        jsonb not null default '{}'::jsonb,
  error         text,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz
);
create unique index if not exists football_sync_jobs_running_uq on football_sync_jobs (workspace_id, provider) where status = 'running';
create index if not exists football_sync_jobs_ws_idx on football_sync_jobs (workspace_id, started_at desc);

-- Provider health is shared (one API key serves the whole platform): last success and failure, a failure streak, and the request window used for rate limiting.
create table if not exists football_provider_health (
  provider              text primary key,
  last_success_at       timestamptz,
  last_failure_at       timestamptz,
  consecutive_failures  integer not null default 0,
  last_error            text,
  window_start          timestamptz,
  window_count          integer not null default 0,
  paused_until          timestamptz,
  updated_at            timestamptz not null default now()
);

-- Short-lived copy of provider responses, shared by every workspace, so one request serves many people and a provider outage can still show the last verified data.
create table if not exists football_provider_cache (
  provider     text not null,
  cache_key    text not null,
  body         jsonb not null,
  fetched_at   timestamptz not null default now(),
  expires_at   timestamptz not null,
  primary key (provider, cache_key)
);
