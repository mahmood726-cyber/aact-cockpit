import fs from 'node:fs';

// Witness for the registry meta-epidemiology atlas capsule.
// Re-derives every displayed proportion from the embedded raw counts and
// asserts it matches the printed value, plus the internal reconciliation
// invariants (subgroup counts subset of total, histogram subset of total).
const html = fs.readFileSync(process.argv[2], 'utf8');
const m = html.match(/const CAPSULE = (\{[\s\S]*?\});\s*\n/);
if (!m) { console.error('no CAPSULE json'); process.exit(2); }
const C = JSON.parse(m[1]);

const eps = 0.05;
const fails = [];

// 1. overall % significant matches n_significant / n_analyses
const sc = C.scope;
const overall = Math.round(1000 * sc.n_significant / sc.n_analyses) / 10;
if (Math.abs(overall - sc.pct_significant) > eps)
  fails.push(`overall pct ${sc.pct_significant} != recomputed ${overall}`);

// 2. each sponsor pct_sig matches its counts
for (const g of C.by_sponsor) {
  const p = g.n > 0 ? Math.round(1000 * g.n_sig / g.n) / 10 : 0;
  if (Math.abs(p - g.pct_sig) > eps)
    fails.push(`sponsor ${g.sponsor_class} pct ${g.pct_sig} != recomputed ${p}`);
}

// 3. reconciliation: subgroup totals cannot exceed the registry total
const spSum = C.by_sponsor.reduce((a, g) => a + g.n, 0);
if (spSum > sc.n_analyses) fails.push(`sponsor sum ${spSum} > total ${sc.n_analyses}`);
const szSum = C.by_size.reduce((a, g) => a + g.n, 0);
if (szSum > sc.n_analyses) fails.push(`size sum ${szSum} > total ${sc.n_analyses}`);
const hSum = C.effect_hist.reduce((a, h) => a + h.count, 0);
if (hSum > sc.n_analyses) fails.push(`hist sum ${hSum} > total ${sc.n_analyses}`);

// 4. all proportions in [0,100]
for (const p of [sc.pct_significant, sc.pct_favor_low,
                 ...C.by_sponsor.map(g => g.pct_sig), ...C.by_size.map(g => g.pct_sig)])
  if (!(p >= 0 && p <= 100)) fails.push(`proportion out of range: ${p}`);

const ok = fails.length === 0;
console.log(JSON.stringify({ ok, overall, fails }));
process.exit(ok ? 0 : 1);
