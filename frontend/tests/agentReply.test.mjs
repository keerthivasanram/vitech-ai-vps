import { isLeakedMechanics, sanitizeAgentReply } from '../src/lib/agentReply.js';
let fail = 0;
const t = (cond, label) => { console.log((cond?'OK   ':'FAIL ')+label); if(!cond) fail++; };

// Leaks that MUST be suppressed
t(isLeakedMechanics("There is no function call needed for your greeting."), "the reported leak is caught");
t(isLeakedMechanics('{"name": "answer", "parameters": {}}'), "tool-call JSON is caught");
t(isLeakedMechanics('{"name": "WHO YOU ARE", "parameters": {}}'), "fake tool name is caught");
t(isLeakedMechanics("No function call is required."), "the variant phrasing is caught");

// Real answers that must SURVIVE — losing an engineering answer would be far
// worse than the leak this prevents.
t(!isLeakedMechanics("Hello! How can I assist you today?"), "a real greeting survives");
t(!isLeakedMechanics("I'm the Vitech Engineering Assistant."), "the identity reply survives");
t(!isLeakedMechanics("**ENGINEERING SPECIFICATION**\n\n| Parameter | Value |"), "a spec table survives");
t(!isLeakedMechanics("I used the generate_specification tool to build this spec, which shows a paint booth with an exhaust airflow of 15120 m3/h and twelve arresting filters across the extract face."), "a long answer mentioning a tool survives");
t(!isLeakedMechanics(""), "an empty reply is not treated as a leak");
t(!isLeakedMechanics(null), "null is safe");

// Substitution behaviour
let seen = null;
const out = sanitizeAgentReply("There is no function call needed for your greeting.", r => seen = r);
t(out.includes("Vitech Engineering Assistant"), "a leak is replaced with a real greeting");
t(seen && seen.includes("function call"), "the leak is reported to the caller, not silently dropped");
t(sanitizeAgentReply("Hello there!") === "Hello there!", "a good reply passes through untouched");

console.log(fail ? `\n${fail} GUARD TEST FAIL` : "\nALL AGENT-GUARD TESTS PASS");
process.exit(fail ? 1 : 0);
