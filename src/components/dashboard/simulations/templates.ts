import type { DistType } from "@/lib/types";

export const DOMAINS = [
  ["general", "General"],
  ["business", "Business"],
  ["finance", "Finance"],
  ["politics", "Politics"],
  ["sports", "Sports"],
] as const;
export type DomainId = (typeof DOMAINS)[number][0];

export const DIST_FIELDS: Record<DistType, { label: string; fields: { key: string; label: string }[]; defaults: Record<string, string>; help: string }> = {
  normal: { label: "Normal", fields: [{ key: "mean", label: "Mean" }, { key: "sd", label: "Std dev" }], defaults: { mean: "0", sd: "1" }, help: "Bell curve; can go negative." },
  lognormal: { label: "Lognormal", fields: [{ key: "mean", label: "Mean" }, { key: "sd", label: "Std dev" }], defaults: { mean: "10", sd: "3" }, help: "Positive, right-skewed. Mean and sd are of the variable itself." },
  uniform: { label: "Uniform", fields: [{ key: "low", label: "Low" }, { key: "high", label: "High" }], defaults: { low: "0", high: "1" }, help: "Every value between low and high equally likely." },
  triangular: { label: "Triangular", fields: [{ key: "low", label: "Low" }, { key: "mode", label: "Most likely" }, { key: "high", label: "High" }], defaults: { low: "0", mode: "1", high: "3" }, help: "Min / most likely / max estimate." },
  beta: { label: "Beta", fields: [{ key: "alpha", label: "Alpha" }, { key: "beta", label: "Beta" }], defaults: { alpha: "2", beta: "2" }, help: "A proportion between 0 and 1." },
  bernoulli: { label: "Yes/No (Bernoulli)", fields: [{ key: "p", label: "P(1)" }], defaults: { p: "0.5" }, help: "1 with probability p, else 0." },
  binomial: { label: "Binomial", fields: [{ key: "n", label: "Trials (n)" }, { key: "p", label: "P(success)" }], defaults: { n: "10", p: "0.5" }, help: "Number of successes in n trials." },
  poisson: { label: "Poisson", fields: [{ key: "lambda", label: "Rate (λ ≤ 50)" }], defaults: { lambda: "4" }, help: "Count of events at average rate λ." },
  constant: { label: "Constant", fields: [{ key: "value", label: "Value" }], defaults: { value: "1" }, help: "A fixed assumption." },
  discrete: { label: "Discrete", fields: [{ key: "values", label: "value:prob, value:prob" }], defaults: { values: "0:0.5, 1:0.5" }, help: "A few values with probabilities summing to 1." },
};

export interface TemplateVar { name: string; type: DistType; params: Record<string, string> }
export interface SimTemplate {
  id: string;
  domain: DomainId;
  name: string;
  blurb: string;
  vars: TemplateVar[];
  outs: { name: string; expr: string; threshold: string }[];
}

// Illustrative scenarios. Every number is an assumption made up for teaching, not data.
export const TEMPLATES: SimTemplate[] = [
  {
    id: "project", domain: "general", name: "Project duration (three tasks)",
    blurb: "Total time when each stage has an optimistic / likely / pessimistic estimate.",
    vars: [
      { name: "design", type: "triangular", params: { low: "5", mode: "8", high: "14" } },
      { name: "build", type: "triangular", params: { low: "10", mode: "15", high: "30" } },
      { name: "test", type: "triangular", params: { low: "3", mode: "5", high: "10" } },
    ],
    outs: [{ name: "total_days", expr: "design + build + test", threshold: "30" }],
  },
  {
    id: "launch", domain: "business", name: "Product launch profit",
    blurb: "Profit under uncertain demand, price and unit cost.",
    vars: [
      { name: "units", type: "normal", params: { mean: "10000", sd: "2500" } },
      { name: "price", type: "triangular", params: { low: "18", mode: "20", high: "24" } },
      { name: "unit_cost", type: "uniform", params: { low: "9", high: "12" } },
      { name: "fixed", type: "constant", params: { value: "60000" } },
    ],
    outs: [{ name: "profit", expr: "max(units, 0) * (price - unit_cost) - fixed", threshold: "0" }],
  },
  {
    id: "portfolio", domain: "finance", name: "One-year real portfolio value",
    blurb: "Scenario analysis of a lump sum after a year of uncertain returns and inflation. Not investment advice.",
    vars: [
      { name: "initial", type: "constant", params: { value: "100000" } },
      { name: "annual_return", type: "normal", params: { mean: "0.06", sd: "0.15" } },
      { name: "inflation", type: "triangular", params: { low: "0.01", mode: "0.025", high: "0.06" } },
    ],
    outs: [{ name: "real_value", expr: "initial * (1 + annual_return) / (1 + inflation)", threshold: "100000" }],
  },
  {
    id: "seats", domain: "politics", name: "Seat share under uncertainty (scenario)",
    blurb: "A scenario assumption about how vote share converts to seats, not an election forecast.",
    vars: [
      { name: "vote_share", type: "normal", params: { mean: "0.48", sd: "0.03" } },
      { name: "amplification", type: "uniform", params: { low: "8", high: "14" } },
    ],
    outs: [{ name: "seat_share", expr: "1 / (1 + exp(-amplification * (vote_share - 0.5)))", threshold: "0.5" }],
  },
  {
    id: "season", domain: "sports", name: "Season points over 10 matches",
    blurb: "Points from a win probability per match and an uncertain draw rate.",
    vars: [
      { name: "wins", type: "binomial", params: { n: "10", p: "0.45" } },
      { name: "draw_rate", type: "uniform", params: { low: "0", high: "0.4" } },
    ],
    outs: [{ name: "points", expr: "3 * wins + floor((10 - wins) * draw_rate)", threshold: "15" }],
  },
];
