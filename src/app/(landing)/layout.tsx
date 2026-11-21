import { Footer } from "@/components/Footer";
import { MotionProvider } from "@/components/Motion";
import { LandingNavigation } from "@/components/landing/LandingNavigation";
import { SectionProgress } from "@/components/landing/SectionProgress";

/** The home page has its own layout: a fixed anchor navigation and a scoped dark theme (.cine). The URL is still "/". */
export default function LandingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="cine flex min-h-screen flex-col">
      <LandingNavigation />
      <SectionProgress />
      <main id="main" className="flex-1">
        <MotionProvider>{children}</MotionProvider>
      </main>
      <Footer />
    </div>
  );
}
