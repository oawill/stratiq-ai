-- Phase 7: the personalised Control Center. Everything here is per authenticated user inside a workspace.

-- Preferences: dashboard layout, preferred domains, notification settings (including quiet hours) and briefing settings. One row per person.
create table if not exists user_preferences (
  user_id       uuid primary key references users(id) on delete cascade,
  dashboard     jsonb not null default '{}'::jsonb,
  notifications jsonb not null default '{}'::jsonb,
  briefing      jsonb not null default '{}'::jsonb,
  updated_at    timestamptz not null default now()
);

-- Universal watchlists: the Phase 2 table gains a domain, a free-text note and a group, and more entity kinds. Existing rows become sports items.
alter table watchlist_items add column if not exists domain text not null default 'sports';
alter table watchlist_items add column if not exists note text;
alter table watchlist_items add column if not exists group_name text;
alter table watchlist_items drop constraint if exists watchlist_items_kind_check;
alter table watchlist_items add constraint watchlist_items_kind_check check (kind in ('team', 'fixture', 'competition', 'company', 'indicator', 'election', 'instrument'));
alter table watchlist_items drop constraint if exists watchlist_items_domain_check;
alter table watchlist_items add constraint watchlist_items_domain_check check (domain in ('sports', 'business', 'politics', 'markets'));
alter table watchlist_items drop constraint if exists watchlist_items_note_check;
alter table watchlist_items add constraint watchlist_items_note_check check (note is null or char_length(note) <= 300);
alter table watchlist_items drop constraint if exists watchlist_items_group_name_check;
alter table watchlist_items add constraint watchlist_items_group_name_check check (group_name is null or char_length(group_name) <= 40);
alter table watchlist_items drop constraint if exists watchlist_items_workspace_id_user_id_kind_item_key_key;
alter table watchlist_items drop constraint if exists watchlist_items_unique_entity;
alter table watchlist_items add constraint watchlist_items_unique_entity unique (workspace_id, user_id, domain, kind, item_key);
create index if not exists watchlist_items_domain_idx on watchlist_items (workspace_id, user_id, domain, created_at desc);

-- Alert rules: nothing is created for anyone; a person opts in by creating a rule.
create table if not exists alert_rules (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references users(id) on delete cascade,
  kind         text not null check (kind in ('watched_result', 'fixture_soon', 'forecast_scored', 'data_stale', 'model_drift', 'briefing_ready')),
  config       jsonb not null default '{}'::jsonb,
  enabled      boolean not null default true,
  created_at   timestamptz not null default now(),
  unique (workspace_id, user_id, kind)
);

-- Notification history. `dedupe_key` makes a repeat of the same event a no-op; `visible_after` holds notifications back during quiet hours.
create table if not exists notifications (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  user_id       uuid not null references users(id) on delete cascade,
  rule_id       uuid references alert_rules(id) on delete set null,
  kind          text not null,
  title         text not null check (char_length(title) <= 200),
  body          text not null check (char_length(body) <= 600),
  source        jsonb not null default '{}'::jsonb,
  dedupe_key    text not null check (char_length(dedupe_key) <= 300),
  created_at    timestamptz not null default now(),
  visible_after timestamptz not null default now(),
  read_at       timestamptz,
  deleted_at    timestamptz,                       -- deleting hides a notification but keeps its dedupe key, so the same event never notifies twice
  unique (workspace_id, user_id, dedupe_key)
);
alter table notifications add column if not exists deleted_at timestamptz;
create index if not exists notifications_user_idx on notifications (workspace_id, user_id, visible_after desc);
create index if not exists notifications_unread_idx on notifications (workspace_id, user_id) where read_at is null;

-- Briefings: a stored summary of what changed in a window, with citations. Private to the person who generated it.
create table if not exists briefings (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references users(id) on delete cascade,
  period       text not null check (period in ('daily', 'weekly')),
  domains      text[] not null,
  window_start timestamptz not null,
  window_end   timestamptz not null,
  content      jsonb not null,
  has_changes  boolean not null,
  created_at   timestamptz not null default now()
);
create index if not exists briefings_user_idx on briefings (workspace_id, user_id, created_at desc);

-- Indexes the Control Center reads through.
create index if not exists match_history_imported_idx on match_history (workspace_id, imported_at desc);
create index if not exists football_predictions_live_idx on football_predictions (workspace_id, created_at desc) where kind = 'live';
