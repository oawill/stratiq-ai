/** Probability of each exact scoreline (home goals down, away goals across), shaded by likelihood. Cells hold the exact percentages. */
export function ScorelineGrid({ grid, covered, size = 6, home, away }: { grid: number[][]; covered: number; size?: number; home: string; away: string }) {
  const cells = grid.slice(0, size).map((row) => row.slice(0, size).map((v) => v / covered));
  const max = Math.max(...cells.flat());
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[280px] border-separate border-spacing-0.5 text-center font-mono text-[10px] sm:text-[11px]">
        <caption className="mb-1 text-left font-sans text-xs text-muted">Chance of each exact score: {home} goals down, {away} goals across</caption>
        <thead>
          <tr>
            <td />
            {Array.from({ length: size }, (_, a) => <th key={a} scope="col" className="font-normal text-muted">{a}</th>)}
          </tr>
        </thead>
        <tbody>
          {cells.map((row, h) => (
            <tr key={h}>
              <th scope="row" className="pr-1 font-normal text-muted">{h}</th>
              {row.map((p, a) => (
                <td key={a} title={`${home} ${h}–${a} ${away}: ${(p * 100).toFixed(1)}%`} className="rounded-sm py-1 transition-colors duration-500" style={{ background: `rgba(0,229,255,${(p / max) * 0.75 + 0.03})`, color: p / max > 0.55 ? "#031225" : "#cbd5e1" }}>
                  {(p * 100).toFixed(p >= 0.095 ? 0 : 1)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
