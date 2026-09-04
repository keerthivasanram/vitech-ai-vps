import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "framer-motion";
import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthProvider.jsx";

/* Order matters: tokens, then keyframes, then shell, then page styles. */
import "./styles/variables.css";
import "./styles/animations.css";
import "./styles/App.css";
import "./styles/pages.css";
import "./styles/studio.css";

/*
 * `reducedMotion="user"` is the half of the accessibility contract the CSS
 * could not keep. `animations.css` neutralises every CSS animation and
 * transition under `prefers-reduced-motion`, but Framer Motion animates by
 * writing INLINE transforms from JavaScript — a stylesheet cannot reach those.
 * So the hero, the quick-action cards, the chat bubbles and every Card still
 * slid and faded for a user who had asked the operating system for none of it.
 * With this, Framer holds those elements at their final values and animates
 * only opacity, which is the behaviour the setting asks for.
 */
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <AuthProvider>
        <App />
      </AuthProvider>
    </MotionConfig>
  </React.StrictMode>
);
