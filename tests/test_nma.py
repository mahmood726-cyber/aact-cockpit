"""Network meta-analysis engine + capsule."""
from __future__ import annotations

import math
import re

import pytest

from aact_cockpit.capsule.nma import nma, connectivity, has_loops
from aact_cockpit.capsule.pooling import pool
from aact_cockpit.capsule import generate_nma_capsule as gn


def _contrast(nct, t1, t2, hr, lo, hi):
    Z = 1.959963984540054
    return {"nct": nct, "t1": t1, "t2": t2,
            "yi": math.log(hr), "sei": (math.log(hi) - math.log(lo)) / (2 * Z),
            "hr": hr, "lci": lo, "uci": hi}


def test_two_treatment_nma_equals_pairwise_dl():
    # a network with one edge type (A vs B, B=reference) must reproduce the
    # standard DL random-effects pairwise pool of A vs B.
    cs = [_contrast("N1", "A", "B", 0.80, 0.66, 0.97),
          _contrast("N2", "A", "B", 0.74, 0.60, 0.92),
          _contrast("N3", "A", "B", 0.83, 0.71, 0.97)]
    res = nma(cs, reference="B", method="DL")
    items = [{"hr": c["hr"], "lci": c["lci"], "uci": c["uci"], "inc": True} for c in cs]
    pw = pool(items, method="DL")
    assert res["rel_to_ref"]["A"]["est"] == pytest.approx(pw["est"], abs=1e-9)
    assert res["tau2"] == pytest.approx(pw["tau2"], abs=1e-9)


def test_connectivity_and_loops():
    star = [_contrast("N1", "A", "ref", 0.8, 0.6, 1.0),
            _contrast("N2", "B", "ref", 0.9, 0.7, 1.1)]
    res = nma(star, reference="ref")
    assert connectivity(res["treatments"], res["edges"]) is True
    assert has_loops(res["treatments"], res["edges"]) is False  # tree
    loop = star + [_contrast("N3", "A", "B", 0.95, 0.7, 1.3)]
    res2 = nma(loop, reference="ref")
    assert has_loops(res2["treatments"], res2["edges"]) is True  # triangle


def test_sucra_bounds():
    cs = [_contrast("N1", "A", "ref", 0.7, 0.55, 0.9),
          _contrast("N2", "B", "ref", 0.95, 0.8, 1.13),
          _contrast("N3", "C", "ref", 1.2, 0.95, 1.51)]
    res = nma(cs, reference="ref")
    for t, v in res["sucra"].items():
        assert 0.0 <= v <= 1.0
    # A (lowest HR, best for a harm outcome) should out-rank C (highest HR)
    assert res["sucra"]["A"] > res["sucra"]["C"]


def test_league_reciprocal():
    cs = [_contrast("N1", "A", "ref", 0.7, 0.55, 0.9),
          _contrast("N2", "B", "ref", 0.9, 0.75, 1.08)]
    res = nma(cs, reference="ref")
    ab = res["league"]["A|B"]["est"]
    ba = res["league"]["B|A"]["est"]
    assert ab * ba == pytest.approx(1.0, abs=1e-9)  # reciprocal contrasts


def test_bucher_consistent_loop():
    # direct A-C agrees with indirect (A-B then B-C): IF ~ 1, large p
    cs = [_contrast("N1", "A", "B", 0.80, 0.70, 0.91),
          _contrast("N2", "B", "C", 0.90, 0.80, 1.01),
          _contrast("N3", "A", "C", 0.72, 0.62, 0.84)]  # ~ 0.80*0.90
    res = nma(cs, reference="C")
    cons = res["consistency"]
    assert cons["assessable"] is True
    loop = cons["loops"][0]
    assert loop["p"] > 0.05            # consistent
    assert cons["inconsistent"] is False


def test_bucher_inconsistent_loop():
    # direct A-C (1.5) contradicts indirect (~0.72) with tight CIs -> p < 0.05
    cs = [_contrast("N1", "A", "B", 0.80, 0.74, 0.86),
          _contrast("N2", "B", "C", 0.90, 0.84, 0.97),
          _contrast("N3", "A", "C", 1.50, 1.38, 1.63)]
    res = nma(cs, reference="C")
    cons = res["consistency"]
    assert cons["loops"][0]["p"] < 0.05
    assert cons["inconsistent"] is True


def test_tree_has_no_loops():
    cs = [_contrast("N1", "A", "ref", 0.8, 0.6, 1.0),
          _contrast("N2", "B", "ref", 0.9, 0.7, 1.1)]
    res = nma(cs, reference="ref")
    assert res["consistency"]["assessable"] is False
    assert res["consistency"]["loops"] == []


def _dataset():
    cs = [_contrast("NCT01", "apixaban", "warfarin", 0.79, 0.66, 0.95),
          _contrast("NCT02", "rivaroxaban", "warfarin", 0.85, 0.70, 1.03),
          _contrast("NCT03", "dabigatran", "warfarin", 0.83, 0.74, 0.93),
          _contrast("NCT04", "apixaban", "aspirin", 0.45, 0.32, 0.62)]
    return {"pico": {"population": "atrial fibrillation", "outcome": "stroke or systemic embolism",
                     "intervention": "anticoagulants", "comparator": "warfarin"},
            "primary_estimand": "hazard ratio for stroke versus warfarin",
            "measure": "HR", "reference": "warfarin", "snapshot_date": "2026-04-12",
            "provenance": {"source": "AACT", "snapshot_date": "2026-04-12"},
            "contrasts": cs, "analysis_rerun": "pass", "notes": []}


def test_nma_capsule_renders_clean():
    res = gn.render(_dataset())
    script = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", res["html"], re.DOTALL))
    assert "null" in script and re.search(r"[,:\[(]\s*None\b", script) is None
    assert "NaN" not in script and "__AACT_" not in res["html"]
    assert res["validation"]["ok"] and res["validation"]["sentence_count"] == 7
    cap = res["capsule"]
    assert cap["kind"] == "nma" and cap["reference"] == "warfarin"
    assert cap["self_audit"]["aact_stats"]["connectivity"] == "pass"
    # tree network -> consistency honestly "not assessable" but disclosed (pass)
    assert cap["self_audit"]["aact_stats"]["consistency"] == "pass"
    assert res["tier"] == "silver"  # connected + r-validated, no human review -> silver


def test_nma_emit(tmp_path):
    man = gn.emit(_dataset(), tmp_path)
    assert man["slug"].startswith("nma-")
    assert (tmp_path / man["slug"] / f"{man['slug']}-capsule.html").is_file()
    assert man["treatments"] >= 3
