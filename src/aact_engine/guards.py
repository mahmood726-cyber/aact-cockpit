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
]
