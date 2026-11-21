import { MAJORITY, PARTIES, TOTAL_SEATS } from "@/lib/landing/politics";

/** A single bar of all seats, split by party, with the majority line. Seats are also listed in text underneath. */
export function SeatChart({ seats, label }: { seats: number[]; label: string }) {
  return (
    <figure>
      <figcaption className="mb-1 text-xs font-semibold text-muted">{label}</figcaption>
      <div className="relative">
        <div className="flex h-8 overflow-hidden rounded-lg" role="img" aria-label={`${label}: ${PARTIES.map((p, i) => `${p.name} ${seats[i]} seats`).join(", ")}. ${MAJORITY} seats are needed for a majority.`}>
          {PARTIES.map((p, i) => (
            <div key={p.id} className="flex items-center justify-center text-[11px] font-bold text-night transition-all duration-700" style={{ width: `${(seats[i] / TOTAL_SEATS) * 100}%`, background: p.colour }}>{seats[i] >= 6 ? seats[i] : ""}</div>
          ))}
        </div>
        <div className="pointer-events-none absolute -top-1 bottom-[-4px] w-px bg-white" style={{ left: `${(MAJORITY / TOTAL_SEATS) * 100}%` }} aria-hidden="true" />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted"><span>0</span><span>{MAJORITY} needed for a majority</span><span>{TOTAL_SEATS}</span></div>
    </figure>
  );
}
