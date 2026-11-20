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

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async redirects() {
    return legacyHostRedirects();
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
