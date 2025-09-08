from __future__ import annotations

from pathlib import Path

from tools.hdae.scan import scan_paths

FIX = Path('tests/fixtures/packs')


def _copy(tmp: Path, name: str) -> str:
    p = tmp / name
    p.write_text((FIX / name).read_text(encoding='utf-8'), encoding='utf-8')
    return str(p)


def test_con019(tmp_path: Path) -> None:
    pos = _copy(tmp_path, 'con019_pos.py')
    neg = _copy(tmp_path, 'con019_neg.py')
    pf = scan_paths([pos])
    nf = scan_paths([neg])
    assert any(f.pack == 'CON-019' for f in pf)
    assert not any(f.pack == 'CON-019' for f in nf)


def test_con020(tmp_path: Path) -> None:
    pos = _copy(tmp_path, 'con020_pos.py')
    neg = _copy(tmp_path, 'con020_neg.py')
    pf = scan_paths([pos])
    nf = scan_paths([neg])
    assert any(f.pack == 'CON-020' for f in pf)
    assert not any(f.pack == 'CON-020' for f in nf)


def test_sec023(tmp_path: Path) -> None:
    pos = _copy(tmp_path, 'sec023_pos.py')
    neg = _copy(tmp_path, 'sec023_neg.py')
    pf = scan_paths([pos])
    nf = scan_paths([neg])
    assert any(f.pack == 'SEC-023' for f in pf)
    assert not any(f.pack == 'SEC-023' for f in nf)

