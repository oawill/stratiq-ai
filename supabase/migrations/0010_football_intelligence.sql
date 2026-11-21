-- Football prediction intelligence. `match_history` (migration 0009) is the football_matches table; the tables below add everything else.
-- Everything is private to a workspace. Nothing here is supplied by VELQORIN: each row records where it came from and when it became available.

-- A new kind of dataset: uploaded advanced statistics (expected goals, shots, corners, odds).
alter table datasets drop constraint if exists datasets_kind_check;
alter table datasets add constraint datasets_kind_check check (kind in ('sports_results', 'market_returns', 'political_seats', 'series', 'football_stats'));

-- Where each body of football data came from, with its coverage and quality at the time.
create table if not exists football_data_sources (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  kind          text not null check (kind in ('match_results', 'fixtures', 'advanced_statistics', 'player_availability')),
  name          text not null,
  provider      text not null default 'user_upload',
  reference     text,
  licence_note  text not null default 'Supplied by the user, who is responsible for having the right to use it.',
  coverage      jsonb not null default '{}'::jsonb,
  quality       jsonb not null default '{}'::jsonb,
  created_by    uuid references users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists football_data_sources_ws_idx on football_data_sources (workspace_id, kind, created_at desc);

create table if not exists football_teams (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  competition   text not null,
  name          text not null,
  first_season  text not null,
  last_season   text not null,
  matches       integer not null default 0,
  updated_at    timestamptz not null default now(),
  unique (workspace_id, competition, name)
);

-- Upcoming fixtures (future-dated rows of an imported fixtures file).
create table if not exists football_fixtures (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  competition   text not null,
  season        text not null,
  fixture_date  date not null,
  home_team     text not null,
  away_team     text not null check (away_team <> home_team),
  source_id     uuid references football_data_sources(id) on delete set null,
  imported_at   timestamptz not null default now(),
  unique (workspace_id, competition, fixture_date, home_team, away_team)
);
create index if not exists football_fixtures_date_idx on football_fixtures (workspace_id, fixture_date);

-- Uploaded advanced statistics, one row per match. `available_at` is when the information could first have been used for a forecast:
-- post-match statistics the day after the match, pre-match odds on the match day.
create table if not exists football_team_statistics (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  dataset_id    uuid not null references datasets(id) on delete cascade,
  match_date    date not null,
  home_team     text not null,
  away_team     text not null,
  home_xg       real, away_xg real,
  home_shots    smallint, away_shots smallint,
  home_shots_on_target smallint, away_shots_on_target smallint,
  home_corners  smallint, away_corners smallint,
  odds_home     real, odds_draw real, odds_away real,
  available_at  timestamptz not null,
  unique (dataset_id, match_date, home_team, away_team)
);
create index if not exists football_team_statistics_ws_idx on football_team_statistics (workspace_id, match_date);

-- Schema for injuries and suspensions. No upload or feed writes to it yet, so the factor reads "unavailable" until one exists.
create table if not exists football_player_availability (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  team          text not null,
  player        text not null,
  status        text not null check (status in ('injured', 'suspended', 'doubtful', 'available')),
  from_date     date not null,
  to_date       date,
  source_id     uuid references football_data_sources(id) on delete set null,
  available_at  timestamptz not null
);
create index if not exists football_player_availability_idx on football_player_availability (workspace_id, team, from_date);

create table if not exists football_backtest_runs (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references workspaces(id) on delete cascade,
  mode           text not null check (mode in ('chronological', 'rolling')),
  status         text not null default 'complete' check (status in ('running', 'complete', 'failed')),
  config         jsonb not null,
  data_sha256    text not null,
  matches        integer not null,
  results        jsonb,
  tuning         jsonb,
  warnings       jsonb,
  created_by     uuid references users(id) on delete set null,
  created_at     timestamptz not null default now(),
  finished_at    timestamptz
);
create index if not exists football_backtest_runs_ws_idx on football_backtest_runs (workspace_id, created_at desc);

-- A model with the exact settings it ran with, so a stored forecast can be reproduced.
create table if not exists football_model_versions (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references workspaces(id) on delete cascade,
  name           text not null,
  version        text not null,
  params         jsonb not null,
  trained_through date,
  data_sha256    text not null,
  backtest_run_id uuid references football_backtest_runs(id) on delete set null,
  created_at     timestamptz not null default now(),
  unique (workspace_id, name, version, data_sha256, backtest_run_id)
);

-- What was known about a fixture at the cutoff, frozen.
create table if not exists football_feature_snapshots (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references workspaces(id) on delete cascade,
  fixture_date   date not null,
  home_team      text not null,
  away_team      text not null,
  cutoff         date not null,
  features       jsonb not null,
  availability   jsonb not null,
  warnings       jsonb not null,
  sha256         text not null,
  created_at     timestamptz not null default now(),
  unique (workspace_id, home_team, away_team, fixture_date, cutoff, sha256)
);

create table if not exists football_predictions (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  kind             text not null check (kind in ('backtest', 'live')),
  backtest_run_id  uuid references football_backtest_runs(id) on delete cascade,
  model_version_id uuid not null references football_model_versions(id) on delete cascade,
  snapshot_id      uuid references football_feature_snapshots(id) on delete set null,
  period           text,
  season           text not null,
  fixture_date     date not null,
  home_team        text not null,
  away_team        text not null,
  cutoff           date not null,
  p_home           real not null,
  p_draw           real not null,
  p_away           real not null,
  p_over_2_5       real,
  p_btts           real,
  expected_home    real,
  expected_away    real,
  outputs          jsonb not null default '{}'::jsonb,
  inputs           jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now()
);
create index if not exists football_predictions_run_idx on football_predictions (backtest_run_id, model_version_id);
create index if not exists football_predictions_fixture_idx on football_predictions (workspace_id, kind, fixture_date, home_team, away_team);
-- one live forecast per model per fixture per cutoff, which makes generating them again harmless
create unique index if not exists football_predictions_live_uq on football_predictions (workspace_id, model_version_id, fixture_date, home_team, away_team, cutoff) where kind = 'live';

create table if not exists football_prediction_outcomes (
  prediction_id  uuid primary key references football_predictions(id) on delete cascade,
  home_goals     smallint not null,
  away_goals     smallint not null,
  outcome        smallint not null check (outcome in (0, 1, 2)),   -- 0 home win, 1 draw, 2 away win
  log_loss       real not null,
  brier          real not null,
  correct        boolean not null,
  scored_at      timestamptz not null default now()
);
