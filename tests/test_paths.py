"""Path discovery: env-first resolution + fail-closed behavior."""
from __future__ import annotations

import pytest

from aact_engine.paths import discover_snapshot_root, detect_snapshot_date


def _make_snapshot(base, date="2026-04-12"):
    snap = base / "AACT" / date
    snap.mkdir(parents=True)
    (snap / "studies.txt").write_text("nct_id|brief_title\nNCT1|x\n", encoding="utf-8")
    return snap


def test_env_home_wins(tmp_path, monkeypatch):
    snap = _make_snapshot(tmp_path)
    monkeypatch.setenv("AACT_HOME", str(tmp_path / "AACT"))
    monkeypatch.delenv("AACT_ROOT", raising=False)
    assert discover_snapshot_root() == snap


def test_cli_root_beats_env(tmp_path, monkeypatch):
    snap = _make_snapshot(tmp_path)
    # AACT_HOME points somewhere invalid; cli_root should still win.
    monkeypatch.setenv("AACT_HOME", str(tmp_path / "nonexistent"))
    assert discover_snapshot_root(cli_root=str(snap)) == snap


def test_newest_date_selected(tmp_path, monkeypatch):
    base = tmp_path / "AACT"
    base.mkdir(parents=True)
    for d in ("2026-01-01", "2026-04-12", "2025-12-31"):
        sd = base / d
        sd.mkdir()
        (sd / "studies.txt").write_text("nct_id\n", encoding="utf-8")
    monkeypatch.setenv("AACT_HOME", str(base))
    monkeypatch.delenv("AACT_ROOT", raising=False)
    assert discover_snapshot_root().name == "2026-04-12"


def test_fail_closed_lists_searched(tmp_path, monkeypatch):
    monkeypatch.setenv("AACT_HOME", str(tmp_path / "nope"))
    monkeypatch.delenv("AACT_ROOT", raising=False)
    # Neutralize the real candidate bases (the live F: snapshot would otherwise resolve).
    monkeypatch.setattr("aact_engine.paths._CANDIDATE_BASES", ())
    with pytest.raises(SystemExit) as ei:
        discover_snapshot_root(cli_root=str(tmp_path / "also-nope"))
    msg = str(ei.value)
    assert "Searched" in msg and "AACT_HOME" in msg


def test_detect_snapshot_date(tmp_path):
    snap = _make_snapshot(tmp_path)
    assert detect_snapshot_date(snap) == "2026-04-12"
