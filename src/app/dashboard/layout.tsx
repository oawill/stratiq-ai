import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { Suspense } from "react";
import { requireSession } from "@/lib/auth";
import { Shell } from "@/components/dashboard/Shell";

export const metadata: Metadata = { title: { default: "Dashboard", template: `%s | ${brand.name}` }, robots: { index: false, follow: false } };

async function Authed({ children }: { children: React.ReactNode }) {
  // Authorization is enforced on the server for every dashboard request.
  const s = await requireSession();
  return <Shell user={{ name: s.name, email: s.email, workspace: s.workspaceName, role: s.role }}>{children}</Shell>;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-screen" aria-busy="true"><p className="p-8 text-muted">Loading workspace…</p></div>}>
      <Authed>{children}</Authed>
    </Suspense>
  );
}
