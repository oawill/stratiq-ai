import { describe, expect, it } from "vitest";
import { matchProbabilities, poissonPmf } from "../src/lib/poisson";
import { buildDuopolyGame, pureNash } from "../src/lib/game";
import { annualMonthly, annualTotal } from "../src/lib/pricing";

describe("poisson", () => {
  it("pmf matches known value", () => {
    expect(poissonPmf(2, 1.5)).toBeCloseTo(0.251, 3);
  });
  it("outcomes sum to 1", () => {
    const m = matchProbabilities(1.6, 1.1);
    expect(m.home + m.draw + m.away).toBeCloseTo(1, 10);
    expect(m.home).toBeGreaterThan(m.away);
  });
  it("symmetric xG gives symmetric result", () => {
    const m = matchProbabilities(1.3, 1.3);
    expect(m.home).toBeCloseTo(m.away, 10);
  });
});

describe("game", () => {
  it("finds the pure Nash equilibrium of a prisoner's dilemma", () => {
    const g = {
      rowLabels: ["C", "D"],
      colLabels: ["C", "D"],
      payoffs: [
        [[3, 3], [0, 5]],
        [[5, 0], [1, 1]],
      ] as [number, number][][],
    };
    expect(pureNash(g)).toEqual([{ row: 1, col: 1 }]);
  });
  it("duopoly equilibria are symmetric", () => {
    const g = buildDuopolyGame();
    for (const e of pureNash(g)) {
      expect(e.row).toBe(e.col);
    }
  });
});

describe("pricing", () => {
  it("annual discount is explicit", () => {
    expect(annualMonthly(59, 0.2)).toBe(47.2);
    expect(annualTotal(12, 0.2)).toBe(115.2);
  });
});
