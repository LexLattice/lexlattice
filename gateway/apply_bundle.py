#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil
import typing as t

Bundle = t.Dict[str, t.Any]

ASK_SIGNAL = "ASK"
STOP_SIGNAL = "STOP"
CLI_GATES = {"ruff", "mypy", "pytest"}
__all__ = [
    "load_bundle",
    "preflight",
    "mask_io",
    "should_ask_stop",
    "ASK_SIGNAL",
    "STOP_SIGNAL",
]


def load_bundle(path: str | pathlib.Path) -> Bundle:
    p = pathlib.Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return t.cast(Bundle, data)


def preflight(bundle: Bundle) -> list[str]:
    """Check presence of CLI validators declared in the bundle (skip logical gates).

    Deterministic and side-effect-free: raises ValueError with actionable hints.
    Returns the list of checked tools on success.
    """
    gates = list(bundle.get("layers", {}).get("L2", {}).get("gates", []))
    cli = [g for g in gates if g in CLI_GATES]
    missing: list[str] = []
    root = pathlib.Path(__file__).resolve().parents[1]
    venv_bin = root / ".venv" / "bin"
    for tool in cli:
        present = shutil.which(tool) is not None or (venv_bin / tool).exists()
        if not present:
            missing.append(tool)
    if missing:
        raise ValueError(f"Missing validators: {', '.join(missing)}. Install dev tools and retry.")
    return cli


def mask_io(bundle: Bundle, *, requires_db: bool = False) -> None:
    # Placeholder: in real adapters, fence file/db usage based on policy.
    if requires_db:
        raise ValueError("DB access is not permitted in this context")


def should_ask_stop(bundle: Bundle, event: str) -> str | None:
    ask = bundle.get("ask_stop", {}).get("ask_if", [])
    stop = bundle.get("ask_stop", {}).get("stop_if", [])
    if any(k in event for k in stop):
        return STOP_SIGNAL
    if any(k in event for k in ask):
        return ASK_SIGNAL
    return None
