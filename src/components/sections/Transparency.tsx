import { Container, PreviewBadge, SectionHeading } from "../ui/primitives";
import { Reveal } from "../Motion";

const ITEMS = [
  ["Historical backtesting", "Models are evaluated on past data they never saw during fitting."],
  ["Probability calibration", "When we say 30%, outcomes should occur about 30% of the time."],
  ["Brier score & log loss", "Proper scoring rules that reward honest, well-calibrated probabilities."],
  ["Model versioning", "Every forecast records the model version that produced it."],
  ["Data provenance", "Inputs are traceable to their source and timestamp."],
  ["Forecast uncertainty", "Ranges and scenarios, never false precision."],
  ["Reproducible simulations", "Seeded runs so results can be re-created and audited."],
];

// Illustrative calibration curve: perfectly calibrated diagonal vs a made-up sample.
const SAMPLE = [
  [0.1, 0.12], [0.25, 0.22], [0.4, 0.43], [0.55, 0.52], [0.7, 0.74], [0.85, 0.81],
];

export function Transparency() {
  const pts = SAMPLE.map(([x, y]) => `${x * 200 + 20},${180 - y * 160}`).join(" ");
  return (
    <section id="performance" className="py-20 lg:py-24">
      <Container>
        <SectionHeading
          eyebrow="Model transparency"
          title="Intelligence You Can Evaluate."
          sub="A forecast you cannot check is just an opinion. STRATIQ AI is designed around measurable, auditable evaluation."
        />
        <div className="grid items-start gap-8 lg:grid-cols-2">
          <ul className="grid gap-3 sm:grid-cols-2">
            {ITEMS.map(([t, d], i) => (
              <li key={t} className="glass h-full rounded-2xl p-4">
              <Reveal delay={i * 0.04}>
                  <h3 className="text-sm font-semibold text-violet">{t}</h3>
                  <p className="mt-1 text-sm text-muted">{d}</p>
                </Reveal>
              </li>
            ))}
          </ul>

          <div className="glass rounded-3xl p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between gap-2">
              <h3 className="font-semibold">Performance dashboard</h3>
              <PreviewBadge>Sample · Evaluation in progress</PreviewBadge>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {["Brier score", "Log loss", "Calibration error"].map((k) => (
                <div key={k} className="rounded-xl border border-line bg-card/60 p-3">
                  <div className="text-[11px] text-muted">{k}</div>
                  <div className="mt-1 font-mono text-lg text-muted">—</div>
                  <div className="text-[10px] text-muted">Pending validation</div>
                </div>
              ))}
            </div>
            <figure className="mt-4">
              <svg viewBox="0 0 240 200" className="w-full" role="img" aria-label="Sample reliability diagram with illustrative points near the diagonal">
                <rect x="20" y="20" width="200" height="160" fill="none" stroke="#334155" />
                <line x1="20" y1="180" x2="220" y2="20" stroke="#94a3b8" strokeDasharray="4 4" />
                <polyline points={pts} fill="none" stroke="#8055f6" strokeWidth="2.5" />
                {SAMPLE.map(([x, y]) => (
                  <circle key={x} cx={x * 200 + 20} cy={180 - y * 160} r="3.5" fill="#22d3ee" />
                ))}
                <text x="120" y="196" textAnchor="middle" fill="#94a3b8" fontSize="9">Predicted probability</text>
              </svg>
              <figcaption className="text-xs text-muted">
                Illustrative reliability diagram with made-up sample points. No accuracy figures are
                claimed until models have been independently backtested and results published here.
              </figcaption>
            </figure>
          </div>
        </div>
      </Container>
    </section>
  );
}
