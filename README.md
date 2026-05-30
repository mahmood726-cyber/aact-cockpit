# AACTCockpit

A local, DuckDB-backed cockpit for **large-scale ClinicalTrials.gov / AACT analysis** that
turns a research question into a **self-auditing e156 capsule** — fully inside the existing
discipline gates (workbook → Sentinel → assurance badge → Overmind).

It unifies the ~12 scattered AACT loaders across the portfolio behind **one `aact_engine`**.

## Architecture

```
AACT snapshot (49 pipe-delimited .txt)  --ingest(once)-->  aact_<date>.duckdb (~2 GB)
        |
   aact_engine        cohort_search -> get_outcome_analyses -> effect_extraction
        |              (every result carries snapshot provenance)
        |  EffectsDataset (frozen contract: src/aact_engine/contracts.py)
   FastAPI cockpit (localhost)   PICO form -> cohort -> effects -> build
        |
   capsule generator   js_val + self-audit + e156 body  (templates/aact_pairwise_capsule.html)
        |
   {slug}-capsule.html   offline · Bronze/Silver/Gold · live JS engine · R cross-val · inspector
        |
   workbook append (append-only) · Sentinel rules · signed assurance · Overmind aact_capsule profile
```

## Setup

```bash
pip install -e .            # duckdb, fastapi, uvicorn, pydantic
python scripts/build_warehouse.py     # one-time ingest (~100s); idempotent rerun is a no-op
```

The snapshot is discovered via `AACT_HOME` or candidate bases (F:/D:/C:); fails closed if absent.
The corrected DuckDB dialect (`quote='"', escape='"'`) is in `src/aact_engine/schema.py`.

## Use

**Interactive (the cockpit GUI):**
```bash
python scripts/serve.py        # http://127.0.0.1:8000
```
PICO → search cohort & extract effects → choose estimator → build capsule → open it.

**Headless / batch (large-scale):**
```bash
python scripts/extract_effects.py --population "heart failure" --outcome "all-cause mortality" \
    --endpoint acm --estimand "hazard ratio for all-cause mortality" --out effects/cardio_mortality.json
python scripts/make_capsule.py --in effects/cardio_mortality.json --out capsules
```

## Discipline

- **Self-audit → tier** reuses E156 `compute_tier`; statistical gotchas (no DL for k<10, HKSJ floor,
  t-PI, log-scale pooling) are named checks. A failed invariant collapses to ≤ Bronze.
- **Placeholder-leak defense (3 layers):** `js_val()` (None→null, raises on NaN) → emit-time scan →
  Sentinel `P1-aact-capsule-leak`.
- **Workbook append is append-only** and never touches any existing `YOUR REWRITE`; dry-run by default.
- **Sentinel rules** (in `F:\Sentinel`): `P0-aact-snapshot-provenance`, `P1-aact-capsule-leak`,
  `P1-capsule-stats-invariant` — scoped to `*-capsule.html`, zero findings elsewhere.
- **Overmind** `aact_capsule` verification profile (build · tests · numeric-regression · browser · regression).

## Tests

```bash
python -m pytest                                             # 48 tests
node tests/node/repool_check.mjs capsules/<slug>/<slug>-capsule.html   # JS engine ↔ Python within 1e-4
```

## Reused (not reinvented)

`AlBurhan parse_effect` · `CardioOracle` taxonomy · `rapidmeta` `pool_dl` math ·
flagship `sglt2-hf-capsule.html` engine · E156 `validate_e156`/`compute_tier`/`sign_badge`.

## Status

MVP vertical = **cardiology all-cause-mortality pairwise MA** proven end-to-end (533 HF RCTs →
25 with extractable effects → pooled HR 0.94, 95% CI 0.91–0.97, I²=17%, Silver tier).
Next verticals (renal / MACE / NMA / DTA / survival) are config + a new template, not new engine code.
