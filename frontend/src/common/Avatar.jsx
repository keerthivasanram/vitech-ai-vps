import { memo } from "react";

/** Initials from a display name: "Loganathan R" -> "LR". */
const initials = (name) =>
  String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

/**
 * Circular avatar. Green gradient with initials by default; `src` renders a
 * photo instead. Size is passed as a CSS custom property, not inline styling.
 */
export const Avatar = memo(function Avatar({ name, src, size = 38, className = "" }) {
  const cls = `avatar ${className}`.trim();
  const vars = { "--avatar-size": `${size}px` };

  if (src) {
    return <img className={`${cls} avatar-img`} style={vars} src={src} alt={name || ""} />;
  }

  return (
    <span className={cls} style={vars} aria-hidden="true">
      {initials(name)}
    </span>
  );
});
