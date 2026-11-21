"use client";

import dynamic from "next/dynamic";
import { ButtonLink } from "../ui/primitives";
import { DemoBadge, SectionShell } from "./SectionShell";
import { LazyMount } from "./LazyMount";

const SportsPanel = dynamic(() => import("./SportsPanel"), { ssr: false });

/** Stadium-inspired backdrop: floodlight beams and faint pitch markings. */
function Stadium() {
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_-10%,rgba(0,229,255,0.16),transparent_62%)]" />
      <div className="absolute -top-24 left-[8%] h-[120%] w-40 -rotate-[18deg] bg-gradient-to-b from-ion/20 via-ion/5 to-transparent blur-2xl" />
      <div className="absolute -top-24 right-[8%] h-[120%] w-40 rotate-[18deg] bg-gradient-to-b from-ion/20 via-ion/5 to-transparent blur-2xl" />
      <svg viewBox="0 0 800 300" preserveAspectRatio="xMidYMax slice" className="absolute inset-x-0 bottom-0 h-1/2 w-full opacity-[0.07]">
        <g fill="none" stroke="#fff" strokeWidth="2">
          <rect x="40" y="40" width="720" height="240" />
          <line x1="400" y1="40" x2="400" y2="280" />
          <circle cx="400" cy="160" r="48" />
          <rect x="40" y="95" width="90" height="130" />
          <rect x="670" y="95" width="90" height="130" />
        </g>
      </svg>
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-night to-transparent" />
    </>
  );
}

export function SportsSection() {
  return (
    <SectionShell id="sports" index="02" eyebrow="Sports" accent="#00E5FF" title={<>Predict Beyond the <span className="text-gradient">Score</span></>}
      sub="Match probabilities, expected goals, form and team strength, with the uncertainty shown rather than hidden." background={<Stadium />}>
      <div className="mb-5"><DemoBadge>Fictional teams · simulated demonstration data · not a real prediction</DemoBadge></div>
      <LazyMount className="min-h-[2180px] md:min-h-[1420px] lg:min-h-[925px]"><SportsPanel /></LazyMount>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <ButtonLink href="/dashboard/sports" className="py-3.5">Try Sports Intelligence</ButtonLink>
        <ButtonLink href="/sports" variant="secondary" className="py-3.5">How VELQORIN Sports works</ButtonLink>
        <p className="text-xs text-muted sm:ml-2">Opens the sports prediction application (log in required).</p>
      </div>
    </SectionShell>
  );
}
