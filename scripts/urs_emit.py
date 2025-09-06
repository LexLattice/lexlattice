#!/usr/bin/env python3
"""
Emit a portable Rulebook Bundle (JSON) combining L0–L3 + NormSet + gates.

Constraints:
- stdlib-only
- Deterministic (no wall-clock); optional date via env var BUNDLE_DATE
- Narrow exceptions; small surface
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
COMPILED_RULEBOOK = ROOT / "docs" / "agents" / "Compiled.Rulebook.md"
NORMSET_PATH = ROOT / "docs" / "norms" / "NormSet.base.yaml"


def read_normset_id(path: Path) -> str:
    try:
        txt = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "NormSet.base.v1"
    m = re.search(r"^id:\s*([^\s#]+)", txt, flags=re.MULTILINE)
    return m.group(1).strip() if m else "NormSet.base.v1"


def parse_l0_l1_from_compiled_md(path: Path) -> Dict[str, List[str]]:
    """Best-effort extraction of L0/L1 rule names from the compiled rulebook.
    Falls back to documented constants if parsing is inconclusive.
    """
    try:
        txt = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        txt = ""

    l0: List[str] = []
    l1: List[str] = []
    cur = None
    for line in txt.splitlines():
        if re.match(r"^##+\s*L0\b", line):
            cur = "L0"
            continue
        if re.match(r"^##+\s*L1\b", line):
            cur = "L1"
            continue
        m = re.match(r"^\s*[-*]\s+([`\w][^`]+)\s*$", line)
        if m and cur in {"L0", "L1"}:
            name = m.group(1).strip().strip("` ")
            (l0 if cur == "L0" else l1).append(name)

    if not l0:
        l0 = ["determinism.first", "small-diffs", "narrow-exceptions"]
    if not l1:
        l1 = ["exceptions.narrow", "io.guards"]
    return {"L0": l0, "L1": l1}


def build_bundle() -> Dict[str, Any]:
    layers = parse_l0_l1_from_compiled_md(COMPILED_RULEBOOK)
    # L2 gates per DoD (norm_audit validators)
    l2 = {"gates": ["ruff", "mypy", "pytest", "docs_updated"]}
    # L3 reporting (journals)
    l3 = {"reporting": ["journals:activity", "journals:self"]}

    generated_at = os.environ.get("BUNDLE_DATE", "1970-01-01")
    normset_id = read_normset_id(NORMSET_PATH)

    obj: Dict[str, Any] = {
        "version": "rb-1",
        "generated_at": generated_at,
        "layers": {"L0": layers["L0"], "L1": layers["L1"], "L2": l2, "L3": l3},
        "normset_id": normset_id,
        "ask_stop": {
            "ask_if": ["gh auth missing", "non-SSH origin", "validators absent"],
            "stop_if": ["would violate L1", "non-stdlib dependency proposed"],
        },
        "waivers": [],
    }
    # Fingerprint over canonical JSON
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    obj["fingerprint"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["json"], default="json")
    ap.add_argument("--out", required=True, help="output file path (json)")
    args = ap.parse_args()

    bundle = build_bundle()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, UnicodeEncodeError, TypeError) as e:
        # Surface actionable message and non-zero exit deterministically
        print(f"Error writing bundle to {out_path}: {type(e).__name__}: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

