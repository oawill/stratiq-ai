-- Phase 4G: football alerts. Delivery is in-app, through the existing `notifications` table (and its quiet hours, caps and deduplication).
-- Nothing is sent to anyone who has not chosen categories: with no row here, or an empty category list, a person receives nothing.

create table if not exists football_notification_preferences (
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  user_id       uuid not null references users(id) on delete cascade,
  categories    text[] not null default '{}' check (cardinality(categories) <= 8),
  competitions  text[] not null default '{EPL}' check (cardinality(competitions) between 1 and 5),
  teams         text[] not null default '{}' check (cardinality(teams) <= 20),
  channels      jsonb not null default '{"email": false, "push": false}'::jsonb,
  updated_at    timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

-- The workspace's football events, each recorded once (the dedupe key is unique), whether or not anyone has asked to hear about it.
create table if not exists football_notification_events (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  category      text not null check (category in ('new_fixture', 'new_prediction', 'probability_change', 'lineup_change', 'final_result', 'evaluation_complete', 'provider_failure', 'data_quality')),
  fixture_id    uuid references football_fixtures(id) on delete set null,
  competition   text not null default 'EPL',
  teams         text[] not null default '{}',
  title         text not null check (char_length(title) <= 200),
  body          text not null check (char_length(body) <= 600),
  href          text,
  detail        jsonb not null default '{}'::jsonb,
  dedupe_key    text not null check (char_length(dedupe_key) <= 250),
  delivered     integer not null default 0,
  created_at    timestamptz not null default now(),
  unique (workspace_id, dedupe_key)
);
create index if not exists football_notification_events_ws_idx on football_notification_events (workspace_id, created_at desc);
