"""The vendored E156 helpers must match the canonical F:\\E156 versions exactly
(when canonical is available). Catches drift between the fork and the source."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aact_cockpit._vendor.e156_validate import validate as v_validate
from aact_cockpit._vendor.assurance import compute_tier as v_compute_tier

_BODIES = [
    ("In heart failure, does treatment change mortality? Twenty-five trials were "
     "aggregated. Effects were pooled on the log scale. The pooled HR was 0.95 "
     "(95% CI 0.92 to 0.98). Heterogeneity was modest. Findings are consistent "
     "with a small effect. Interpretation is limited by the snapshot."),
    "Too few sentences. Only two here.",
]
_CHECKSETS = [
    {"citation_cascade": "pass", "data_file_present": "pass", "code_runs": "pass",
     "dashboard_match": "pass", "claim_language": "pass", "analysis_rerun": "pass",
     "external_review": "pass"},
    {"citation_cascade": "pass", "data_file_present": "pass", "code_runs": "pass",
     "dashboard_match": "fail", "claim_language": "pass", "analysis_rerun": "not-run",
     "external_review": "not-run"},
    {"citation_cascade": "pass", "data_file_present": "pass", "code_runs": "not-run",
     "dashboard_match": "pass", "claim_language": "pass", "analysis_rerun": "not-run",
     "external_review": "not-run"},
]


def _canonical():
    for c in (r"F:\E156\scripts", r"C:\E156\scripts"):
        if (Path(c) / "validate_e156.py").is_file():
            if c not in sys.path:
                sys.path.insert(0, c)
            from validate_e156 import validate
            from build_assurance_jsons import compute_tier
            return validate, compute_tier
    return None


def test_vendor_validate_matches_canonical():
    canon = _canonical()
    if canon is None:
        pytest.skip("canonical F:\\E156 not available")
    c_validate, _ = canon
    for body in _BODIES:
        cv = c_validate(body, strict_words=True)
        vv = v_validate(body, strict_words=True)
        assert cv["ok"] == vv["ok"]
        assert cv["sentence_count"] == vv["sentence_count"]
        assert cv["word_count"] == vv["word_count"]


def test_vendor_compute_tier_matches_canonical():
    canon = _canonical()
    if canon is None:
        pytest.skip("canonical F:\\E156 not available")
    _, c_compute_tier = canon
    for checks in _CHECKSETS:
        assert c_compute_tier(checks) == v_compute_tier(checks)


def test_vendor_standalone():
    # vendored works without canonical
    r = v_validate(_BODIES[0], strict_words=True)
    assert r["ok"] and r["sentence_count"] == 7
    assert v_compute_tier(_CHECKSETS[0]) == "gold"
    assert v_compute_tier(_CHECKSETS[1]) == "none"
    assert v_compute_tier(_CHECKSETS[2]) == "silver"
