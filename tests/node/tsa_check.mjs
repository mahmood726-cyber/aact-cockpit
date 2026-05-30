// TSA numeric witness: extract the capsule's own cumulative-TSA JS engine +
// CAPSULE data, run cumulative() under Node, assert it reproduces the Python-
// embedded final cumulative Z (and crossing step) within 1e-6.
//
// Usage: node tests/node/tsa_check.mjs <tsa-capsule.html>
import { readFileSync } from "node:fs";

const file = process.argv[2];
if (!file) { console.error("usage: node tsa_check.mjs <tsa-capsule.html>"); process.exit(2); }
const html = readFileSync(file, "utf8");

const capLine = html.split("\n").find(l => l.trimStart().startsWith("const CAPSULE ="));
if (!capLine) { console.error("CAPSULE const not found"); process.exit(2); }
const CAPSULE = JSON.parse(capLine.slice(capLine.indexOf("=") + 1).trim().replace(/;\s*$/, ""));

const startTok = "const Z = 1.959963984540054,";
const endTok = "function defaults()";
const si = html.indexOf(startTok), ei = html.indexOf(endTok);
if (si < 0 || ei < 0 || ei < si) { console.error("engine block not located"); process.exit(2); }
const engine = html.slice(si, ei);

const runner = new Function("CAPSULE", engine + "\nreturn cumulative(CAPSULE.studies);");
const res = runner(CAPSULE);

const py = CAPSULE.tsa;
const dZ = Math.abs(res.final_z - py.final_z);
const dT = Math.abs(res.final_t - py.final_t);
const crossOk = res.crossed === py.crossed;
const TOL = 1e-6;
const ok = dZ < TOL && dT < TOL && crossOk;

console.log(`JS  final_z=${res.final_z.toFixed(6)} final_t=${res.final_t.toFixed(4)} crossed@${res.crossed} concl=${res.conclusion}`);
console.log(`PY  final_z=${py.final_z.toFixed(6)} final_t=${py.final_t.toFixed(4)} crossed@${py.crossed} concl=${py.conclusion}`);
console.log(`ΔZ=${dZ.toExponential(2)} Δt=${dT.toExponential(2)} crossMatch=${crossOk}  ${ok ? "PASS" : "FAIL"}`);
process.exit(ok ? 0 : 1);
