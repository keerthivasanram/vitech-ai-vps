import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

/* Order matters: tokens, then keyframes, then shell, then page styles. */
import "./styles/variables.css";
import "./styles/animations.css";
import "./styles/App.css";
import "./styles/pages.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
