import { Pool } from "pg";

// Server-only module: never import from a client component.
// DATABASE_URL works with any PostgreSQL, including Supabase's connection string.
const globalForPg = globalThis as unknown as { pgPool?: Pool };

export function getPool(): Pool | null {
  const url = process.env.DATABASE_URL;
  if (!url) return null;
  if (!globalForPg.pgPool) {
    globalForPg.pgPool = new Pool({
      connectionString: url,
      max: 5,
      ssl: process.env.DATABASE_SSL === "false" ? false : { rejectUnauthorized: false },
    });
  }
  return globalForPg.pgPool;
}
