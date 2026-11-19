-- STRATIQ AI application core: auth, workspaces, models, sports data, predictions,
-- and tables reserved for later modules. All user-owned rows carry workspace_id.

create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique check (email = lower(email)),
  name          text not null check (char_length(name) between 1 and 120),
  password_hash text not null,
  created_at    timestamptz not null default now()
);

-- Session id is the SHA-256 of the cookie token; the raw token is never stored.
create table if not exists sessions (
  id         text primary key,
  user_id    uuid not null references users(id) on delete cascade,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists sessions_user_idx on sessions (user_id);

create table if not exists workspaces (
  id         uuid primary key default gen_random_uuid(),
  name       text not null check (char_length(name) between 1 and 120),
  created_at timestamptz not null default now()
);

create table if not exists workspace_members (
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references users(id) on delete cascade,
  role         text not null check (role in ('owner','admin','member','viewer')),
  created_at   timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
create index if not exists workspace_members_user_idx on workspace_members (user_id);

-- Model registry (global reference data).
create table if not exists model_versions (
  id          uuid primary key default gen_random_uuid(),
  domain      text not null check (domain in ('sports','business','politics','finance','simulation')),
  name        text not null,
  version     text not null,
  description text not null,
  status      text not null default 'experimental' check (status in ('active','experimental','retired')),
  assumptions jsonb not null default '[]'::jsonb,
  limitations jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now(),
  unique (name, version)
);

-- Sports reference data. The development dataset is FICTIONAL and flagged as such.
create table if not exists sports_leagues (
  id          text primary key,
  name        text not null,
  country     text not null,
  data_source text not null default 'fictional-dev-dataset',
  is_fictional boolean not null default true
);
create table if not exists sports_teams (
  id        text primary key,
  league_id text not null references sports_leagues(id),
  name      text not null
);
create table if not exists sports_matches (
  id           bigserial primary key,
  league_id    text not null references sports_leagues(id),
  home_team_id text not null references sports_teams(id),
  away_team_id text not null references sports_teams(id),
  kickoff      timestamptz not null,
  home_goals   int check (home_goals >= 0),
  away_goals   int check (away_goals >= 0),
  status       text not null check (status in ('scheduled','finished')),
  data_source  text not null default 'fictional-dev-dataset',
  check (home_team_id <> away_team_id),
  check ((status = 'finished') = (home_goals is not null and away_goals is not null))
);
create index if not exists sports_matches_league_idx on sports_matches (league_id, kickoff);

-- Predictions are IMMUTABLE records (see trigger below).
create table if not exists predictions (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references workspaces(id) on delete cascade,
  user_id         uuid not null references users(id),
  domain          text not null,
  model_version_id uuid not null references model_versions(id),
  subject_type    text not null,
  subject_id      text not null,
  feature_cutoff  timestamptz not null,
  inputs          jsonb not null,
  outputs         jsonb not null,
  assumptions     jsonb not null,
  input_hash      text not null,
  created_at      timestamptz not null default now()
);
create index if not exists predictions_ws_idx on predictions (workspace_id, created_at desc);

create or replace function forbid_prediction_mutation() returns trigger as $$
begin
  raise exception 'predictions are immutable records';
end;
$$ language plpgsql;

drop trigger if exists predictions_immutable on predictions;
create trigger predictions_immutable
  before update or delete on predictions
  for each row execute function forbid_prediction_mutation();

-- Evaluation metrics: only ever written by a real backtest run.
create table if not exists evaluation_metrics (
  id               uuid primary key default gen_random_uuid(),
  model_version_id uuid not null references model_versions(id),
  metric           text not null,
  value            double precision not null,
  sample_size      int not null,
  dataset          text not null,
  computed_at      timestamptz not null default now()
);

-- Reserved for later modules (Business, Simulation Lab).
create table if not exists strategic_scenarios (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  created_by   uuid not null references users(id),
  title        text not null,
  domain       text not null,
  definition   jsonb not null,
  created_at   timestamptz not null default now()
);
create table if not exists payoff_matrices (
  id           uuid primary key default gen_random_uuid(),
  scenario_id  uuid not null references strategic_scenarios(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  matrix       jsonb not null,
  solution     jsonb,
  created_at   timestamptz not null default now()
);
create table if not exists simulation_runs (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  created_by   uuid not null references users(id),
  domain       text not null,
  config       jsonb not null,
  seed         bigint not null,
  status       text not null default 'queued' check (status in ('queued','running','completed','failed')),
  progress     real not null default 0,
  result       jsonb,
  error        text,
  created_at   timestamptz not null default now(),
  finished_at  timestamptz
);

create table if not exists activity_history (
  id           bigserial primary key,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid references users(id),
  kind         text not null,
  summary      text not null,
  ref_type     text,
  ref_id       text,
  created_at   timestamptz not null default now()
);
create index if not exists activity_ws_idx on activity_history (workspace_id, created_at desc);

create table if not exists audit_logs (
  id           bigserial primary key,
  workspace_id uuid,
  user_id      uuid,
  action       text not null,
  detail       jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);
