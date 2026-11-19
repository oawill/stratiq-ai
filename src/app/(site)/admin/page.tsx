import type { Metadata } from "next";
import { Suspense } from "react";
import { isAdmin } from "@/lib/adminAuth";
import { getPool } from "@/lib/db";
import { logout } from "./actions";
import { LoginForm } from "./LoginForm";
import { Container } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

interface Row {
  id: string;
  full_name: string;
  email: string;
  country: string;
  interest: string;
  intended_use: string;
  source: string | null;
  created_at: Date;
}

function Stat({ title, items }: { title: string; items: { k: string; n: string }[] }) {
  return (
    <div className="glass rounded-2xl p-4">
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      <ul className="space-y-1 text-sm text-muted">
        {items.map((i) => <li key={i.k} className="flex justify-between"><span>{i.k}</span><span className="font-mono text-ink">{i.n}</span></li>)}
      </ul>
    </div>
  );
}

async function AdminContent() {
  // Authorization is enforced here, on the server, on every request.
  if (!(await isAdmin())) return <LoginForm />;

  const pool = getPool();
  if (!pool) return <Container className="py-16">DATABASE_URL is not configured.</Container>;

  let rows: Row[] = [];
  let byInterest: { k: string; n: string }[] = [];
  let bySource: { k: string; n: string }[] = [];
  let byDay: { d: string; n: string }[] = [];
  let failed = false;
  try {
    rows = (await pool.query<Row>("select * from early_access_signups order by created_at desc limit 500")).rows;
    byInterest = (await pool.query("select interest k, count(*) n from early_access_signups group by 1 order by 2 desc")).rows;
    bySource = (await pool.query("select coalesce(source,'unknown') k, count(*) n from early_access_signups group by 1 order by 2 desc")).rows;
    byDay = (await pool.query("select to_char(created_at::date,'YYYY-MM-DD') d, count(*) n from early_access_signups group by 1 order by 1 desc limit 14")).rows;
  } catch (e) {
    console.error(e);
    failed = true;
  }

  return (
    <Container className="py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">Early-access signups <span className="text-muted">({rows.length})</span></h1>
        <form action={logout}><button className="text-sm text-violet underline">Sign out</button></form>
      </div>
      {failed && <p role="alert" className="mb-4 text-red-400">Could not load data. Has the migration been applied?</p>}
      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <Stat title="By interest" items={byInterest} />
        <Stat title="By source" items={bySource} />
        <Stat title="Last 14 days with signups" items={byDay.map((r) => ({ k: r.d, n: r.n }))} />
      </div>
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead className="bg-bg2 text-xs text-muted">
            <tr>{["When", "Name", "Email", "Country", "Interest", "Use", "Source"].map((h) => <th key={h} scope="col" className="px-3 py-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="px-3 py-2 font-mono text-xs">{new Date(r.created_at).toISOString().slice(0, 16).replace("T", " ")}</td>
                <td className="px-3 py-2">{r.full_name}</td>
                <td className="px-3 py-2">{r.email}</td>
                <td className="px-3 py-2">{r.country}</td>
                <td className="px-3 py-2">{r.interest}</td>
                <td className="px-3 py-2">{r.intended_use}</td>
                <td className="px-3 py-2 text-muted">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Container>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Container className="py-16 text-muted">Loading…</Container>}>
      <AdminContent />
    </Suspense>
  );
}
