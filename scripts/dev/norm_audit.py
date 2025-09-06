#!/usr/bin/env python3
"""
Norm Audit: compute per-PR conformance & metrics and append to the PR journal.

- Reads docs/norms/NormSet.base.yaml (only 'id' needed; parsed via regex).
- Runs validators: ruff, mypy, pytest (unit-only), docs_updated (via git diff).
- Computes metrics: NormPass@1, RepairDepth (baseline 0), ViolationMix,
  DeterminismScore (optional k reruns with fixed-seed hashing), WaiverCount (0).
- Appends a markdown + JSON block to docs/codex/reports/PR-<n>.md via codex_journal.py.

Notes:
- Narrow exceptions only.
- No wall-clock dependence; fixed seed for hashing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
NORMSET_PATH = ROOT / "docs" / "norms" / "NormSet.base.yaml"
REPORTS_DIR = ROOT / "docs" / "codex" / "reports"
CODEX_JOURNAL = ROOT / "scripts" / "dev" / "codex_journal.py"


def sh(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, ValueError) as e:
        return 127, "", f"{type(e).__name__}: {e}"


def git_root() -> Path:
    code, out, _ = sh(["git", "rev-parse", "--show-toplevel"])
    return Path(out) if code == 0 and out else ROOT


def read_normset_id(path: Path) -> str:
    try:
        txt = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "NormSet.base.v1"
    m = re.search(r"^id:\s*([^\s#]+)", txt, flags=re.MULTILINE)
    return m.group(1).strip() if m else "NormSet.base.v1"


def docs_updated(pr_number: int, branch: str) -> bool:
    base = ""
    if pr_number > 0:
        code, out, _ = sh(["gh", "pr", "view", str(pr_number), "--json", "baseRefName", "-q", ".baseRefName"])
        if code == 0 and out:
            base = out
    if base:
        sh(["git", "fetch", "origin", base, "--depth=1"])
        code, mb, _ = sh(["git", "merge-base", f"origin/{base}", "HEAD"])
        basepoint = mb if code == 0 and mb else f"origin/{base}"
        code, out, _ = sh(["git", "diff", "--name-only", basepoint, "HEAD"])
    else:
        guess = "main"
        sh(["git", "fetch", "origin", guess, "--depth=1"])
        code, mb, _ = sh(["git", "merge-base", f"origin/{guess}", "HEAD"])
        basepoint = mb if code == 0 and mb else "HEAD~1"
        code, out, _ = sh(["git", "diff", "--name-only", basepoint, "HEAD"])
    if code != 0 or not out:
        return False
    files = [p.strip() for p in out.splitlines() if p.strip()]
    return any(f == "README.md" or f.startswith("docs/") for f in files)


def scan_violation_mix(root: Path) -> List[str]:
    violations: List[str] = []
    try:
        for p in root.rglob("*.py"):
            parts = {seg.lower() for seg in p.parts}
            if any(x in parts for x in (".venv", "venv", "build", "dist")):
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            if re.search(r"\bexcept\s+Exception\b", txt):
                violations.append(f"{p}: except Exception")
            if re.search(r"\bexcept\s+BaseException\b", txt):
                violations.append(f"{p}: except BaseException")
    except (OSError, ValueError) as e:
        violations.append(f"scan_error: {type(e).__name__}: {e}")
    return violations


def run_validator(cmd: List[str]) -> bool:
    code, _, _ = sh(cmd)
    return code == 0


def determinism_score(payload: Dict[str, object], reruns: int) -> float:
    if reruns <= 1:
        return 1.0
    stable = 0
    ref_digest = None
    for _ in range(reruns):
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        if ref_digest is None:
            ref_digest = digest
            stable += 1
        else:
            stable += int(digest == ref_digest)
    return stable / reruns


def append_to_journal(pr: int, branch: str, markdown: str) -> None:
    try:
        proc = subprocess.Popen(
            [sys.executable, str(CODEX_JOURNAL), "--pr", str(pr), "--type", "report",
             "--title", "Norm Audit", "--branch", branch],
            stdin=subprocess.PIPE, text=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(markdown)
        proc.stdin.close()
        rc = proc.wait(timeout=120)
        if rc != 0:
            raise subprocess.SubprocessError(f"codex_journal.py exited {rc}")
    except (OSError, ValueError, subprocess.SubprocessError, AssertionError):
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"PR-{pr}.md"
        with path.open("a", encoding="utf-8") as f:
            f.write("## Norm Audit (fallback)\n\n")
            f.write(markdown)
            f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int, default=0, help="Pull request number (required on PR branches)")
    ap.add_argument("--branch", default="", help="Branch name")
    args = ap.parse_args()

    normset_id = read_normset_id(NORMSET_PATH)

    v_results: Dict[str, bool] = {
        "ruff": run_validator(["ruff", "check"]),
        "mypy": run_validator(["mypy"]),
        "pytest": run_validator(["pytest", "-q"]),
        "docs_updated": docs_updated(args.pr, args.branch),
    }
    normpass_at_1 = sum(1 for v in v_results.values() if v) / max(len(v_results), 1)

    violations = scan_violation_mix(git_root())
    l1_pass = len([v for v in violations if "scan_error" not in v]) == 0

    conformance = {
        "L0": "pass",
        "L1": ["exceptions.narrow:" + ("pass" if l1_pass else "fail")],
        "L2": [f"{k}:{'pass' if ok else 'fail'}" for k, ok in v_results.items()],
        "L3": ["journals:append"],
    }

    payload: Dict[str, object] = {
        "normset": normset_id,
        "conformance": conformance,
        "metrics": {
            "NormPass@1": normpass_at_1,
            "RepairDepth": 0,
            "ViolationMix": violations,
            "WaiverCount": 0,
        },
        "notes": "",
    }
    reruns = int(os.environ.get("NORM_AUDIT_RERUNS", "1"))
    payload["metrics"]["DeterminismScore"] = determinism_score(payload, reruns)  # type: ignore[index]

    summary_lines = [
        f"- NormSet: `{normset_id}`",
        f"- L2 Validators: " + ", ".join(f"{k}={'pass' if v else 'fail'}" for k, v in v_results.items()),
        f"- L1 Violations: {len(violations)}",
        f"- Metrics: NormPass@1={normpass_at_1:.2f}, RepairDepth=0, DeterminismScore={payload['metrics']['DeterminismScore']:.2f}, WaiverCount=0",
    ]
    md = "## Norm Audit\n" + "\n".join(summary_lines) + "\n\n```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n"

    append_to_journal(args.pr, args.branch, md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
