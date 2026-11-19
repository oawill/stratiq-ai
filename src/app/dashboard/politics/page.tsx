import type { Metadata } from "next";
import { ComingSoon } from "@/components/dashboard/ComingSoon";

export const metadata: Metadata = { title: "Political Intelligence" };

export default function Page() {
  return (
    <ComingSoon
      title="Political Intelligence"
      step="Step 5"
      summary="Nonpartisan coalition and policy scenario tools."
      planned={["Coalition formation simulator","Voting power calculations","Aggregate turnout sensitivity","Policy tradeoff analysis","Scenario comparisons"]}
      note="Scenario assumptions only. No polling data will be fabricated and no individual voter targeting will be built."
    />
  );
}
