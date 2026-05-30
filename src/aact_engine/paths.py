"""AACT snapshot path discovery — single source of truth, fail-closed.

Generalises EvidenceForecast/_aact_paths.py: that module only scanned D:/C:
and would miss the live F: snapshot. Here we (a) honour explicit input and the
AACT_HOME/AACT_ROOT env vars first, (b) scan candidate *bases* and auto-detect
the newest ``YYYY-MM-DD`` snapshot subdirectory rather than hardcoding a date,
and (c) fail closed listing what was searched.

Per lessons.md: "Do not hardcode one drive. Use config, candidate-root
discovery, or explicit path inputs and fail closed if no snapshot is found."
This file intentionally carries the drive-specific candidate list; Sentinel's
P0-hardcoded-local-path is a false positive here (candidate-root discovery is
exactly what the rule recommends).
"""
# sentinel:skip-file  (P0-hardcoded-local-path: candidate-root discovery, see docstring)
from __future__ import annotations

import os
import re
from pathlib import Path

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

# Candidate base directories that may contain dated snapshot subdirs, OR be a
# snapshot root themselves. First resolvable wins; within a base, newest date.
_CANDIDATE_BASES: tuple[str, ...] = (
    r"F:\AACT-storage\AACT",
    r"D:\AACT-storage\AACT",
    r"D:\AACT",
    r"C:\AACT",
    r"C:\Users\user\AACT",
)


def _is_snapshot_dir(p: Path) -> bool:
    """A snapshot root is a directory containing studies.txt."""
    return p.is_dir() and (p / "studies.txt").is_file()


def _newest_snapshot_under(base: Path) -> Path | None:
    """If ``base`` is itself a snapshot, return it; else return the dated
    subdirectory with the newest valid YYYY-MM-DD name that is a snapshot."""
    if _is_snapshot_dir(base):
        return base
    if not base.is_dir():
        return None
    dated = [
        c for c in base.iterdir()
        if c.is_dir() and _DATE_RE.match(c.name) and _is_snapshot_dir(c)
    ]
    if not dated:
        return None
    return max(dated, key=lambda c: c.name)  # ISO date sorts lexicographically


def discover_snapshot_root(cli_root: str | os.PathLike | None = None) -> Path:
    """Return the AACT snapshot root directory (holds studies.txt).

    Resolution order:
      1. ``cli_root`` argument
      2. ``AACT_HOME`` env var, then ``AACT_ROOT`` (back-compat)
      3. Newest dated snapshot under the first resolvable candidate base

    Raises ``SystemExit`` listing searched locations if nothing resolves.
    """
    searched: list[str] = []

    if cli_root:
        p = Path(cli_root)
        if _is_snapshot_dir(p):
            return p
        searched.append(f"{p} (cli_root)")

    for env_name in ("AACT_HOME", "AACT_ROOT"):
        env = os.environ.get(env_name)
        if env:
            p = Path(env)
            snap = _newest_snapshot_under(p) if p.is_dir() else None
            if snap is not None:
                return snap
            searched.append(f"{p} ({env_name})")

    for base in _CANDIDATE_BASES:
        bp = Path(base)
        snap = _newest_snapshot_under(bp)
        if snap is not None:
            return snap
        searched.append(base)

    raise SystemExit(
        "AACT snapshot not found. Set AACT_HOME to a directory containing "
        "studies.txt (or a parent holding dated YYYY-MM-DD snapshot dirs). "
        "Searched: " + "; ".join(searched)
    )


def detect_snapshot_date(root: Path) -> str:
    """Return the YYYY-MM-DD snapshot date parsed from the root dir name.

    Falls back to the file mtime date of studies.txt if the directory is not
    date-named, so a non-standard layout still yields a provenance date rather
    than crashing.
    """
    m = _DATE_RE.match(root.name)
    if m:
        return root.name
    # Fallback: derive from studies.txt mtime (UTC date).
    import datetime as _dt
    ts = (root / "studies.txt").stat().st_mtime
    return _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


__all__ = ["discover_snapshot_root", "detect_snapshot_date"]
