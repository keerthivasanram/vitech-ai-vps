import { NavIcon } from "../components/NavIcon";
import { NAV } from "../lib/constants";

/* Flatten the nav so nested items (the agents) resolve too. */
const flatNav = NAV.flatMap((n) => (n.children ? n.children : [n]));

/** Shared state for pages on the roadmap (Drawing Agent, Settings, …). */
export function RoadmapPage({ id }) {
  const item = flatNav.find((n) => n.id === id) || { label: "Coming soon", icon: "Hexagon" };

  const note = {
    drawing:
      "This agent will run on the same deterministic engine and be orchestrated by the Supervisor Agent. Coming in a later phase.",
    settings:
      "Workspace settings — model selection, agent prompts and access control — arrive with the multi-user phase.",
    standards:
      "Design codes and standards become searchable once the document ingestion pipeline runs.",
    vendor_catalogues:
      "Supplier catalogues become searchable once the document ingestion pipeline runs.",
  }[id] || "On the roadmap.";

  return (
    <div className="placeholder">
      <span className="placeholder-ic">
        <NavIcon name={item.icon} size={30} />
      </span>
      <h1>{item.label}</h1>
      <p>{note}</p>
      <p className="placeholder-note">Not yet available.</p>
    </div>
  );
}
