import { memo } from "react";
import logoUrl from "../assets/logo.png";
import logoDarkUrl from "../assets/logo-dark.png";

/**
 * Official Vitech wordmark, trimmed to its ink (245x79, transparent).
 *
 * Two assets rather than a CSS filter: the artwork's tagline is near-black
 * green and dies on the dark sidebar, but inverting the image to fix that also
 * shifts the brand green. The dark variant lifts only the near-black ink and
 * leaves every green pixel byte-identical, so the brand colour is exact in
 * both themes.
 */
export const Logo = memo(function Logo({ height = 44, isDark = false }) {
  return (
    <span className="logo-shell">
      <img
        className="logo"
        src={isDark ? logoDarkUrl : logoUrl}
        height={height}
        alt="Vitech — Vision with Technology"
        draggable="false"
      />
    </span>
  );
});

/**
 * The compact Vitech mark — the same V the favicon carries, so the collapsed
 * rail is still unmistakably this product. The wordmark cannot shrink to a
 * 44px rail and stay legible, which is why this exists rather than a scaled
 * <Logo>.
 */
export const LogoMark = memo(function LogoMark({ size = 32 }) {
  return (
    <svg
      className="logo-mark"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Vitech"
    >
      <defs>
        <linearGradient id="vt-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#4ade80" />
          <stop offset="55%" stopColor="#22c55e" />
          <stop offset="100%" stopColor="#15803d" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="#0b3f22" />
      <path d="M10 14 h11 l8 22 l8 -22 h11 l-15 34 h-8 Z" fill="url(#vt-mark)" />
      <path d="M40 12 h11 l-5 11 h-9 Z" fill="#4ade80" opacity="0.85" />
    </svg>
  );
});
