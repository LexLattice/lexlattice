# ruff: noqa: I001
from __future__ import annotations

from pathlib import Path
import json

from tools.hdae.scan import scan_paths


FIX = Path("tests/fixtures")


def test_scan_core_packs(tmp_path: Path) -> None:
    # copy fixtures into tmp and scan
    files = []
    for name in ("bex_before.py", "sil_before.py", "mda_before.py", "sub_before.py"):
        src = (FIX / name).read_text(encoding="utf-8")
        path = tmp_path / name
        path.write_text(src, encoding="utf-8")
        files.append(str(path))

    findings = scan_paths(files)
    by_pack: dict[str, int] = {}
    for f in findings:
        by_pack.setdefault(f.pack, 0)
        by_pack[f.pack] += 1

    assert by_pack.get("BEX-001", 0) == 1
    assert by_pack.get("SIL-002", 0) == 1
    assert by_pack.get("MDA-003", 0) == 1
    assert by_pack.get("SUB-006", 0) == 1

    # Ensure JSONL serializable
    js = [json.loads(f.to_json()) for f in findings]
    assert all("pack" in j and "file" in j for j in js)
