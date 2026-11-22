-- Phase 4B: versioned pre-match forecasts for live fixtures.
-- Every forecast is a new row. A row is never changed after it is written, except that one of a fixture's rows is marked as the official evaluation forecast.

create table if not exists football_prediction_versions (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  fixture_id       uuid not null references football_fixtures(id) on delete cascade,
  version_no       integer not null check (version_no > 0),
  model_version_id uuid not null references football_model_versions(id),
  model_name       text not null,
  goal_model       text not null,
  snapshot_id      uuid not null references football_feature_snapshots(id),
  input_sha256     text not null,
  generated_at     timestamptz not null,
  kickoff_utc      timestamptz not null,
  checkpoint       text not null check (checkpoint in ('discovery', 'h48', 'h24', 'h6', 'h1', 'reschedule', 'lineup', 'manual')),
  refresh_reason   text not null check (char_length(refresh_reason) between 1 and 300),
  p_home           real not null check (p_home between 0 and 1),
  p_draw           real not null check (p_draw between 0 and 1),
  p_away           real not null check (p_away between 0 and 1),
  expected_home    real,
  expected_away    real,
  p_over_2_5       real check (p_over_2_5 is null or p_over_2_5 between 0 and 1),
  p_btts           real check (p_btts is null or p_btts between 0 and 1),
  top_scorelines   jsonb not null default '[]'::jsonb,
  drivers          jsonb not null default '[]'::jsonb,
  warnings         jsonb not null default '[]'::jsonb,
  completeness     jsonb not null,
  provider_refs    jsonb not null default '{}'::jsonb,
  change_from_previous jsonb,
  is_official      boolean not null default false,
  created_at       timestamptz not null default now(),
  unique (fixture_id, version_no),
  -- generated strictly before kickoff, and the three outcome probabilities add up to one
  check (generated_at < kickoff_utc),
  check (abs(p_home + p_draw + p_away - 1) < 0.002)
);
create index if not exists football_prediction_versions_fixture_idx on football_prediction_versions (fixture_id, version_no desc);
create index if not exists football_prediction_versions_ws_idx on football_prediction_versions (workspace_id, generated_at desc);
-- one official evaluation forecast per fixture
create unique index if not exists football_prediction_versions_official_uq on football_prediction_versions (fixture_id) where is_official;

-- A stored forecast cannot be edited. Only the official marker may change.
create or replace function football_prediction_versions_immutable() returns trigger as $$
begin
  if (to_jsonb(new) - 'is_official') is distinct from (to_jsonb(old) - 'is_official') then
    raise exception 'A stored forecast cannot be changed; generate a new version instead.' using errcode = 'check_violation';
  end if;
  return new;
end;
$$ language plpgsql;
drop trigger if exists football_prediction_versions_immutable_trg on football_prediction_versions;
create trigger football_prediction_versions_immutable_trg before update on football_prediction_versions for each row execute function football_prediction_versions_immutable();
