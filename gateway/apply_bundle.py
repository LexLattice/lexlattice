#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil
import typing as t

Bundle = t.Dict[str, t.Any]


def load_bundle(path: str | pathlib.Path) -> Bundle:
    p = pathlib.Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return t.cast(Bundle, data)


def preflight(bundle: Bundle) -> None:
    """Enforce pre-run checks derived from L2 gates.

    Deterministic and side-effect-free: raises ValueError with actionable hints.
    """
    gates = bundle.get("layers", {}).get("L2", {}).get("gates", [])
    missing: list[str] = []
    root = pathlib.Path(__file__).resolve().parents[1]
    venv_bin = root / ".venv" / "bin"
    for tool in ("ruff", "mypy", "pytest"):
        if tool in gates:
            present = shutil.which(tool) is not None or (venv_bin / tool).exists()
            if not present:
                missing.append(tool)
    if missing:
        raise ValueError(f"Missing validators: {', '.join(missing)}. Install dev tools and retry.")


def mask_io(bundle: Bundle, *, requires_db: bool = False) -> None:
    # Placeholder: in real adapters, fence file/db usage based on policy.
    if requires_db:
        raise ValueError("DB access is not permitted in this context")


def should_ask_stop(bundle: Bundle, event: str) -> str | None:
    ask = bundle.get("ask_stop", {}).get("ask_if", [])
    stop = bundle.get("ask_stop", {}).get("stop_if", [])
    if any(k in event for k in stop):
        return "STOP"
    if any(k in event for k in ask):
        return "ASK"
    return None
