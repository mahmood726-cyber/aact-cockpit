# Contributing

## Branch & review flow

Trivial, low-risk changes (docs, a new `analyses/*.json`, a new pairwise vertical)
may go straight to `master`. **Changes to a statistical engine** —
`src/aact_cockpit/capsule/{pooling,tsa,nma}.py`, `src/aact_engine/{effects,nma}.py`,
or any capsule template's JS engine — should go through a **PR** so the
`/code-review` gate and CI run *before* merge. These are correctness-critical and
benefit from a second look (the post-hoc review of the NMA engine, for example,
found a latent `lower_is_better` ranking bug and a Bucher independence gap).

## The cross-validation invariant (do not break)

Every capsule's numbers must agree **three ways**, and CI enforces it on every push:

1. **Python self-audit** computes the result and the assurance checks.
2. **The live in-browser JS engine** must reproduce the Python result bit-for-bit
   (deterministic; SUCRA uses a 32-bit xorshift mirrored in both). Verified by the
   Node witnesses in `tests/node/*.mjs` via `scripts/verify_docs.py`.
3. **The R reference package** (`metafor` for pairwise/TSA, `netmeta` + a manual
   `metafor` Bucher for NMA) must match within tolerance. Verified by
   `scripts/r_validate*.R`.

If you change an engine, re-run locally before pushing:

```bash
python -m pytest -q
python scripts/verify_docs.py docs
R_LIBS_USER="$HOME/R-libs" Rscript scripts/r_validate.R docs
R_LIBS_USER="$HOME/R-libs" Rscript scripts/r_validate_nma.R docs
```

## Honesty rules

- Never claim a tier the evidence doesn't support. A consistency `warn` caps at
  Bronze (surfaced), a hard failure is `none`. Gold needs an independent R rerun
  **and** human sign-off.
- State network/analysis limitations in the capsule (e.g. "tree network —
  consistency not assessable"; "mixes treatment lines/populations") rather than
  letting the ranking imply more than the data shows.
