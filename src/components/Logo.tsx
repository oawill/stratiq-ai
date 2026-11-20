import { useId } from "react";
import Link from "next/link";
import { brand } from "@/lib/brand";

/** Original geometric "V" mark: a bold V with a nested cyan chevron and a vertex node. */
export function LogoMark({ size = 32 }: { size?: number }) {
  const id = useId();
  const g = `vq-${id.replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={g} x1="6" y1="4" x2="34" y2="36" gradientUnits="userSpaceOnUse">
          <stop stopColor="#A78BFA" />
          <stop offset="0.55" stopColor="#8055F6" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" fill="#111A2E" stroke={`url(#${g})`} strokeOpacity="0.5" />
      <path d="M9.5 11 20 30 30.5 11" stroke={`url(#${g})`} strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15.2 11 20 19.4 24.8 11" stroke="#22D3EE" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.9" />
      <circle cx="20" cy="30" r="2.2" fill="#22D3EE" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label={brand.name}>
      <LogoMark />
      <span className="text-[17px] font-bold tracking-[0.12em]">
        {brand.name}
      </span>
    </Link>
  );
}
