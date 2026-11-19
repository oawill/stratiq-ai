import type { Metadata } from "next";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { AuthForm } from "@/components/AuthForm";

export const metadata: Metadata = { title: "Create Account", robots: { index: false } };

async function Content() {
  if (await getSession()) redirect("/dashboard");
  return <AuthForm mode="signup" />;
}

export default function Page() {
  return <Suspense fallback={<div className="glass h-96 rounded-3xl" />}><Content /></Suspense>;
}
