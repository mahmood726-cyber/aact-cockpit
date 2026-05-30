// NMA numeric witness: extract the capsule's own JS NMA engine + CAPSULE data,
// run nmaFit() under Node, and assert it reproduces the Python-embedded NMA
// (HR vs reference within 1e-4, tau^2 within 1e-4, SUCRA within 0.03).
//
// Usage: node tests/node/nma_check.mjs <nma-capsule.html>
import { readFileSync } from "node:fs";

const file = process.argv[2];
if (!file) { console.error("usage: node nma_check.mjs <nma-capsule.html>"); process.exit(2); }
const html = readFileSync(file, "utf8");

const capLine = html.split("\n").find(l => l.trimStart().startsWith("const CAPSULE ="));
if (!capLine) { console.error("CAPSULE const not found"); process.exit(2); }
const CAPSULE = JSON.parse(capLine.slice(capLine.indexOf("=") + 1).trim().replace(/;\s*$/, ""));

const startTok = "const Z = 1.959963984540054;";
const endTok = "// ---- state ----";
const si = html.indexOf(startTok), ei = html.indexOf(endTok);
if (si < 0 || ei < 0 || ei < si) { console.error("engine block not located"); process.exit(2); }
const engine = html.slice(si, ei);

const runner = new Function("CAPSULE", engine + "\nreturn nmaFit(CAPSULE.contrasts, CAPSULE.reference);");
const res = runner(CAPSULE);
const py = CAPSULE.nma;

let maxHR = 0, maxSU = 0;
for (const t of py.treatments) {
  maxHR = Math.max(maxHR, Math.abs(res.rel_to_ref[t].est - py.rel_to_ref[t].est));
  maxSU = Math.max(maxSU, Math.abs(res.sucra[t] - py.sucra[t]));
}
const dTau = Math.abs(res.tau2 - py.tau2);
const ok = maxHR < 1e-4 && dTau < 1e-4 && maxSU < 0.03;

console.log(`JS tau2=${res.tau2.toFixed(5)}  PY tau2=${py.tau2.toFixed(5)}  Δtau2=${dTau.toExponential(2)}`);
console.log(`max ΔHR(vs ref)=${maxHR.toExponential(2)}  max ΔSUCRA=${maxSU.toFixed(4)}`);
for (const t of py.treatments)
  console.log(`  ${t.padEnd(12)} JS HR=${res.rel_to_ref[t].est.toFixed(4)} SUCRA=${(res.sucra[t]*100).toFixed(0)}%  | PY HR=${py.rel_to_ref[t].est.toFixed(4)} SUCRA=${(py.sucra[t]*100).toFixed(0)}%`);
console.log(ok ? "PASS" : "FAIL");
process.exit(ok ? 0 : 1);
