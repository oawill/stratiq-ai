"use client";

import { useRef, type ReactNode } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

export type TransitionKind = "home-sports" | "sports-strategy" | "strategy-politics" | "politics-markets";

// Each motif is drawn in a 1200 x 140 box. Only SVG: no canvas, no images, nothing to download.
const dots = (n: number) => Array.from({ length: n }, (_, i) => ({ x: 60 + i * (1080 / (n - 1)), y: 70 + Math.sin(i * 1.7) * 38 }));

function Network({ c }: { c: string }) {
  const p = dots(15);
  return (
    <g stroke={c} fill={c}>
      {p.map((a, i) => p.slice(i + 1, i + 3).map((b, j) => <line key={`${i}${j}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeOpacity="0.5" strokeWidth="1" />))}
      {p.map((a, i) => <circle key={i} cx={a.x} cy={a.y} r="3.2" stroke="none" />)}
    </g>
  );
}
function Pitch({ c }: { c: string }) {
  return (
    <g stroke={c} fill="none" strokeWidth="1.4" strokeOpacity="0.8">
      <line x1="30" y1="70" x2="1170" y2="70" /><line x1="600" y1="14" x2="600" y2="126" />
      <circle cx="600" cy="70" r="34" /><rect x="30" y="26" width="150" height="88" /><rect x="30" y="48" width="56" height="44" />
      <rect x="1020" y="26" width="150" height="88" /><rect x="1114" y="48" width="56" height="44" />
    </g>
  );
}
function Grid({ c }: { c: string }) {
  return (
    <g stroke={c} strokeOpacity="0.55" strokeWidth="1">
      {Array.from({ length: 21 }, (_, i) => <line key={`v${i}`} x1={i * 60} y1="0" x2={i * 60} y2="140" />)}
      {Array.from({ length: 5 }, (_, i) => <line key={`h${i}`} x1="0" y1={i * 35} x2="1200" y2={i * 35} />)}
    </g>
  );
}
function Board({ c }: { c: string }) {
  return (
    <g fill={c}>
      {Array.from({ length: 2 }, (_, r) => Array.from({ length: 18 }, (_, k) => (r + k) % 2 === 0 ? <rect key={`${r}${k}`} x={60 + k * 60} y={r * 70} width="60" height="70" opacity="0.28" /> : null))}
    </g>
  );
}
function Tree({ c }: { c: string }) {
  const kids = [28, 70, 112];
  return (
    <g stroke={c} fill="none" strokeWidth="1.3" strokeOpacity="0.75">
      {kids.map((y) => <path key={y} d={`M160 70 C 260 70, 300 ${y}, 420 ${y}`} />)}
      {kids.flatMap((y) => [-18, 18].map((d) => <path key={`${y}${d}`} d={`M430 ${y} C 520 ${y}, 560 ${y + d}, 660 ${y + d}`} />))}
      <circle cx="150" cy="70" r="10" fill={c} fillOpacity="0.4" />
      {kids.map((y) => <circle key={`n${y}`} cx="428" cy={y} r="6" fill={c} fillOpacity="0.5" />)}
    </g>
  );
}
function MapShapes({ c }: { c: string }) {
  return (
    <g stroke={c} fill={c} fillOpacity="0.14" strokeOpacity="0.8" strokeWidth="1.3" strokeLinejoin="round">
      <path d="M180 30 L330 16 L430 44 L400 100 L270 112 L170 96 Z" />
      <path d="M430 44 L560 30 L620 82 L560 124 L420 110 L400 100 Z" />
      <path d="M620 82 L760 40 L860 70 L820 120 L690 126 L560 124 Z" />
      <path d="M860 70 L980 34 L1060 78 L1010 118 L900 118 L820 120 Z" />
    </g>
  );
}
function Chart({ c }: { c: string }) {
  const pts = Array.from({ length: 26 }, (_, i) => [60 + i * 44, 110 - i * 2.4 - Math.sin(i * 0.9) * 16 - (i > 12 ? Math.sin(i * 2.1) * 8 : 0)]);
  return (
    <g stroke={c} fill="none" strokeWidth="1.4">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} strokeOpacity="0.85" />
      {pts.filter((_, i) => i % 2 === 0).map(([x, y], i) => <g key={i}><line x1={x} x2={x} y1={y - 12} y2={y + 12} strokeOpacity="0.5" /><rect x={x - 5} y={y - 6} width="10" height="12" fill={c} fillOpacity={i % 3 ? 0.35 : 0.05} /></g>)}
    </g>
  );
}

const PAIRS: Record<TransitionKind, { from: [ReactNode, string]; to: [ReactNode, string]; label: string }> = {
  "home-sports": { from: [<Network key="a" c="#60A5FA" />, "#60A5FA"], to: [<Pitch key="b" c="#00E5FF" />, "#00E5FF"], label: "The network resolves into a football pitch" },
  "sports-strategy": { from: [<Grid key="a" c="#00E5FF" />, "#00E5FF"], to: [<Board key="b" c="#8B5CF6" />, "#8B5CF6"], label: "The analytical grid becomes a strategy board" },
  "strategy-politics": { from: [<Tree key="a" c="#8B5CF6" />, "#8B5CF6"], to: [<MapShapes key="b" c="#60A5FA" />, "#60A5FA"], label: "The decision tree becomes an electoral map" },
  "politics-markets": { from: [<MapShapes key="a" c="#60A5FA" />, "#60A5FA"], to: [<Chart key="b" c="#34D399" />, "#34D399"], label: "The map becomes a financial chart" },
};

/**
 * A decorative band between two sections. As it scrolls through the viewport the visual motif of the section above fades out and
 * rises away while the motif of the section below fades in. With reduced motion both are shown still. Purely decorative (aria-hidden).
 */
export function SectionTransition({ kind }: { kind: TransitionKind }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = usePrefersReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const p = useTransform(scrollYProgress, [0.3, 0.7], [0, 1]);
  const fromOpacity = useTransform(p, [0, 1], [1, 0]);
  const toOpacity = useTransform(p, [0, 1], [0, 1]);
  const fromY = useTransform(p, [0, 1], [0, -22]);
  const toY = useTransform(p, [0, 1], [22, 0]);
  const pair = PAIRS[kind];
  return (
    <div ref={ref} aria-hidden="true" data-transition={kind} className="pointer-events-none relative -my-px h-24 overflow-hidden sm:h-32" style={{ background: `linear-gradient(180deg, ${pair.from[1]}10, ${pair.to[1]}10)` }}>
      <motion.svg viewBox="0 0 1200 140" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" style={reduce ? { opacity: 0.5 } : { opacity: fromOpacity, y: fromY }}>{pair.from[0]}</motion.svg>
      <motion.svg viewBox="0 0 1200 140" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" style={reduce ? { opacity: 0.5 } : { opacity: toOpacity, y: toY }}>{pair.to[0]}</motion.svg>
      <div className="absolute inset-0 bg-gradient-to-b from-night via-transparent to-night" />
    </div>
  );
}
