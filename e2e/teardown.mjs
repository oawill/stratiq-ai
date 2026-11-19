// Removes every account created by the end-to-end tests (e2e-*@stratiq.test) and their workspaces.
import fs from "node:fs";
import pg from "pg";

if (fs.existsSync(".env.local")) {
  for (const l of fs.readFileSync(".env.local", "utf8").split(/\r?\n/)) {
    const m = /^([A-Z_0-9]+)=(.*)$/.exec(l);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}

export default async function globalTeardown() {
  const url = process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
  if (!url) return;
  const c = new pg.Client({ connectionString: url, ssl: { rejectUnauthorized: false } });
  await c.connect();
  try {
    await c.query("begin");
    // Predictions are immutable; deleting a test workspace needs the explicit maintenance opt-in.
    await c.query("select set_config('stratiq.allow_prediction_delete','on',true)");
    const users = (await c.query("select id from users where email like 'e2e-%@stratiq.test'")).rows.map((r) => r.id);
    if (users.length) {
      const ws = (await c.query(
        `select w.id from workspaces w
          where exists (select 1 from workspace_members m where m.workspace_id = w.id and m.user_id = any($1))
            and not exists (select 1 from workspace_members m where m.workspace_id = w.id and m.user_id <> all($1))`,
        [users],
      )).rows.map((r) => r.id);
      await c.query("delete from audit_logs where workspace_id = any($1) or user_id = any($2)", [ws, users]);
      await c.query("delete from workspaces where id = any($1)", [ws]);
      await c.query("delete from users where id = any($1)", [users]);
      console.log(`e2e teardown: removed ${users.length} account(s) and ${ws.length} workspace(s)`);
    }
    await c.query("commit");
  } catch (e) {
    await c.query("rollback");
    throw e;
  } finally {
    await c.end();
  }
}
