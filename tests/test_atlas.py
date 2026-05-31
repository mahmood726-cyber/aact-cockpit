"""Registry meta-epidemiology atlas capsule: generation, self-audit, invariants.

Uses a synthetic atlas dict (no warehouse needed) so it runs in CI. The engine
that produces real atlases (aact_engine.metaepi) is exercised separately when a
warehouse is present.
"""
import json
from pathlib import Path

import pytest

from aact_cockpit.capsule.generate_atlas_capsule import (
    render, compute_self_audit, draft_e156_body,
)

ROOT = Path(__file__).resolve().parents[1]


def _atlas():
    return {
        "kind": "atlas", "snapshot_date": "2026-04-12",
        "provenance": {"snapshot_date": "2026-04-12", "source": "AACT"},
        "scope": {"n_analyses": 1000, "n_trials": 400, "n_significant": 368,
                  "pct_significant": 36.8, "median_effect": 1.07, "pct_favor_low": 42.2},
        "by_sponsor": [
            {"sponsor_class": "INDUSTRY", "n": 600, "n_sig": 240, "pct_sig": 40.0},
            {"sponsor_class": "OTHER", "n": 300, "n_sig": 78, "pct_sig": 26.0},
            {"sponsor_class": "NIH", "n": 100, "n_sig": 22, "pct_sig": 22.0},
        ],
        "by_size": [
            {"bin": "<100", "n": 300, "median_abs_logeffect": 0.49, "pct_sig": 24.9},
            {"bin": "100-499", "n": 400, "median_abs_logeffect": 0.46, "pct_sig": 33.1},
            {"bin": "500-1999", "n": 200, "median_abs_logeffect": 0.32, "pct_sig": 44.0},
            {"bin": ">=2000", "n": 100, "median_abs_logeffect": 0.20, "pct_sig": 36.9},
        ],
        "effect_hist": [
            {"center": -0.4, "count": 50}, {"center": -0.2, "count": 200},
            {"center": 0.0, "count": 400}, {"center": 0.2, "count": 180},
            {"center": 0.4, "count": 40},
        ],
    }


def test_render_ok():
    r = render(_atlas())
    assert r["validation"]["ok"]
    assert r["tier"] in ("bronze", "silver", "gold")
    assert "__AACT_CAPSULE_JSON__" not in r["html"]
    assert r["capsule"]["slug"] == "registry-meta-epidemiology-atlas"


def test_self_audit_all_pass_on_clean_input():
    audit = compute_self_audit(_atlas())
    assert all(v == "pass" for v in audit["atlas_stats"].values()), audit["atlas_stats"]
    # reconciled + reproducible but no external rerun -> silver
    assert audit["checks"]["dashboard_match"] == "pass"
    assert audit["checks"]["analysis_rerun"] == "not-run"


def test_self_audit_catches_bad_proportion():
    a = _atlas()
    a["by_sponsor"][0]["pct_sig"] = 140.0  # impossible
    audit = compute_self_audit(a)
    assert audit["atlas_stats"]["proportions_valid"] == "fail"
    assert audit["checks"]["dashboard_match"] == "fail"


def test_self_audit_catches_nonreconciling_subgroups():
    a = _atlas()
    a["by_sponsor"][0]["n"] = 10_000  # exceeds total -> cannot be a subset
    audit = compute_self_audit(a)
    assert audit["atlas_stats"]["sponsor_reconciles"] == "fail"


def test_self_audit_catches_significance_inconsistency():
    a = _atlas()
    a["scope"]["pct_significant"] = 90.0  # contradicts n_sig/n_analyses
    audit = compute_self_audit(a)
    assert audit["atlas_stats"]["significance_consistent"] == "fail"


def test_e156_body_is_valid_and_156():
    body = draft_e156_body(_atlas())
    assert len(body.split()) <= 156
    # the headline numbers must appear
    assert "36.8 percent" in body
    assert "5,136" not in body  # synthetic trial count is 400, not the real dump
    assert "400 trials" in body or "400" in body


def test_displayed_proportions_match_counts():
    """Every printed pct_sig must equal round(100*n_sig/n,1) — the JS self-consistency
    check relies on this; assert it in Python too."""
    a = _atlas()
    for g in a["by_sponsor"]:
        assert abs(round(100.0 * g["n_sig"] / g["n"], 1) - g["pct_sig"]) <= 0.05


def test_no_none_or_nan_leak():
    r = render(_atlas())
    script = r["html"].split("<script>")[1]
    assert "None" not in script
    assert "NaN" not in r["html"]
    assert "Infinity" not in r["html"]
    assert "n participants" not in r["html"]
