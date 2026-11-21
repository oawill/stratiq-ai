import { DOMAINS, type Domain } from "../../lib/site";

export type SlideVisual = "sports" | "business" | "politics" | "finance";

export interface CarouselSlide {
  /** Also the URL hash and the element id of the slide (for example `/#business`). */
  id: Domain["slug"];
  /** Short label used by the header menu, the pagination and screen readers. */
  label: string;
  eyebrow: string;
  headline: string;
  text: string;
  points: string[];
  accent: string;
  visual: SlideVisual;
  /** The interactive demonstration further down the same page. */
  demoHref: string;
  demoLabel: string;
  /** Cinematic background, one per slide (CSS only: nothing to download). */
  background: string;
}

const NIGHT = "#030b1c";

/** Presentation settings per domain. Names, headlines, descriptions and feature lists come from DOMAINS so there is one source of copy. */
const STYLE: Record<Domain["slug"], Pick<CarouselSlide, "label" | "eyebrow" | "accent" | "visual" | "demoLabel" | "background">> = {
  sports: {
    label: "Sports Intelligence",
    eyebrow: "Sports Intelligence",
    accent: "#00e5ff",
    visual: "sports",
    demoLabel: "Try the match demo",
    background: `radial-gradient(60% 70% at 78% 42%, rgba(0,229,255,0.20), transparent 70%), repeating-linear-gradient(90deg, rgba(0,229,255,0.045) 0 64px, transparent 64px 128px), linear-gradient(180deg, #04162a, ${NIGHT})`,
  },
  business: {
    label: "Business Strategy",
    eyebrow: "Business Strategy",
    accent: "#8b5cf6",
    visual: "business",
    demoLabel: "Try the pricing game",
    background: `radial-gradient(55% 65% at 76% 45%, rgba(139,92,246,0.26), transparent 70%), linear-gradient(rgba(139,92,246,0.07) 1px, transparent 1px) 0 0/56px 56px, linear-gradient(90deg, rgba(139,92,246,0.07) 1px, transparent 1px) 0 0/56px 56px, linear-gradient(180deg, #0b0f2e, ${NIGHT})`,
  },
  politics: {
    label: "Political Intelligence",
    eyebrow: "Political Intelligence",
    accent: "#60a5fa",
    visual: "politics",
    demoLabel: "Try the election demo",
    background: `radial-gradient(60% 70% at 74% 44%, rgba(37,99,235,0.28), transparent 70%), radial-gradient(rgba(96,165,250,0.18) 1.2px, transparent 1.4px) 0 0/28px 28px, linear-gradient(180deg, #061431, ${NIGHT})`,
  },
  finance: {
    label: "Financial Intelligence",
    eyebrow: "Financial Intelligence",
    accent: "#34d399",
    visual: "finance",
    demoLabel: "Try the risk demo",
    background: `radial-gradient(60% 70% at 78% 40%, rgba(52,211,153,0.18), transparent 70%), repeating-linear-gradient(0deg, rgba(52,211,153,0.06) 0 1px, transparent 1px 48px), linear-gradient(180deg, #041a1c, ${NIGHT})`,
  },
};

/** The interactive demonstrations below the carousel use these ids. */
export const DEMO_IDS: Record<Domain["slug"], string> = {
  sports: "sports-demo",
  business: "strategy-demo",
  politics: "politics-demo",
  finance: "markets-demo",
};

/** The slides, in order. Edit STYLE or DOMAINS to change them; the carousel itself is driven entirely by this list. */
export const SLIDES: CarouselSlide[] = DOMAINS.map((d) => ({
  id: d.slug,
  headline: d.headline,
  text: d.description,
  points: d.features.slice(0, 3),
  demoHref: `#${DEMO_IDS[d.slug]}`,
  ...STYLE[d.slug],
}));

export function slideIndexFromHash(hash: string): number {
  const id = hash.replace(/^#/, "");
  return SLIDES.findIndex((s) => s.id === id);
}
