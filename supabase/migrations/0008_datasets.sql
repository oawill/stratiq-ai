-- User-supplied datasets (CSV uploads), private to a workspace. `data` is the validated, normalized content (not the raw
-- file); `sha256` identifies exactly what a result was computed from.
create table if not exists datasets (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  kind          text not null check (kind in ('sports_results', 'market_returns', 'political_seats', 'series')),
  name          text not null check (char_length(name) between 1 and 120),
  description   text check (description is null or char_length(description) <= 500),
  row_count     integer not null check (row_count >= 0),
  summary       jsonb not null,
  data          jsonb not null,
  sha256        text not null,
  created_by    uuid references users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists datasets_ws_idx on datasets (workspace_id, created_at desc);
