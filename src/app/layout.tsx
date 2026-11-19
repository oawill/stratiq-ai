import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { MotionProvider } from "@/components/Motion";
import { Footer } from "@/components/Footer";
import { SITE_URL } from "@/lib/site";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const description =
  "AI-powered predictions, game-theoretic simulations, and scenario planning across sports, business, politics, and financial markets.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "STRATIQ AI — Predict. Simulate. Strategize.",
    template: "%s | STRATIQ AI",
  },
  description,
  openGraph: {
    type: "website",
    siteName: "STRATIQ AI",
    title: "STRATIQ AI — Strategic Intelligence for a Complex World",
    description,
  },
  twitter: { card: "summary_large_image", title: "STRATIQ AI", description },
};

export const viewport: Viewport = { themeColor: "#080D1B", colorScheme: "dark" };

const orgJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "STRATIQ AI",
  url: SITE_URL,
  slogan: "Predict. Simulate. Strategize.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
      <body className="flex min-h-screen flex-col">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
        />
        <Nav />
        <main id="main" className="flex-1">
          <MotionProvider>{children}</MotionProvider>
        </main>
        <Footer />
      </body>
    </html>
  );
}
