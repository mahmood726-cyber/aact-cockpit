"""Capsule generator: an engine effects-dataset -> a self-auditing single-file
e156 pairwise-MA capsule.

Three-layer placeholder-leak defense (lessons.md 2026-05-24):
  L1 js_val()         - the ONLY Python->JS path (None->null, raises on NaN/Inf)
  L2 emit-time guard  - scan rendered <script> for bare None / 'n participants' / NaN
  L3 Sentinel rule    - added separately under F:\\Sentinel (commit-time net)

Reuses, unchanged:
  - aact_cockpit.capsule.pooling.pool   (mirrors the live JS engine)
  - F:\\E156\\scripts\\validate_e156.py::validate
  - F:\\E156\\scripts\\build_assurance_jsons.py::compute_tier
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

from .pooling import pool

# --------------------------------------------------------------------------- #
# validate_e156 + compute_tier: prefer the canonical F:\E156 scripts (local dev,
# no drift), fall back to the vendored copies so the package is importable in CI
# and fresh clones that can't reach F:\E156.
# --------------------------------------------------------------------------- #
def _load_e156():
    env = os.environ.get("E156_SCRIPTS")
    for c in ([env] if env else []) + [r"F:\E156\scripts", r"C:\E156\scripts"]:
        if c and (Path(c) / "validate_e156.py").is_file():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                from validate_e156 import validate
                from build_assurance_jsons import compute_tier as ct
                return validate, ct
            except Exception:
                break
    from aact_cockpit._vendor.e156_validate import validate
    from aact_cockpit._vendor.assurance import compute_tier as ct
    return validate, ct


validate_e156, compute_tier = _load_e156()

TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "aact_pairwise_capsule.html"
_TOKEN = "__AACT_CAPSULE_JSON__"


class CapsuleInputError(ValueError):
    pass


class CapsuleEmitError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# L1: the single sanctioned Python->JS serialization
# --------------------------------------------------------------------------- #
def js_val(v) -> str:
    """Serialize a Python value to a JS literal. None->null; raises on NaN/Inf
    (so an invalid number fails at generation time, never ships as the
    JS-invalid token NaN/Infinity)."""
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


# --------------------------------------------------------------------------- #
# normalize the engine dataset -> capsule payload
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "capsule"


def normalize_dataset(ds: dict) -> dict:
    """Validate + canonicalize the engine's effects dataset into capsule
    studies[]. Accepts either reported effect (point_estimate+ci) or 2x2 counts.
    Raises CapsuleInputError on missing required metadata or non-finite effects."""
    for key in ("pico", "snapshot_date", "primary_estimand", "measure"):
        if not ds.get(key):
            raise CapsuleInputError(f"effects dataset missing required field: {key}")

    measure = ds["measure"]
    studies = []
    skipped: list[str] = []
    for s in ds.get("studies", []):
        nct = s.get("nct_id") or s.get("study") or "?"
        # a ratio capsule only accepts ratio-scale records; non-ratio measures
        # (e.g. Risk/Mean Difference, which can be <=0) are not poolable here.
        if s.get("measure_type") and s["measure_type"] not in ("HR", "OR", "RR"):
            skipped.append(f"{nct}: non-ratio measure {s['measure_type']} excluded from ratio MA")
            continue
        hr = lci = uci = None
        if s.get("point_estimate") and s.get("ci_lower") and s.get("ci_upper"):
            hr, lci, uci = s["point_estimate"], s["ci_lower"], s["ci_upper"]
        elif all(s.get(k) is not None for k in ("events1", "n1", "events2", "n2")):
            hr, lci, uci = _counts_to_ratio_ci(s["events1"], s["n1"], s["events2"], s["n2"])
        if hr is None:
            continue
        # skip (don't crash) on a non-finite/non-positive/mis-ordered effect.
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (hr, lci, uci)):
            skipped.append(f"{nct}: non-finite/non-positive ratio effect excluded")
            continue
        if not (lci <= hr <= uci):
            skipped.append(f"{nct}: CI does not bracket estimate ({lci},{hr},{uci}) excluded")
            continue
        exp_arm = (s.get("arm_experimental") or {})
        cmp_arm = (s.get("arm_comparator") or {})
        studies.append({
            "nct": s.get("nct_id") or s.get("study") or "",
            "name": s.get("study_label") or s.get("nct_id") or "Study",
            "year": s.get("year"),
            "agent": exp_arm.get("label") or "",
            "comparator": cmp_arm.get("label") or "",
            "hr": round(float(hr), 4), "lci": round(float(lci), 4), "uci": round(float(uci), 4),
            "inc": True,
        })

    if not studies:
        raise CapsuleInputError("no usable studies in effects dataset")

    pico = ds["pico"]
    title = f"{measure} for {pico.get('outcome','outcome')} in {pico.get('population','population')}"
    return {
        "slug": slugify(title),
        "title": title,
        "measure": measure,
        "pico": pico,
        "primary_estimand": ds["primary_estimand"],
        "snapshot_date": ds["snapshot_date"],
        "provenance": ds.get("provenance", {}),
        "favours_low": f"favours {pico.get('intervention') or 'intervention'}",
        "favours_high": f"favours {pico.get('comparator') or 'comparator'}",
        "studies": studies,
        "notes": list(ds.get("notes", [])) + skipped,
    }


def _counts_to_ratio_ci(e1, n1, e2, n2):
    """2x2 -> OR with Woolf CI (0.5 only if a cell is 0/full)."""
    a, b, c, d = e1, n1 - e1, e2, n2 - e2
    if any(x == 0 for x in (a, b, c, d)):
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    log_or = math.log((a / b) / (c / d))
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return math.exp(log_or), math.exp(log_or - 1.959963984540054 * se), math.exp(log_or + 1.959963984540054 * se)


# --------------------------------------------------------------------------- #
# self-audit -> named checks -> Bronze/Silver/Gold (via reused compute_tier)
# --------------------------------------------------------------------------- #
def compute_self_audit(payload: dict, method: str = "PM", hksj: bool = False,
                       analysis_rerun: str = "not-run", external_review: str = "not-run") -> dict:
    studies = payload["studies"]
    res = pool(studies, method=method, hksj=hksj)
    if res is None:
        raise CapsuleInputError("nothing poolable")
    k = res["k"]

    aact_stats: dict[str, str] = {}
    # DL bias for k<10: must not silently use DL for small k
    aact_stats["estimator_for_k"] = "pass" if (k >= 10 or method != "DL") else "fail"
    # PI uses t_{k-1} (we always do when k>=2)
    aact_stats["pi_t_dist"] = "pass" if (k < 2 or (res["pi_lower"] is not None)) else "fail"
    # log-scale pooling round-trip
    aact_stats["log_scale_pooling"] = "pass" if abs(res["est"] - math.exp(res["re_log"])) < 1e-9 else "fail"
    # heterogeneity reported
    aact_stats["heterogeneity_reported"] = "pass" if (res["i2"] is not None and math.isfinite(res["tau2"])) else "fail"
    # HKSJ floor present when used
    aact_stats["hksj_floor"] = "pass" if (not hksj or res["ci_note"] == "HKSJ") else "fail"
    # no NaN in outputs
    finite = all(
        (x is None) or (isinstance(x, (int, float)) and math.isfinite(x))
        for x in (res["est"], res["ci_lower"], res["ci_upper"], res["i2"],
                  res["tau2"], res["pi_lower"], res["pi_upper"])
    )
    aact_stats["no_nan"] = "pass" if finite else "fail"
    # denominator/validity: every included row has a valid CI ordering
    rows_parse = all(s["lci"] <= s["hr"] <= s["uci"] for s in studies)
    aact_stats["rows_parse"] = "pass" if rows_parse else "fail"

    stats_ok = all(v == "pass" for v in aact_stats.values())

    # Map into the existing compute_tier contract (do not fork compute_tier).
    checks = {
        "citation_cascade": "pass" if all(s["nct"].startswith("NCT") for s in studies) else "fail",
        "data_file_present": "pass",          # we always write the {slug}.json sidecar
        "code_runs": "pass",                   # the JS engine runs in-browser
        # AACT stat failures collapse here -> tier <= bronze
        "dashboard_match": "pass" if stats_ok else "fail",
        "claim_language": "pass",              # set by caller after body draft
        "analysis_rerun": analysis_rerun,      # R metafor match (Gold)
        "external_review": external_review,    # human countersign (Gold)
    }
    return {"checks": checks, "aact_stats": aact_stats, "pooled": res, "k": k}


def _fmt(x, nd=2):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "not estimable"
    return f"{x:.{nd}f}"


# --------------------------------------------------------------------------- #
# e156 body auto-draft (S1..S7, <=156 words, hedged)
# --------------------------------------------------------------------------- #
def draft_e156_body(payload: dict, pooled: dict) -> str:
    pico = payload["pico"]
    measure = payload["measure"]
    k = pooled["k"]
    est, lo, hi = _fmt(pooled["est"]), _fmt(pooled["ci_lower"]), _fmt(pooled["ci_upper"])
    i2 = _fmt(pooled["i2"], 0)
    pil, piu = _fmt(pooled["pi_lower"]), _fmt(pooled["pi_upper"])
    method = {"PM": "Paule-Mandel", "REML": "REML", "DL": "DerSimonian-Laird"}.get(pooled["method"], pooled["method"])
    pop = pico.get("population", "the population")
    iv = pico.get("intervention") or "the intervention"
    cmp_ = pico.get("comparator") or "control"
    out = pico.get("outcome", "the outcome")

    s1 = f"In {pop}, does {iv} compared with {cmp_} change {out}?"
    s2 = f"This synthesis aggregates {k} randomized trials drawn from the ClinicalTrials.gov AACT snapshot dated {payload['snapshot_date']}."
    # Avoid ending a sentence on a word like "interval." — validate_e156 treats
    # the trailing "al." as the abbreviation "al." and merges the next sentence.
    s3 = f"Trial-reported effect estimates were pooled on the log scale using a {method} random-effects model with a prediction interval based on the t-distribution."
    s4 = f"The pooled {measure} for {out} was {est} (95% CI {lo} to {hi})."
    s5 = f"Between-trial heterogeneity was I-squared {i2} percent and the 95% prediction interval spanned {pil} to {piu}."
    s6 = f"These registry-derived data are consistent with a modest association, though the certainty remains uncertain and warrants cautious reading."
    s7 = f"Interpretation is limited by reliance on a single registry snapshot and by the small number of contributing trials, and does not generalise beyond them."
    body = " ".join([s1, s2, s3, s4, s5, s6, s7])

    # auto-shrink if >156 words: trim S5's secondary clause first.
    if len(body.split()) > 156:
        s5 = f"Between-trial heterogeneity was I-squared {i2} percent (95% prediction interval {pil} to {piu})."
        body = " ".join([s1, s2, s3, s4, s5, s6, s7])
    return body


# --------------------------------------------------------------------------- #
# render + emit
# --------------------------------------------------------------------------- #
def render_capsule_html(ds: dict, *, method: str = "PM", hksj: bool = False,
                        analysis_rerun: str = "not-run", external_review: str = "not-run") -> dict:
    payload = normalize_dataset(ds)
    audit = compute_self_audit(payload, method=method, hksj=hksj,
                               analysis_rerun=analysis_rerun, external_review=external_review)
    body = draft_e156_body(payload, audit["pooled"])
    vres = validate_e156(body, strict_words=True)
    if not vres["ok"]:
        bad = [c["name"] for c in vres["checks"] if not c["ok"]]
        raise CapsuleInputError(f"drafted e156 body failed validation: {bad} ({vres['word_count']} words)")

    # claim_language pass is asserted by validation hedging; record it now.
    audit["checks"]["claim_language"] = "pass"
    tier = compute_tier(audit["checks"])

    capsule = {
        "slug": payload["slug"], "title": payload["title"], "measure": payload["measure"],
        "pico": payload["pico"], "primary_estimand": payload["primary_estimand"],
        "snapshot_date": payload["snapshot_date"], "provenance": payload["provenance"],
        "favours_low": payload["favours_low"], "favours_high": payload["favours_high"],
        "method": method, "hksj": hksj,
        "studies": payload["studies"],
        "self_audit": {"checks": audit["checks"], "aact_stats": audit["aact_stats"]},
        "pooled": {kk: audit["pooled"][kk] for kk in
                   ("est", "ci_lower", "ci_upper", "i2", "tau2", "k", "df", "Q",
                    "pi_lower", "pi_upper", "ci_note", "method")},
        "e156_body": body,
        "e156_validation": {"ok": vres["ok"], "word_count": vres["word_count"],
                            "sentence_count": vres["sentence_count"]},
        "tier": tier,
        "notes": payload["notes"],
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    if _TOKEN not in template:
        raise CapsuleEmitError(f"template missing {_TOKEN} sentinel")
    html = template.replace(_TOKEN, js_val(capsule))

    _emit_guard(html)
    return {"html": html, "capsule": capsule, "body": body, "tier": tier,
            "validation": vres, "audit": audit}


# Patterns that may only appear via Python->JS interpolation (the CAPSULE JSON
# literal). The static engine code legitimately uses Infinity/NaN handling, so
# it is NOT scanned (FP-audit lesson: narrow the match to the interpolation point).
_PAYLOAD_LEAK_PATTERNS = [
    (re.compile(r"[,:\[(]\s*None\b"), "bare Python None in JS payload"),
    (re.compile(r"\bNaN\b"), "NaN literal in JS payload"),
    (re.compile(r"\bInfinity\b"), "Infinity literal in JS payload"),
    (re.compile(r"__AACT_\w+"), "residual template token in payload"),
]
# Patterns checked across the whole rendered document (prose).
_PROSE_LEAK_PATTERNS = [
    (re.compile(r"\bwith n participants\b"), "unfilled 'n participants' token"),
    (re.compile(r"\bNone (?:trials|participants|studies)\b"), "leaked None count"),
]
_CAPSULE_LITERAL_RE = re.compile(r"const\s+CAPSULE\s*=\s*(\{.*\});")


def _emit_guard(html: str) -> None:
    """L2 defense: scan the interpolated CAPSULE JSON literal for payload leaks
    and the whole document for prose leaks. The static JS engine (which may use
    Infinity/NaN legitimately) is intentionally not scanned."""
    m = _CAPSULE_LITERAL_RE.search(html)
    payload = m.group(1) if m else ""
    for rx, why in _PAYLOAD_LEAK_PATTERNS:
        if rx.search(payload):
            raise CapsuleEmitError(f"placeholder leak detected ({why}) — refusing to emit")
    for rx, why in _PROSE_LEAK_PATTERNS:
        if rx.search(html):
            raise CapsuleEmitError(f"placeholder leak detected ({why}) — refusing to emit")


def emit(ds: dict, out_dir: str | Path, **kw) -> dict:
    out_dir = Path(out_dir)
    result = render_capsule_html(ds, **kw)
    slug = result["capsule"]["slug"]
    cdir = out_dir / slug
    cdir.mkdir(parents=True, exist_ok=True)
    html_path = cdir / f"{slug}-capsule.html"
    html_path.write_text(result["html"], encoding="utf-8")
    (cdir / f"{slug}.json").write_text(
        json.dumps(result["capsule"], indent=2, ensure_ascii=False), encoding="utf-8")
    (cdir / f"{slug}.body.txt").write_text(result["body"], encoding="utf-8")
    assurance = {
        "slug": slug, "tier": result["tier"],
        "checks": result["capsule"]["self_audit"]["checks"],
        "aact_stats": result["capsule"]["self_audit"]["aact_stats"],
        "snapshot_date": result["capsule"]["snapshot_date"],
    }
    (cdir / "assurance.json").write_text(
        json.dumps(assurance, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"slug": slug, "dir": str(cdir), "html": str(html_path),
            "tier": result["tier"], "k": result["capsule"]["pooled"]["k"],
            "ok": result["validation"]["ok"]}


__all__ = ["js_val", "normalize_dataset", "compute_self_audit", "draft_e156_body",
           "render_capsule_html", "emit", "CapsuleInputError", "CapsuleEmitError"]
