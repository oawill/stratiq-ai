/** Independent-Poisson football model. Pure math, no network, no AI. */
export function poissonPmf(k: number, lambda: number): number {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  let logP = -lambda + k * Math.log(lambda);
  for (let i = 2; i <= k; i++) logP -= Math.log(i);
  return Math.exp(logP);
}

export interface MatchProbabilities {
  home: number;
  draw: number;
  away: number;
  /** Probability grid [homeGoals][awayGoals], truncated at maxGoals. */
  grid: number[][];
  mostLikely: { home: number; away: number; p: number };
  covered: number;
}

export function matchProbabilities(
  homeXg: number,
  awayXg: number,
  maxGoals = 10,
): MatchProbabilities {
  const grid: number[][] = [];
  let home = 0;
  let draw = 0;
  let away = 0;
  let covered = 0;
  let best = { home: 0, away: 0, p: -1 };
  for (let h = 0; h <= maxGoals; h++) {
    const row: number[] = [];
    for (let a = 0; a <= maxGoals; a++) {
      const p = poissonPmf(h, homeXg) * poissonPmf(a, awayXg);
      row.push(p);
      covered += p;
      if (h > a) home += p;
      else if (h === a) draw += p;
      else away += p;
      if (p > best.p) best = { home: h, away: a, p };
    }
    grid.push(row);
  }
  // Renormalise the truncated tail so the three outcomes sum to 1.
  return {
    home: home / covered,
    draw: draw / covered,
    away: away / covered,
    grid,
    mostLikely: best,
    covered,
  };
}
