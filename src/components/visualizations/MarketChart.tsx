import type { Candle, Regime } from "@/lib/landing/markets";

export const REGIME_COLOUR: Record<Regime, string> = { Uptrend: "#34D399", Downtrend: "#FB7185", Range: "#94A3B8", "High volatility": "#FBBF24" };

/**
 * Candlestick chart of a SIMULATED price series, with a regime strip underneath and a realised-volatility line. Up days are filled
 * green with the body drawn solid, down days red with an outlined body, so direction is not carried by colour alone.
 */
export function MarketChart({ candles, regimes }: { candles: Candle[]; regimes: { i: number; regime: Regime; volatility: number }[] }) {
  const W = 640, H = 250, top = 8, plotH = 150, stripY = 172, volY = 192, volH = 52;
  const lo = Math.min(...candles.map((c) => c.low)), hi = Math.max(...candles.map((c) => c.high));
  const y = (v: number) => top + (1 - (v - lo) / (hi - lo)) * (plotH - top);
  const step = W / candles.length;
  const vols = regimes.map((r) => r.volatility);
  const vmax = Math.max(...vols, 0.01);
  const volPath = regimes.map((r, i) => `${i === 0 ? "M" : "L"}${(i + 0.5) * step} ${volY + volH - (r.volatility / vmax) * volH}`).join(" ");
  const last = regimes[regimes.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Simulated price chart of ${candles.length} days from ${candles[0].open.toFixed(1)} to ${candles[candles.length - 1].close.toFixed(1)}. The latest regime is ${last.regime}. This is simulated data, not market data.`} className="h-auto w-full">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => <line key={t} x1="0" x2={W} y1={top + t * (plotH - top)} y2={top + t * (plotH - top)} stroke="rgba(148,163,184,0.12)" />)}
      {candles.map((c, i) => {
        const x = (i + 0.5) * step;
        const up = c.close >= c.open;
        const colour = up ? "#34D399" : "#FB7185";
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={colour} strokeWidth="1" />
            <rect x={x - step * 0.3} width={step * 0.6} y={y(Math.max(c.open, c.close))} height={Math.max(1.2, Math.abs(y(c.open) - y(c.close)))} fill={up ? colour : "#030B1C"} stroke={colour} strokeWidth="1.2" />
          </g>
        );
      })}
      <g>{regimes.map((r, i) => <rect key={i} x={i * step} y={stripY} width={step + 0.3} height="12" fill={REGIME_COLOUR[r.regime]} opacity="0.85"><title>{`Day ${i + 1}: ${r.regime}`}</title></rect>)}</g>
      <path d={volPath} fill="none" stroke="#FBBF24" strokeWidth="1.4" />
      <path d={`${volPath} L${W - step / 2} ${volY + volH} L${step / 2} ${volY + volH} Z`} fill="rgba(251,191,36,0.1)" />
      <text x="4" y={volY + 10} fontSize="9" fill="#94A3B8">realised volatility</text>
    </svg>
  );
}
