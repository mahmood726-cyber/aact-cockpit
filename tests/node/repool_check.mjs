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

// 3) run pool() + the full diagnostic suite using the capsule's own code
const runner = new Function("CAPSULE", engine + "\nreturn {" +
  "pool:pool(CAPSULE.studies), egger:egger(CAPSULE.studies), loo:leaveOneOut(CAPSULE.studies)," +
  "trimfill:trimFill(CAPSULE.studies), influence:influence(CAPSULE.studies), metareg:metaRegression(CAPSULE.studies)};");
const res = runner(CAPSULE);

const py = CAPSULE.pooled;
const dEst = Math.abs(res.pool.est - py.est);
const dLo = Math.abs(res.pool.ciL - py.ci_lower);
const dHi = Math.abs(res.pool.ciU - py.ci_upper);
const TOL = 1e-4;

const diag = CAPSULE.diagnostics || {};
let dEg = 0, dLoo = 0, dTf = 0, dInf = 0, dMr = 0;
if (diag.egger && res.egger) dEg = Math.abs(res.egger.intercept - diag.egger.intercept);
if (diag.loo && diag.loo.length)
  for (let i = 0; i < diag.loo.length; i++) dLoo = Math.max(dLoo, Math.abs((res.loo[i]?.est ?? 0) - diag.loo[i].est));
let tfk = true;
if (diag.trimfill && res.trimfill) {
  tfk = res.trimfill.k0 === diag.trimfill.k0;
  dTf = Math.abs(res.trimfill.est - diag.trimfill.est);
}
if (diag.influence && diag.influence.length)
  for (let i = 0; i < diag.influence.length; i++)
    dInf = Math.max(dInf, Math.abs((res.influence[i]?.cook ?? 0) - diag.influence[i].cook),
                          Math.abs((res.influence[i]?.hat ?? 0) - diag.influence[i].hat));
if (diag.metareg && res.metareg) dMr = Math.abs(res.metareg.b1 - diag.metareg.b1);

const ok = dEst < TOL && dLo < TOL && dHi < TOL && dEg < 1e-6 && dLoo < 1e-4
  && tfk && dTf < 1e-6 && dInf < 1e-6 && dMr < 1e-9;

console.log(`pool Δest=${dEst.toExponential(2)} (k=${res.pool.k})  egger Δ=${dEg.toExponential(2)}  loo Δ=${dLoo.toExponential(2)}`);
console.log(`trimfill k0 match=${tfk} Δest=${dTf.toExponential(2)}  influence Δ=${dInf.toExponential(2)}  metareg Δb1=${dMr.toExponential(2)}`);
console.log(ok ? "PASS" : "FAIL");
process.exit(ok ? 0 : 1);
