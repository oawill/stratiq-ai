"use client";

import dynamic from "next/dynamic";
import { ButtonLink } from "../ui/primitives";
import { DemoBadge, SectionShell } from "./SectionShell";
import { LazyMount } from "./LazyMount";

const StrategyPanel = dynamic(() => import("./StrategyPanel"), { ssr: false });

/** Chess-inspired backdrop: a fading board and a single oversized piece. */
function Board() {
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_80%_20%,rgba(139,92,246,0.2),transparent_60%)]" />
      <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "repeating-conic-gradient(#8B5CF6 0% 25%, transparent 0% 50%)", backgroundSize: "88px 88px", maskImage: "radial-gradient(ellipse at 75% 35%, black, transparent 68%)", WebkitMaskImage: "radial-gradient(ellipse at 75% 35%, black, transparent 68%)" }} />
      <span className="absolute -right-6 top-10 select-none text-[22rem] leading-none text-royal/[0.06]">♞</span>
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-night to-transparent" />
    </>
  );
}

export function StrategySection() {
  return (
    <SectionShell id="strategy-demo" index="02" eyebrow="Strategy" accent="#8B5CF6" title={<>Think Several <span className="text-gradient">Moves Ahead</span></>}
      sub="Game Theory for Real-World Decisions: model how a competitor responds before you commit, and see where each side has no reason to move." background={<Board />}>
      <div className="mb-5"><DemoBadge>Illustrative assumptions · not a forecast of any real market</DemoBadge></div>
      <LazyMount className="min-h-[1810px] md:min-h-[1455px] lg:min-h-[910px]"><StrategyPanel /></LazyMount>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <ButtonLink href="/dashboard/business" className="py-3.5">Explore Strategy Simulator</ButtonLink>
        <ButtonLink href="/how-it-works" variant="secondary" className="py-3.5">How VELQORIN Strategy works</ButtonLink>
        <p className="text-xs text-muted sm:ml-2">Opens the strategy application (log in required).</p>
      </div>
    </SectionShell>
  );
}
