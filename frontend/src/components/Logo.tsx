import React from "react";

interface LogoProps {
  className?: string;
  title?: string;
}

/**
 * VieScanner brand logo (inline SVG).
 *
 * Sử dụng inline để:
 *  - Render ngay không cần network request.
 *  - Scale theo container qua Tailwind utility (size-*, w-*, h-*).
 *  - Có thể style với CSS nếu cần.
 */
export default function Logo({ className, title = "VieScanner" }: LogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label={title}
      className={className}
    >
      <title>{title}</title>
      {/* Background card */}
      <rect width="64" height="64" rx="12" fill="#1e3a8a" />

      {/* ID card body */}
      <rect x="10" y="16" width="44" height="32" rx="4" fill="#ffffff" />

      {/* Red top stripe (Vietnam flag accent) */}
      <rect x="10" y="16" width="44" height="6" rx="4" fill="#dc2626" />
      <rect x="10" y="19" width="44" height="3" fill="#dc2626" />

      {/* Portrait placeholder */}
      <circle cx="20" cy="32" r="4" fill="#1e3a8a" />
      <path d="M14 42 Q14 38 20 38 Q26 38 26 42 Z" fill="#1e3a8a" />

      {/* Info lines */}
      <rect x="30" y="28" width="18" height="2" rx="1" fill="#1e3a8a" />
      <rect x="30" y="33" width="14" height="2" rx="1" fill="#94a3b8" />
      <rect x="30" y="38" width="16" height="2" rx="1" fill="#94a3b8" />

      {/* Scan line accent */}
      <line
        x1="6"
        y1="32"
        x2="58"
        y2="32"
        stroke="#22d3ee"
        strokeWidth="1.5"
        strokeDasharray="2 2"
        opacity="0.7"
      />
    </svg>
  );
}
