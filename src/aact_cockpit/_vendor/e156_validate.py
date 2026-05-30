"""Vendored from F:\\E156\\scripts\\validate_e156.py (validate() + helpers).
Single source of truth is F:\\E156; this copy exists only so the package is
importable in CI / fresh clones. Keep the regexes in sync.
"""
from __future__ import annotations

import re

LINK_RE = re.compile(r"(https?://|www\.|doi\.org/)", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s*#+\s+", re.MULTILINE)
INTERVAL_RE = re.compile(
    r"\b(?:(?:9[059]|99)%?\s*(?:CI|CrI|PI|confidence interval|credible interval|prediction interval)"
    r"|CI|IQR|prediction interval|credible interval"
    r"|(?:CI|IQR|range|interval)\s+\d+[–—.-]+\d+"
    r"|within\s+[\d.]+|tolerance|parity|matched.*within"
    r"|\d+\.?\d*\s*(?:percent|%)(?:\s|[.,;:])|(?:pass|passed)\s+(?:\d+|all)"
    r"|\d+\s*(?:of|/)\s*\d+)\b",
    re.IGNORECASE,
)
ESTIMATE_RE = re.compile(
    r"\b(?:RR|OR|HR|MD|SMD|RD|AUC|IRR|NNT|WMD"
    r"|sensitivity|specificity|mean difference|risk ratio|odds ratio|hazard ratio"
    r"|relative risk|risk difference|rate ratio|fragility index|median|prevalence"
    r"|calibration slope|proportion|correlation|r-squared|eta.squared"
    r"|number needed to treat|incidence rate|concordance|accuracy"
    r"|RMST|restricted mean survival|replication probability"
    r"|coverage|parity|tolerance|pass rate|matched|deviation"
    r"|error|bias|reduction|compliance|concordance rate"
    r"|scenarios?\s+passed|percent|tau.squared|I.squared"
    r"|pooled\s+estimates?|validation|coefficient"
    r"|optimism|classification|convincing|credibility"
    r"|count|counts|stock|backlog|share|records?|studies?|family|families)\b",
    re.IGNORECASE,
)
QUANT_RE = re.compile(
    r"\b(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?:percent|%|studies?|records?|trials?|patients?|events?|rate|share|stock|backlog|counts?)\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d{3,}(?:\.\d+)?\b"
    r"|\b\d+\s*(?:of|/)\s*\d+\b",
    re.IGNORECASE,
)

_ABBREVIATIONS = sorted([
    "et al.", "e.g.", "i.e.", "U.S.", "U.K.",
    "Dr.", "Mr.", "Ms.", "vs.", "al.", "No.", "St.", "Prof.", "Fig.", "Vol.",
    "Eq.", "Jr.", "Sr.", "Ltd.", "Inc.", "Dept.", "Surg.", "Suppl.", "Ref.",
    "M.D.",
    "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.",
], key=len, reverse=True)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "\x00"))
    parts = _SENT_SPLIT_RE.split(protected.strip())
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]


def count_words(text: str) -> int:
    return len(text.split())


def coerce_sentences(structured_sentences) -> list[str]:
    coerced = []
    for entry in structured_sentences or []:
        text = str(entry.get("text", "")).strip() if isinstance(entry, dict) else str(entry).strip()
        if text:
            coerced.append(text)
    return coerced


def validate(text: str, strict_words: bool = True, structured_sentences=None) -> dict:
    sentences = coerce_sentences(structured_sentences) or split_sentences(text)
    words = count_words(text)
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("single paragraph", "\n\n" not in text, "Body must not contain blank-line paragraph breaks.")
    add("sentence count", len(sentences) == 7, f"Found {len(sentences)} sentences.")
    add("word count", words <= 156 if strict_words else words <= 170, f"Found {words} words.")
    add("no headings", not HEADING_RE.search(text), "No markdown headings allowed in body.")
    add("no links", not LINK_RE.search(text), "No links or DOI links allowed in body.")
    add("result sentence has interval",
        len(sentences) >= 4 and bool(INTERVAL_RE.search(sentences[3]) or QUANT_RE.search(sentences[3])),
        "Sentence 4 should include a quantitative result.")
    add("result sentence has estimand",
        len(sentences) >= 4 and bool(ESTIMATE_RE.search(sentences[3])),
        "Sentence 4 should name an effect measure or test metric.")
    add("boundary sentence present",
        len(sentences) >= 7 and any(kw in sentences[6].lower() for kw in [
            "is limited", "are limited", "limited by", "limited to", "limitation",
            "cannot", "may not", "could not", "does not", "do not extend",
            "unclear", "uncertain", "caution", "warrant",
            "scope", "boundary", "harm", "restrict", "constrain",
            "exclude", "generali", "not generali"]),
        "Sentence 7 should express a limitation, harm, or scope boundary.")

    return {"word_count": words, "sentence_count": len(sentences),
            "checks": checks, "ok": all(c["ok"] for c in checks)}
