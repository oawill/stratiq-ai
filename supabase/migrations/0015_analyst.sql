-- AI Analyst: private, user-scoped conversations. A conversation belongs to one person in one workspace; nobody else (including other members) can read it.
-- Stored: the questions and answers, the display blocks and citations needed to show an answer again, and a few remembered subjects (clubs, a fixture, a saved
-- simulation) so follow-up questions work. Tool results are NOT stored; only compact blocks. Old conversations are deleted after the retention period.

create table if not exists analyst_conversations (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references users(id) on delete cascade,
  title        text not null check (char_length(title) between 1 and 120),
  state        jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists analyst_conversations_user_idx on analyst_conversations (workspace_id, user_id, updated_at desc);

create table if not exists analyst_messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references analyst_conversations(id) on delete cascade,
  workspace_id    uuid not null references workspaces(id) on delete cascade,
  user_id         uuid not null references users(id) on delete cascade,
  role            text not null check (role in ('user', 'assistant')),
  content         text not null check (char_length(content) <= 8000),
  blocks          jsonb,
  citations       jsonb,
  trust           jsonb,
  tool_calls      jsonb,
  proposals       jsonb,
  mode            text,
  usage           jsonb,
  created_at      timestamptz not null default now()
);
create index if not exists analyst_messages_conv_idx on analyst_messages (conversation_id, created_at);
