"""Verify every published capsule in a directory: run the matching Node numeric
witness (pairwise repool / TSA cumulative) and a payload leak scan. Exits non-
zero on any failure. Used by CI and runnable locally.

Usage:
    python scripts/verify_docs.py docs
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PAYLOAD_LEAKS = [
    (re.compile(r"[,:\[(]\s*None\b"), "bare None"),
    (re.compile(r"\bNaN\b"), "NaN"),
    (re.compile(r"\bInfinity\b"), "Infinity"),
    (re.compile(r"__AACT_\w+"), "residual token"),
]
_CAP_RE = re.compile(r"const\s+CAPSULE\s*=\s*(\{.*\});")
# A top-level `const top=...` shadows the browser global window.top and throws
# "Identifier 'top' has already been declared" — invisible to the Node witness
# (no window) but fatal in a browser. Catch declarations of reserved globals.
_SHADOW_RE = re.compile(
    r"(?:(?:const|let|var)\s+|,\s*)"
    r"(top|name|length|parent|closed|status|location|self)\s*=")
_SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def verify(docs: Path) -> int:
    capsules = sorted(docs.glob("*/*-capsule.html"))
    if not capsules:
        print(f"no capsules under {docs}")
        return 1
    failures: list[str] = []
    for html in capsules:
        text = html.read_text(encoding="utf-8")
        m = _CAP_RE.search(text)
        payload = m.group(1) if m else ""
        kind = "pairwise"
        try:
            kind = json.loads(payload).get("kind", "pairwise")
        except ValueError:
            failures.append(f"{html.name}: CAPSULE JSON not parseable")
        # leak scan (payload only — static engine legitimately uses Infinity)
        for rx, why in _PAYLOAD_LEAKS:
            if rx.search(payload):
                failures.append(f"{html.name}: payload leak {why}")
        # browser-global shadowing (would crash in a browser, not in Node)
        scripts = "\n".join(m.group(1) for m in _SCRIPT_BLOCK_RE.finditer(text))
        for m in _SHADOW_RE.finditer(scripts):
            failures.append(f"{html.name}: declares reserved browser global '{m.group(1)}' "
                            f"(shadows window.{m.group(1)} — crashes in browser)")
        # numeric witness (per capsule kind)
        witness = {"tsa": "tests/node/tsa_check.mjs",
                   "nma": "tests/node/nma_check.mjs",
                   "atlas": "tests/node/atlas_check.mjs",
                   "audit": "tests/node/audit_check.mjs"}.get(kind, "tests/node/repool_check.mjs")
        r = subprocess.run(["node", str(_ROOT / witness), str(html)],
                           capture_output=True, text=True)
        status = "PASS" if r.returncode == 0 else "FAIL"
        print(f"  [{status}] {kind:8s} {html.parent.name}")
        if r.returncode != 0:
            failures.append(f"{html.name}: witness failed\n{r.stdout}{r.stderr}")

    print(f"\n{len(capsules)} capsules checked, {len(failures)} failures")
    for f in failures:
        print("  ! " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(verify(Path(sys.argv[1] if len(sys.argv) > 1 else "docs")))
