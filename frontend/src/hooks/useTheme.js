import { useCallback, useEffect, useState } from "react";

const KEY = "vitech_theme";

/* Light is the product's designed default, so we do NOT follow the OS here:
   a dark-mode machine would otherwise never see the intended look. Dark is
   opt-in via the header toggle, and that choice is what gets remembered. */
const initial = () => {
  const saved = localStorage.getItem(KEY);
  return saved === "dark" ? "dark" : "light";
};

/**
 * Light/dark theme. Writes data-theme on <html>, which is what
 * variables.css keys its dark overrides off.
 */
export function useTheme() {
  const [theme, setTheme] = useState(initial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);

  return { theme, toggle, isDark: theme === "dark" };
}
