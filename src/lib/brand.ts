/** Single source of truth for the product's name, taglines and product names. Import this instead of typing the brand. */
export const brand = {
  name: "VELQORIN.ai",
  shortName: "VELQORIN",
  tagline: "Intelligence Beyond Prediction",
  secondaryTagline: "Predict. Simulate. Strategize.",
  heroHeadline: "Predict Outcomes. Understand Strategy. Shape Better Decisions.",
  /** Intended production domain. Not configured anywhere until ownership and DNS are confirmed. */
  domain: "velqorin.ai",
  description:
    "VELQORIN.ai is an AI-powered predictive analytics and strategic intelligence platform combining machine learning, probability modeling, game theory, and scenario simulations across sports, business, politics, and financial markets.",
  shortDescription:
    "AI-powered predictive analytics and strategic intelligence across sports, business, politics, and financial markets.",
  /** Dark theme colors, also used for the manifest and generated icons. */
  colors: { background: "#080D1B", surface: "#111A2E", violet: "#8055F6", cyan: "#22D3EE" },
  /** Product names. Routes (/sports, /dashboard/business, ...) are unchanged. */
  products: {
    sports: { name: "VELQORIN Sports", function: "Sports predictions and analytics" },
    strategy: { name: "VELQORIN Strategy", function: "Business game theory and competitive intelligence" },
    politics: { name: "VELQORIN Politics", function: "Political and coalition scenario analysis" },
    markets: { name: "VELQORIN Markets", function: "Financial market and risk intelligence" },
    simlab: { name: "VELQORIN SimLab", function: "Cross-domain strategic simulations" },
  },
} as const;

export type ProductKey = keyof typeof brand.products;
