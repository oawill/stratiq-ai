-- Users can belong to several workspaces; this records the one they last switched to.
-- NULL (or a workspace they have left) falls back to their oldest membership.
alter table users add column if not exists active_workspace_id uuid references workspaces(id) on delete set null;
