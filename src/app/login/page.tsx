import type { Metadata } from "next";
import { ButtonLink, Container, PreviewBadge } from "@/components/ui/primitives";

export const metadata: Metadata = {
  title: "Log In",
  robots: { index: false },
};

export default function Page() {
  return (
    <Container className="max-w-md py-20">
      <div className="glass rounded-3xl p-8 text-center">
        <PreviewBadge>Coming soon</PreviewBadge>
        <h1 className="mt-4 text-3xl font-extrabold">Log In</h1>
        <p className="mt-3 text-sm text-muted">
          User accounts and the STRATIQ AI application launch with early access. There is nothing to
          sign in to yet — register your interest and we&apos;ll invite you.
        </p>
        <ButtonLink href="/early-access" className="mt-6 w-full">Get Early Access</ButtonLink>
        <p className="mt-6 text-xs text-muted">
          Site administrator? <a className="text-violet underline" href="/admin">Admin sign-in</a>
        </p>
      </div>
    </Container>
  );
}
