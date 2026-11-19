-- Simulation Lab: richer run tracking for asynchronous Monte Carlo jobs.
alter table simulation_runs add column if not exists title text not null default 'Untitled simulation';
alter table simulation_runs add column if not exists iterations int;
alter table simulation_runs add column if not exists started_at timestamptz;
alter table simulation_runs add column if not exists heartbeat_at timestamptz;

alter table simulation_runs drop constraint if exists simulation_runs_status_check;
alter table simulation_runs add constraint simulation_runs_status_check
  check (status in ('queued','running','completed','failed','cancelled'));

create index if not exists simulation_runs_ws_idx on simulation_runs (workspace_id, created_at desc);
