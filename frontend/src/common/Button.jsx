import { memo } from "react";

/**
 * Button primitive.
 * variant: "primary" (green gradient) | "ghost" (outlined)
 */
export const Button = memo(function Button({
  variant = "primary",
  size,
  icon: Icon,
  iconRight: IconRight,
  className = "",
  children,
  ...rest
}) {
  const cls = [
    "btn",
    `btn-${variant}`,
    size === "sm" ? "btn-sm" : "",
    className,
  ].filter(Boolean).join(" ");

  return (
    <button type="button" className={cls} {...rest}>
      {Icon && <Icon size={16} strokeWidth={1.8} aria-hidden="true" />}
      {children}
      {IconRight && <IconRight size={16} strokeWidth={1.8} aria-hidden="true" />}
    </button>
  );
});
