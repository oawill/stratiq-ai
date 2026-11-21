-- SimLab: persistent records of scenario simulations (starting with the sports simulator). Each run stores its inputs, outputs, model version, input data provenance,
-- random seed (null for deterministic models) and timestamp. Runs of the same scenario form a version chain through scenario_key, version and parent_id.

create table if not exists simlab_runs (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  created_by    uuid not null references users(id),
  domain        text not null check (domain in ('sports', 'business', 'politics', 'markets')),
  title         text not null check (char_length(title) between 1 and 120),
  scenario_key  uuid not null,
  version       integer not null default 1 check (version >= 1),
  parent_id     uuid references simlab_runs(id) on delete set null,
  model_name    text not null,
  model_version text not null,
  inputs        jsonb not null,
  outputs       jsonb not null,
  provenance    jsonb not null,
  seed          bigint,
  created_at    timestamptz not null default now()
);
create index if not exists simlab_runs_ws_idx on simlab_runs (workspace_id, created_at desc);
create index if not exists simlab_runs_user_idx on simlab_runs (workspace_id, created_by, created_at desc);
create index if not exists simlab_runs_key_idx on simlab_runs (workspace_id, scenario_key, version);
