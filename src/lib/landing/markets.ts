import { normCdf, normInv, normal, rng } from "./stats";

/**
 * Illustrative market risk analysis. Prices are SIMULATED (a seeded random walk) and every drift and volatility is an assumption shown
 * on screen. Nothing is a forecast, a historical record, or a promise of return.
 *
 * Portfolio value after T years starts at 100 and is lognormal: ln V = (mu - sigma^2 / 2) T + sigma sqrt(T) Z, with Z standard normal.
 */
export type ScenarioId = "bull" | "base" | "bear";
export type RiskId = "conservative" | "balanced" | "aggressive";
export type Months = 1 | 3 | 12;

export const SCENARIOS: { id: ScenarioId; label: string; mu: number; sigma: number; blurb: string }[] = [
  { id: "bull", label: "Bull", mu: 0.14, sigma: 0.14, blurb: "Assumes equities drift up 14% a year with 14% volatility." },
  { id: "base", label: "Base", mu: 0.06, sigma: 0.17, blurb: "Assumes equities drift up 6% a year with 17% volatility." },
  { id: "bear", label: "Bear", mu: -0.12, sigma: 0.28, blurb: "Assumes equities drift down 12% a year with 28% volatility." },
];

export const RISKS: { id: RiskId; label: string; equity: number }[] = [
  { id: "conservative", label: "Conservative", equity: 0.3 },
  { id: "balanced", label: "Balanced", equity: 0.6 },
  { id: "aggressive", label: "Aggressive", equity: 0.9 },
];

export const MONTHS: Months[] = [1, 3, 12];
/** The defensive sleeve (bonds and cash) is held constant across scenarios, and correlated slightly with equities. */
export const DEFENSIVE = { mu: 0.03, sigma: 0.05, rho: 0.1 };
export const START = 100;

export function portfolio(sc: ScenarioId, risk: RiskId): { mu: number; sigma: number; weight: number } {
  const s = SCENARIOS.find((x) => x.id === sc)!;
  const w = RISKS.find((x) => x.id === risk)!.equity;
  const mu = w * s.mu + (1 - w) * DEFENSIVE.mu;
  const variance = w * w * s.sigma ** 2 + (1 - w) ** 2 * DEFENSIVE.sigma ** 2 + 2 * w * (1 - w) * DEFENSIVE.rho * s.sigma * DEFENSIVE.sigma;
  return { mu, sigma: Math.sqrt(variance), weight: w };
}

const lognormalParams = (mu: number, sigma: number, years: number) => ({ m: (mu - (sigma * sigma) / 2) * years, s: sigma * Math.sqrt(years) });
const valueAt = (m: number, s: number, p: number) => START * Math.exp(m + s * normInv(p));

export interface Distribution {
  mu: number;
  sigma: number;
  months: number;
  quantiles: { q05: number; q25: number; q50: number; q75: number; q95: number };
  /** Probability that the portfolio is worth less than it started. */
  lossProbability: number;
  /** Average value across the worst 5% of outcomes. */
  worstFivePercentAverage: number;
  bins: { from: number; to: number; probability: number }[];
}

export function distribution(sc: ScenarioId, risk: RiskId, months: Months): Distribution {
  const { mu, sigma } = portfolio(sc, risk);
  const { m, s } = lognormalParams(mu, sigma, months / 12);
  const q = (p: number) => valueAt(m, s, p);
  const cdf = (x: number) => normCdf((Math.log(x / START) - m) / s);
  const lo = q(0.005);
  const hi = q(0.995);
  const N = 28;
  const bins = Array.from({ length: N }, (_, i) => {
    const from = lo + ((hi - lo) * i) / N;
    const to = lo + ((hi - lo) * (i + 1)) / N;
    return { from, to, probability: cdf(to) - cdf(from) };
  });
  return {
    mu, sigma, months,
    quantiles: { q05: q(0.05), q25: q(0.25), q50: q(0.5), q75: q(0.75), q95: q(0.95) },
    lossProbability: normCdf((0 - m) / s),
    // E[V | V <= q05] = START exp(m + s^2/2) Phi(z - s) / 0.05 for the lognormal.
    worstFivePercentAverage: (START * Math.exp(m + (s * s) / 2) * normCdf(normInv(0.05) - s)) / 0.05,
    bins,
  };
}

/** Quantile bands over time (the fan chart), from the same lognormal model at each step. */
export function fan(sc: ScenarioId, risk: RiskId, months: Months, steps = 12) {
  const { mu, sigma } = portfolio(sc, risk);
  return Array.from({ length: steps + 1 }, (_, i) => {
    const t = (months / 12) * (i / steps);
    if (t === 0) return { t: 0, q05: START, q25: START, q50: START, q75: START, q95: START };
    const { m, s } = lognormalParams(mu, sigma, t);
    return { t, q05: valueAt(m, s, 0.05), q25: valueAt(m, s, 0.25), q50: valueAt(m, s, 0.5), q75: valueAt(m, s, 0.75), q95: valueAt(m, s, 0.95) };
  });
}

export const STRESSES = [
  { label: "Equities fall 20%", equity: -0.2, defensive: 0.0 },
  { label: "Equities fall 35%, defensive assets fall 5%", equity: -0.35, defensive: -0.05 },
  { label: "Rates shock: equities -8%, defensive -8%", equity: -0.08, defensive: -0.08 },
  { label: "Defensive sleeve fails: equities flat, defensive -15%", equity: 0.0, defensive: -0.15 },
];

/** Instant portfolio change under each hypothetical shock: weight x equity shock + (1 - weight) x defensive shock. */
export function stress(risk: RiskId) {
  const w = RISKS.find((x) => x.id === risk)!.equity;
  return STRESSES.map((s) => ({ ...s, impact: w * s.equity + (1 - w) * s.defensive }));
}

export interface Candle { i: number; open: number; high: number; low: number; close: number }

/** A SIMULATED daily price series (seeded random walk, 8% annual drift and 22% volatility). It is not market data. */
export function candles(seed = 11, n = 60): Candle[] {
  const draw = rng(seed);
  const sigma = 0.22 / Math.sqrt(252);
  const mu = 0.08 / 252;
  let price = 100;
  return Array.from({ length: n }, (_, i) => {
    // regime change in the middle so the demonstration shows a volatile stretch
    const vol = i > 26 && i < 40 ? sigma * 2.2 : sigma;
    const open = price;
    const close = open * Math.exp(mu - (vol * vol) / 2 + vol * normal(draw));
    const wick = Math.abs(normal(draw)) * vol * 0.6;
    const high = Math.max(open, close) * (1 + wick);
    const low = Math.min(open, close) * (1 - Math.abs(normal(draw)) * vol * 0.6);
    price = close;
    return { i, open, high, low, close };
  });
}

export type Regime = "Uptrend" | "Downtrend" | "Range" | "High volatility";

/** Labels each day from the previous 10 days: high volatility if realised volatility is well above its median, else by trend. */
export function regimes(c: Candle[], window = 10): { i: number; regime: Regime; volatility: number }[] {
  const rets = c.map((x) => Math.log(x.close / x.open));
  const out = c.map((_, i) => {
    const w = rets.slice(Math.max(0, i - window + 1), i + 1);
    const mean = w.reduce((a, b) => a + b, 0) / w.length;
    const vol = Math.sqrt(w.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, w.length - 1)) * Math.sqrt(252);
    return { i, vol, trend: w.reduce((a, b) => a + b, 0) };
  });
  const vols = out.slice(window).map((o) => o.vol).sort((a, b) => a - b);
  const threshold = (vols[Math.floor(vols.length / 2)] ?? 0) * 1.35;
  return out.map((o) => ({
    i: o.i,
    volatility: o.vol,
    regime: (o.i >= window && o.vol > threshold ? "High volatility" : o.trend > 0.012 ? "Uptrend" : o.trend < -0.012 ? "Downtrend" : "Range") as Regime,
  }));
}
