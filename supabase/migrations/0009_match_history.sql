-- Historical match results a workspace has imported (one row per played fixture), and a log of each import with its validation
-- report. Private to the workspace. Season and source stay here; the CSV export carries only the five match columns.
create table if not exists match_history (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  competition      text not null check (competition in ('EPL')),
  season           text not null check (season ~ '^[0-9]{4}/[0-9]{2}$'),
  match_date       date not null,
  home_team        text not null check (char_length(home_team) between 1 and 60),
  away_team        text not null check (char_length(away_team) between 1 and 60 and away_team <> home_team),
  home_goals       smallint not null check (home_goals between 0 and 30),
  away_goals       smallint not null check (away_goals between 0 and 30),
  source_provider  text not null default 'user_upload',
  source_reference text,
  imported_at      timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  -- the same fixture can only be stored once, which is what makes repeated imports safe
  constraint match_history_fixture unique (workspace_id, competition, season, match_date, home_team, away_team)
);
create index if not exists match_history_season_idx on match_history (workspace_id, competition, season);
create index if not exists match_history_date_idx on match_history (workspace_id, match_date);
create index if not exists match_history_home_idx on match_history (workspace_id, home_team);
create index if not exists match_history_away_idx on match_history (workspace_id, away_team);

create table if not exists match_imports (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  competition   text not null,
  filename      text,
  file_sha256   text,
  status        text not null check (status in ('ok', 'needs_review')),
  report        jsonb not null,
  created_by    uuid references users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists match_imports_ws_idx on match_imports (workspace_id, competition, created_at desc);
