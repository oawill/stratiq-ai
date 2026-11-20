import { after, NextResponse } from "next/server";
import { earlyAccessEmail, sendQuietly } from "@/lib/email";
import { getPool } from "@/lib/db";
import { signupSchema } from "@/lib/signup";


// Best-effort per-instance rate limit (use Vercel Firewall / WAF rate limiting for hard guarantees).
const hits = new Map<string, number[]>();
function limited(ip: string) {
  const now = Date.now();
  const arr = (hits.get(ip) ?? []).filter((t) => now - t < 10 * 60_000);
  arr.push(now);
  hits.set(ip, arr);
  return arr.length > 5;
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request." }, { status: 400 });
  }

  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (limited(ip)) {
    return NextResponse.json({ ok: false, error: "Too many attempts. Please try again later." }, { status: 429 });
  }

  const parsed = signupSchema.safeParse(body);
  if (!parsed.success) {
    // Honeypot or invalid input. Do not reveal which anti-spam rule fired.
    const fields: Record<string, string> = {};
    for (const issue of parsed.error.issues) fields[String(issue.path[0])] ??= issue.message;
    if (fields.website) {
      return NextResponse.json({ ok: false, error: "Submission rejected." }, { status: 400 });
    }
    return NextResponse.json({ ok: false, error: "Please check the highlighted fields.", fields }, { status: 422 });
  }
  const d = parsed.data;
  if (typeof d.t === "number" && Date.now() - d.t < 2500) {
    return NextResponse.json({ ok: false, error: "Submission rejected." }, { status: 400 });
  }

  const pool = getPool();
  if (!pool) {
    return NextResponse.json(
      { ok: false, error: "Registration is temporarily unavailable. Please try again later." },
      { status: 503 },
    );
  }

  try {
    const res = await pool.query(
      `insert into early_access_signups (full_name, email, country, interest, intended_use, consent, source)
       values ($1,$2,$3,$4,$5,true,$6)
       on conflict (email) do nothing
       returning id`,
      [d.fullName, d.email, d.country, d.interest, d.use, d.source ?? null],
    );
    if (res.rowCount === 0) {
      return NextResponse.json(
        { ok: false, duplicate: true, error: "This email is already on the early-access list." },
        { status: 409 },
      );
    }
    after(() => sendQuietly(earlyAccessEmail(d.email, d.fullName)));
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("early-access insert failed", err instanceof Error ? err.message : err);
    return NextResponse.json(
      { ok: false, error: "We could not save your registration. Please try again." },
      { status: 500 },
    );
  }
}
