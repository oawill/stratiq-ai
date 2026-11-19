import { Logo } from "@/components/Logo";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main id="main" className="relative flex flex-1 flex-col items-center justify-center px-4 py-12">
      <div className="pointer-events-none absolute -top-32 left-1/2 h-96 w-[700px] -translate-x-1/2 rounded-full bg-primary/20 blur-[120px]" aria-hidden="true" />
      <div className="relative w-full max-w-md">
        <div className="mb-8 flex justify-center"><Logo /></div>
        {children}
      </div>
    </main>
  );
}
