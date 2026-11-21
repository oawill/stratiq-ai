import type { Game } from "@/lib/game";

/**
 * A two-player payoff matrix styled as a board. Each cell shows (our profit, rival profit). Markers are text as well as colour:
 * "NE" marks a pure Nash equilibrium (neither side gains by switching alone) and "BR" our best reply to the rival's committed price.
 */
export function PayoffMatrix({ game, nash, committedCol, bestRow }: { game: Game; nash: { row: number; col: number }[]; committedCol?: number; bestRow: number | null }) {
  const isNash = (r: number, c: number) => nash.some((n) => n.row === r && n.col === c);
  const fmt = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString()}`;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[300px] border-separate border-spacing-1 text-center text-xs">
        <caption className="mb-2 text-left text-xs text-muted">Profit per period: we pick a row price, the rival picks a column price. Cells read (us, rival).</caption>
        <thead>
          <tr>
            <td />
            {game.colLabels.map((l, c) => (
              <th key={l} scope="col" className={`pb-1 font-semibold ${committedCol === c ? "text-royal" : "text-muted"}`}>
                <span className="block text-[10px] font-normal text-muted">Rival</span>{l}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {game.payoffs.map((row, r) => (
            <tr key={game.rowLabels[r]}>
              <th scope="row" className="pr-1 text-left font-semibold text-muted"><span className="block text-[10px] font-normal">Us</span>{game.rowLabels[r]}</th>
              {row.map(([us, them], c) => {
                const ne = isNash(r, c);
                const br = committedCol === c && bestRow === r;
                const dark = (r + c) % 2 === 0;
                const dim = committedCol !== undefined && committedCol !== c;
                return (
                  <td key={c} className={`rounded-lg border px-1 py-2 font-mono transition-all duration-500 ${ne ? "border-ion shadow-[0_0_18px_-4px_#00E5FF]" : br ? "border-royal shadow-[0_0_18px_-4px_#8B5CF6]" : "border-white/10"} ${dim ? "opacity-35" : ""}`} style={{ background: dark ? "rgba(139,92,246,0.14)" : "rgba(37,99,235,0.1)" }}>
                    <span className={us >= 0 ? "text-emerald-200" : "text-rose-200"}>{fmt(us)}</span>
                    <span className="text-muted"> , </span>
                    <span className={them >= 0 ? "text-emerald-200/80" : "text-rose-200/80"}>{fmt(them)}</span>
                    {(ne || br) && <span className="mt-1 flex justify-center gap-1">{ne && <span className="rounded bg-ion/20 px-1 text-[10px] font-bold text-ion">NE</span>}{br && <span className="rounded bg-royal/25 px-1 text-[10px] font-bold text-violet">BR</span>}</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
