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

/**
 * Circuit-trace decoration for the sidebar's bottom-left corner.
 * Purely decorative — rendered at ~6% opacity behind the nav.
 */
export const CircuitDeco = memo(function CircuitDeco() {
  return (
    <svg
      className="sidebar-deco"
      viewBox="0 0 300 320"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M6 40 L60 40 L60 96 L120 96 L120 150" />
      <path d="M6 110 L38 110 L38 190 L96 190 L96 250 L160 250" />
      <path d="M6 210 L26 210 L26 300 L110 300" />
      <path d="M60 40 L60 8" />
      <path d="M120 150 L188 150 L188 208 L240 208" />
      <path d="M96 190 L150 190 L150 130" />
      <path d="M160 250 L160 296 L220 296" />
      <path d="M38 110 L82 110 L82 60 L140 60" />
      <circle cx="120" cy="150" r="5" />
      <circle cx="96" cy="190" r="5" />
      <circle cx="160" cy="250" r="5" />
      <circle cx="188" cy="208" r="4" />
      <circle cx="150" cy="130" r="4" />
      <circle cx="140" cy="60" r="4" />
      <circle cx="110" cy="300" r="4" />
      <circle cx="240" cy="208" r="4" />
      <circle cx="220" cy="296" r="4" />
      <rect x="52" y="32" width="16" height="16" rx="3" />
      <rect x="30" y="102" width="16" height="16" rx="3" />
    </svg>
  );
});
