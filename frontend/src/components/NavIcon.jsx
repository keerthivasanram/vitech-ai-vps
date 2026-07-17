import { memo } from "react";
import {
  Bot, LayoutDashboard, ReceiptText, Database, FolderKanban, FileText,
  BookOpen, Package, PenTool, Settings, Search, Sparkles, ClipboardList,
  BarChart3, ShieldCheck, Hexagon,
} from "lucide-react";

/* Icons are imported by name rather than dynamically resolved: the bundler can
   then tree-shake everything else out of lucide's 5,900-icon surface. */
const ICONS = {
  Bot, LayoutDashboard, ReceiptText, Database, FolderKanban, FileText,
  BookOpen, Package, PenTool, Settings, Search, Sparkles, ClipboardList,
  BarChart3, ShieldCheck, Hexagon,
};

/** Resolve a lucide icon by the name used in constants.js. */
export const getIcon = (name) => ICONS[name] || Hexagon;

/** Render a named icon at the app's standard 1.8 stroke. */
export const NavIcon = memo(function NavIcon({ name, size = 20, strokeWidth = 1.8, ...rest }) {
  const Icon = getIcon(name);
  return <Icon size={size} strokeWidth={strokeWidth} aria-hidden="true" {...rest} />;
});
