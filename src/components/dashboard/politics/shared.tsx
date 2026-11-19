"use client";

import type { PolKind } from "@/lib/types";
import { ScenarioSaveBar } from "../analysis";

export { field, num, pc, useAnalysis } from "../analysis";

export function SaveBar({ kind, inputs, valid, onSaved }: { kind: PolKind; inputs: unknown; valid: boolean; onSaved: () => void }) {
  return <ScenarioSaveBar endpoint="politics/scenarios" kind={kind} inputs={inputs} valid={valid} onSaved={onSaved} />;
}
