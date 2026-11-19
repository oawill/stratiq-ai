"use client";

import { useActionState } from "react";
import { login } from "./actions";
import { Button } from "@/components/ui/primitives";

export function LoginForm() {
  const [state, action, pending] = useActionState(login, undefined);
  return (
    <form action={action} className="glass mx-auto mt-16 max-w-sm space-y-4 rounded-3xl p-8">
      <h1 className="text-2xl font-bold">Admin sign-in</h1>
      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required className="w-full rounded-xl border border-line bg-bg/70 px-4 py-3 text-sm" />
      </div>
      {state?.error && <p role="alert" className="text-sm text-red-400">{state.error}</p>}
      <Button type="submit" className="w-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
    </form>
  );
}
