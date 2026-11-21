# Home page: one carousel, then the demonstrations

The home page (`/`) is a single page. A full-screen carousel presents the four intelligence capabilities as slides; below it the same page continues with an interactive demonstration for each capability, then the trust and conversion sections. It is an enhancement: every route, API, model, sign-in and billing flow is unchanged.

## The carousel

| Slide | URL hash | Copy comes from |
|---|---|---|
| 1 Sports Intelligence | `#sports` | `DOMAINS` in `src/lib/site.ts` |
| 2 Business Strategy | `#business` | same |
| 3 Political Intelligence | `#politics` | same |
| 4 Financial Intelligence | `#finance` | same |

Each slide has its own CSS-only cinematic background, headline, supporting text, three capability chips, an animated SVG illustration (labelled "Illustration only · not real data"), a call to action that jumps to the matching demonstration further down the same page, and a "Get Started" link.

**Controls**

- Mouse wheel / trackpad: one deliberate gesture moves one slide. Wheel events are ignored while a transition runs (900 ms lock) and while the decaying tail of a trackpad's momentum arrives, so a flick cannot skip slides.
- After the last slide, a downward wheel scrolls the page normally. Scrolling back to the very top and wheeling up returns to slide 4. The carousel only owns the wheel when the page is at the top.
- Touch: a horizontal swipe changes slide; vertical movement scrolls the page (`touch-action: pan-y`).
- Previous / next buttons, pagination dots (with accessible names) and a progress bar (`role="progressbar"`).
- Left / Right arrow keys while the carousel is on screen (ignored in form fields and with modifier keys).
- Links such as `/#business` choose a slide on arrival and later (header menu, browser back). The slide changes the address with `history.replaceState`, so no page loads and no history entries pile up.
- Transitions are 750 ms. Reduced motion: slide changes are instant, entry animations and illustrations are shown finished, and the transition bands are still.
- Accessibility: `aria-roledescription="carousel"`/`"slide"`, inactive slides are `inert` and `aria-hidden`, a polite live region announces the slide, a visually hidden `<h1>` names the page.

**Header** (one only): VELQORIN | Platform | Solutions | How It Works | Pricing | Get Started. Platform, How It Works and Pricing scroll to the section on the page; Solutions opens a menu of the four slides; Get Started goes to `/signup`. On phones the same items are in one menu.

## Where things live

| Path | What |
|---|---|
| `src/components/carousel/slides.ts` | Slide data (merged from `DOMAINS` plus per-slide style, background, demo link). Edit this to change the slides. |
| `src/components/carousel/HeroCarousel.tsx` | The carousel component and its wiring (wheel, keys, touch, hash). |
| `src/components/carousel/input.ts` | Pure input rules (wheel lock and momentum handling, swipe, clamping) with unit tests in `input.test.ts`. |
| `src/components/carousel/CarouselVisuals.tsx` | The four animated SVG illustrations. |
| `src/components/landing/LandingNavigation.tsx` | The header. |
| `src/app/(landing)/` | Layout (`.cine` theme, header, footer) and the page. |

## Demonstrations below the carousel

Sports (`#sports-demo`), Strategy (`#strategy-demo`), Politics (`#politics-demo`) and Markets (`#markets-demo`) are unchanged from the previous version: interactive, deterministic, clearly labelled as fictional or simulated, and tested (`src/lib/landing/landing.test.ts`). Then: workflow strip, How it works (`#how`), capabilities (`#intelligence`), methodology and performance disclosures (`#performance`), pricing (`#pricing`) and early access (`#early-access`).

## Honesty rules

- Carousel illustrations show no figures and are labelled as illustrations. Demonstrations use fictional teams, parties, regions and prices and say so.
- No live fixtures, results, market data or model performance are shown or implied. Markets text says "scenarios, not predictions or guaranteed returns".

## Design system

The cinematic palette applies only inside `.cine` (`src/app/globals.css`): `#030B1C`, `#07152B`, cyan `#00E5FF`, blue `#2563EB`, violet `#8B5CF6`, text `#F8FAFC`, muted `#94A3B8`. Button fills use violet-600 so white text meets 4.5:1. Brand is written **VELQORIN**; velqorin.ai is the web address.

## Tests

- `npm run test` (vitest): 58 tests, including the carousel input rules (rapid wheel = one slide, momentum tail ignored, pass-through after the last slide, swipe direction) and the slide list.
- e2e `unified landing page...`: one header, buttons/dots/keys/progress, wheel (six quick notches = one slide; page scrolls after the last slide and the carousel returns when scrolling back to the top), Solutions menu and hash links without a reload (a marker on `window` survives), slide CTA to demo, all four demonstrations, trust/pricing sections, phone (swipe, menu, no sideways scroll) and reduced motion.

## Not done, and recommendations

- The separate `/sports`, `/business`, `/politics` and `/finance` pages from the earlier site still exist (the footer links to them). If "one landing page" should mean these go away, redirect them to `/#sports` and so on and update the footer and sitemap.
- Swipe is tested by dispatching touch events, not on a physical phone. Check a real device (iOS Safari especially) after deploying.
- The older home-page pieces (`sections/Hero.tsx`, `sections/Demo.tsx`, `demo/*`, `DashboardMock.tsx`, `ParticleField.tsx`) are unused; delete when convenient.
- Lighthouse was measured on the previous scroll layout (100/100/96/100); it has not been re-run for the carousel.
