"use client";

import { motion } from "framer-motion";
import type { SlideVisual } from "./slides";

/**
 * One light animated SVG per slide. They are illustrations of the kind of output each module produces, not data: no figures are shown.
 * Animation plays when the slide becomes active and is skipped (shown finished) when the visitor prefers reduced motion.
 */
interface VisualProps {
  accent: string;
  active: boolean;
  reduce: boolean;
}

const ease = [0.22, 1, 0.36, 1] as const;

/** Draws a stroke in when active. */
function Draw({ d, active, reduce, delay = 0, ...rest }: { d: string; active: boolean; reduce: boolean; delay?: number } & React.ComponentProps<"path">) {
  return (
    <motion.path
      d={d}
      initial={false}
      animate={{ pathLength: active || reduce ? 1 : 0, opacity: active || reduce ? 1 : 0 }}
      transition={{ duration: reduce ? 0 : 1.2, delay: active && !reduce ? delay : 0, ease }}
      {...(rest as object)}
    />
  );
}

function Sports({ accent, active, reduce }: VisualProps) {
  const bars = [0.52, 0.24, 0.24];
  return (
    <>
      <g fill="none" stroke={accent} strokeWidth="1.5" strokeOpacity="0.7">
        <Draw d="M40 40 H440 V230 H40 Z" active={active} reduce={reduce} />
        <Draw d="M240 40 V230" active={active} reduce={reduce} delay={0.2} />
        <circle cx="240" cy="135" r="34" strokeDasharray="4 5" />
        <Draw d="M40 85 H100 V185 H40" active={active} reduce={reduce} delay={0.3} />
        <Draw d="M440 85 H380 V185 H440" active={active} reduce={reduce} delay={0.3} />
      </g>
      <Draw d="M70 190 C 150 70, 230 210, 300 110 S 400 90, 420 130" active={active} reduce={reduce} delay={0.5} fill="none" stroke="#f8fafc" strokeWidth="2" strokeDasharray="2 7" strokeLinecap="round" />
      {active && !reduce && (
        <circle r="6" fill={accent}>
          <animateMotion dur="5s" repeatCount="indefinite" path="M70 190 C 150 70, 230 210, 300 110 S 400 90, 420 130" />
        </circle>
      )}
      <g>
        {bars.map((w, i) => (
          <motion.rect key={i} x="40" y={262 + i * 22} height="10" rx="5" fill={accent} fillOpacity={i === 0 ? 0.9 : 0.4 - i * 0.1} initial={false} animate={{ width: active || reduce ? w * 400 : 0 }} transition={{ duration: reduce ? 0 : 1, delay: reduce ? 0 : 0.7 + i * 0.12, ease }} />
        ))}
      </g>
    </>
  );
}

function Business({ accent, active, reduce }: VisualProps) {
  const cells = Array.from({ length: 9 }, (_, i) => ({ x: 190 + (i % 3) * 82, y: 50 + Math.floor(i / 3) * 70, hot: i === 4 }));
  return (
    <>
      <g fill="none" stroke={accent} strokeWidth="1.4" strokeOpacity="0.75">
        <Draw d="M30 150 C 90 150, 110 85, 170 85" active={active} reduce={reduce} />
        <Draw d="M30 150 C 90 150, 110 150, 170 150" active={active} reduce={reduce} delay={0.1} />
        <Draw d="M30 150 C 90 150, 110 215, 170 215" active={active} reduce={reduce} delay={0.2} />
        <circle cx="30" cy="150" r="8" fill={accent} fillOpacity="0.5" />
      </g>
      {cells.map((c, i) => (
        <motion.rect
          key={i}
          x={c.x}
          y={c.y}
          width="72"
          height="60"
          rx="10"
          fill={accent}
          stroke={accent}
          initial={false}
          animate={{ fillOpacity: active || reduce ? (c.hot ? [0.45, 0.8, 0.45] : [0.1, 0.22, 0.1]) : 0, strokeOpacity: active || reduce ? (c.hot ? 1 : 0.4) : 0 }}
          transition={{ duration: reduce ? 0 : 2.6, repeat: active && !reduce ? Infinity : 0, delay: reduce ? 0 : (i % 3) * 0.2 + Math.floor(i / 3) * 0.15, ease: "easeInOut" }}
        />
      ))}
      <text x="226" y="285" fill="#94a3b8" fontSize="12" textAnchor="middle">Payoff matrix · equilibrium highlighted</text>
    </>
  );
}

function Politics({ accent, active, reduce }: VisualProps) {
  // A hemicycle of seats. Seats are coloured by position only to show how coalitions form; there are no real parties or results.
  const seats: { x: number; y: number; k: number }[] = [];
  const rows = [5, 6, 7, 8, 9];
  let n = 0;
  rows.forEach((count, r) => {
    const rad = 70 + r * 28;
    for (let i = 0; i < count * 3; i++) {
      const a = Math.PI - (i / (count * 3 - 1)) * Math.PI;
      seats.push({ x: Math.round((240 + Math.cos(a) * rad) * 10) / 10, y: Math.round((230 - Math.sin(a) * rad) * 10) / 10, k: n++ }); // rounded: server and browser trig differ in the last digits
    }
  });
  const palette = [accent, "#a78bfa", "#94a3b8"];
  const total = seats.length;
  return (
    <>
      {seats.map((s, i) => {
        const frac = (i % 40) / 40;
        const colour = palette[frac < 0.42 ? 0 : frac < 0.75 ? 1 : 2];
        return (
          <motion.circle key={s.k} cx={s.x} cy={s.y} r="5" fill={colour} initial={false} animate={{ opacity: active || reduce ? 0.9 : 0, scale: active || reduce ? 1 : 0.4 }} transition={{ duration: reduce ? 0 : 0.5, delay: reduce ? 0 : (i / total) * 1.1 }} style={{ transformOrigin: `${s.x}px ${s.y}px` }} />
        );
      })}
      <text x="240" y="262" fill="#94a3b8" fontSize="12" textAnchor="middle">Seat scenarios · coalition thresholds</text>
    </>
  );
}

function Finance({ accent, active, reduce }: VisualProps) {
  const line = "M30 210 C 80 190, 110 215, 150 170 S 220 150, 260 120 S 330 135, 370 95";
  return (
    <>
      <g stroke="#94a3b8" strokeOpacity="0.2">
        {[60, 110, 160, 210, 260].map((y) => <line key={y} x1="30" x2="450" y1={y} y2={y} />)}
      </g>
      <motion.path d="M370 95 L450 40 L450 190 L370 120 Z" fill={accent} initial={false} animate={{ fillOpacity: active || reduce ? 0.18 : 0 }} transition={{ duration: reduce ? 0 : 1, delay: reduce ? 0 : 1.1 }} />
      <Draw d={line} active={active} reduce={reduce} fill="none" stroke={accent} strokeWidth="2.5" strokeLinecap="round" />
      <Draw d="M370 95 L450 65" active={active} reduce={reduce} delay={1.1} fill="none" stroke={accent} strokeWidth="1.5" strokeDasharray="5 5" />
      <Draw d="M370 95 L450 150" active={active} reduce={reduce} delay={1.1} fill="none" stroke={accent} strokeWidth="1.5" strokeDasharray="5 5" />
      <text x="240" y="285" fill="#94a3b8" fontSize="12" textAnchor="middle">Scenario range widens with the horizon</text>
    </>
  );
}

const VISUALS: Record<SlideVisual, (p: VisualProps) => React.JSX.Element> = { sports: Sports, business: Business, politics: Politics, finance: Finance };

export function CarouselVisual({ kind, accent, active, reduce }: VisualProps & { kind: SlideVisual }) {
  const V = VISUALS[kind];
  return (
    <figure className="m-0 w-full">
      <svg viewBox="0 0 480 300" role="img" aria-label={`Illustration of ${kind} analysis. Not real data.`} className="h-auto w-full max-h-[34svh] lg:max-h-[52svh]" style={{ filter: `drop-shadow(0 0 28px ${accent}33)` }}>
        <V accent={accent} active={active} reduce={reduce} />
      </svg>
      <figcaption className="mt-2 text-center text-[11px] text-muted">Illustration only · not real data</figcaption>
    </figure>
  );
}
