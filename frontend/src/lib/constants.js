/* Static app configuration: agent ids, navigation, per-view copy. */

// The two live Flowise chatflows. Override the ids via .env if they change.
export const ENGINEERING_AGENT_ID =
  import.meta.env.VITE_ENGINEERING_AGENT_ID || "c4bfba16-aeb0-4c1b-840e-21b474639a8d";
export const QUOTATION_AGENT_ID =
  import.meta.env.VITE_QUOTATION_AGENT_ID || "6fa5a302-2d73-4191-bbea-ce98e4af2f1f";

export const AGENT_IDS = {
  engineering: ENGINEERING_AGENT_ID,
  quotation: QUOTATION_AGENT_ID,
};

export const agentUrl = (view) =>
  `/flowise/api/v1/prediction/${AGENT_IDS[view] || ENGINEERING_AGENT_ID}`;

export const isChatView = (v) => v === "engineering" || v === "quotation";

// Tools whose numbers come from the deterministic engine (not the model).
export const DETERMINISTIC_TOOLS = ["generate_quotation", "generate_specification"];

// Views that render the CollectionPage (a knowledge-base collection detail).
export const COLLECTION_KEYS = [
  "historical_projects", "specifications", "quotations",
  "standards", "vendor_catalogues", "drawings", "rules",
];

/* --------------------------------------------------------------------------
   Navigation. `icon` is a lucide icon name resolved in <NavIcon>.
   Items with status "soon" are roadmap pages and render a marker dot.
   An item with `children` is an expandable group rather than a destination.

   Documents / Standards / Vendor Documents are intentionally absent: they are
   internal surfaces we don't expose to clients. Their pages and routes still
   exist and are reachable from the Knowledge Base collection cards.
   -------------------------------------------------------------------------- */
export const NAV = [
  {
    id: "agents",
    label: "AI Agent",
    icon: "Bot",
    group: "Workspace",
    children: [
      { id: "engineering", label: "Engineering Agent", icon: "Bot",         status: "live" },
      { id: "quotation",   label: "Quotation Agent",   icon: "ReceiptText", status: "live" },
      { id: "drawing",     label: "Drawing Studio",    icon: "PenTool",     status: "live" },
    ],
  },
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard", group: "Workspace", status: "live" },

  { id: "knowledge",           label: "Knowledge Base", icon: "Database",     group: "Data", status: "live" },
  { id: "historical_projects", label: "Projects",       icon: "FolderKanban", group: "Data", status: "live" },

  { id: "profile",   label: "Profile",   icon: "UserRound",      group: "System", status: "live" },
  { id: "live_help", label: "Live Help", icon: "LifeBuoy",       group: "System", status: "live" },
  { id: "settings",  label: "Settings",  icon: "Settings",       group: "System", status: "live" },
];

/* Every child id under the collapsible agent group. */
export const AGENT_VIEWS = NAV.find((n) => n.id === "agents").children.map((c) => c.id);

// Header title + hero copy per view.
export const VIEW_TITLES = {
  dashboard: "Dashboard",
  engineering: "Engineering Agent",
  quotation: "Quotation Agent",
  drawing: "Drawing Studio",
  knowledge: "Knowledge Base",
  upload: "Documents",
  settings: "Settings",
  profile: "Profile",
  live_help: "Live Help",
  historical_projects: "Projects",
  standards: "Engineering Standards",
  vendor_catalogues: "Vendor Documents",
  specifications: "Specifications",
  quotations: "Quotations",
  drawings: "Drawings",
  rules: "Engineering Rules",
};

/* Empty-state copy + starter prompts per chat agent (keyed by view). */
export const AGENT_UI = {
  engineering: {
    name: "Vitech AI Agent",
    hero: "How can I assist you today?",
    sub: "Your intelligent assistant for Vitech knowledge, documents, analytics and more.",
    chips: [
      "Generate a wet scrubber spec for 800 CFM, 750 mm tower, 4 nos.",
      "Generate a specification for a 10 x 6 powder paint booth.",
      "What did C2C Engineering order?",
      "Which clients are in the database?",
      "How does a wet scrubber remove particulates from air?",
      "Convert 800 CFM to CMH.",
    ],
  },
  quotation: {
    name: "Vitech Quotation Agent",
    hero: "Budgetary quotations, on demand",
    sub: "Generate a budgetary quotation from your historical offers, revise the quantity or size, or compare past quotes.",
    chips: [
      "Quote a wet scrubber 800 CFM, 750 mm tower, 4 nos.",
      "Make that 6 nos instead.",
      "What have we quoted for Wheels India Ltd?",
      "Compare an 800 CFM scrubber with a 3000 CFM scrubber.",
      "How many projects have we quoted, and in which categories?",
    ],
  },
};

/* Quick-action cards under the hero. Each sends a real prompt to the agent. */
export const QUICK_ACTIONS = [
  { icon: "Search",    title: "Search",    sub: "Company Policies", prompt: "Which clients are in the database?" },
  { icon: "FileText",  title: "Analyze",   sub: "Documents",        prompt: "What did C2C Engineering order?" },
  { icon: "ClipboardList", title: "Summarize", sub: "Reports",      prompt: "How many projects have we quoted, and in which categories?" },
  { icon: "Sparkles",  title: "Ask",       sub: "Anything",         prompt: "How does a wet scrubber remove particulates from air?" },
];

export const THINK_LABELS = [
  "Thinking",
  "Understanding your request",
  "Searching the knowledge base",
  "Reasoning over past projects",
  "Composing the answer",
];
