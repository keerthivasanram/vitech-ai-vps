import { memo } from "react";
import { motion } from "framer-motion";
import { Bot } from "lucide-react";
import { greeting } from "../lib/format";

/**
 * The agent mark.
 *
 * This was a radar sweep, a breathing gradient, two pulsing rings, four
 * particles on independent orbits and an energy wave off the centre — seven
 * perpetual animations on one 120px decoration, on the first screen of an
 * engineering tool. What is left is the glass core and two still rings: the
 * same mark, holding still.
 */
const Orb = memo(function Orb() {
  return (
    <motion.div
      className="orb"
      aria-hidden="true"
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: 0.08 }}
    >
      <span className="orb-ring orb-ring-1" />
      <span className="orb-ring orb-ring-2" />
      <span className="orb-core">
        <Bot size={24} strokeWidth={1.7} />
      </span>
    </motion.div>
  );
});

/**
 * Hero: greeting, headline, one-line description, and the agent mark.
 */
export const HeroCard = memo(function HeroCard({ userName, title, subtitle }) {
  return (
    <motion.section
      className="hero"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="hero-t">
        <p className="hero-greet">{greeting()}, {userName}</p>
        <h2 className="hero-h1">{title}</h2>
        <p className="hero-sub">{subtitle}</p>
      </div>
      <Orb />
    </motion.section>
  );
});
