"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/primitives";
import { acceptInvite } from "./actions";

export function AcceptButton({ token }: { token: string }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <div>
      <Button
        type="button"
        className="w-full"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const r = await acceptInvite(token); // redirects to the dashboard on success
            if (r?.error) setError(r.error);
          })
        }
      >
        {pending ? "Joining…" : "Accept invitation"}
      </Button>
      {error && <p role="alert" className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}
    </div>
  );
}
