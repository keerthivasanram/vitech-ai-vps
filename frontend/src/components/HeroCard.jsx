import { memo } from "react";
import { motion } from "framer-motion";
import { Bot } from "lucide-react";
import { greeting } from "../lib/format";

/**
 * Four orbiting highlight dots — clean glowing points on clearly-defined
 * circular tracks, no comet trails (the trails read as messy at this size).
 * Each rides its own radius/speed/direction/phase so they never sync up.
 * A negative `delay` offsets each as if already mid-orbit on first paint.
 */
const PARTICLES = [
  { radius: 6,  duration: 16, direction: "normal",  delay: -3,  size: 5, flicker: 3.6 },
  { radius: 15, duration: 22, direction: "reverse", delay: -8,  size: 4, flicker: 4.4 },
  { radius: 24, duration: 13, direction: "normal",  delay: -2,  size: 5, flicker: 3.1 },
  { radius: 32, duration: 26, direction: "reverse", delay: -11, size: 3, flicker: 4.9 },
];

/**
 * The premium AI core, kept deliberately calm and refined:
 *   • a soft breathing gradient orb behind everything
 *   • a slow conic "radar sweep" — one bright arc rotating around a faint ring
 *   • two clean concentric guide rings
 *   • four small glowing dots on independent circular orbits (no trails)
 *   • a soft energy wave off the center every 5s
 *   • the glass core holding the bot mark
 * All ambient motion is CSS; the entrance is Framer Motion.
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
      <span className="orb-sweep" />
      <span className="orb-ring orb-ring-1" />
      <span className="orb-ring orb-ring-2" />

      {PARTICLES.map((p, i) => (
        <span
          key={i}
          className="orb-orbit"
          style={{
            inset: `${p.radius}%`,
            animationDuration: `${p.duration}s`,
            animationDirection: p.direction,
            animationDelay: `${p.delay}s`,
          }}
        >
          <span
            className="orb-node"
            style={{
              width: p.size,
              height: p.size,
              marginLeft: -p.size / 2,
              animationDuration: `${p.flicker}s`,
              animationDelay: `${p.delay}s`,
            }}
          />
        </span>
      ))}

      <span className="orb-wave" />
      <span className="orb-core">
        <Bot size={26} strokeWidth={1.8} />
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
