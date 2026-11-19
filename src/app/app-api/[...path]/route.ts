import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { apiBase } from "@/lib/api";
import { mintApiToken } from "@/lib/auth";

// Authenticated proxy for browser -> Python API. The browser only holds its session cookie;
// the internal API token is minted here, on the server, per request.
async function handle(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const session = await getSession();
  if (!session) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });

  if (req.method !== "GET") {
    // CSRF defence in depth (cookie is SameSite=Lax): require same-origin + JSON.
    const origin = req.headers.get("origin");
    const host = req.headers.get("host");
    if (!origin || new URL(origin).host !== host) {
      return NextResponse.json({ detail: "Cross-origin request blocked" }, { status: 403 });
    }
    if (!req.headers.get("content-type")?.includes("application/json")) {
      return NextResponse.json({ detail: "Expected JSON" }, { status: 415 });
    }
  }

  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target = `${apiBase()}/api/v1/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const res = await fetch(target, {
    method: req.method,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${mintApiToken(session)}`,
      ...(req.method !== "GET" ? { "Content-Type": "application/json" } : {}),
    },
    body: req.method === "GET" ? undefined : await req.text(),
  });
  return new NextResponse(res.body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
  });
}

export { handle as GET, handle as POST };
