import { ArrowRight, BarChart3, Compass, Database, FlaskConical } from "lucide-react";
import { Container } from "../ui/primitives";
import { Reveal } from "../Motion";

const STEPS = [
  { icon: Database, title: "Data", accent: "#00E5FF", text: "Bring your own results as CSV files. Every row is checked and nothing is guessed or filled in." },
  { icon: BarChart3, title: "Analysis", accent: "#60A5FA", text: "Models fit on past data: Elo, Poisson and Dixon-Coles for football, plus game-theory and risk solvers." },
  { icon: FlaskConical, title: "Simulation", accent: "#8B5CF6", text: "Run scenarios and repeatable simulations with seeds, so the same inputs give the same answer." },
  { icon: Compass, title: "Decision intelligence", accent: "#34D399", text: "Explainable results saved with their model version and inputs, so a decision can be reviewed later." },
];

/** A four-step visual of how data becomes a decision. Each description matches what the application actually does. */
export function WorkflowStrip() {
  return (
    <section id="workflow" aria-labelledby="workflow-title" className="cine-section py-16 lg:py-20">
      <Container>
        <Reveal className="mx-auto mb-10 max-w-2xl text-center">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-ion">The workflow</p>
          <h2 id="workflow-title" className="text-3xl font-extrabold tracking-tight sm:text-4xl">Data → Analysis → Simulation → <span className="text-gradient">Decision intelligence</span></h2>
        </Reveal>
        <ol className="grid gap-4 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <Reveal delay={i * 0.08} className="h-full">
                <div className="glass relative h-full rounded-2xl p-5">
                <span className="mb-3 flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: `${s.accent}1f`, color: s.accent }}><s.icon className="h-5 w-5" aria-hidden="true" /></span>
                  <span className="font-mono text-xs text-muted">0{i + 1}</span>
                </span>
                <h3 className="font-bold">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{s.text}</p>
                {i < STEPS.length - 1 && <ArrowRight className="absolute -right-3.5 top-1/2 z-10 hidden h-6 w-6 -translate-y-1/2 text-muted lg:block" aria-hidden="true" />}
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
