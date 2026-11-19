// Server-only client for the Python (FastAPI) service.
import { mintApiToken, type Session } from "./auth";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function apiBase(): string {
  if (process.env.PY_API_URL) return process.env.PY_API_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://127.0.0.1:8000";
}

export async function apiFetch<T>(session: Session, path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase()}/api/v1/${path.replace(/^\//, "")}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
      Authorization: `Bearer ${mintApiToken(session)}`,
    },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}
