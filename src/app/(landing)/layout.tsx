import { Footer } from "@/components/Footer";
import { MotionProvider } from "@/components/Motion";
import { LandingNavigation } from "@/components/landing/LandingNavigation";

/** The home page has its own layout: one fixed navigation and a scoped dark theme (.cine). The URL is still "/". */
export default function LandingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="cine flex min-h-screen flex-col">
      <LandingNavigation />
      <main id="main" className="flex-1">
        <MotionProvider>{children}</MotionProvider>
      </main>
      <Footer />
    </div>
  );
}
