/**
 * A football pitch (105 x 68) with an attacking-intensity heatmap. The team attacks left to right. The intensity is ILLUSTRATIVE,
 * generated from a demonstration attack rating, and is not tracking data.
 */
export function FootballPitch({ heat, colour, label }: { heat: number[][]; colour: string; label: string }) {
  const rows = heat.length;
  const cols = heat[0].length;
  const max = Math.max(...heat.flat());
  const cw = 105 / cols;
  const ch = 68 / rows;
  const line = { stroke: "rgba(248,250,252,0.55)", strokeWidth: 0.35, fill: "none" } as const;
  return (
    <svg viewBox="0 0 105 68" role="img" aria-label={`${label}. Illustrative attacking intensity, strongest near the opposition goal. Not tracking data.`} className="h-auto w-full rounded-xl">
      <defs>
        <linearGradient id="pitch-turf" x1="0" x2="1">
          <stop offset="0" stopColor="#06231f" />
          <stop offset="0.5" stopColor="#0a3a2f" />
          <stop offset="1" stopColor="#06231f" />
        </linearGradient>
        <clipPath id="pitch-clip"><rect width="105" height="68" rx="1.5" /></clipPath>
      </defs>
      <rect width="105" height="68" rx="1.5" fill="url(#pitch-turf)" />
      {Array.from({ length: 10 }, (_, i) => <rect key={i} x={i * 10.5} width="5.25" height="68" fill="rgba(255,255,255,0.025)" />)}
      <g clipPath="url(#pitch-clip)">
        {heat.map((row, r) => row.map((v, c) => <rect key={`${r}-${c}`} x={c * cw} y={r * ch} width={cw + 0.05} height={ch + 0.05} fill={colour} opacity={Math.pow(v / max, 1.4) * 0.85} className="transition-opacity duration-700" />))}
      </g>
      <rect x="0.4" y="0.4" width="104.2" height="67.2" {...line} />
      <line x1="52.5" y1="0.4" x2="52.5" y2="67.6" {...line} />
      <circle cx="52.5" cy="34" r="9.15" {...line} />
      <circle cx="52.5" cy="34" r="0.6" fill="rgba(248,250,252,0.7)" />
      <rect x="0.4" y="13.85" width="16.5" height="40.3" {...line} />
      <rect x="0.4" y="24.85" width="5.5" height="18.3" {...line} />
      <rect x="88.1" y="13.85" width="16.5" height="40.3" {...line} />
      <rect x="99.1" y="24.85" width="5.5" height="18.3" {...line} />
      <path d="M16.9 27.5 A9.15 9.15 0 0 1 16.9 40.5" {...line} />
      <path d="M88.1 27.5 A9.15 9.15 0 0 0 88.1 40.5" {...line} />
    </svg>
  );
}
