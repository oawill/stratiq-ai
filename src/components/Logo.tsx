import Link from "next/link";

export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="lg-s" x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#A78BFA" />
          <stop offset="0.55" stopColor="#8055F6" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" fill="#111A2E" stroke="url(#lg-s)" strokeOpacity="0.5" />
      {/* Abstract S: two opposed arcs joined through a central node */}
      <path
        d="M28 12.5c-2-2-5-3-8-3-4.4 0-7.5 2.2-7.5 5.3 0 7.2 15 3.9 15 10.9 0 3.2-3.3 5.4-7.8 5.4-3.3 0-6.3-1.1-8.2-3.1"
        stroke="url(#lg-s)"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <circle cx="20" cy="20" r="2.4" fill="#22D3EE" />
      <circle cx="28" cy="12.5" r="1.8" fill="#A78BFA" />
      <circle cx="12" cy="28.5" r="1.8" fill="#8055F6" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label="STRATIQ AI">
      <LogoMark />
      <span className="text-[17px] font-bold tracking-[0.12em]">
        STRATIQ<span className="ml-1 text-violet">AI</span>
      </span>
    </Link>
  );
}
