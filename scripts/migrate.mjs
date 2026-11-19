// Applies supabase/migrations/*.sql in order, recording each in schema_migrations.
// Usage: node scripts/migrate.mjs   (reads DATABASE_URL_UNPOOLED or DATABASE_URL from env / .env.local)
import fs from "node:fs";
import path from "node:path";
import pg from "pg";

if (fs.existsSync(".env.local")) {
  for (const l of fs.readFileSync(".env.local", "utf8").split(/\r?\n/)) {
    const m = /^([A-Z_0-9]+)=(.*)$/.exec(l);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}
const url = process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL is not set");

const client = new pg.Client({ connectionString: url, ssl: { rejectUnauthorized: false } });
await client.connect();
await client.query("create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())");
const dir = "supabase/migrations";
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".sql")).sort()) {
  const done = await client.query("select 1 from schema_migrations where name=$1", [f]);
  if (done.rowCount) { console.log("skip ", f); continue; }
  await client.query("begin");
  try {
    await client.query(fs.readFileSync(path.join(dir, f), "utf8"));
    await client.query("insert into schema_migrations(name) values ($1)", [f]);
    await client.query("commit");
    console.log("apply", f);
  } catch (e) {
    await client.query("rollback");
    throw e;
  }
}
await client.end();
