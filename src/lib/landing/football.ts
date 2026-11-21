import { matchProbabilities, type MatchProbabilities } from "../poisson";

/** Illustrative football demonstration. Every team and fixture is FICTIONAL; nothing here is a real result or a verified model output. */
export type Result = "W" | "D" | "L";

export interface DemoTeam {
  id: string;
  name: string;
  short: string;
  colour: string;
  /** Scoring multiplier against an average defence (1 = average). */
  attack: number;
  /** Goals-conceded multiplier (1 = average, lower is better). */
  defence: number;
  /** The last five results, oldest first (illustrative). */
  form: Result[];
  /** 0 = narrow and central, 1 = wide: shapes the illustrative pitch heatmap only. */
  width: number;
}

export const TEAMS: DemoTeam[] = [
  { id: "north", name: "Northgate FC", short: "NOR", colour: "#00E5FF", attack: 1.32, defence: 0.82, form: ["W", "W", "D", "W", "L"], width: 0.45 },
  { id: "river", name: "Riverside United", short: "RIV", colour: "#8B5CF6", attack: 1.08, defence: 0.95, form: ["L", "W", "D", "D", "W"], width: 0.7 },
  { id: "harbour", name: "Harbour City", short: "HAR", colour: "#2563EB", attack: 1.18, defence: 1.1, form: ["W", "L", "W", "L", "D"], width: 0.6 },
  { id: "iron", name: "Ironvale Athletic", short: "IRO", colour: "#F59E0B", attack: 0.86, defence: 0.9, form: ["D", "D", "L", "W", "D"], width: 0.35 },
  { id: "west", name: "Westfield Rovers", short: "WES", colour: "#10B981", attack: 0.95, defence: 1.18, form: ["L", "L", "D", "W", "L"], width: 0.55 },
  { id: "crest", name: "Crestmoor Town", short: "CRE", colour: "#F43F5E", attack: 0.78, defence: 1.28, form: ["L", "D", "L", "L", "W"], width: 0.5 },
];

export const FIXTURES: { id: string; home: string; away: string; label: string }[] = [
  { id: "f1", home: "north", away: "river", label: "Northgate FC v Riverside United" },
  { id: "f2", home: "harbour", away: "iron", label: "Harbour City v Ironvale Athletic" },
  { id: "f3", home: "west", away: "crest", label: "Westfield Rovers v Crestmoor Town" },
];

export const LEAGUE_MEAN_GOALS = 1.35;
export const HOME_ADVANTAGE = 1.12;
/** How far each side's expected goals is moved to show the uncertainty band (a fraction, illustrative). */
export const UNCERTAINTY_SHIFT = 0.15;

export interface Params {
  homeAttack: number;
  homeDefence: number;
  awayAttack: number;
  awayDefence: number;
  homeAdvantage: number;
}

export interface Scenario {
  id: string;
  label: string;
  note: string;
  /** Returns adjusted parameters; only the model's own inputs are changed. */
  apply: (p: Params) => Params;
}

export const SCENARIOS: Scenario[] = [
  { id: "base", label: "Baseline", note: "The demonstration ratings as given.", apply: (p) => p },
  { id: "striker", label: "Home key attacker unavailable", note: "Home attack multiplied by 0.85 (an assumption, not an estimate).", apply: (p) => ({ ...p, homeAttack: p.homeAttack * 0.85 }) },
  { id: "park", label: "Away side defends deep", note: "Away attack x0.9 and away goals conceded x0.9 (an assumption).", apply: (p) => ({ ...p, awayAttack: p.awayAttack * 0.9, awayDefence: p.awayDefence * 0.9 }) },
  { id: "neutral", label: "Neutral venue", note: "Home advantage removed (factor 1.00).", apply: (p) => ({ ...p, homeAdvantage: 1 }) },
];

export function paramsFor(home: DemoTeam, away: DemoTeam): Params {
  return { homeAttack: home.attack, homeDefence: home.defence, awayAttack: away.attack, awayDefence: away.defence, homeAdvantage: HOME_ADVANTAGE };
}

/** Expected goals: league mean x own attack x opponent's goals-conceded multiplier (x home advantage for the home side). */
export function expectedGoals(p: Params): { home: number; away: number } {
  return { home: LEAGUE_MEAN_GOALS * p.homeAdvantage * p.homeAttack * p.awayDefence, away: LEAGUE_MEAN_GOALS * p.awayAttack * p.homeDefence };
}

export interface Interval {
  lo: number;
  hi: number;
}
export interface Forecast {
  xg: { home: number; away: number };
  probs: MatchProbabilities;
  intervals: { home: Interval; draw: Interval; away: Interval };
  topScorelines: { home: number; away: number; p: number }[];
}

/** Probabilities from the Poisson model, plus the range they move through when each side's expected goals is shifted by +/-15%. */
export function forecast(p: Params): Forecast {
  const xg = expectedGoals(p);
  const probs = matchProbabilities(xg.home, xg.away);
  const corners = [-1, 1].flatMap((a) => [-1, 1].map((b) => matchProbabilities(xg.home * (1 + a * UNCERTAINTY_SHIFT), xg.away * (1 + b * UNCERTAINTY_SHIFT))));
  const span = (pick: (m: MatchProbabilities) => number, base: number): Interval => ({ lo: Math.min(base, ...corners.map(pick)), hi: Math.max(base, ...corners.map(pick)) });
  const cells = probs.grid.flatMap((row, h) => row.map((v, a) => ({ home: h, away: a, p: v / probs.covered })));
  cells.sort((x, y) => y.p - x.p);
  return {
    xg,
    probs,
    intervals: { home: span((m) => m.home, probs.home), draw: span((m) => m.draw, probs.draw), away: span((m) => m.away, probs.away) },
    topScorelines: cells.slice(0, 5),
  };
}

export const pointsPerMatch = (form: Result[]) => form.reduce((s, r) => s + (r === "W" ? 3 : r === "D" ? 1 : 0), 0) / form.length;

/** Overall strength index on a 0-100 scale from attack and defence (50 = average): 50 + 50 tanh(ln(attack / defence)). */
export const strengthIndex = (t: Pick<DemoTeam, "attack" | "defence">) => 50 + 50 * Math.tanh(Math.log(t.attack / t.defence));

export const COLS = 12;
export const ROWS = 7;
/**
 * Illustrative attacking-intensity zones on a pitch (the team attacks left to right), normalised so the cells sum to 1.
 * Built from the demo attack rating and a width setting. It is NOT player-tracking data.
 */
export function pitchHeat(attack: number, width: number): number[][] {
  const cells: number[][] = [];
  let total = 0;
  for (let r = 0; r < ROWS; r++) {
    const row: number[] = [];
    for (let c = 0; c < COLS; c++) {
      const x = c / (COLS - 1);
      const y = r / (ROWS - 1);
      const depth = Math.exp(-((x - 0.82) ** 2) / 0.09) * attack + 0.25 * Math.exp(-((x - 0.5) ** 2) / 0.12);
      const central = Math.exp(-((y - 0.5) ** 2) / 0.05);
      const wide = Math.exp(-((y - 0.12) ** 2) / 0.03) + Math.exp(-((y - 0.88) ** 2) / 0.03);
      const v = depth * ((1 - width) * central + width * (0.55 * wide + 0.45 * central));
      row.push(v);
      total += v;
    }
    cells.push(row);
  }
  return cells.map((row) => row.map((v) => v / total));
}
