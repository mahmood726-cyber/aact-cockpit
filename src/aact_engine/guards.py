"""Data-quality guards informed by lessons.md.

Each guard is a pure function called at the row/result boundary so failures are
legible and testable in isolation.
"""
from __future__ import annotations

import re

_NEGATION_RE = re.compile(r"\b(not|non|never)\b", re.IGNORECASE)


def reject_negated_count(text: str, number_start: int, window: int = 30) -> bool:
    """Return True if the number at ``text[number_start:]`` should be REJECTED
    because the preceding context negates it.

    Guards against the lessons.md "Not Randomized 1,807" class: a regex that
    matches "<number> <metric>" or "<metric> <number>" silently captures a
    negated count. We scan the ``window`` characters preceding the number for
    not/non/never (including glued forms like ``non-``).

    Example:
        "Not Randomized 1,807"  -> rejected (True)
        "Deaths 1,807"          -> accepted (False)
    """
    if number_start <= 0:
        return False
    pre = text[max(0, number_start - window):number_start]
    # glued negation like "non-randomized"
    if re.search(r"\bnon-?\w", pre, re.IGNORECASE):
        return True
    return bool(_NEGATION_RE.search(pre))


def normalize_intervention_type(t: str | None) -> str:
    """AACT intervention_type values are lowercase (drug, device, biological).
    Normalize defensively before comparison."""
    return (t or "").strip().lower()


def assert_columns_exist(con, table: str, columns) -> None:
    """Header-drift guard: confirm every required column exists before a SELECT.

    AACT column names shift between snapshots; this fails closed with a clear
    diff rather than producing a Binder error mid-query.
    """
    have = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table],
        ).fetchall()
    }
    missing = [c for c in columns if c not in have]
    if missing:
        raise KeyError(
            f"Table '{table}' is missing required columns {missing}. "
            f"Present: {sorted(have)[:12]}..."
        )


# --------------------------------------------------------------------------- #
# Field-semantics registry for the cohort/effect eligibility filters.
#
# Companion to aact_engine.audits.FLAG_META (which documents the audit boolean
# flags). Documents what each cohort filter VALUE actually selects, so the
# eligibility is legible, and pairs with assert_value_present() to fail closed if
# a snapshot renames/recases a value (the filter would otherwise silently match
# nothing or the wrong set).
# --------------------------------------------------------------------------- #
COHORT_FIELDS = {
    "study_type = 'interventional'":
        "keeps interventional trials only; EXCLUDES observational and expanded-access records",
    "allocation = 'randomized'":
        ("keeps randomized designs; trials with a NULL/absent allocation are EXCLUDED "
         "(missing is not the same as non-randomized), as are 'N/A' and 'Non-Randomized'"),
    "results_first_posted_date IS NOT NULL":
        ("keeps trials that have POSTED results on ClinicalTrials.gov; a registered trial "
         "without posted results is excluded (this is a results-bearing cohort, not all trials)"),
}

# selection semantics of effect_extraction (documented, not a value filter)
EFFECT_SELECTION_NOTES = (
    "[field-semantics] one record per trial (the first usable analysis for the chosen endpoint); "
    "p-value-only analyses with no estimate+CI are dropped; arms are mapped to "
    "experimental-vs-comparator and the endpoint is keyword-classified from the outcome title."
)


def cohort_field_notes() -> list[str]:
    """The documented eligibility semantics, for surfacing on a cohort result."""
    return [f"{expr} — {meaning}" for expr, meaning in COHORT_FIELDS.items()]


def assert_value_present(con, table: str, column: str, value: str) -> int:
    """Value-drift guard: fail closed if `lower(table.column) = value` matches no
    rows. AACT recases/renames categorical values between snapshots; a filter that
    silently matches nothing is worse than an error. Returns the row count."""
    n = con.execute(
        f"SELECT count(*) FROM {table} WHERE lower(CAST({column} AS VARCHAR)) = ?",
        [value.lower()],
    ).fetchone()[0]
    if n == 0:
        raise ValueError(
            f"AACT value-drift guard: no rows where {table}.{column} = {value!r} "
            f"(case-insensitive). The snapshot may have renamed/recased this value; "
            f"the eligibility filter would silently select nothing."
        )
    return n


def assert_nonempty(rows, context: str):
    """>0 rows before analysis. Returns rows unchanged; raises if empty."""
    if not rows:
        raise ValueError(f"No rows for analysis: {context}")
    return rows


def enforce_derived_hr_null_ci(yi, sei, ci_lower, ci_upper, derived: bool):
    """Derived-effect rule (lessons.md): if yi/sei were reconstructed (e.g. from
    2x2 counts or a point estimate without a reported CI), the natural-scale CI
    must be nulled so a synthesized SE is never mistaken for a reported CI.
    Returns possibly-adjusted (ci_lower, ci_upper).
    """
    if derived:
        return None, None
    return ci_lower, ci_upper


__all__ = [
    "reject_negated_count",
    "normalize_intervention_type",
    "assert_columns_exist",
    "assert_nonempty",
    "enforce_derived_hr_null_ci",
    "COHORT_FIELDS",
    "EFFECT_SELECTION_NOTES",
    "cohort_field_notes",
    "assert_value_present",
]
