"""Capsule generator: leak defense, pooling parity, badge tiers, body validity."""
from __future__ import annotations

import json
import math
import re

import pytest

from aact_cockpit.capsule import generate_capsule as gc
from aact_cockpit.capsule.pooling import (pool, diagnostics, egger, leave_one_out,
                                          meta_regression, influence, trim_and_fill)


def _yi(triples, years=None):
    out = []
    for i, (h, l, u) in enumerate(triples):
        d = {"hr": h, "lci": l, "uci": u, "nct": f"NCT0{i}", "name": f"Trial {i}", "inc": True}
        if years:
            d["year"] = years[i]
        out.append(d)
    return out


def test_meta_regression_trend():
    # effect drifts up with year -> positive slope
    items = _yi([(0.60, 0.50, 0.72), (0.70, 0.58, 0.85), (0.85, 0.72, 1.00),
                 (0.95, 0.80, 1.13), (1.05, 0.88, 1.25)],
                years=[2010, 2013, 2016, 2019, 2022])
    mr = meta_regression(items, [it["year"] for it in items])
    assert mr["k"] == 5 and mr["b1"] > 0 and 0.0 <= mr["r2"] <= 1.0
    # no years -> None
    assert meta_regression(_yi([(0.8, 0.6, 1.0), (0.9, 0.7, 1.1), (0.85, 0.7, 1.0)]),
                           [None, None, None]) is None


def test_influence_flags_outlier():
    items = _yi([(0.80, 0.74, 0.86), (0.82, 0.76, 0.89), (0.79, 0.73, 0.86),
                 (1.60, 1.40, 1.83)])  # last one is a clear outlier
    inf = influence(items)
    assert len(inf) == 4
    assert all(0 <= d["hat"] <= 1 for d in inf)
    assert inf[-1]["influential"] is True   # the outlier is flagged


def test_trim_and_fill_symmetric_zero():
    # symmetric set -> k0 == 0, adjusted == observed
    items = _yi([(0.70, 0.55, 0.89), (0.85, 0.70, 1.03), (1.00, 0.85, 1.18),
                 (1.18, 0.97, 1.43), (1.43, 1.12, 1.82)])
    tf = trim_and_fill(items)
    assert tf["k0"] == 0
    assert abs(tf["est"] - tf["est_observed"]) < 1e-9


def test_diagnostics_suite_complete():
    d = diagnostics(_yi([(0.8, 0.66, 0.97), (0.74, 0.6, 0.92), (0.83, 0.71, 0.97),
                         (0.9, 0.8, 1.02)], years=[2018, 2019, 2020, 2021]),
                    x_values=[2018, 2019, 2020, 2021])
    assert set(d) == {"egger", "loo", "trimfill", "influence", "metareg"}
    assert d["metareg"] is not None and d["trimfill"] is not None and len(d["influence"]) == 4


def _items(triples):
    return [{"hr": h, "lci": l, "uci": u, "nct": f"NCT0{i}", "name": f"Trial {i}", "inc": True}
            for i, (h, l, u) in enumerate(triples)]


def test_egger_computed_and_finite():
    import math
    d = diagnostics(_items([(0.80, 0.66, 0.97), (0.82, 0.70, 0.96), (0.78, 0.60, 1.01),
                            (0.85, 0.74, 0.98), (0.79, 0.65, 0.96)]))
    e = d["egger"]
    assert e["k"] == 5
    assert all(math.isfinite(e[k]) for k in ("intercept", "se", "t", "p"))
    assert 0.0 <= e["p"] <= 1.0
    assert len(d["loo"]) == 5
    for l in d["loo"]:
        assert l["lo"] < l["est"] < l["hi"]


def test_egger_needs_three():
    assert egger(_items([(0.8, 0.6, 1.0), (0.9, 0.7, 1.1)])) is None
    assert leave_one_out(_items([(0.8, 0.6, 1.0), (0.9, 0.7, 1.1)])) == []


def test_leave_one_out_each_omits_one():
    items = _items([(0.80, 0.66, 0.97), (0.74, 0.60, 0.92), (0.83, 0.71, 0.97), (0.90, 0.80, 1.02)])
    loo = leave_one_out(items)
    assert len(loo) == 4
    assert {l["omitted"] for l in loo} == {it["nct"] for it in items}


def test_capsule_embeds_diagnostics():
    # the e156 body + capsule payload carry Egger + LOO when k>=3
    ds = {
        "pico": {"population": "x", "outcome": "y"}, "snapshot_date": "2026-04-12",
        "primary_estimand": "HR for y", "measure": "HR",
        "provenance": {"source": "AACT"},
        "studies": [{"nct_id": f"NCT0{i}", "study_label": f"T{i}", "year": 2018 + i,
                     "point_estimate": h, "ci_lower": l, "ci_upper": u,
                     "arm_experimental": {"label": "drug"}, "arm_comparator": {"label": "placebo"}}
                    for i, (h, l, u) in enumerate([(0.8, 0.66, 0.97), (0.82, 0.7, 0.96),
                                                   (0.78, 0.6, 1.01), (0.85, 0.74, 0.98)])],
        "notes": [],
    }
    res = gc.render_capsule_html(ds)
    diag = res["capsule"]["diagnostics"]
    assert diag["egger"]["k"] == 4 and len(diag["loo"]) == 4
    assert "Egger" in res["body"]


def _dataset(k=5, measure="HR"):
    base = [(0.74, 0.65, 0.85), (0.75, 0.65, 0.86), (0.79, 0.69, 0.90),
            (0.82, 0.73, 0.92), (0.67, 0.52, 0.85), (0.90, 0.80, 1.02),
            (0.88, 0.75, 1.03), (1.00, 0.92, 1.09), (0.94, 0.81, 1.08),
            (0.85, 0.70, 1.03), (0.91, 0.80, 1.04), (0.70, 0.55, 0.90),
            (0.78, 0.62, 0.98), (0.95, 0.83, 1.09), (0.62, 0.38, 1.01)]
    studies = []
    for i in range(k):
        hr, lo, hi = base[i % len(base)]
        studies.append({
            "nct_id": f"NCT0{1000000+i}", "study_label": f"Trial {i+1}", "year": 2018+i,
            "point_estimate": hr, "ci_lower": lo, "ci_upper": hi,
            "arm_experimental": {"label": "Drug"}, "arm_comparator": {"label": "Placebo"},
        })
    return {
        "pico": {"population": "heart failure", "outcome": "all-cause mortality",
                 "intervention": "SGLT2 inhibitor", "comparator": "placebo"},
        "snapshot_date": "2026-04-12", "measure": measure,
        "primary_estimand": f"{measure} for all-cause mortality",
        "provenance": {"source": "ClinicalTrials.gov via AACT", "snapshot_date": "2026-04-12"},
        "studies": studies, "notes": [],
    }


def test_js_val_none_and_nan():
    assert gc.js_val(None) == "null"
    assert gc.js_val(1.5) == "1.5"
    with pytest.raises(ValueError):
        gc.js_val(float("nan"))


def test_no_none_or_nan_leak():
    res = gc.render_capsule_html(_dataset(5))
    script = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", res["html"], re.DOTALL))
    assert "null" in script
    assert re.search(r"[,:\[(]\s*None\b", script) is None
    assert "NaN" not in script and "Infinity" not in script
    assert "__AACT_" not in res["html"]


def test_pooling_matches_reference_dl():
    # our pool(DL) vs the rapidmeta pool_dl algorithm, recomputed inline
    ds = _dataset(5)
    items = [{"hr": s["point_estimate"], "lci": s["ci_lower"], "uci": s["ci_upper"], "inc": True}
             for s in ds["studies"]]
    r = pool(items, method="DL")
    # reference DL (validate_living_ma_portfolio.pool_dl math)
    data = [(math.log(i["hr"]), (math.log(i["uci"]) - math.log(i["lci"])) / (2 * 1.96)) for i in items]
    sW = sum(1 / s**2 for _, s in data)
    sWY = sum(y / s**2 for y, s in data)
    sWY2 = sum(y**2 / s**2 for y, s in data)
    sW2 = sum(1 / s**4 for _, s in data)
    Q = max(0, sWY2 - sWY**2 / sW); df = len(data) - 1
    tau2 = max(0, (Q - df) / (sW - sW2 / sW)) if Q > df else 0
    sWR = sum(1 / (s**2 + tau2) for _, s in data); sWRY = sum(y / (s**2 + tau2) for y, s in data)
    est_ref = math.exp(sWRY / sWR)
    assert r["est"] == pytest.approx(est_ref, abs=1e-4)


def test_badge_small_k_not_gold():
    res = gc.render_capsule_html(_dataset(3))
    assert res["tier"] in ("bronze", "silver")  # never gold without rerun+review
    assert res["capsule"]["self_audit"]["checks"]["analysis_rerun"] == "not-run"


def test_badge_dl_small_k_fails_to_none():
    # forcing DL with k<10 must flip estimator_for_k -> fail -> dashboard_match fail -> tier none
    res = gc.render_capsule_html(_dataset(4), method="DL")
    assert res["capsule"]["self_audit"]["aact_stats"]["estimator_for_k"] == "fail"
    assert res["capsule"]["self_audit"]["checks"]["dashboard_match"] == "fail"
    assert res["tier"] == "none"


def test_badge_gold_eligible():
    res = gc.render_capsule_html(_dataset(15), analysis_rerun="pass", external_review="pass")
    assert res["tier"] == "gold"


def test_e156_body_validates():
    res = gc.render_capsule_html(_dataset(6))
    assert res["validation"]["ok"] is True
    assert res["validation"]["sentence_count"] == 7
    assert res["validation"]["word_count"] <= 156


def test_bad_study_skipped_not_crashed():
    # one non-ratio (MD) study and one non-positive study must be skipped, not raise
    ds = _dataset(5)
    ds["studies"].append({"nct_id": "NCT0BAD1", "study_label": "MD trial", "year": 2020,
                          "measure_type": "MD", "point_estimate": -0.3, "ci_lower": -0.6, "ci_upper": 0.1,
                          "arm_experimental": {"label": "Drug"}, "arm_comparator": {"label": "Placebo"}})
    ds["studies"].append({"nct_id": "NCT0BAD2", "study_label": "neg trial", "year": 2020,
                          "point_estimate": -1.0, "ci_lower": -2.0, "ci_upper": 0.5,
                          "arm_experimental": {"label": "Drug"}, "arm_comparator": {"label": "Placebo"}})
    res = gc.render_capsule_html(ds)
    assert res["capsule"]["pooled"]["k"] == 5  # the 2 bad ones excluded
    notes = " ".join(res["capsule"]["notes"])
    assert "NCT0BAD1" in notes and "NCT0BAD2" in notes


def test_emit_writes_files(tmp_path):
    man = gc.emit(_dataset(5), tmp_path)
    cdir = tmp_path / man["slug"]
    assert (cdir / f"{man['slug']}-capsule.html").is_file()
    assert (cdir / "assurance.json").is_file()
    assert (cdir / f"{man['slug']}.body.txt").is_file()
    a = json.loads((cdir / "assurance.json").read_text(encoding="utf-8"))
    assert a["snapshot_date"] == "2026-04-12"
