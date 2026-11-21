import { pureNash, type Game } from "../game";

/**
 * Illustrative two-firm pricing game. The demand model is the one used by the Strategy simulator demo (lib/game.ts), extended with
 * two scenario levers. All numbers are assumptions shown on screen, not forecasts.
 *
 *   share_us = clamp(0.5 + shift + sensitivity x (price_them - price_us))
 *   demand   = marketSize x (1.6 - average price / 20)
 *   profit   = quantity x (price - unitCost) - fixedCost
 */
export const PRICES = [8, 12, 16] as const;
export const PRICE_NAMES = ["Low", "Medium", "High"] as const;

export interface StrategyParams {
  marketSize: number;
  sensitivity: number;
  unitCost: number;
  /** Our fixed cost; the competitor's is `rivalFixedCost`. */
  fixedCost: number;
  rivalFixedCost: number;
  /** Extra share we win at equal prices (brand, distribution). */
  shift: number;
}

export const BASE: StrategyParams = { marketSize: 1000, sensitivity: 0.06, unitCost: 5, fixedCost: 1500, rivalFixedCost: 1500, shift: 0 };

export function profits(us: number, them: number, p: StrategyParams): [number, number] {
  const share = Math.min(1, Math.max(0, 0.5 + p.shift + p.sensitivity * (them - us)));
  const demand = Math.max(0, p.marketSize * (1.6 - (us + them) / 2 / 20));
  return [demand * share * (us - p.unitCost) - p.fixedCost, demand * (1 - share) * (them - p.unitCost) - p.rivalFixedCost];
}

export function buildGame(p: StrategyParams): Game {
  const labels = PRICES.map((x, i) => `${PRICE_NAMES[i]} ($${x})`);
  return {
    rowLabels: labels,
    colLabels: labels,
    payoffs: PRICES.map((a) => PRICES.map((b) => profits(a, b, p).map(Math.round) as [number, number])),
  };
}

export type ScenarioId = "rival-lowers" | "rival-holds" | "expand-share" | "new-market";

export interface StrategyScenario {
  id: ScenarioId;
  label: string;
  blurb: string;
  assumptions: string[];
  params: StrategyParams;
  /** When the rival has committed to a price, the column index of that price. */
  rivalCommits?: number;
}

export const SCENARIOS: StrategyScenario[] = [
  { id: "rival-lowers", label: "Competitor lowers prices", blurb: "The rival commits to the Low price ($8). What is our best reply?", assumptions: ["Rival price fixed at $8", "All other assumptions unchanged"], params: BASE, rivalCommits: 0 },
  { id: "rival-holds", label: "Competitor maintains prices", blurb: "The rival stays at the Medium price ($12). What is our best reply?", assumptions: ["Rival price fixed at $12", "All other assumptions unchanged"], params: BASE, rivalCommits: 1 },
  { id: "expand-share", label: "Company expands market share", blurb: "A distribution push wins us extra share at equal prices, at a higher fixed cost. Both firms still choose prices at the same time.", assumptions: ["+8 points of share at equal prices", "Our fixed cost +$400", "Both firms choose prices simultaneously"], params: { ...BASE, shift: 0.08, fixedCost: BASE.fixedCost + 400 } },
  { id: "new-market", label: "Company enters a new market", blurb: "Total demand grows 25%, but entering costs us $700 more in fixed cost. Both firms still choose prices at the same time.", assumptions: ["Market size +25% for both firms", "Our fixed cost +$700 (entry cost)", "Both firms choose prices simultaneously"], params: { ...BASE, marketSize: BASE.marketSize * 1.25, fixedCost: BASE.fixedCost + 700 } },
];

export interface TreeBranch {
  ours: number;
  reply: number;
  payoffs: [number, number];
}
export interface Analysis {
  scenario: StrategyScenario;
  game: Game;
  nash: { row: number; col: number }[];
  /** Our profit for each of our prices against the reference column (the committed price, or the equilibrium reply). */
  outcomes: { label: string; profit: number; best: boolean }[];
  referenceLabel: string;
  bestRow: number | null;
  /** We choose first, then the rival picks the price that maximises its own profit (ties go to the lower price). */
  tree: { branches: TreeBranch[]; best: number };
  sensitivity: { sensitivity: number; profit: number | null }[];
  baseline: { nashProfit: number | null };
}

const rivalBest = (us: number, p: StrategyParams) => {
  let best = 0;
  PRICES.forEach((them, j) => {
    if (profits(us, them, p)[1] > profits(us, PRICES[best], p)[1] + 1e-9) best = j;
  });
  return best;
};

/** Our profit in the first pure equilibrium (null when there is none), or our best reply to a committed rival price. */
function referenceProfit(p: StrategyParams, committed?: number): number | null {
  if (committed !== undefined) return Math.max(...PRICES.map((us) => profits(us, PRICES[committed], p)[0]));
  const eq = pureNash(buildGame(p));
  return eq.length ? profits(PRICES[eq[0].row], PRICES[eq[0].col], p)[0] : null;
}

const rounded = (v: number | null) => (v === null ? null : Math.round(v));

export function analyse(id: ScenarioId): Analysis {
  const scenario = SCENARIOS.find((s) => s.id === id)!;
  const p = scenario.params;
  const game = buildGame(p);
  const nash = pureNash(game);
  const col = scenario.rivalCommits ?? (nash.length ? nash[0].col : null);
  const values = col === null ? [] : PRICES.map((us) => profits(us, PRICES[col], p)[0]);
  const bestRow = values.length ? values.indexOf(Math.max(...values)) : null;
  const branches = PRICES.map((us, i) => {
    const reply = rivalBest(us, p);
    return { ours: i, reply, payoffs: profits(us, PRICES[reply], p).map(Math.round) as [number, number] };
  });
  const treeBest = branches.reduce((b, x, i) => (x.payoffs[0] > branches[b].payoffs[0] ? i : b), 0);
  return {
    scenario,
    game,
    nash,
    outcomes: PRICES.map((_, i) => ({ label: `${PRICE_NAMES[i]} ($${PRICES[i]})`, profit: Math.round(values[i] ?? 0), best: i === bestRow })),
    referenceLabel:
      col === null
        ? "No pure-strategy equilibrium, so there is no single reply to compare against"
        : scenario.rivalCommits !== undefined
          ? `Rival fixed at ${PRICE_NAMES[col]} ($${PRICES[col]})`
          : `Rival at its equilibrium price, ${PRICE_NAMES[col]} ($${PRICES[col]})`,
    bestRow,
    tree: { branches, best: treeBest },
    sensitivity: [0.03, 0.06, 0.09].map((s) => ({ sensitivity: s, profit: rounded(referenceProfit({ ...p, sensitivity: s }, scenario.rivalCommits)) })),
    baseline: { nashProfit: rounded(referenceProfit(BASE)) },
  };
}
