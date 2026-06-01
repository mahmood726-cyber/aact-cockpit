"""ct.gov registry-audit capsule: generation, self-audit, reconciliation.

Synthetic audit dict (no warehouse) so it runs in CI. The real engine
(aact_engine.audits) is smoke-tested only when a warehouse is present.
"""
import json
from pathlib import Path

import pytest

from aact_cockpit.capsule.generate_audit_capsule import (
    render, compute_self_audit, draft_e156_body,
)

ROOT = Path(__file__).resolve().parents[1]


def _audit():
    return {
        "kind": "audit", "audit_id": "ctgov-stopped-trial-disclosure-gap",
        "title": "Stopped-trial disclosure gap",
        "source_repo": "ctgov-stopped-trial-disclosure-gap",
        "source_url": "https://github.com/mahmood726-cyber/ctgov-stopped-trial-disclosure-gap",
        "snapshot_date": "2026-04-12",
        "provenance": {"snapshot_date": "2026-04-12", "source": "AACT"},
        "question": ("How much worse do stopped trials look on ClinicalTrials.gov than completed "
                     "trials once older closed interventional studies are grouped by final status?"),
        "estimand": "No-results and ghost-protocol rates across final-status groups",
        "scope": {"n_eligible": 1000, "definition": "closed interventional studies first posted in 2024 or earlier"},
        "groups": [
            {"label": "Completed", "n": 800, "metrics": {"no_results_pct": 74.9, "ghost_pct": 73.8,
                                                          "reason_missing_pct": 0.0, "visible_pct": 25.1}},
            {"label": "Terminated", "n": 150, "metrics": {"no_results_pct": 60.9, "ghost_pct": 59.1,
                                                          "reason_missing_pct": 10.2, "visible_pct": 39.1}},
            {"label": "Withdrawn", "n": 50, "metrics": {"no_results_pct": 100.0, "ghost_pct": 100.0,
                                                        "reason_missing_pct": 13.1, "visible_pct": 0.0}},
        ],
        "primary_metric": "no_results_pct",
        "metric_order": ["no_results_pct", "ghost_pct", "reason_missing_pct"],
        "metric_labels": {"no_results_pct": "no results posted", "ghost_pct": "ghost protocol",
                          "reason_missing_pct": "stop-reason missing", "visible_pct": "results visible"},
        "findings": ["Withdrawn studies reach 100.0% no-results and 100.0% ghost-protocol.",
                     "Completed studies sit at 74.9% no-results versus 60.9% for terminated."],
        "caveats": "Final-status labels are registry entries and do not adjudicate operational history.",
    }


def test_render_ok_and_silver():
    r = render(_audit())
    assert r["validation"]["ok"]
    assert r["tier"] == "silver"
    assert "__AACT_CAPSULE_JSON__" not in r["html"]
    assert r["capsule"]["kind"] == "audit"
    assert r["capsule"]["source_url"].endswith("ctgov-stopped-trial-disclosure-gap")


def test_self_audit_clean_passes():
    audit = compute_self_audit(_audit())
    assert all(v == "pass" for v in audit["audit_stats"].values()), audit["audit_stats"]
    assert audit["checks"]["dashboard_match"] == "pass"


def test_self_audit_catches_nonpartition():
    a = _audit()
    a["groups"][0]["n"] = 999  # sum no longer equals n_eligible
    audit = compute_self_audit(a)
    assert audit["audit_stats"]["partition_reconciles"] == "fail"
    assert audit["checks"]["dashboard_match"] == "fail"


def test_self_audit_catches_bad_proportion():
    a = _audit()
    a["groups"][0]["metrics"]["no_results_pct"] = 140.0
    audit = compute_self_audit(a)
    assert audit["audit_stats"]["proportions_valid"] == "fail"


def test_e156_body_valid_and_bounded():
    body = draft_e156_body(_audit())
    assert len(body.split()) <= 156
    # S7 boundary keyword present
    assert "limited to" in body.lower()


def test_live_sample_passthrough_and_rendered():
    a = _audit()
    a["live_sample"] = [{"nct_id": "NCT01234567", "sponsor_class": "OTHER", "aact_derived": True}]
    a["live_sample_size"] = 1
    a["live_note"] = "live note here"
    r = render(a)
    assert r["capsule"]["live_sample"][0]["nct_id"] == "NCT01234567"
    assert "NCT01234567" in r["html"]            # sample embedded for the browser to query
    assert "liveSection" in r["html"]            # live-refresh UI present
    assert "eutils.ncbi.nlm.nih.gov" in r["html"] and "europepmc" in r["html"]


def test_no_live_sample_key_when_absent():
    r = render(_audit())  # baseline audit carries no live sample
    assert "live_sample" not in r["capsule"]


def test_interpretation_drives_s6_and_passes_through():
    a = _audit()
    a["interpretation"] = "Stopping a trial deepens the risk that the public record stays silent."
    body = draft_e156_body(a)
    assert "Stopping a trial deepens the risk" in body
    r = render(a)
    assert r["validation"]["ok"]


def test_validity_passthrough():
    a = _audit()
    a["validity"] = {"flag_checks": [{"flag": "fda_drug", "meaning": "drug", "prevalence_pct": 11.2,
                                      "expected": [4, 22], "status": "pass"}],
                     "scope_status": "pass", "scope_expected": [150000, 400000]}
    r = render(a)
    assert r["capsule"]["validity"]["flag_checks"][0]["flag"] == "fda_drug"
    assert "Field semantics" in r["html"]
    assert "fda_drug" in r["html"]


def test_no_leak():
    r = render(_audit())
    script = r["html"].split("<script>")[1]
    assert "None" not in script
    assert "NaN" not in r["html"] and "Infinity" not in r["html"]
    assert "Decimal" not in r["html"]


# --- engine smoke test, only when a warehouse exists ---
def _have_warehouse():
    # discover_snapshot_root() fails closed with SystemExit when no AACT snapshot
    # is present (e.g. CI), which is BaseException, not Exception — catch both so
    # collection never crashes.
    try:
        from aact_engine.paths import discover_snapshot_root, detect_snapshot_date
        from aact_engine.ingest import default_db_path
        return Path(default_db_path(detect_snapshot_date(discover_snapshot_root()))).is_file()
    except BaseException:
        return False


@pytest.mark.skipif(not _have_warehouse(), reason="no AACT warehouse on this machine")
def test_engine_runs_and_reconciles():
    from aact_engine.audits import run_audit, AUDITS
    from aact_engine.query import open_warehouse
    con = open_warehouse()
    try:
        for aid in AUDITS:
            a = run_audit(aid, con=con)
            assert a["scope"]["n_eligible"] == sum(g["n"] for g in a["groups"])
            assert all(0 <= p <= 100 for g in a["groups"] for p in g["metrics"].values())
            render(a)  # must produce a valid capsule
            # validity layer: field semantics + scope must be in their honest bands
            v = a["validity"]
            assert v["scope_status"] == "pass", (aid, a["scope"]["n_eligible"], v["scope_expected"])
            for c in v["flag_checks"]:
                assert c["status"] == "pass", (aid, c)  # FLAG_META bands must match reality
            if "publication" in aid:
                assert len(a["live_sample"]) == 60
                assert all(set(x) == {"nct_id", "sponsor_class", "aact_derived"}
                           for x in a["live_sample"])
    finally:
        con.close()
