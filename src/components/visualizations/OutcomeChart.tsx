/** Signed horizontal bars around a zero line (profit can be negative). The best option is outlined and labelled in text. */
export function OutcomeChart({ rows, caption }: { rows: { label: string; value: number; best?: boolean }[]; caption: string }) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
  const money = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString()}`;
  return (
    <figure className="space-y-2.5">
      <figcaption className="sr-only">{caption}</figcaption>
      {rows.map((r) => {
        const w = (Math.abs(r.value) / max) * 50;
        return (
          <div key={r.label} className="grid grid-cols-[6.5rem_1fr_4.8rem] items-center gap-2 text-xs">
            <span className={r.best ? "font-bold text-violet" : "text-muted"}>{r.label}{r.best ? " ★" : ""}</span>
            <span className="relative h-4 rounded bg-white/[0.04]" role="img" aria-label={`${r.label}: ${money(r.value)}${r.best ? ", best option" : ""}`}>
              <span className="absolute inset-y-0 left-1/2 w-px bg-white/30" aria-hidden="true" />
              <span className={`absolute inset-y-0 rounded transition-all duration-700 ${r.best ? "outline outline-1 outline-royal" : ""}`} style={{ [r.value >= 0 ? "left" : "right"]: "50%", width: `${w}%`, background: r.value >= 0 ? "linear-gradient(90deg,#8B5CF699,#8B5CF6)" : "linear-gradient(90deg,#FB718599,#FB7185)" }} />
            </span>
            <span className="text-right font-mono">{money(r.value)}</span>
          </div>
        );
      })}
    </figure>
  );
}
