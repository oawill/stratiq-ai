import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

// Server-only. ADMIN_PASSWORD and ADMIN_SESSION_SECRET must be set; otherwise admin is disabled.
export const COOKIE = "stratiq_admin";
const TTL_MS = 8 * 60 * 60 * 1000;

function secret() {
  return process.env.ADMIN_SESSION_SECRET ?? "";
}
function sign(payload: string) {
  return createHmac("sha256", secret()).update(payload).digest("hex");
}

export function adminConfigured() {
  return !!process.env.ADMIN_PASSWORD && secret().length >= 32;
}

export function checkPassword(input: string) {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  if (!expected) return false;
  const a = Buffer.from(input);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function makeToken() {
  const exp = String(Date.now() + TTL_MS);
  return `${exp}.${sign(exp)}`;
}

export async function isAdmin(): Promise<boolean> {
  if (!adminConfigured()) return false;
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || Number(exp) < Date.now()) return false;
  const good = sign(exp);
  return sig.length === good.length && timingSafeEqual(Buffer.from(sig), Buffer.from(good));
}
