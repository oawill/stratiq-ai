"use client";

import dynamic from "next/dynamic";
import { ButtonLink } from "../ui/primitives";
import { DemoBadge, SectionShell } from "./SectionShell";
import { LazyMount } from "./LazyMount";

const PoliticsPanel = dynamic(() => import("./PoliticsPanel"), { ssr: false });

/** A faint contour map behind the section. */
function Contours() {
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_20%_30%,rgba(37,99,235,0.2),transparent_60%)]" />
      <svg viewBox="0 0 800 500" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full opacity-[0.12]">
        <g fill="none" stroke="#60A5FA" strokeWidth="1">
          {Array.from({ length: 9 }, (_, i) => <ellipse key={i} cx="260" cy="230" rx={60 + i * 42} ry={40 + i * 30} transform={`rotate(${-14 + i * 2} 260 230)`} />)}
        </g>
      </svg>
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-night to-transparent" />
    </>
  );
}

export function PoliticsSection() {
  return (
    <SectionShell id="politics-demo" index="03" eyebrow="Politics" accent="#60A5FA" title={<>Understand the Political <span className="text-gradient">Landscape</span></>}
      sub="Election Forecasting & Scenario Intelligence: explore turnout, regional swings and coalitions, with forecasts, hypotheticals and historical facts kept apart. Transparent and nonpartisan." background={<Contours />}>
      <div className="mb-5"><DemoBadge>Fictional country · simulated data · nonpartisan illustration</DemoBadge></div>
      <LazyMount className="min-h-[1960px] md:min-h-[1835px] lg:min-h-[870px]"><PoliticsPanel /></LazyMount>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <ButtonLink href="/dashboard/politics" className="py-3.5">Explore Political Intelligence</ButtonLink>
        <ButtonLink href="/how-it-works" variant="secondary" className="py-3.5">How VELQORIN Politics works</ButtonLink>
        <p className="text-xs text-muted sm:ml-2">Opens the politics application (log in required).</p>
      </div>
    </SectionShell>
  );
}
