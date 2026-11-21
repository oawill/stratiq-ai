import { PARTIES, type RegionResult } from "@/lib/landing/politics";

/** Hand-drawn outlines of the six regions of a FICTIONAL country. The shapes are schematic; they are not real geography. */
const SHAPES: Record<string, { d: string; label: [number, number] }> = {
  north: { d: "M60 34 L190 14 L300 30 L320 92 L212 106 L92 102 Z", label: [190, 62] },
  coast: { d: "M300 30 L372 62 L384 172 L332 224 L292 162 L320 92 Z", label: [346, 128] },
  central: { d: "M92 102 L212 106 L320 92 L292 162 L252 204 L122 194 L72 152 Z", label: [150, 152] },
  valley: { d: "M32 112 L92 102 L72 152 L122 194 L92 252 L32 212 L20 152 Z", label: [60, 178] },
  islands: { d: "M172 258 L232 252 L262 286 L204 304 L152 288 Z", label: [208, 280] },
  capital: { d: "M196 132 L256 126 L270 166 L228 188 L190 172 Z", label: [230, 158] },
};

/**
 * Regions are shaded by the leading party; the stronger the lead, the stronger the colour. Each region is a keyboard-operable button
 * that selects it. The leading party is also written in text, so colour is never the only signal.
 */
export function ElectionMap({ regions, selected, onSelect }: { regions: RegionResult[]; selected: string | null; onSelect: (id: string | null) => void }) {
  return (
    <svg viewBox="0 0 400 320" role="group" aria-label="Schematic map of a fictional country. Select a region to apply a swing to it." className="h-auto w-full">
      <defs>
        <filter id="map-glow"><feGaussianBlur stdDeviation="3" /></filter>
      </defs>
      {regions.map((r) => {
        const shape = SHAPES[r.region.id];
        const sorted = [...r.shares].sort((a, b) => b - a);
        const lead = sorted[0] - sorted[1];
        const party = PARTIES[r.leader];
        const on = selected === r.region.id;
        const label = `${r.region.name}: ${party.name} leads by ${(lead * 100).toFixed(1)} points, ${r.region.seats} seats${on ? ", selected" : ""}`;
        return (
          <g key={r.region.id} role="button" tabIndex={0} aria-pressed={on} aria-label={label} onClick={() => onSelect(on ? null : r.region.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(on ? null : r.region.id); } }} className="cursor-pointer outline-none [&:focus-visible>path]:stroke-white [&:focus-visible>path]:stroke-[3]">
            <path d={shape.d} fill={party.colour} fillOpacity={0.22 + Math.min(0.5, lead * 3.2)} stroke={on ? "#F8FAFC" : party.colour} strokeOpacity={on ? 1 : 0.7} strokeWidth={on ? 2.5 : 1.2} strokeLinejoin="round" className="transition-all duration-500" />
            <text x={shape.label[0]} y={shape.label[1] - 4} textAnchor="middle" fontSize="10" fontWeight="600" fill="#F8FAFC">{r.region.name.split(" ").slice(-1)[0]}</text>
            <text x={shape.label[0]} y={shape.label[1] + 9} textAnchor="middle" fontSize="9" fontFamily="monospace" fill="#CBD5E1">{party.id} · {r.region.seats}</text>
          </g>
        );
      })}
    </svg>
  );
}
