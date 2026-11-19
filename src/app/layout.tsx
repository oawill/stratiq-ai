import type { Metadata, Viewport } from "next";
import { brand } from "@/lib/brand";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { SITE_URL } from "@/lib/site";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const title = `${brand.name} — ${brand.tagline}`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  applicationName: brand.name,
  title: { default: title, template: `%s | ${brand.name}` },
  description: brand.shortDescription,
  openGraph: { type: "website", siteName: brand.name, title, description: brand.shortDescription, locale: "en_US" },
  twitter: { card: "summary_large_image", title, description: brand.shortDescription },
};

export const viewport: Viewport = { themeColor: "#080D1B", colorScheme: "dark" };

const orgJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: brand.name,
  alternateName: brand.shortName,
  url: SITE_URL,
  slogan: brand.tagline,
  description: brand.description,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
      <body className="flex min-h-screen flex-col">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
        />
        {children}
      </body>
    </html>
  );
}
