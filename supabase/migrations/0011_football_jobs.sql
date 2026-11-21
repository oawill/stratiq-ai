-- Phase 10: scheduled football jobs (reconcile, forecast upcoming fixtures, monitor drift, retrain) and a "rejected" backtest status.

alter table football_backtest_runs drop constraint if exists football_backtest_runs_status_check;
alter table football_backtest_runs add constraint football_backtest_runs_status_check check (status in ('running', 'complete', 'failed', 'rejected'));

create table if not exists football_job_runs (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  kind         text not null check (kind in ('scheduled', 'monitor', 'retrain')),
  trigger      text not null check (trigger in ('schedule', 'manual')),
  status       text not null check (status in ('complete', 'skipped', 'failed')),
  detail       jsonb not null default '{}'::jsonb,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz
);
create index if not exists football_job_runs_ws_idx on football_job_runs (workspace_id, started_at desc);
