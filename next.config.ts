import type { NextConfig } from "next";

// Old hosting hostnames that should forward to the real website once it is live.
const LEGACY_HOSTS = ["stratiq-ai.vercel.app", "stratiq-ai-cicerah.vercel.app"];

/**
 * Redirects the legacy hosts to NEXT_PUBLIC_SITE_URL, but only once that variable points somewhere else (i.e. after the domain
 * cutover). Until then it is inactive, so nothing changes. /api, /app-api and /_next are excluded because the web app calls its own
 * Python function over PY_API_URL, which may still name a legacy host for a moment after cutover.
 */
function legacyHostRedirects(): { source: string; has: { type: "host"; value: string }[]; destination: string; permanent: boolean }[] {
  const site = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "");
  if (!site) return [];
  let host: string;
  try {
    host = new URL(site).hostname;
  } catch {
    return [];
  }
  if (LEGACY_HOSTS.includes(host) || host === "localhost") return [];
  return LEGACY_HOSTS.map((value) => ({
    source: "/:path((?!api/|app-api/|_next/).*)",
    has: [{ type: "host" as const, value }],
    destination: `${site}/:path`,
    permanent: true,
  }));
}

/**
 * Baseline security headers for every response. HSTS is already added by the platform. A full Content-Security-Policy is deliberately not
 * set: it needs per-request nonces for Next.js inline scripts and would need testing against every page; only `frame-ancestors` (the
 * clickjacking control) is set here, which is safe on its own.
 */
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(self)" },
];

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async redirects() {
    // The four per-domain pages were folded into the home page carousel: /sports is slide 1 of /, and so on.
    const slides = ["sports", "business", "politics", "finance"].map((s) => ({ source: `/${s}`, destination: `/#${s}`, permanent: true }));
    return [...slides, { source: "/dashboard/simlab", destination: "/dashboard/simulations", permanent: false },
      { source: "/sports/football/matches/:id", destination: "/dashboard/sports/football/matches/:id", permanent: false },   // the dashboard enforces sign-in
      ...legacyHostRedirects()];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
