import type { Metadata } from "next";
import { ComingSoon } from "@/components/dashboard/ComingSoon";

export const metadata: Metadata = { title: "Financial Intelligence" };

export default function Page() {
  return (
    <ComingSoon
      title="Financial Intelligence"
      step="Step 6"
      summary="Portfolio scenarios and risk simulation."
      planned={["Portfolio scenario builder","Historical return analysis (permitted data provider required)","Market stress testing","Monte Carlo risk simulations","Value at Risk and Expected Shortfall"]}
      note="Educational scenario modeling, not investment advice. There will be no automated trading."
    />
  );
}
