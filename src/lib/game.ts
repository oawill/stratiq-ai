/** Two-player normal-form game utilities with pure-strategy Nash detection. */
export interface Game {
  rowLabels: string[];
  colLabels: string[];
  /** payoffs[r][c] = [rowPlayerPayoff, colPlayerPayoff] */
  payoffs: [number, number][][];
}

export function pureNash(g: Game): { row: number; col: number }[] {
  const out: { row: number; col: number }[] = [];
  const R = g.rowLabels.length;
  const C = g.colLabels.length;
  for (let r = 0; r < R; r++) {
    for (let c = 0; c < C; c++) {
      const [u1, u2] = g.payoffs[r][c];
      let rowBest = true;
      for (let r2 = 0; r2 < R; r2++) if (g.payoffs[r2][c][0] > u1) rowBest = false;
      let colBest = true;
      for (let c2 = 0; c2 < C; c2++) if (g.payoffs[r][c2][1] > u2) colBest = false;
      if (rowBest && colBest) out.push({ row: r, col: c });
    }
  }
  return out;
}

/** Row-player strategies that maximise payoff against column c. */
export function bestResponseRow(g: Game, c: number): number[] {
  const vals = g.payoffs.map((row) => row[c][0]);
  const m = Math.max(...vals);
  return vals.flatMap((v, i) => (v === m ? [i] : []));
}

/* ---- Hypothetical duopoly pricing model (illustrative assumptions only) ---- */
export const PRICE_LEVELS = [
  { label: "Low", price: 8 },
  { label: "Medium", price: 12 },
  { label: "High", price: 16 },
] as const;

export interface DuopolyParams {
  marketSize: number; // baseline total demand
  sensitivity: number; // share shift per $ price gap
  unitCost: number;
  fixedCost: number;
}

export const DEFAULT_DUOPOLY: DuopolyParams = {
  marketSize: 1000,
  sensitivity: 0.06,
  unitCost: 5,
  fixedCost: 1500,
};

/**
 * share_A = clamp(0.5 + s * (pB - pA)); total demand shrinks with the average price.
 * Profit = quantity * (price - unit cost) - fixed cost.
 */
export function duopolyProfit(
  pA: number,
  pB: number,
  p: DuopolyParams,
): [number, number] {
  const shareA = Math.min(1, Math.max(0, 0.5 + p.sensitivity * (pB - pA)));
  const avg = (pA + pB) / 2;
  const demand = Math.max(0, p.marketSize * (1.6 - avg / 20));
  const qA = demand * shareA;
  const qB = demand * (1 - shareA);
  return [
    qA * (pA - p.unitCost) - p.fixedCost,
    qB * (pB - p.unitCost) - p.fixedCost,
  ];
}

export function buildDuopolyGame(p: DuopolyParams = DEFAULT_DUOPOLY): Game {
  const labels = PRICE_LEVELS.map((l) => `${l.label} ($${l.price})`);
  return {
    rowLabels: labels,
    colLabels: labels,
    payoffs: PRICE_LEVELS.map((a) =>
      PRICE_LEVELS.map((b) => {
        const [x, y] = duopolyProfit(a.price, b.price, p);
        return [Math.round(x), Math.round(y)] as [number, number];
      }),
    ),
  };
}
