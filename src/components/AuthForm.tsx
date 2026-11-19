"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "./ui/primitives";
import { login, signup, type FormState } from "@/app/(auth)/actions";

const input =
  "w-full rounded-xl border border-line bg-bg/70 px-4 py-3 text-sm text-ink focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";

export function AuthForm({ mode, next }: { mode: "login" | "signup"; next?: string }) {
  const [state, action, pending] = useActionState<FormState | undefined, FormData>(mode === "login" ? login : signup, undefined);
  const fe = state?.fields ?? {};
  const err = (k: string) => (fe[k] ? <p id={`${k}-err`} className="mt-1 text-xs text-red-400">{fe[k]}</p> : null);
  return (
    <form action={action} className="glass space-y-4 rounded-3xl p-7">
      <h1 className="text-2xl font-extrabold">{mode === "login" ? "Log in" : "Create your account"}</h1>
      <input type="hidden" name="next" value={next ?? ""} />
      {mode === "signup" && (
        <div>
          <label htmlFor="name" className="mb-1.5 block text-sm font-medium">Name</label>
          <input id="name" name="name" autoComplete="name" required className={input} aria-invalid={!!fe.name} />
          {err("name")}
        </div>
      )}
      <div>
        <label htmlFor="email" className="mb-1.5 block text-sm font-medium">Email</label>
        <input id="email" name="email" type="email" autoComplete="email" required className={input} aria-invalid={!!fe.email} aria-describedby={fe.email ? "email-err" : undefined} />
        {err("email")}
      </div>
      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm font-medium">Password</label>
        <input id="password" name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "signup" ? 10 : undefined} required className={input} aria-invalid={!!fe.password} />
        {mode === "signup" && !fe.password && <p className="mt-1 text-xs text-muted">At least 10 characters.</p>}
        {err("password")}
      </div>
      {state?.error && <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{state.error}</p>}
      <Button type="submit" className="w-full py-3.5" disabled={pending}>
        {pending ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Please wait…</> : mode === "login" ? "Log in" : "Create account"}
      </Button>
      <p className="text-center text-sm text-muted">
        {mode === "login" ? <>No account? <Link className="text-violet underline" href="/signup">Create one</Link></> : <>Already registered? <Link className="text-violet underline" href="/login">Log in</Link></>}
      </p>
    </form>
  );
}
