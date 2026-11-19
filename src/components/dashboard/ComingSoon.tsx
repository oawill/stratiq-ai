import Link from "next/link";
import { brand } from "@/lib/brand";
import { Check } from "lucide-react";
import { Badge, PageTitle, Panel } from "./ui";

export function ComingSoon({ title, step, summary, planned, note }: { title: string; step: string; summary: string; planned: string[]; note?: string }) {
  return (
    <>
      <PageTitle title={title} sub={summary} right={<Badge tone="amber">Not built yet · {step}</Badge>} />
      <Panel title="Planned capabilities">
        <ul className="grid gap-2 sm:grid-cols-2">
          {planned.map((p) => (
            <li key={p} className="flex items-start gap-2 text-sm"><Check className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />{p}</li>
          ))}
        </ul>
        {note && <p className="mt-4 rounded-lg border border-line bg-bg/60 p-3 text-xs text-muted">{note}</p>}
        <p className="mt-4 text-sm text-muted">Nothing on this page is functional yet. Try <Link href="/dashboard/sports" className="text-violet underline">{brand.products.sports.name}</Link>, which is live.</p>
      </Panel>
    </>
  );
}
