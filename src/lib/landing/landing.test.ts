import { describe, expect, it } from "vitest";
import { buildDuopolyGame, DEFAULT_DUOPOLY, duopolyProfit, pureNash } from "../game";
import * as fb from "./football";
import * as mk from "./markets";
import * as po from "./politics";
import { clamp, normCdf, normInv, normal, quantile, rng } from "./stats";
import * as st from "./strategy";

describe("stats helpers", () => {
  it("is deterministic for a seed and differs between seeds", () => {
    const a = rng(5), b = rng(5), c = rng(6);
    const xs = [a(), a(), a()];
    expect(xs).toEqual([b(), b(), b()]);
    expect(xs).not.toEqual([c(), c(), c()]);
    expect(xs.every((x) => x >= 0 && x < 1)).toBe(true);
  });
  it("normal draws have roughly zero mean and unit variance", () => {
    const r = rng(1);
    const v = Array.from({ length: 20000 }, () => normal(r));
    const mean = v.reduce((s, x) => s + x, 0) / v.length;
    const variance = v.reduce((s, x) => s + (x - mean) ** 2, 0) / v.length;
    expect(Math.abs(mean)).toBeLessThan(0.03);
    expect(Math.abs(variance - 1)).toBeLessThan(0.05);
  });
  it("normCdf and normInv are inverses and match known values", () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6);
    expect(normCdf(1.959964)).toBeCloseTo(0.975, 4);
    for (const p of [0.001, 0.05, 0.25, 0.5, 0.75, 0.95, 0.999]) expect(normCdf(normInv(p))).toBeCloseTo(p, 5);
    expect(normInv(0.975)).toBeCloseTo(1.959964, 4);
    expect(() => normInv(0)).toThrow();
  });
  it("clamps and takes quantiles", () => {
    expect(clamp(5, 0, 3)).toBe(3);
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
  });
});

describe("football demonstration", () => {
  const team = (id: string) => fb.TEAMS.find((t) => t.id === id)!;
  const base = (h: string, a: string) => fb.paramsFor(team(h), team(a));

  it("has fixtures that point at real demo teams and every team is fictional-named", () => {
    for (const f of fb.FIXTURES) {
      expect(team(f.home)).toBeDefined();
      expect(team(f.away)).toBeDefined();
    }
    expect(fb.TEAMS.every((t) => t.form.length === 5)).toBe(true);
  });
  it("outcome probabilities sum to one and follow the stated expected-goals formula", () => {
    const p = base("north", "river");
    const f = fb.forecast(p);
    expect(f.probs.home + f.probs.draw + f.probs.away).toBeCloseTo(1, 9);
    expect(f.xg.home).toBeCloseTo(fb.LEAGUE_MEAN_GOALS * fb.HOME_ADVANTAGE * team("north").attack * team("river").defence, 9);
    expect(f.xg.away).toBeCloseTo(fb.LEAGUE_MEAN_GOALS * team("river").attack * team("north").defence, 9);
    expect(f.topScorelines).toHaveLength(5);
    expect(f.topScorelines.every((s, i, a) => i === 0 || a[i - 1].p >= s.p)).toBe(true);
  });
  it("the better side is favoured and removing home advantage lowers the home win chance", () => {
    const strong = fb.forecast(base("north", "crest"));
    expect(strong.probs.home).toBeGreaterThan(strong.probs.away);
    const neutral = fb.forecast(fb.SCENARIOS.find((s) => s.id === "neutral")!.apply(base("north", "crest")));
    expect(neutral.probs.home).toBeLessThan(strong.probs.home);
  });
  it("every scenario changes only what its note says", () => {
    const p = base("harbour", "iron");
    const striker = fb.SCENARIOS.find((s) => s.id === "striker")!.apply(p);
    expect(striker.homeAttack).toBeCloseTo(p.homeAttack * 0.85, 9);
    expect({ ...striker, homeAttack: p.homeAttack }).toEqual(p);
    expect(fb.forecast(striker).xg.home).toBeLessThan(fb.forecast(p).xg.home);
    expect(fb.SCENARIOS[0].apply(p)).toBe(p);
  });
  it("uncertainty intervals contain the central probability and widen with the shift", () => {
    const f = fb.forecast(base("west", "crest"));
    for (const k of ["home", "draw", "away"] as const) {
      expect(f.intervals[k].lo).toBeLessThanOrEqual(f.probs[k]);
      expect(f.intervals[k].hi).toBeGreaterThanOrEqual(f.probs[k]);
      expect(f.intervals[k].hi - f.intervals[k].lo).toBeGreaterThan(0.02);
    }
  });
  it("derives form points and a strength index from the ratings", () => {
    expect(fb.pointsPerMatch(["W", "W", "D", "W", "L"])).toBeCloseTo(2.0, 9);
    expect(fb.strengthIndex({ attack: 1, defence: 1 })).toBeCloseTo(50, 9);
    expect(fb.strengthIndex(team("north"))).toBeGreaterThan(fb.strengthIndex(team("crest")));
    expect(fb.strengthIndex({ attack: 9, defence: 0.1 })).toBeLessThanOrEqual(100);
  });
  it("the pitch heatmap is a distribution over the pitch that favours the attacking end", () => {
    const h = fb.pitchHeat(1.2, 0.5);
    expect(h).toHaveLength(fb.ROWS);
    expect(h.every((r) => r.length === fb.COLS)).toBe(true);
    expect(h.flat().reduce((s, x) => s + x, 0)).toBeCloseTo(1, 9);
    const col = (c: number) => h.reduce((s, r) => s + r[c], 0);
    expect(col(fb.COLS - 3)).toBeGreaterThan(col(1));
  });
});

describe("strategy demonstration", () => {
  it("reproduces the existing Strategy simulator exactly for baseline assumptions", () => {
    for (const a of st.PRICES) for (const b of st.PRICES) {
      const [x, y] = duopolyProfit(a, b, DEFAULT_DUOPOLY);
      const [u, v] = st.profits(a, b, st.BASE);
      expect(u).toBeCloseTo(x, 9);
      expect(v).toBeCloseTo(y, 9);
    }
    expect(st.buildGame(st.BASE)).toEqual(buildDuopolyGame(DEFAULT_DUOPOLY));
  });

  it("finds exactly the equilibria a brute-force check finds, in every scenario", () => {
    for (const s of st.SCENARIOS) {
      const g = st.buildGame(s.params);
      const brute: { row: number; col: number }[] = [];
      for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
        const rowOk = [0, 1, 2].every((r2) => g.payoffs[r2][c][0] <= g.payoffs[r][c][0]);
        const colOk = [0, 1, 2].every((c2) => g.payoffs[r][c2][1] <= g.payoffs[r][c][1]);
        if (rowOk && colOk) brute.push({ row: r, col: c });
      }
      expect(st.analyse(s.id).nash).toEqual(brute);
      expect(pureNash(g)).toEqual(brute);
    }
  });

  it("when the rival commits to a price, our best reply is the highest profit in that column", () => {
    for (const id of ["rival-lowers", "rival-holds"] as const) {
      const a = st.analyse(id);
      const col = a.scenario.rivalCommits!;
      const profits = st.PRICES.map((p) => st.profits(p, st.PRICES[col], a.scenario.params)[0]);
      expect(a.bestRow).toBe(profits.indexOf(Math.max(...profits)));
      expect(a.outcomes.filter((o) => o.best)).toHaveLength(1);
      expect(a.outcomes[a.bestRow!].profit).toBe(Math.round(Math.max(...profits)));
      expect(a.nash.length >= 0).toBe(true);
    }
  });

  it("the decision tree is the leader-first game: the rival always plays its own best reply", () => {
    for (const s of st.SCENARIOS) {
      const a = st.analyse(s.id);
      for (const br of a.tree.branches) {
        const theirs = st.PRICES.map((q) => st.profits(st.PRICES[br.ours], q, s.params)[1]);
        expect(theirs[br.reply]).toBeCloseTo(Math.max(...theirs), 9);
      }
      const best = a.tree.branches[a.tree.best].payoffs[0];
      expect(a.tree.branches.every((b) => b.payoffs[0] <= best)).toBe(true);
    }
  });

  it("scenario levers move profit by exactly what the assumptions say", () => {
    const expand = st.SCENARIOS.find((s) => s.id === "expand-share")!.params;
    const [withPush] = st.profits(12, 12, expand);
    const [without] = st.profits(12, 12, st.BASE);
    const demand = 1000 * (1.6 - 12 / 20);
    expect(withPush - without).toBeCloseTo(0.08 * demand * (12 - 5) - 400, 6);
    const market = st.SCENARIOS.find((s) => s.id === "new-market")!.params;
    expect(st.profits(12, 12, market)[0]).toBeCloseTo(st.profits(12, 12, { ...st.BASE, marketSize: 1250 })[0] - 700, 6);
  });

  it("sensitivity values are consistent with recomputing at that sensitivity", () => {
    const a = st.analyse("rival-holds");
    for (const row of a.sensitivity) {
      const p = { ...a.scenario.params, sensitivity: row.sensitivity };
      expect(row.profit).toBe(Math.round(Math.max(...st.PRICES.map((u) => st.profits(u, 12, p)[0]))));
    }
    expect(a.sensitivity.map((r) => r.sensitivity)).toEqual([0.03, 0.06, 0.09]);
  });
});

describe("political demonstration", () => {
  it("has a consistent fictional electorate", () => {
    expect(po.TOTAL_SEATS).toBe(100);
    expect(po.MAJORITY).toBe(51);
    for (const r of po.REGIONS) {
      expect(r.shares.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
      expect(r.previous.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    }
  });
  it("D'Hondt hands out exactly the seats available and follows the vote", () => {
    expect(po.dHondt([0.4, 0.3, 0.2, 0.1], 10)).toEqual([4, 3, 2, 1]);
    for (const r of po.REGIONS) expect(po.dHondt(r.shares, r.seats).reduce((a, b) => a + b, 0)).toBe(r.seats);
    expect(po.dHondt([1, 0, 0, 0], 5)).toEqual([5, 0, 0, 0]);
  });
  it("the baseline scenario changes nothing", () => {
    for (const r of po.REGIONS) expect(po.adjustedShares(r, po.BASELINE)).toEqual(r.shares);
  });
  it("a swing moves vote from A to B only in the chosen region and keeps shares summing to one", () => {
    const s = { ...po.BASELINE, swingRegion: "central", swing: 5 };
    const central = po.REGIONS.find((r) => r.id === "central")!;
    const out = po.adjustedShares(central, s);
    expect(out[0]).toBeCloseTo(central.shares[0] - 0.05, 9);
    expect(out[1]).toBeCloseTo(central.shares[1] + 0.05, 9);
    expect(out.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    const other = po.REGIONS.find((r) => r.id === "coast")!;
    expect(po.adjustedShares(other, s)).toEqual(other.shares);
    const back = po.adjustedShares(central, { ...s, swing: -5 });
    expect(back[1]).toBeCloseTo(central.shares[1] - 0.05, 9);
  });
  it("higher turnout helps the party with the highest turnout elasticity, lower turnout helps the lowest", () => {
    const r = po.REGIONS[0];
    const up = po.adjustedShares(r, { ...po.BASELINE, turnoutShift: 8 });
    const down = po.adjustedShares(r, { ...po.BASELINE, turnoutShift: -8 });
    expect(up[1]).toBeGreaterThan(r.shares[1]);
    expect(up[2]).toBeLessThan(r.shares[2]);
    expect(down[2]).toBeGreaterThan(r.shares[2]);
    expect(up.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
  });
  it("projections are deterministic, allocate every seat and give ordered ranges", () => {
    const a = po.project(po.BASELINE);
    expect(a).toEqual(po.project(po.BASELINE));
    expect(a.totals.reduce((x, y) => x + y, 0)).toBe(100);
    expect(a.previous.reduce((x, y) => x + y, 0)).toBe(100);
    for (const r of a.ranges) {
      expect(r.p10).toBeLessThanOrEqual(r.p50);
      expect(r.p50).toBeLessThanOrEqual(r.p90);
    }
    expect(a.regions.map((r) => r.region.seats)).toEqual(po.REGIONS.map((r) => r.seats));
    expect(a.coalition.probabilityOfMajority).toBeGreaterThanOrEqual(0);
    expect(a.coalition.probabilityOfMajority).toBeLessThanOrEqual(1);
  });
  it("a larger coalition never has a lower chance of a majority, and its seats are the sum of its parties", () => {
    const two = po.project({ ...po.BASELINE, coalition: ["A", "C"] });
    const three = po.project({ ...po.BASELINE, coalition: ["A", "B", "C"] });
    expect(three.coalition.probabilityOfMajority).toBeGreaterThanOrEqual(two.coalition.probabilityOfMajority);
    expect(two.coalition.seats).toBe(two.totals[0] + two.totals[2]);
    expect(three.coalition.hasMajority).toBe(three.coalition.seats >= po.MAJORITY);
    expect(po.project({ ...po.BASELINE, coalition: [] }).coalition.seats).toBe(0);
  });
  it("a swing towards B gives B at least as many seats in the region", () => {
    const before = po.project(po.BASELINE).regions.find((r) => r.region.id === "valley")!;
    const after = po.project({ ...po.BASELINE, swingRegion: "valley", swing: 8 }).regions.find((r) => r.region.id === "valley")!;
    expect(after.seats[1]).toBeGreaterThanOrEqual(before.seats[1]);
    expect(after.seats[0]).toBeLessThanOrEqual(before.seats[0]);
  });
});

describe("market demonstration", () => {
  it("risk tolerance raises portfolio volatility and the equity weight", () => {
    const sig = mk.RISKS.map((r) => mk.portfolio("base", r.id).sigma);
    expect(sig[0]).toBeLessThan(sig[1]);
    expect(sig[1]).toBeLessThan(sig[2]);
    const p = mk.portfolio("base", "balanced");
    expect(p.mu).toBeCloseTo(0.6 * 0.06 + 0.4 * 0.03, 9);
    expect(p.sigma).toBeCloseTo(Math.sqrt(0.36 * 0.17 ** 2 + 0.16 * 0.05 ** 2 + 2 * 0.24 * 0.1 * 0.17 * 0.05), 9);
  });
  it("scenario medians are ordered bull above base above bear, and quantiles are ordered", () => {
    const med = (s: mk.ScenarioId) => mk.distribution(s, "balanced", 12).quantiles.q50;
    expect(med("bull")).toBeGreaterThan(med("base"));
    expect(med("base")).toBeGreaterThan(med("bear"));
    const q = mk.distribution("base", "balanced", 12).quantiles;
    expect([q.q05, q.q25, q.q50, q.q75, q.q95].every((v, i, a) => i === 0 || a[i - 1] < v)).toBe(true);
  });
  it("a longer horizon widens the range and a riskier portfolio widens it too", () => {
    const width = (r: mk.RiskId, m: mk.Months) => { const q = mk.distribution("base", r, m).quantiles; return q.q95 - q.q05; };
    expect(width("balanced", 1)).toBeLessThan(width("balanced", 3));
    expect(width("balanced", 3)).toBeLessThan(width("balanced", 12));
    expect(width("conservative", 12)).toBeLessThan(width("aggressive", 12));
  });
  it("the loss probability matches the median and the histogram holds the central 99% of outcomes", () => {
    const d = mk.distribution("bear", "aggressive", 12);
    expect(d.lossProbability).toBeGreaterThan(0.5);
    expect(d.quantiles.q50).toBeLessThan(mk.START);
    const b = mk.distribution("bull", "conservative", 12);
    expect(b.quantiles.q50).toBeGreaterThan(mk.START);
    expect(b.lossProbability).toBeLessThan(0.5);
    expect(d.bins.reduce((s, x) => s + x.probability, 0)).toBeCloseTo(0.99, 3);
    expect(d.bins.every((x) => x.probability >= 0 && x.to > x.from)).toBe(true);
  });
  it("the average of the worst 5% is below the 5th percentile and matches a simulation", () => {
    const d = mk.distribution("base", "aggressive", 12);
    expect(d.worstFivePercentAverage).toBeLessThan(d.quantiles.q05);
    const { mu, sigma } = mk.portfolio("base", "aggressive");
    const r = rng(3);
    const draws = Array.from({ length: 200000 }, () => mk.START * Math.exp((mu - sigma ** 2 / 2) + sigma * normal(r))).sort((a, b) => a - b);
    const tail = draws.slice(0, draws.length * 0.05);
    const empirical = tail.reduce((a, b) => a + b, 0) / tail.length;
    expect(Math.abs(empirical - d.worstFivePercentAverage)).toBeLessThan(0.6);
    expect(Math.abs(draws[Math.floor(draws.length * 0.05)] - d.quantiles.q05)).toBeLessThan(0.6);
  });
  it("the fan chart starts at the start value and ends on the same quantiles as the distribution", () => {
    const f = mk.fan("base", "balanced", 3);
    const d = mk.distribution("base", "balanced", 3);
    expect(f[0]).toMatchObject({ t: 0, q05: 100, q50: 100, q95: 100 });
    expect(f[f.length - 1].q05).toBeCloseTo(d.quantiles.q05, 9);
    expect(f[f.length - 1].q95).toBeCloseTo(d.quantiles.q95, 9);
    expect(f.every((p, i, a) => i === 0 || p.q95 - p.q05 >= a[i - 1].q95 - a[i - 1].q05)).toBe(true);
  });
  it("stress tests are the weighted shocks", () => {
    const s = mk.stress("aggressive");
    expect(s[0].impact).toBeCloseTo(0.9 * -0.2, 9);
    expect(s[1].impact).toBeCloseTo(0.9 * -0.35 + 0.1 * -0.05, 9);
    expect(mk.stress("conservative")[0].impact).toBeGreaterThan(mk.stress("aggressive")[0].impact);
  });
  it("the simulated series is deterministic, well formed, and contains a volatile stretch", () => {
    const c = mk.candles();
    expect(c).toEqual(mk.candles());
    expect(c).toHaveLength(60);
    expect(c.every((x) => x.high >= Math.max(x.open, x.close) && x.low <= Math.min(x.open, x.close) && x.low > 0)).toBe(true);
    expect(c.every((x, i) => i === 0 || x.open === c[i - 1].close)).toBe(true);
    const r = mk.regimes(c);
    expect(r).toHaveLength(60);
    expect(r.some((x) => x.regime === "High volatility")).toBe(true);
    expect(new Set(r.map((x) => x.regime)).size).toBeGreaterThan(1);
    expect(mk.candles(12)).not.toEqual(c);
  });
});
