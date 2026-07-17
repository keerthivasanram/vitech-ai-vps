import { memo } from "react";
import { motion } from "framer-motion";

/** Standard surface: 20px radius, 24px padding, 1px border, soft shadow. */
export const Card = memo(function Card({ as = "section", className = "", children, ...rest }) {
  const Tag = as;
  return (
    <Tag className={`card ${className}`.trim()} {...rest}>
      {children}
    </Tag>
  );
});

/** Card that fades+rises in. `index` staggers it within a group. */
export const MotionCard = memo(function MotionCard({
  index = 0,
  className = "",
  children,
  ...rest
}) {
  return (
    <motion.section
      className={`card ${className}`.trim()}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1], delay: index * 0.05 }}
      {...rest}
    >
      {children}
    </motion.section>
  );
});

/** Header row inside a panel card: title left, optional action right. */
export const PanelHead = memo(function PanelHead({ title, action, onAction }) {
  return (
    <header className="panel-head">
      <h2 className="panel-title">{title}</h2>
      {action && (
        <button type="button" className="panel-link" onClick={onAction}>
          {action}
        </button>
      )}
    </header>
  );
});
