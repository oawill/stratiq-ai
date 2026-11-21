import { normal, quantile, rng } from "./stats";

/**
 * Illustrative election model for a FICTIONAL country. Parties are neutral labels and the regions are invented. Nothing here is a
 * forecast about a real election. Seats are allocated region by region with the D'Hondt method.
 */
export const PARTIES = [
  { id: "A", name: "Party A", colour: "#00E5FF" },
  { id: "B", name: "Party B", colour: "#8B5CF6" },
  { id: "C", name: "Party C", colour: "#F59E0B" },
  { id: "D", name: "Party D", colour: "#34D399" },
] as const;

export interface Region {
  id: string;
  name: string;
  seats: number;
  /** Share of eligible voters who voted in the last (fictional) election. */
  turnout: number;
  /** Vote shares of parties A to D (sum 1) in the baseline forecast. */
  shares: number[];
  /** Vote shares at the previous (fictional) election, for comparison. */
  previous: number[];
}

export const REGIONS: Region[] = [
  { id: "north", name: "Northern Highlands", seats: 14, turnout: 0.66, shares: [0.34, 0.27, 0.24, 0.15], previous: [0.31, 0.3, 0.25, 0.14] },
  { id: "coast", name: "Eastern Coast", seats: 18, turnout: 0.7, shares: [0.29, 0.36, 0.2, 0.15], previous: [0.32, 0.33, 0.2, 0.15] },
  { id: "central", name: "Central Plains", seats: 24, turnout: 0.64, shares: [0.31, 0.26, 0.28, 0.15], previous: [0.3, 0.27, 0.3, 0.13] },
  { id: "valley", name: "Western Valley", seats: 16, turnout: 0.68, shares: [0.22, 0.3, 0.3, 0.18], previous: [0.25, 0.28, 0.3, 0.17] },
  { id: "islands", name: "Southern Islands", seats: 8, turnout: 0.62, shares: [0.2, 0.24, 0.17, 0.39], previous: [0.19, 0.25, 0.2, 0.36] },
  { id: "capital", name: "Capital District", seats: 20, turnout: 0.74, shares: [0.28, 0.33, 0.14, 0.25], previous: [0.3, 0.31, 0.15, 0.24] },
];

export const TOTAL_SEATS = REGIONS.reduce((s, r) => s + r.seats, 0);
export const MAJORITY = Math.floor(TOTAL_SEATS / 2) + 1;
/** How strongly each party's turnout responds to national turnout (1 = in proportion). An assumption shown on screen. */
export const TURNOUT_ELASTICITY = [1.0, 1.3, 0.8, 1.0];
/** Spread of the random shocks used for the uncertainty range (illustrative). */
export const NATIONAL_NOISE = 0.04;
export const REGIONAL_NOISE = 0.05;

export interface Scenario {
  /** Change in turnout everywhere, in percentage points. */
  turnoutShift: number;
  /** Region where a swing is applied, if any. */
  swingRegion: string | null;
  /** Percentage points of vote moved from Party A to Party B in that region (negative moves them from B to A). */
  swing: number;
  /** Parties assumed to govern together. */
  coalition: string[];
}

export const BASELINE: Scenario = { turnoutShift: 0, swingRegion: null, swing: 0, coalition: ["A", "C"] };

const normalise = (v: number[]) => {
  const s = v.reduce((a, b) => a + b, 0);
  return v.map((x) => x / s);
};

/** A region's vote shares after the swing (if it is the swing region) and the national turnout change. */
export function adjustedShares(region: Region, s: Scenario): number[] {
  let sh = [...region.shares];
  if (s.swingRegion === region.id && s.swing !== 0) {
    const move = Math.min(Math.abs(s.swing) / 100, s.swing > 0 ? sh[0] : sh[1]);
    if (s.swing > 0) { sh[0] -= move; sh[1] += move; } else { sh[1] -= move; sh[0] += move; }
  }
  if (s.turnoutShift !== 0) {
    const ratio = Math.max(0.2, (region.turnout + s.turnoutShift / 100) / region.turnout);
    sh = normalise(sh.map((x, i) => x * Math.pow(ratio, TURNOUT_ELASTICITY[i])));
  }
  return sh;
}

/** D'Hondt: each seat goes to the party with the highest votes / (seats already won + 1). */
export function dHondt(shares: number[], seats: number): number[] {
  const won = shares.map(() => 0);
  for (let i = 0; i < seats; i++) {
    let best = 0;
    shares.forEach((v, p) => { if (v / (won[p] + 1) > shares[best] / (won[best] + 1) + 1e-12) best = p; });
    won[best]++;
  }
  return won;
}

export interface RegionResult { region: Region; shares: number[]; seats: number[]; leader: number }
export interface Projection {
  regions: RegionResult[];
  totals: number[];
  /** 10th, 50th and 90th percentile of seats from the uncertainty runs. */
  ranges: { p10: number; p50: number; p90: number }[];
  coalition: { parties: string[]; seats: number; hasMajority: boolean; probabilityOfMajority: number };
  previous: number[];
  runs: number;
}

const sumSeats = (rs: RegionResult[]) => PARTIES.map((_, p) => rs.reduce((s, r) => s + r.seats[p], 0));
const leaderOf = (v: number[]) => v.indexOf(Math.max(...v));

function resultFor(shareFor: (r: Region) => number[]): RegionResult[] {
  return REGIONS.map((region) => {
    const shares = shareFor(region);
    return { region, shares, seats: dHondt(shares, region.seats), leader: leaderOf(shares) };
  });
}

export function project(s: Scenario, runs = 400, seed = 7): Projection {
  const regions = resultFor((r) => adjustedShares(r, s));
  const totals = sumSeats(regions);
  const idx = s.coalition.map((id) => PARTIES.findIndex((p) => p.id === id)).filter((i) => i >= 0);
  const draw = rng(seed);
  const samples: number[][] = PARTIES.map(() => []);
  let majority = 0;
  for (let k = 0; k < runs; k++) {
    const national = PARTIES.map(() => normal(draw) * NATIONAL_NOISE);
    const seats = PARTIES.map(() => 0);
    for (const r of REGIONS) {
      const base = adjustedShares(r, s);
      const noisy = normalise(base.map((x, p) => x * Math.exp(national[p] + normal(draw) * REGIONAL_NOISE)));
      dHondt(noisy, r.seats).forEach((n, p) => { seats[p] += n; });
    }
    seats.forEach((n, p) => samples[p].push(n));
    if (idx.reduce((a, p) => a + seats[p], 0) >= MAJORITY) majority++;
  }
  const ranges = samples.map((v) => { const sorted = [...v].sort((a, b) => a - b); return { p10: quantile(sorted, 0.1), p50: quantile(sorted, 0.5), p90: quantile(sorted, 0.9) }; });
  const coalitionSeats = idx.reduce((a, p) => a + totals[p], 0);
  return {
    regions, totals, ranges, runs,
    coalition: { parties: s.coalition, seats: coalitionSeats, hasMajority: coalitionSeats >= MAJORITY, probabilityOfMajority: majority / runs },
    previous: sumSeats(resultFor((r) => normalise(r.previous))),
  };
}
