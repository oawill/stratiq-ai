/** Single source of truth for the brand. VELQORIN is the brand; velqorin.ai is the website address. */
export const brand = {
  name: "VELQORIN",
  domain: "velqorin.ai",
  website: "https://velqorin.ai",
  tagline: "Intelligence Beyond Prediction",
  secondaryTagline: "Predict. Simulate. Strategize.",
  description: "AI-powered predictive analytics, game theory, and strategic intelligence.",

  /** Homepage copy and search-engine metadata. */
  heroHeadline: "Predict Outcomes. Understand Strategy. Shape Better Decisions.",
  heroDescription:
    "VELQORIN combines artificial intelligence, predictive analytics, game theory, and scenario simulations to help individuals and organizations make better decisions across sports, business, politics, and financial markets.",
  homeTitle: "VELQORIN | AI Prediction & Strategic Intelligence",
  metaDescription:
    "Explore AI-powered sports predictions, business game theory, political scenarios, and financial intelligence with VELQORIN.",

  /** Dark theme colors, also used for the manifest and generated icons. */
  colors: { background: "#080D1B", surface: "#111A2E", violet: "#8055F6", cyan: "#22D3EE" },

  /** Product names. Routes (/sports, /dashboard/business, ...) are unchanged. */
  products: {
    sports: { name: "VELQORIN Sports", function: "Sports predictions and analytics" },
    strategy: { name: "VELQORIN Strategy", function: "Business strategy and game theory" },
    politics: { name: "VELQORIN Politics", function: "Political scenario intelligence" },
    markets: { name: "VELQORIN Markets", function: "Financial market and risk intelligence" },
    simlab: { name: "VELQORIN SimLab", function: "Strategic simulation engine" },
  },
} as const;

export type ProductKey = keyof typeof brand.products;
