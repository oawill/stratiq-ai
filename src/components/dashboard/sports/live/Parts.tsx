"use client";

import { Badge } from "../../ui";
import { MODEL_LABEL, STATUS_LABEL, STATUS_TONE, pc, stamp, type Freshness, type Percent } from "./live";

/** Home / draw / away as a labelled bar. The numbers are always printed, so the colours carry no meaning on their own. */
export function ProbBar({ percent, home, away, compact = false }: { percent: Percent; home: string; away: string; compact?: boolean }) {
  const seg = [
    { k: "home", v: percent.home, c: "bg-cyan", l: home },
    { k: "draw", v: percent.draw, c: "bg-muted/60", l: "Draw" },
    { k: "away", v: percent.away, c: "bg-violet", l: away },
  ];
  return (
    <div role="group" aria-label={`Forecast: ${home} ${pc(percent.home)}, draw ${pc(percent.draw)}, ${away} ${pc(percent.away)}`}>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/5" aria-hidden="true">
        {seg.map((s) => <div key={s.k} className={s.c} style={{ width: `${s.v}%` }} />)}
      </div>
      <div className={`mt-1 flex justify-between gap-2 font-mono ${compact ? "text-[11px]" : "text-xs"}`}>
        <span>{compact ? "H" : home} {pc(percent.home)}</span><span>D {pc(percent.draw)}</span><span>{compact ? "A" : away} {pc(percent.away)}</span>
      </div>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "muted"}>{STATUS_LABEL[status] ?? status}</Badge>;
}

export function ModelBadge({ model }: { model: string }) {
  return <Badge tone="violet">{MODEL_LABEL[model] ?? model}</Badge>;
}

/** Shown whenever fixtures may be out of date: never synchronised, provider failing, or not refreshed recently. */
export function FreshnessBanner({ f, tz }: { f: Freshness; tz: string }) {
  if (!f.message) return <p className="text-xs text-muted">Fixtures last verified with the provider {stamp(f.last_verified_at, tz)}.</p>;
  return (
    <div role="status" className="rounded-xl border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
      <strong className="font-semibold">{f.stale ? "Possibly out of date. " : ""}</strong>{f.message}
      {f.last_verified_at && <> Last verified {stamp(f.last_verified_at, tz)}.</>}
      {f.last_error && <> Provider message: {f.last_error}</>}
    </div>
  );
}
