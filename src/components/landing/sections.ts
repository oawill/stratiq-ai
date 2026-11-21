/** The five cinematic sections, in scroll order. `accent` is each section's signature colour. */
export const CINE_SECTIONS = [
  { id: "home", label: "Home", accent: "#00E5FF" },
  { id: "sports", label: "Sports", accent: "#00E5FF" },
  { id: "strategy", label: "Strategy", accent: "#8B5CF6" },
  { id: "politics", label: "Politics", accent: "#60A5FA" },
  { id: "markets", label: "Markets", accent: "#34D399" },
] as const;

export type CineSectionId = (typeof CINE_SECTIONS)[number]["id"];

/** Every anchor the landing navigation can mark as active (the five sections plus the trust and pricing sections below them). */
export const NAV_TARGETS = ["home", "sports", "strategy", "politics", "markets", "pricing"] as const;
