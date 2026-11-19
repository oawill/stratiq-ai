import type { Metadata } from "next";
import { ComingSoon } from "@/components/dashboard/ComingSoon";

export const metadata: Metadata = { title: "Business Strategy" };

export default function Page() {
  return (
    <ComingSoon
      title="Business Strategy"
      step="Step 3"
      summary="Interactive game-theory workspace with a deterministic solver."
      planned={["Define two competitors and their strategies","Enter payoffs and generate a payoff matrix","Pure Nash equilibria, best responses, dominant strategies","Payoff sensitivity analysis","Save and compare scenarios"]}
      note="Equilibria will be computed by a deterministic solver, never by a language model."
    />
  );
}
