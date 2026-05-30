"""Effect-size conversion + AACT param_type classification.

The converters are lifted from AlBurhan/alburhan/ingest/parser.py (already unit
tested), with scipy.stats.norm.ppf replaced by the literal two-sided 95% z so
the engine has no scipy dependency. Z95 is exact to machine precision.
"""
from __future__ import annotations

import math

from .contracts import EffectRecord, ArmEffect
from .guards import enforce_derived_hr_null_ci

# Two-sided 95% normal quantile: stats.norm.ppf(0.975)
Z95 = 1.959963984540054


def _z(conf_level: float) -> float:
    if abs(conf_level - 0.95) < 1e-9:
        return Z95
    # Rare non-95% CIs: fall back to a small rational approx via math.
    # (Acklam's inverse-normal is overkill; AACT CIs are ~always 95%.)
    raise ValueError(f"Unsupported confidence level {conf_level}; only 95% wired.")


def hr_to_yi_sei(hr, ci_lo, ci_hi, conf_level=0.95):
    return math.log(hr), (math.log(ci_hi) - math.log(ci_lo)) / (2 * _z(conf_level))


def or_to_yi_sei(or_val, ci_lo, ci_hi, conf_level=0.95):
    return math.log(or_val), (math.log(ci_hi) - math.log(ci_lo)) / (2 * _z(conf_level))


def rr_to_yi_sei(rr, ci_lo, ci_hi, conf_level=0.95):
    return math.log(rr), (math.log(ci_hi) - math.log(ci_lo)) / (2 * _z(conf_level))


def md_to_yi_sei(md, ci_lo, ci_hi, conf_level=0.95):
    return md, (ci_hi - ci_lo) / (2 * _z(conf_level))


def counts_to_yi_sei(events_t, total_t, events_c, total_c):
    """2x2 -> log(OR) with SE via Woolf. 0.5 continuity ONLY if a cell is 0
    (lessons.md: unconditional 0.5 biases OR toward 1)."""
    a, b = events_t, total_t - events_t
    c, d = events_c, total_c - events_c
    if any(x == 0 for x in (a, b, c, d)):
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    return math.log(a * d / (b * c)), math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)


_PARAM_TYPE_RULES = (
    ("HR", ("hazard ratio", "hr")),
    ("OR", ("odds ratio",)),
    ("RR", ("risk ratio", "relative risk", "rate ratio")),
    ("MD", ("mean difference", "ls mean difference", "least squares mean difference")),
)


def classify_param_type(param_type: str | None, method: str | None = None) -> str | None:
    """Map AACT's human param_type/method strings to a canonical measure type.
    Returns None when it cannot be classified confidently — caller SKIPS the row
    (never guess; lessons.md)."""
    pt = (param_type or "").strip().lower()
    mt = (method or "").strip().lower()
    if not pt:
        # Sometimes only the method hints (e.g. Cox -> HR), but without an
        # estimate value the row is skipped upstream anyway; be conservative.
        if "cox" in mt or "hazard" in mt:
            return "HR"
        return None
    for canon, needles in _PARAM_TYPE_RULES:
        for nd in needles:
            if nd in pt:
                return canon
    return None


def _to_float(x):
    if x is None:
        return None
    try:
        v = float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None
    return v if math.isfinite(v) else None


def extract_effect(row: dict) -> EffectRecord | None:
    """Build an EffectRecord from a joined outcome_analyses row dict, or None if
    the row lacks a usable estimate+CI (e.g. p-value-only rows).

    Expected keys: nct_id, study_label, year, endpoint, param_type, param_value,
    ci_lower_limit, ci_upper_limit, ci_percent, method, outcome_id,
    outcome_analysis_id, arm_experimental (ArmEffect|None), arm_comparator.
    """
    measure = classify_param_type(row.get("param_type"), row.get("method"))
    if measure is None:
        return None

    est = _to_float(row.get("param_value"))
    ci_lo = _to_float(row.get("ci_lower_limit"))
    ci_hi = _to_float(row.get("ci_upper_limit"))
    if est is None or ci_lo is None or ci_hi is None:
        return None  # p-value-only / no-CI rows are skipped
    if est <= 0 or ci_lo <= 0 or ci_hi <= 0:
        # ratio measures must be positive to take logs
        if measure in ("HR", "OR", "RR"):
            return None
    if ci_lo >= ci_hi:
        return None

    conf = (_to_float(row.get("ci_percent")) or 95.0) / 100.0
    try:
        if measure == "HR":
            yi, sei = hr_to_yi_sei(est, ci_lo, ci_hi, conf)
        elif measure == "OR":
            yi, sei = or_to_yi_sei(est, ci_lo, ci_hi, conf)
        elif measure == "RR":
            yi, sei = rr_to_yi_sei(est, ci_lo, ci_hi, conf)
        else:  # MD
            yi, sei = md_to_yi_sei(est, ci_lo, ci_hi, conf)
    except (ValueError, ZeroDivisionError):
        return None
    if not (math.isfinite(yi) and math.isfinite(sei)) or sei <= 0:
        return None

    derived = False  # this path uses a reported CI, not a reconstruction
    ci_lo_out, ci_hi_out = enforce_derived_hr_null_ci(yi, sei, ci_lo, ci_hi, derived)

    return EffectRecord(
        nct_id=row["nct_id"],
        study_label=row.get("study_label") or row["nct_id"],
        year=row.get("year"),
        endpoint=row.get("endpoint", "other"),
        measure_type=measure,
        point_estimate=est,
        ci_lower=ci_lo_out,
        ci_upper=ci_hi_out,
        ci_percent=(_to_float(row.get("ci_percent")) or 95.0),
        yi=yi,
        sei=sei,
        derived=derived,
        source_nct_id=row["nct_id"],
        source_outcome_id=str(row.get("outcome_id", "")),
        source_outcome_analysis_id=str(row.get("outcome_analysis_id", "")),
        source_method=row.get("method") or "",
        arm_experimental=row.get("arm_experimental"),
        arm_comparator=row.get("arm_comparator"),
    )


__all__ = [
    "Z95", "hr_to_yi_sei", "or_to_yi_sei", "rr_to_yi_sei", "md_to_yi_sei",
    "counts_to_yi_sei", "classify_param_type", "extract_effect",
]
