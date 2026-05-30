// Numeric-regression witness: extract the capsule's OWN embedded JS engine and
// CAPSULE data, run pool() under Node, and assert it reproduces the Python-
// embedded pooled estimate within 1e-4 (the rapidmeta portfolio threshold).
//
// Usage: node tests/node/repool_check.mjs <capsule.html>
import { readFileSync } from "node:fs";

const file = process.argv[2];
if (!file) { console.error("usage: node repool_check.mjs <capsule.html>"); process.exit(2); }
const html = readFileSync(file, "utf8");

// 1) the CAPSULE constant (single-line JSON literal)
const capLine = html.split("\n").find(l => l.trimStart().startsWith("const CAPSULE ="));
if (!capLine) { console.error("CAPSULE const not found"); process.exit(2); }
const jsonText = capLine.slice(capLine.indexOf("=") + 1).trim().replace(/;\s*$/, "");
const CAPSULE = JSON.parse(jsonText);

// 2) the engine block (Z .. pool), which has no DOM dependencies
const startTok = "const Z = 1.959963984540054;";
const endTok = "// ---- state ----";
const si = html.indexOf(startTok), ei = html.indexOf(endTok);
if (si < 0 || ei < 0 || ei < si) { console.error("engine block not located"); process.exit(2); }
const engine = html.slice(si, ei);

// 3) run pool(CAPSULE.studies) using the capsule's exact code
const runner = new Function("CAPSULE", engine + "\nreturn pool(CAPSULE.studies);");
const res = runner(CAPSULE);

const py = CAPSULE.pooled;
const dEst = Math.abs(res.est - py.est);
const dLo = Math.abs(res.ciL - py.ci_lower);
const dHi = Math.abs(res.ciU - py.ci_upper);
const TOL = 1e-4;
const ok = dEst < TOL && dLo < TOL && dHi < TOL;

console.log(`JS  est=${res.est.toFixed(6)} ci=[${res.ciL.toFixed(6)},${res.ciU.toFixed(6)}] k=${res.k}`);
console.log(`PY  est=${py.est.toFixed(6)} ci=[${py.ci_lower.toFixed(6)},${py.ci_upper.toFixed(6)}] k=${py.k}`);
console.log(`Δest=${dEst.toExponential(2)} Δlo=${dLo.toExponential(2)} Δhi=${dHi.toExponential(2)}  ${ok ? "PASS" : "FAIL"}`);
process.exit(ok ? 0 : 1);
