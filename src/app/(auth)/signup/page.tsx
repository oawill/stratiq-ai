import type { Metadata } from "next";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { AuthForm } from "@/components/AuthForm";

export const metadata: Metadata = { title: "Create Account", robots: { index: false } };

async function Content({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  if (await getSession()) redirect("/dashboard");
  const { next } = await searchParams;
  return <AuthForm mode="signup" next={next} />;
}

export default function Page(props: { searchParams: Promise<{ next?: string }> }) {
  return <Suspense fallback={<div className="glass h-96 rounded-3xl" />}><Content {...props} /></Suspense>;
}
