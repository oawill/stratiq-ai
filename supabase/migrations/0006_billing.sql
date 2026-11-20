-- Billing: one subscription row per workspace (no row = the free Explorer plan), written only by the Stripe webhook.
create table if not exists subscriptions (
  workspace_id uuid primary key references workspaces(id) on delete cascade,
  plan text not null check (plan in ('sports_pro', 'strategy_pro')),
  status text not null,
  billing_interval text not null default 'month' check (billing_interval in ('month', 'year')),
  stripe_customer_id text not null,
  stripe_subscription_id text not null unique,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  updated_at timestamptz not null default now()
);
create index if not exists subscriptions_customer_idx on subscriptions (stripe_customer_id);

-- Webhook idempotency: Stripe retries events, so each event id is processed once.
create table if not exists stripe_events (
  event_id text primary key,
  type text not null,
  received_at timestamptz not null default now()
);
