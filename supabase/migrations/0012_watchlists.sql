-- Watchlists: a person's own list of Premier League clubs and upcoming fixtures to keep an eye on. Personal to the user within a workspace.

create table if not exists watchlist_items (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references users(id) on delete cascade,
  kind         text not null check (kind in ('team', 'fixture')),
  item_key     text not null check (char_length(item_key) between 1 and 200),   -- team name, or "date|home|away"
  label        text not null check (char_length(label) between 1 and 200),
  created_at   timestamptz not null default now(),
  unique (workspace_id, user_id, kind, item_key)
);
create index if not exists watchlist_items_user_idx on watchlist_items (workspace_id, user_id, created_at desc);
