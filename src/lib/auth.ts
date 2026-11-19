// Server-only. Session tokens are random; only their SHA-256 is stored in Postgres.
import { createHash, createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getPool } from "./db";

const scrypt = promisify(scryptCb) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;

export const SESSION_COOKIE = "stratiq_session";
const SESSION_TTL_MS = 14 * 24 * 60 * 60 * 1000;

export async function hashPassword(pw: string): Promise<string> {
  const salt = randomBytes(16);
  const key = await scrypt(pw, salt, 64);
  return `scrypt$${salt.toString("hex")}$${key.toString("hex")}`;
}

export async function verifyPassword(pw: string, stored: string): Promise<boolean> {
  const [alg, saltHex, keyHex] = stored.split("$");
  if (alg !== "scrypt" || !saltHex || !keyHex) return false;
  const key = await scrypt(pw, Buffer.from(saltHex, "hex"), 64);
  const expected = Buffer.from(keyHex, "hex");
  return key.length === expected.length && timingSafeEqual(key, expected);
}

const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");

export interface Session {
  userId: string;
  name: string;
  email: string;
  workspaceId: string;
  workspaceName: string;
  role: "owner" | "admin" | "member" | "viewer";
}

export async function createSession(userId: string): Promise<void> {
  const pool = getPool();
  if (!pool) throw new Error("Database is not configured");
  const token = randomBytes(32).toString("base64url");
  const expires = new Date(Date.now() + SESSION_TTL_MS);
  await pool.query("insert into sessions (id, user_id, expires_at) values ($1,$2,$3)", [sha256(token), userId, expires]);
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    expires,
  });
}

export async function getSession(): Promise<Session | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const pool = getPool();
  if (!pool) return null;
  const { rows } = await pool.query(
    `select u.id user_id, u.name, u.email, w.id workspace_id, w.name workspace_name, m.role
       from sessions s
       join users u on u.id = s.user_id
       join workspace_members m on m.user_id = u.id
       join workspaces w on w.id = m.workspace_id
      where s.id = $1 and s.expires_at > now()
      order by m.created_at asc limit 1`,
    [sha256(token)],
  );
  const r = rows[0];
  if (!r) return null;
  return { userId: r.user_id, name: r.name, email: r.email, workspaceId: r.workspace_id, workspaceName: r.workspace_name, role: r.role };
}

export async function requireSession(): Promise<Session> {
  const s = await getSession();
  if (!s) redirect("/login");
  return s;
}

export async function destroySession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (token) await getPool()?.query("delete from sessions where id = $1", [sha256(token)]);
  jar.delete(SESSION_COOKIE);
}

const b64 = (o: object | Buffer) => Buffer.from(o instanceof Buffer ? o : JSON.stringify(o)).toString("base64url");

/** Short-lived HS256 token for server-to-server calls to the Python API. Never sent to browsers. */
export function mintApiToken(s: Session): string {
  const secret = process.env.INTERNAL_API_SECRET ?? "";
  if (secret.length < 32) throw new Error("INTERNAL_API_SECRET is not configured");
  const head = b64({ alg: "HS256", typ: "JWT" });
  const body = b64({ sub: s.userId, wid: s.workspaceId, iss: "stratiq-web", exp: Math.floor(Date.now() / 1000) + 60 });
  const sig = createHmac("sha256", secret).update(`${head}.${body}`).digest("base64url");
  return `${head}.${body}.${sig}`;
}
