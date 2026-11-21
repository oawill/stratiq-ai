import type { TreeBranch } from "@/lib/landing/strategy";
import { PRICES, PRICE_NAMES } from "@/lib/landing/strategy";

/**
 * Leader-first decision tree: we choose a price, the rival replies with the price that maximises its own profit, and the leaf shows
 * (our profit, rival profit). The best path for us is highlighted. This is a sequential view; the matrix shows simultaneous choices.
 */
export function DecisionTree({ branches, best }: { branches: TreeBranch[]; best: number }) {
  const W = 520;
  const H = 230;
  const y = (i: number) => 38 + i * 78;
  const money = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString()}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Decision tree. If we choose ${PRICE_NAMES[best]} we earn ${money(branches[best].payoffs[0])} after the rival's best reply, the highest of our three options.`} className="h-auto w-full">
      <circle cx="42" cy={H / 2} r="18" fill="rgba(139,92,246,0.25)" stroke="#8B5CF6" />
      <text x="42" y={H / 2 + 4} textAnchor="middle" fontSize="11" fill="#F8FAFC">We</text>
      {branches.map((b, i) => {
        const on = i === best;
        const colour = on ? "#8B5CF6" : "rgba(148,163,184,0.45)";
        return (
          <g key={i}>
            <path d={`M60 ${H / 2} C 110 ${H / 2}, 110 ${y(i)}, 160 ${y(i)}`} fill="none" stroke={colour} strokeWidth={on ? 2.2 : 1.2} />
            <text x="112" y={(H / 2 + y(i)) / 2 - 4} fontSize="10" fill="#94A3B8" textAnchor="middle">{PRICE_NAMES[b.ours]} ${PRICES[b.ours]}</text>
            <circle cx="170" cy={y(i)} r="12" fill="rgba(37,99,235,0.25)" stroke={on ? "#8B5CF6" : "#2563EB"} />
            <text x="170" y={y(i) + 3.5} textAnchor="middle" fontSize="9" fill="#F8FAFC">Rival</text>
            <path d={`M182 ${y(i)} L 300 ${y(i)}`} fill="none" stroke={colour} strokeWidth={on ? 2.2 : 1.2} />
            <text x="241" y={y(i) - 6} fontSize="10" fill="#94A3B8" textAnchor="middle">best reply: {PRICE_NAMES[b.reply]} ${PRICES[b.reply]}</text>
            <rect x="300" y={y(i) - 17} width="206" height="34" rx="8" fill={on ? "rgba(139,92,246,0.22)" : "rgba(255,255,255,0.04)"} stroke={on ? "#8B5CF6" : "rgba(148,163,184,0.3)"} />
            <text x="403" y={y(i) - 2} textAnchor="middle" fontSize="11" fontFamily="monospace" fill={b.payoffs[0] >= 0 ? "#A7F3D0" : "#FECDD3"}>us {money(b.payoffs[0])}</text>
            <text x="403" y={y(i) + 11} textAnchor="middle" fontSize="10" fontFamily="monospace" fill="#94A3B8">rival {money(b.payoffs[1])}</text>
            {on && <text x="510" y={y(i) - 20} textAnchor="end" fontSize="9" fontWeight="bold" fill="#A78BFA">BEST FOR US</text>}
          </g>
        );
      })}
    </svg>
  );
}
