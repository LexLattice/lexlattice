#!/usr/bin/env python3
# MIT License — see LICENSE in repo root
# Copyright (c) 2025 LexLattice
"""
Append a machine-readable audit event in NDJSON form.
We keep timestamps **only** in audits (not in bundles).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Any, Dict


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_line(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Append a Norm Audit event (NDJSON)")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--sha", required=True, help="short commit sha")
    ap.add_argument("--bundle", required=True, help="path to .llbundle.json")
    ap.add_argument("--event", required=True, choices=["compile", "enforce", "waiver_ignored", "ask", "stop"])
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    # read bundle hash (optional)
    bundle_hash = None
    try:
        with open(args.bundle, "r", encoding="utf-8") as f:
            obj = json.load(f)
            bundle_hash = obj.get("hash") if isinstance(obj, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, AttributeError, TypeError, KeyError):
        bundle_hash = None

    line = {
        "ts_utc": utc_now_iso(),
        "event": args.event,
        "pr": args.pr,
        "sha": args.sha,
        "bundle": os.path.relpath(args.bundle),
        "bundleHash": bundle_hash,
        "notes": args.notes,
    }
    out = f"docs/audit/PR-{args.pr}.ndjson"
    write_line(out, line)
    print(f"[norm_audit] appended → {out}")


if __name__ == "__main__":
    main()
