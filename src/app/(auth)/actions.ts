"use server";

import { headers } from "next/headers";
import { after } from "next/server";
import { redirect } from "next/navigation";
import { sendQuietly, welcomeEmail } from "@/lib/email";
import { z } from "zod";
import { createSession, destroySession, hashPassword, verifyPassword } from "@/lib/auth";
import { getPool } from "@/lib/db";

export interface FormState {
  error?: string;
  fields?: Record<string, string>;
}

// Best-effort per-instance throttle. Use WAF rate limiting for hard guarantees in production.
const attempts = new Map<string, number[]>();
function throttled(key: string, max: number) {
  const now = Date.now();
  const arr = (attempts.get(key) ?? []).filter((t) => now - t < 15 * 60_000);
  arr.push(now);
  attempts.set(key, arr);
  return arr.length > max;
}
async function clientIp() {
  return (await headers()).get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
}

const safeNext = (v: FormDataEntryValue | null) => {
  const s = typeof v === "string" ? v : "";
  return s.startsWith("/dashboard") && !s.startsWith("//") ? s : "/dashboard";
};

const signupSchema = z.object({
  name: z.string().trim().min(1, "Enter your name.").max(120),
  email: z.string().trim().toLowerCase().email("Enter a valid email address.").max(254),
  password: z.string().min(10, "Use at least 10 characters.").max(200),
});

export async function signup(_: FormState | undefined, form: FormData): Promise<FormState> {
  const pool = getPool();
  if (!pool) return { error: "Accounts are temporarily unavailable." };
  if (throttled(`signup:${await clientIp()}`, 8)) return { error: "Too many attempts. Please try again later." };
  const parsed = signupSchema.safeParse({ name: form.get("name"), email: form.get("email"), password: form.get("password") });
  if (!parsed.success) {
    const fields: Record<string, string> = {};
    for (const i of parsed.error.issues) fields[String(i.path[0])] ??= i.message;
    return { error: "Please check the highlighted fields.", fields };
  }
  const { name, email, password } = parsed.data;
  const hash = await hashPassword(password);
  const client = await pool.connect();
  let userId: string;
  try {
    await client.query("begin");
    const u = await client.query(
      "insert into users (email, name, password_hash) values ($1,$2,$3) on conflict (email) do nothing returning id",
      [email, name, hash],
    );
    if (u.rowCount === 0) {
      await client.query("rollback");
      return { error: "An account with this email already exists.", fields: { email: "Already registered." } };
    }
    userId = u.rows[0].id;
    const w = await client.query("insert into workspaces (name) values ($1) returning id", [`${name}'s workspace`]);
    await client.query("insert into workspace_members (workspace_id, user_id, role) values ($1,$2,'owner')", [w.rows[0].id, userId]);
    await client.query("insert into audit_logs (workspace_id, user_id, action) values ($1,$2,'user.signup')", [w.rows[0].id, userId]);
    await client.query("commit");
  } catch (e) {
    await client.query("rollback").catch(() => {});
    console.error("signup failed", e instanceof Error ? e.message : e);
    return { error: "We could not create your account. Please try again." };
  } finally {
    client.release();
  }
  await createSession(userId);
  after(() => sendQuietly(welcomeEmail(email, name)));
  redirect(safeNext(form.get("next")));
}

// Compare against a real hash even for unknown emails so response time does not reveal accounts.
const DUMMY = "scrypt$00000000000000000000000000000000$" + "00".repeat(64);

export async function login(_: FormState | undefined, form: FormData): Promise<FormState> {
  const pool = getPool();
  if (!pool) return { error: "Sign-in is temporarily unavailable." };
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const password = String(form.get("password") ?? "");
  if (throttled(`login:${await clientIp()}`, 15) || throttled(`login:${email}`, 8)) {
    return { error: "Too many attempts. Please try again later." };
  }
  const { rows } = await pool.query("select id, password_hash from users where email = $1", [email]);
  const ok = await verifyPassword(password, rows[0]?.password_hash ?? DUMMY);
  if (!rows[0] || !ok) return { error: "Incorrect email or password." };
  await createSession(rows[0].id);
  redirect(safeNext(form.get("next")));
}

export async function logout() {
  await destroySession();
  redirect("/login");
}
