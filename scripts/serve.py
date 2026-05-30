"""Launch the local AACT Cockpit (127.0.0.1 only)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("aact_cockpit.cockpit.app:app", host="127.0.0.1", port=8000, reload=False)
