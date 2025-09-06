#!/usr/bin/env python3
"""Validate NormSet.base.yaml minimally (stdlib-only).

Checks:
- file exists and readable
- has an `id:` at top-level
- contains `layers:` block

Exit codes:
- 0: OK
- 2: validation failure
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def validate(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        txt = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return [f"cannot read {path}: {type(e).__name__}: {e}"]

    # Accept optional leading spaces and inline comments after the key
    if not re.search(r"(?m)^\s*id\s*:\s*\S+", txt):
        errs.append("missing `id:`")
    if not re.search(r"(?m)^\s*layers\s*:\s*", txt):
        errs.append("missing `layers:` block")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path",
        default="docs/norms/NormSet.base.yaml",
        help="Path to NormSet YAML file",
    )
    args = ap.parse_args()
    target = Path(args.path)
    print(f"validating {target}…")
    errs = validate(target)
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
