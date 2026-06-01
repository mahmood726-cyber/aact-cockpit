import fs from 'node:fs';

// Witness for ct.gov registry-audit capsules. Re-checks the internal
// reconciliation invariants from the embedded JSON: subgroups partition the
// eligible set exactly, every proportion is a valid percentage, every group
// denominator is positive.
const html = fs.readFileSync(process.argv[2], 'utf8');
const m = html.match(/const CAPSULE = (\{[\s\S]*?\});\s*\n/);
if (!m) { console.error('no CAPSULE json'); process.exit(2); }
const C = JSON.parse(m[1]);

const fails = [];
const sum = C.groups.reduce((a, g) => a + g.n, 0);
if (sum !== C.scope.n_eligible)
  fails.push(`partition: sum(group n)=${sum} != n_eligible=${C.scope.n_eligible}`);
for (const g of C.groups) {
  if (!(g.n > 0)) fails.push(`group ${g.label} has non-positive n`);
  for (const [k, p] of Object.entries(g.metrics))
    if (!(p >= 0 && p <= 100)) fails.push(`group ${g.label} ${k}=${p} out of [0,100]`);
  if (!(C.primary_metric in g.metrics))
    fails.push(`group ${g.label} missing primary metric ${C.primary_metric}`);
}

const ok = fails.length === 0;
console.log(JSON.stringify({ ok, audit: C.slug, n_eligible: C.scope.n_eligible, groups: C.groups.length, fails }));
process.exit(ok ? 0 : 1);
