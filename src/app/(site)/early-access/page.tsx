import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { Suspense } from "react";
import { Container } from "@/components/ui/primitives";
import { EarlyAccessForm } from "@/components/EarlyAccessForm";

export const metadata: Metadata = {
  title: "Get Early Access",
  description: `Join the ${brand.name} early-access list.`,
  alternates: { canonical: "/early-access" },
};

async function Content({ searchParams }: { searchParams: Promise<{ plan?: string }> }) {
  const { plan } = await searchParams;
  const source = plan ? `pricing:${plan}`.slice(0, 100) : "early-access-page";
  return (
    <Container className="max-w-xl py-16">
      <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">Get Early Access</h1>
      <p className="mb-8 mt-3 text-muted">
        Tell us a little about yourself. We&apos;ll only use your details to contact you about {brand.name}.
      </p>
      <EarlyAccessForm source={source} />
    </Container>
  );
}

export default function Page(props: { searchParams: Promise<{ plan?: string }> }) {
  return (
    <Suspense fallback={<Container className="max-w-xl py-16 text-muted">Loading…</Container>}>
      <Content {...props} />
    </Suspense>
  );
}
