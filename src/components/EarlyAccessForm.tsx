"use client";

import { useEffect, useRef, useState } from "react";
import { brand } from "@/lib/brand";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "./ui/primitives";
import { INTERESTS, USES } from "@/lib/signup";

type State =
  | { s: "idle" }
  | { s: "sending" }
  | { s: "done" }
  | { s: "error"; msg: string; fields?: Record<string, string> };

const input =
  "w-full rounded-xl border border-line bg-bg/70 px-4 py-3 text-sm text-ink placeholder:text-muted/70 focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";

export function EarlyAccessForm({ source = "website" }: { source?: string }) {
  const [state, setState] = useState<State>({ s: "idle" });
  const startedAt = useRef(0);

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setState({ s: "sending" });
    try {
      const res = await fetch("/api/early-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fullName: f.get("fullName"),
          email: f.get("email"),
          country: f.get("country"),
          interest: f.get("interest") || undefined,
          use: f.get("use") || undefined,
          consent: f.get("consent") === "on",
          website: f.get("website") ?? "",
          source,
          t: startedAt.current,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) setState({ s: "done" });
      else setState({ s: "error", msg: data.error ?? "Something went wrong.", fields: data.fields });
    } catch {
      setState({ s: "error", msg: "Network error. Your registration was not saved — please try again." });
    }
  }

  if (state.s === "done") {
    return (
      <div role="status" className="glass rounded-3xl p-8 text-center">
        <CheckCircle2 className="mx-auto h-12 w-12 text-success" aria-hidden="true" />
        <h3 className="mt-4 text-xl font-bold">You&apos;re on the list.</h3>
        <p className="mt-2 text-sm text-muted">Thanks for registering. We&apos;ll be in touch about early access.</p>
      </div>
    );
  }

  const fe = state.s === "error" ? (state.fields ?? {}) : {};
  const err = (k: string) =>
    fe[k] ? (
      <p id={`${k}-err`} className="mt-1 text-xs text-red-400">
        {fe[k]}
      </p>
    ) : null;

  return (
    <form onSubmit={onSubmit} noValidate className="glass space-y-4 rounded-3xl p-6 sm:p-8" aria-describedby={state.s === "error" ? "form-err" : undefined}>
      <div>
        <label htmlFor="fullName" className="mb-1.5 block text-sm font-medium">Full name</label>
        <input id="fullName" name="fullName" autoComplete="name" required className={input} aria-invalid={!!fe.fullName} aria-describedby={fe.fullName ? "fullName-err" : undefined} />
        {err("fullName")}
      </div>
      <div>
        <label htmlFor="email" className="mb-1.5 block text-sm font-medium">Email address</label>
        <input id="email" name="email" type="email" autoComplete="email" required className={input} aria-invalid={!!fe.email} aria-describedby={fe.email ? "email-err" : undefined} />
        {err("email")}
      </div>
      <div>
        <label htmlFor="country" className="mb-1.5 block text-sm font-medium">Country</label>
        <input id="country" name="country" autoComplete="country-name" required className={input} aria-invalid={!!fe.country} aria-describedby={fe.country ? "country-err" : undefined} />
        {err("country")}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="interest" className="mb-1.5 block text-sm font-medium">Primary interest</label>
          <select id="interest" name="interest" required defaultValue="" className={input} aria-invalid={!!fe.interest}>
            <option value="" disabled>Select…</option>
            {INTERESTS.map((i) => <option key={i}>{i}</option>)}
          </select>
          {err("interest")}
        </div>
        <div>
          <label htmlFor="use" className="mb-1.5 block text-sm font-medium">Intended use</label>
          <select id="use" name="use" required defaultValue="" className={input} aria-invalid={!!fe.use}>
            <option value="" disabled>Select…</option>
            {USES.map((i) => <option key={i}>{i}</option>)}
          </select>
          {err("use")}
        </div>
      </div>
      {/* Honeypot — hidden from people and assistive tech */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label>Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
      </div>
      <div>
        <label className="flex items-start gap-3 text-sm text-muted">
          <input type="checkbox" name="consent" className="mt-1 h-4 w-4 accent-[#8055f6]" aria-invalid={!!fe.consent} />
          <span>I agree to be contacted about {brand.name} early access and to my details being stored for that purpose.</span>
        </label>
        {err("consent")}
      </div>
      {state.s === "error" && (
        <p id="form-err" role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {state.msg}
        </p>
      )}
      <Button type="submit" className="w-full py-3.5" disabled={state.s === "sending"}>
        {state.s === "sending" ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Submitting…</> : "Request Early Access"}
      </Button>
    </form>
  );
}
