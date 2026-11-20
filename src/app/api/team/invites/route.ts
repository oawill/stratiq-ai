import { after, NextResponse } from "next/server";
import { ApiError, apiFetch } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { emailConfigured, inviteEmail, sendQuietly } from "@/lib/email";
import { SITE_URL } from "@/lib/site";

interface Created {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  token: string;
}

// Creates an invitation through the Python API (which enforces roles and seat limits), then builds the one-time link and,
// when email is configured, sends it. The token is shown to the inviter once, here, and never stored in plain text.
export async function POST(req: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) return NextResponse.json({ error: "Cross-origin request blocked." }, { status: 403 });

  let body: { email?: unknown; role?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  try {
    const inv = await apiFetch<Created>(session, "team/invites", { method: "POST", body: JSON.stringify({ email: body.email, role: body.role }) });
    const link = `${SITE_URL}/invite/${inv.token}`;
    after(() => sendQuietly(inviteEmail(inv.email, session.name, session.workspaceName, inv.role, link)));
    return NextResponse.json({ id: inv.id, email: inv.email, role: inv.role, expires_at: inv.expires_at, link, emailed: emailConfigured() }, { status: 201 });
  } catch (e) {
    if (e instanceof ApiError) {
      let message = e.message;
      try {
        const d = JSON.parse(e.message);
        if (d && typeof d.message === "string") message = d.message;
        else if (Array.isArray(d)) message = "Enter a valid email address.";
      } catch {}
      return NextResponse.json({ error: message }, { status: e.status });
    }
    console.error("invite failed", e instanceof Error ? e.message : e);
    return NextResponse.json({ error: "Could not create the invitation." }, { status: 502 });
  }
}
