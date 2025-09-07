# ruff: noqa: I001
from __future__ import annotations

from pathlib import Path

from tools.hdae.patch_cst import apply_all


FIX = Path("tests/fixtures")


def _patch_file(before_name: str) -> tuple[str, str]:
    src = (FIX / before_name).read_text(encoding="utf-8")
    out, diffs = apply_all(src, before_name)
    return out, "\n".join(diffs)


def test_bex_idempotent() -> None:
    out, diff = _patch_file("bex_before.py")
    assert out.strip() == (FIX / "bex_after.py").read_text(encoding="utf-8").strip()
    # idempotency
    out2, diff2 = apply_all(out, "bex_before.py")
    assert out2 == out
    assert diff2 == []


def test_sil_idempotent() -> None:
    out, _ = _patch_file("sil_before.py")
    assert out.strip() == (FIX / "sil_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "sil_before.py")
    assert out2 == out
    assert diff2 == []


def test_mda_idempotent() -> None:
    out, _ = _patch_file("mda_before.py")
    assert out.strip() == (FIX / "mda_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "mda_before.py")
    assert out2 == out
    assert diff2 == []


def test_sub_idempotent() -> None:
    out, _ = _patch_file("sub_before.py")
    assert out.strip() == (FIX / "sub_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "sub_before.py")
    assert out2 == out
    assert diff2 == []
