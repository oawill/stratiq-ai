-- Predictions stay immutable: UPDATE is always rejected.
-- DELETE is rejected unless a maintenance transaction explicitly opts in with
--   set local stratiq.allow_prediction_delete = 'on';
-- (needed for deleting a workspace/account). The application never sets this.
create or replace function forbid_prediction_mutation() returns trigger as $$
begin
  if tg_op = 'DELETE' and current_setting('stratiq.allow_prediction_delete', true) = 'on' then
    return old;
  end if;
  raise exception 'predictions are immutable records';
end;
$$ language plpgsql;
