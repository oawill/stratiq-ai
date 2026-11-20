-- Teams: invitations and comments.

-- An invitation is bound to an email address and carries a single-use token. Only the SHA-256 of the token is stored.
create table if not exists workspace_invites (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  email         text not null check (email = lower(email) and char_length(email) <= 254),
  role          text not null check (role in ('admin', 'member', 'viewer')),
  token_hash    text not null unique,
  invited_by    uuid references users(id) on delete set null,
  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null,
  accepted_at   timestamptz,
  revoked_at    timestamptz
);
create index if not exists workspace_invites_ws_idx on workspace_invites (workspace_id, created_at desc);
-- At most one live (pending) invitation per workspace and email.
create unique index if not exists workspace_invites_pending_uq on workspace_invites (workspace_id, email)
  where accepted_at is null and revoked_at is null;

-- Comments on saved work. item_type picks the table the item lives in; replies go one level deep (parent_id).
create table if not exists comments (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  item_type     text not null check (item_type in ('prediction', 'scenario', 'simulation')),
  item_id       uuid not null,
  parent_id     uuid references comments(id) on delete cascade,
  author_id     uuid not null references users(id) on delete cascade,
  body          text not null check (char_length(body) between 1 and 2000),
  created_at    timestamptz not null default now(),
  deleted_at    timestamptz
);
create index if not exists comments_item_idx on comments (workspace_id, item_type, item_id, created_at);
