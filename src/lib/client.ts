// Browser-side helpers for the authenticated proxy at /app-api (see src/app/app-api).
export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/app-api/${path}`, init);
  if (res.status === 204) return undefined as T;
  const j = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = j.detail;
    throw new Error(
      typeof d === "string" ? d : Array.isArray(d?.errors) ? d.errors.join(" ") : Array.isArray(d) ? d.map((x: { loc?: unknown[]; msg?: string }) => `${(x.loc ?? []).slice(1).join(".")}: ${x.msg}`).join("; ") : "Request failed",
    );
  }
  return j as T;
}

export const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
