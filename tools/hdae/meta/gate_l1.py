from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Set, Tuple

# Resolve repo root from this file location
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
CONFIG_PATH = os.path.join(ROOT, "tools", "hdae", "meta", "gate_config.yaml")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_yaml_minimal(s: str) -> Dict[str, object]:
    # Importing local minimal YAML to avoid external deps
    from tools.hdae.cli import _load_yaml_minimal as _yaml

    data = _yaml(s)
    if not isinstance(data, dict):
        return {}
    return data  # type: ignore[return-value]


def _jsonl_lines(path: str) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    try:
        text = _read(path)
    except OSError:
        return out
    for ln in [l for l in text.splitlines() if l.strip()]:
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    return out


def _discover_changed_files(base_ref: str) -> Set[str]:
    # Prefer origin/<base>...HEAD; fallback to <base>...HEAD
    for base in (f"origin/{base_ref}", base_ref):
        try:
            cp = subprocess.run(
                ["git", "diff", "--name-only", f"{base}...HEAD"],
                check=True,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
            files = [l.strip() for l in cp.stdout.splitlines() if l.strip()]
            return set(files)
        except subprocess.CalledProcessError:
            continue
    return set()


def _load_config() -> Dict[str, object]:
    try:
        return _load_yaml_minimal(_read(CONFIG_PATH))
    except OSError:
        return {}


def _count_waivers(conf: Dict[str, object], pr: int, gate_ids: Set[str], cwd: str) -> int:
    pattern = str(conf.get("waiver_file_pattern", "docs/agents/waivers/PR-{pr}.md"))
    regex = str(conf.get("waiver_tf_regex", r"\btf_id\s*:\s*([A-Z]+-\d{3})\b"))
    path = os.path.abspath(os.path.join(cwd, pattern.format(pr=pr)))
    if not os.path.exists(path):
        return 0
    try:
        text = _read(path)
    except OSError:
        return 0
    matches: List[str]
    try:
        matches = re.findall(regex, text)
    except re.error:
        matches = []
    count = sum(1 for m in matches if str(m) in gate_ids)
    if count:
        return count
    # Fallback: count occurrences of gate IDs directly
    direct = 0
    for gid in gate_ids:
        direct += text.count(gid)
    if direct:
        return direct
    # File exists but no recognizable lines → count at least 1
    return 1


def _compute_gate(pr: int, base: str | None, changed_list_file: str | None) -> Tuple[Dict[str, object], int]:
    conf = _load_config()
    gate_ids = set(str(x) for x in conf.get("gate_on_tf_ids", []))
    scan_path = str(conf.get("scan_path", "hdae-scan.jsonl"))
    cwd = os.getcwd()
    scan_abs = os.path.abspath(os.path.join(cwd, scan_path))
    # Determine changed files
    changed: Set[str] = set()
    if changed_list_file:
        try:
            lines = _read(changed_list_file)
            changed = {l.strip() for l in lines.splitlines() if l.strip()}
        except OSError:
            changed = set()
    else:
        if base:
            changed = _discover_changed_files(base)
        else:
            changed = set()

    items = _jsonl_lines(scan_abs)
    total_all = len(items)
    l1_in_pr = 0
    for obj in items:
        tf_id = str(obj.get("tf_id") or obj.get("pack") or "")
        fpath = str(obj.get("file") or obj.get("path") or obj.get("filename") or "")
        if not tf_id or not fpath:
            continue
        if tf_id not in gate_ids:
            continue
        if changed and fpath not in changed:
            continue
        l1_in_pr += 1

    waivers = _count_waivers(conf, pr, gate_ids, cwd)
    remaining = max(l1_in_pr - waivers, 0)
    result: Dict[str, object] = {
        "total_all": total_all,
        "l1_in_pr": l1_in_pr,
        "waivers": waivers,
        "remaining_l1": remaining,
        "changed_files": len(changed),
        "gate_tf_ids": sorted(gate_ids),
    }
    return result, (1 if remaining > 0 else 0)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hdae-gate", description="H-DAE L1 gate on PR footprint")
    ap.add_argument("--pr", type=int, default=int(os.environ.get("PR_NUMBER", "0") or 0))
    ap.add_argument("--base", type=str, default=os.environ.get("GITHUB_BASE_REF", ""))
    ap.add_argument("--changed", type=str, default="", help="Optional path to newline-delimited changed files list")
    args = ap.parse_args(argv)
    res, code = _compute_gate(args.pr, args.base or None, args.changed or None)
    print(json.dumps(res, ensure_ascii=False))
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
