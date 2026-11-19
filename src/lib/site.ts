import { Activity, Briefcase, Landmark, LineChart, type LucideIcon } from "lucide-react";
import { brand } from "./brand";

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export interface Domain {
  slug: "sports" | "business" | "politics" | "finance";
  name: string;
  short: string;
  icon: LucideIcon;
  accent: string;
  headline: string;
  description: string;
  features: string[];
  cta: string;
}

export const DOMAINS: Domain[] = [
  {
    slug: "sports",
    name: brand.products.sports.name,
    short: "Sports",
    icon: Activity,
    accent: "#22d3ee",
    headline: "Predict the Game. Understand the Strategy.",
    description:
      "Analyze team performance, match probabilities, tactical decisions, and thousands of possible game scenarios using advanced AI forecasting.",
    features: [
      "Match outcome probabilities",
      "Team and player analytics",
      "Tactical scenario modeling",
      "Historical backtesting",
      "Explainable predictions",
    ],
    cta: `Explore ${brand.products.sports.name}`,
  },
  {
    slug: "business",
    name: brand.products.strategy.name,
    short: "Business",
    icon: Briefcase,
    accent: "#8055f6",
    headline: "Outthink the Competition.",
    description:
      "Use game theory and predictive simulations to understand competitor behavior, evaluate pricing strategies, and make informed business decisions.",
    features: [
      "Competitive pricing simulation",
      "Market entry analysis",
      "Nash equilibrium modeling",
      "Competitor response scenarios",
      "Strategic decision comparisons",
    ],
    cta: `Explore ${brand.products.strategy.name}`,
  },
  {
    slug: "politics",
    name: brand.products.politics.name,
    short: "Politics",
    icon: Landmark,
    accent: "#a78bfa",
    headline: "Understand Political Possibilities.",
    description:
      "Explore electoral uncertainty, coalition formation, policy tradeoffs, and strategic interactions through transparent, nonpartisan scenario modeling.",
    features: [
      "Aggregate election scenarios",
      "Coalition analysis",
      "Policy simulations",
      "Turnout sensitivity",
      "Strategic interaction modeling",
    ],
    cta: `Explore ${brand.products.politics.name}`,
  },
  {
    slug: "finance",
    name: brand.products.markets.name,
    short: "Finance",
    icon: LineChart,
    accent: "#10b981",
    headline: "Navigate Markets with Better Intelligence.",
    description:
      "Explore market uncertainty, portfolio risk, economic scenarios, and strategic financial decisions through quantitative analysis.",
    features: [
      "Market regime analysis",
      "Financial risk simulations",
      "Portfolio stress testing",
      "Macro sensitivity analysis",
      "Scenario comparisons",
    ],
    cta: `Explore ${brand.products.markets.name}`,
  },
];

export const NAV = [
  { label: "Product", href: "/#product" },
  { label: "Intelligence", href: "/#intelligence", dropdown: true },
  { label: "How It Works", href: "/how-it-works" },
  { label: "Performance", href: "/#performance" },
  { label: "Pricing", href: "/pricing" },
  { label: "About", href: "/about" },
] as const;
