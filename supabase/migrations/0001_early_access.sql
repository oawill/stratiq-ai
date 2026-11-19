-- Early-access signups. Emails are stored lower-cased and are unique.
create table if not exists early_access_signups (
  id           bigserial primary key,
  full_name    text        not null check (char_length(full_name) between 2 and 120),
  email        text        not null unique check (email = lower(email)),
  country      text        not null,
  interest     text        not null check (interest in ('Sports','Business','Politics','Finance')),
  intended_use text        not null check (intended_use in ('Personal','Analyst','Business','Enterprise')),
  consent      boolean     not null check (consent = true),
  source       text,
  created_at   timestamptz not null default now()
);

create index if not exists early_access_created_idx on early_access_signups (created_at desc);

-- Supabase: block all direct client access. The app reads/writes through the server
-- using DATABASE_URL (a privileged server-side connection) — never from the browser.
alter table early_access_signups enable row level security;
