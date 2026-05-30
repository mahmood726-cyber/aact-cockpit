"""Effect-size conversions vs hand calc + param_type classification."""
from __future__ import annotations

import math

import pytest

from aact_engine.effects import (
    Z95, hr_to_yi_sei, or_to_yi_sei, counts_to_yi_sei,
    classify_param_type, extract_effect,
)


def test_hr_log_scale_vs_handcalc():
    yi, sei = hr_to_yi_sei(0.75, 0.60, 0.94)
    assert yi == pytest.approx(math.log(0.75), abs=1e-12)
    assert sei == pytest.approx((math.log(0.94) - math.log(0.60)) / (2 * Z95), abs=1e-12)


def test_or_log_scale():
    yi, sei = or_to_yi_sei(1.5, 1.1, 2.0)
    assert yi == pytest.approx(math.log(1.5), abs=1e-12)
    assert sei > 0


def test_counts_zero_cell_continuity_only_when_zero():
    # no zero cell: no 0.5 added
    yi, sei = counts_to_yi_sei(20, 100, 30, 100)
    a, b, c, d = 20, 80, 30, 70
    assert yi == pytest.approx(math.log(a * d / (b * c)), abs=1e-12)
    # zero cell: 0.5 added, result finite
    yi0, sei0 = counts_to_yi_sei(0, 100, 10, 100)
    assert math.isfinite(yi0) and math.isfinite(sei0)


@pytest.mark.parametrize("pt,method,expect", [
    ("Hazard Ratio (HR)", "Cox Proportional Hazards", "HR"),
    ("Odds Ratio (OR)", "Regression, Logistic", "OR"),
    ("Risk Ratio (RR)", None, "RR"),
    ("Mean Difference (Net)", None, "MD"),
    (None, "Cox Proportional Hazards", "HR"),
    ("Slope", None, None),
    (None, "Log Rank", None),
])
def test_classify_param_type(pt, method, expect):
    assert classify_param_type(pt, method) == expect


def test_extract_effect_skips_pvalue_only():
    row = {"nct_id": "NCT1", "param_type": None, "param_value": None,
           "ci_lower_limit": None, "ci_upper_limit": None, "method": "Log Rank"}
    assert extract_effect(row) is None


def test_extract_effect_builds_record():
    row = {
        "nct_id": "NCT1", "study_label": "Trial 1", "year": 2019,
        "endpoint": "acm", "param_type": "Hazard Ratio (HR)", "param_value": "0.83",
        "ci_lower_limit": "0.71", "ci_upper_limit": "0.97", "ci_percent": "95.0",
        "method": "Cox Proportional Hazards", "outcome_id": "10",
        "outcome_analysis_id": "100",
    }
    rec = extract_effect(row)
    assert rec is not None
    assert rec.measure_type == "HR"
    assert rec.yi == pytest.approx(math.log(0.83), abs=1e-12)
    assert rec.derived is False
    assert rec.ci_lower == 0.71 and rec.ci_upper == 0.97
    assert rec.nct_id == rec.source_nct_id == "NCT1"
