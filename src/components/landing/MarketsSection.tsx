"use client";

import dynamic from "next/dynamic";
import { ButtonLink } from "../ui/primitives";
import { DemoBadge, SectionShell } from "./SectionShell";
import { LazyMount } from "./LazyMount";

const MarketsPanel = dynamic(() => import("./MarketsPanel"), { ssr: false });

/** A faint chart grid and trace behind the section. */
function Terminal() {
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_85%_15%,rgba(52,211,153,0.15),transparent_60%)]" />
      <div className="grid-bg absolute inset-0 opacity-70" />
      <svg viewBox="0 0 800 300" preserveAspectRatio="none" className="absolute inset-x-0 top-24 h-72 w-full opacity-[0.1]">
        <polyline fill="none" stroke="#34D399" strokeWidth="2" points="0,220 60,200 120,230 180,170 240,185 300,120 360,150 420,90 480,130 540,70 600,100 660,40 720,75 800,30" />
      </svg>
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-night to-transparent" />
    </>
  );
}

export function MarketsSection() {
  return (
    <SectionShell id="markets" index="05" eyebrow="Markets" accent="#34D399" title={<>Navigate <span className="text-gradient">Uncertainty</span></>}
      sub="Market Forecasting & Risk Intelligence: see the range of outcomes under explicit assumptions, not a single number promised as a return." background={<Terminal />}>
      <div className="mb-5"><DemoBadge>Simulated prices and assumptions · not market data · not investment advice</DemoBadge></div>
      <LazyMount className="min-h-[1500px] lg:min-h-[880px]"><MarketsPanel /></LazyMount>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <ButtonLink href="/dashboard/finance" className="py-3.5">Explore Market Intelligence</ButtonLink>
        <ButtonLink href="/finance" variant="secondary" className="py-3.5">How VELQORIN Markets works</ButtonLink>
        <p className="text-xs text-muted sm:ml-2">Opens the markets application (log in required). Not investment advice.</p>
      </div>
    </SectionShell>
  );
}
