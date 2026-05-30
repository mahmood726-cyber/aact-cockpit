"""Trial Sequential Analysis engine + capsule."""
from __future__ import annotations

import math
import re

import pytest

from aact_cockpit.capsule.tsa import cumulative, Z_ALPHA_2
from aact_cockpit.capsule import generate_tsa_capsule as gt


def _studies(hrs):
    """hrs: list of (year, hr, lci, uci)."""
    out = []
    for i, (yr, hr, lo, hi) in enumerate(hrs):
        out.append({"nct": f"NCT0{1000000+i}", "name": f"Trial {i+1}", "year": yr,
                    "hr": hr, "lci": lo, "uci": hi, "inc": True})
    return out


def test_cumulative_information_monotone_and_obf():
    s = _studies([(2015, 0.80, 0.65, 0.98), (2017, 0.78, 0.66, 0.92),
                  (2019, 0.82, 0.72, 0.93), (2021, 0.85, 0.77, 0.94)])
    res = cumulative(s)
    infos = [st["info"] for st in res["steps"]]
    assert all(b >= a - 1e-9 for a, b in zip(infos, infos[1:]))  # non-decreasing info
    # OBF boundary formula z_alpha/sqrt(t)
    for st in res["steps"]:
        assert st["obf"] == pytest.approx(Z_ALPHA_2 / math.sqrt(st["t"]), rel=1e-9)
    assert res["deff"] >= 1.0
    assert res["ris"] > 0


def test_chronological_order_independent_of_input_order():
    s = _studies([(2019, 0.82, 0.72, 0.93), (2015, 0.80, 0.65, 0.98)])
    import random
    s2 = list(reversed(s))
    r1, r2 = cumulative(s), cumulative(s2)
    assert [st["est"] for st in r1["steps"]] == [st["est"] for st in r2["steps"]]


def test_firm_crossing_detected():
    # many concordant strong effects -> boundary crossed
    s = _studies([(2010+i, 0.70, 0.60, 0.82) for i in range(8)])
    res = cumulative(s)
    assert res["crossed"] is not None
    assert res["conclusion"] == "firm"


def _dataset(hrs):
    studies = []
    for i, (yr, hr, lo, hi) in enumerate(hrs):
        studies.append({"nct_id": f"NCT0{1000000+i}", "study_label": f"Trial {i+1}", "year": yr,
                        "point_estimate": hr, "ci_lower": lo, "ci_upper": hi,
                        "arm_experimental": {"label": "Drug"}, "arm_comparator": {"label": "Placebo"}})
    return {"pico": {"population": "heart failure", "outcome": "all-cause mortality",
                     "intervention": "drug", "comparator": "placebo"},
            "snapshot_date": "2026-04-12", "measure": "HR",
            "primary_estimand": "hazard ratio for all-cause mortality",
            "provenance": {"source": "AACT", "snapshot_date": "2026-04-12"},
            "studies": studies, "notes": []}


def test_tsa_capsule_no_leak_and_validates():
    ds = _dataset([(2014+i, 0.80, 0.66, 0.97) for i in range(6)])
    res = gt.render(ds)
    script = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", res["html"], re.DOTALL))
    assert "null" in script and re.search(r"[,:\[(]\s*None\b", script) is None
    assert "NaN" not in script and "__AACT_" not in res["html"]
    assert res["validation"]["ok"] and res["validation"]["sentence_count"] == 7
    assert res["capsule"]["self_audit"]["aact_stats"]["obf_boundary_formula"] == "pass"
    assert res["capsule"]["kind"] == "tsa"


def test_tsa_emit(tmp_path):
    ds = _dataset([(2014+i, 0.80, 0.66, 0.97) for i in range(6)])
    man = gt.emit(ds, tmp_path)
    assert man["slug"].startswith("tsa-")
    assert (tmp_path / man["slug"] / f"{man['slug']}-capsule.html").is_file()
    assert man["conclusion"] in ("firm", "insufficient", "ris_reached_null")
