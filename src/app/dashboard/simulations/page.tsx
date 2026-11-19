import type { Metadata } from "next";
import { ComingSoon } from "@/components/dashboard/ComingSoon";

export const metadata: Metadata = { title: "Simulation Lab" };

export default function Page() {
  return (
    <ComingSoon
      title="Simulation Lab"
      step="Step 4"
      summary="A shared Monte Carlo engine for every domain."
      planned={["Domain selection and scenario configuration","Probability distributions and variable inputs","Reproducible random seeds","Asynchronous runs with progress and status","Scenario comparison, sensitivity analysis and exportable reports"]}
      note="Runs will be seeded so any result can be reproduced exactly."
    />
  );
}
