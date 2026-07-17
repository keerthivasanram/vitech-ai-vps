import { memo } from "react";
import { motion } from "framer-motion";
import { Bot } from "lucide-react";
import { greeting } from "../lib/format";

/**
 * The glowing AI illustration: layered rings, a breathing glow and a glass
 * core holding the bot mark. Ring motion is CSS (ambient loops); the entrance
 * is Framer Motion.
 */
const Orb = memo(function Orb() {
  return (
    <motion.div
      className="orb"
      aria-hidden="true"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
    >
      <span className="orb-glow" />
      <span className="orb-ring orb-ring-1" />
      <span className="orb-ring orb-ring-2" />
      <span className="orb-ring orb-ring-3" />
      <span className="orb-node orb-node-1" />
      <span className="orb-node orb-node-2" />
      <span className="orb-node orb-node-3" />
      <span className="orb-core">
        <Bot size={28} strokeWidth={1.8} />
      </span>
    </motion.div>
  );
});

/**
 * Hero: greeting, headline, one-line description, and the orb.
 */
export const HeroCard = memo(function HeroCard({ userName, title, subtitle }) {
  return (
    <motion.section
      className="hero"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="hero-t">
        <p className="hero-greet">
          {greeting()}, {userName}!
          <span className="hero-wave" role="img" aria-label="waving hand">👋</span>
        </p>
        <h2 className="hero-h1">{title}</h2>
        <p className="hero-sub">{subtitle}</p>
      </div>
      <Orb />
    </motion.section>
  );
});
