export interface ProbabilityBar {
  key: string;
  label: string;
  /** Central probability, 0 to 1. */
  value: number;
  /** Optional uncertainty range, 0 to 1. */
  lo?: number;
  hi?: number;
  colour: string;
}

/**
 * Horizontal probability bars with an optional uncertainty band. Widths animate with CSS transitions (switched off for reduced motion
 * by the global rule), so changing an input slides the bars rather than redrawing them.
 */
export function ProbabilityChart({ bars, caption }: { bars: ProbabilityBar[]; caption: string }) {
  return (
    <figure className="space-y-3">
      <figcaption className="sr-only">{caption}</figcaption>
      {bars.map((b) => (
        <div key={b.key}>
          <div className="mb-1 flex items-baseline justify-between text-sm">
            <span className="font-semibold">{b.label}</span>
            <span className="font-mono">
              <span style={{ color: b.colour }}>{(b.value * 100).toFixed(1)}%</span>
              {b.lo !== undefined && b.hi !== undefined && <span className="ml-2 text-xs text-muted">({(b.lo * 100).toFixed(0)}–{(b.hi * 100).toFixed(0)}%)</span>}
            </span>
          </div>
          <div className="relative h-3 overflow-hidden rounded-full bg-white/[0.06]" role="img" aria-label={`${b.label} ${(b.value * 100).toFixed(1)} percent`}>
            {b.lo !== undefined && b.hi !== undefined && (
              <div className="absolute inset-y-0 rounded-full opacity-30 transition-all duration-700" style={{ left: `${b.lo * 100}%`, width: `${(b.hi - b.lo) * 100}%`, background: b.colour }} />
            )}
            <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out" style={{ width: `${b.value * 100}%`, background: `linear-gradient(90deg, ${b.colour}99, ${b.colour})`, boxShadow: `0 0 14px ${b.colour}66` }} />
          </div>
        </div>
      ))}
    </figure>
  );
}
