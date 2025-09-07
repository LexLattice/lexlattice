# ruff: noqa: I001
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


PY = sys.executable


def _run_gate(tmp: Path, changed: list[str], scan_lines: list[dict], pr: int, waiver_text: str | None = None) -> tuple[int, dict]:
    # Prepare working dir with scan + changed + optional waiver
    scan = tmp / 'hdae-scan.jsonl'
    scan.write_text("\n".join(json.dumps(x) for x in scan_lines), encoding='utf-8')
    ch = tmp / 'changed.txt'
    ch.write_text("\n".join(changed), encoding='utf-8')
    if waiver_text is not None:
        wdir = tmp / 'docs' / 'agents' / 'waivers'
        wdir.mkdir(parents=True, exist_ok=True)
        (wdir / f'PR-{pr}.md').write_text(waiver_text, encoding='utf-8')

    # The gate reads scan/waivers relative to CWD; run from tmp and invoke script by absolute path
    script = Path.cwd() / 'tools' / 'hdae' / 'meta' / 'gate_l1.py'
    cp = subprocess.run(
        f"cd '{tmp}' && {PY} '{script}' --pr {pr} --base main --changed '{ch}'",
        shell=True,
        text=True,
        capture_output=True,
    )
    data = {}
    if cp.stdout.strip():
        try:
            data = json.loads(cp.stdout.strip())
        except Exception:
            data = {}
    return cp.returncode, data


def test_gate_all_waived(tmp_path: Path) -> None:
    # 3 L1 in footprint, 3 waived → exit 0
    scan = [
        {"tf_id": "BEX-001", "file": "a.py"},
        {"tf_id": "SIL-002", "file": "b.py"},
        {"tf_id": "BEX-001", "file": "c.py"},
        {"tf_id": "MDA-003", "file": "d.py"},
    ]
    changed = ["a.py", "b.py", "c.py", "other.txt"]
    waiver = "tf_id: BEX-001\ntf_id: SIL-002\ntf_id: BEX-001\n"
    code, data = _run_gate(tmp_path, changed, scan, pr=99, waiver_text=waiver)
    assert code == 0
    assert data.get('l1_in_pr') == 3
    assert data.get('waivers') >= 3
    assert data.get('remaining_l1') == 0


def test_gate_partial_waived_fails(tmp_path: Path) -> None:
    scan = [
        {"tf_id": "BEX-001", "file": "a.py"},
        {"tf_id": "SIL-002", "file": "b.py"},
        {"tf_id": "BEX-001", "file": "c.py"},
    ]
    changed = ["a.py", "b.py", "c.py"]
    waiver = "tf_id: BEX-001\ntf_id: SIL-002\n"  # only 2 waived
    code, data = _run_gate(tmp_path, changed, scan, pr=42, waiver_text=waiver)
    assert code == 1
    assert data.get('remaining_l1') == 1


def test_gate_outside_footprint_ignored(tmp_path: Path) -> None:
    scan = [
        {"tf_id": "BEX-001", "file": "x.py"},
        {"tf_id": "SIL-002", "file": "y.py"},
    ]
    changed = ["a.py"]
    code, data = _run_gate(tmp_path, changed, scan, pr=5, waiver_text=None)
    assert code == 0
    assert data.get('l1_in_pr') == 0


def test_gate_no_scan_file_ok(tmp_path: Path) -> None:
    # No scan file → zeros and exit 0
    changed = ["a.py"]
    ch = tmp_path / 'changed.txt'
    ch.write_text("\n".join(changed), encoding='utf-8')
    script = Path.cwd() / 'tools' / 'hdae' / 'meta' / 'gate_l1.py'
    cp = subprocess.run(
        f"cd '{tmp_path}' && {PY} '{script}' --pr 1 --base main --changed '{ch}'",
        shell=True,
        text=True,
        capture_output=True,
    )
    assert cp.returncode == 0
    data = json.loads(cp.stdout.strip() or '{}')
    assert data.get('total_all', 0) == 0
    assert data.get('remaining_l1', 0) == 0


def test_gate_waiver_file_no_tf_lines_counts_one(tmp_path: Path) -> None:
    scan = [{"tf_id": "BEX-001", "file": "a.py"}]
    changed = ["a.py"]
    waiver = "This is a waiver file without tf lines.\n"
    code, data = _run_gate(tmp_path, changed, scan, pr=7, waiver_text=waiver)
    assert data.get('waivers', 0) >= 1
