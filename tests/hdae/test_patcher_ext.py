# ruff: noqa: I001
from __future__ import annotations

from pathlib import Path

from tools.hdae.patch_cst import apply_all


FIX = Path("tests/fixtures/packs")


def _patch_file(before_name: str, packs: set[str] | None = None) -> tuple[str, str]:
    src = (FIX / before_name).read_text(encoding="utf-8")
    out, diffs = apply_all(src, before_name, packs)
    return out, "\n".join(diffs)


def test_res_idempotent() -> None:
    out, _ = _patch_file("res_before.py", {"RES-005"})
    assert out.strip() == (FIX / "res_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "res_before.py", {"RES-005"})
    assert out2 == out
    assert diff2 == []


def test_arg_idempotent() -> None:
    out, _ = _patch_file("arg_before.py", {"ARG-008"})
    assert out.strip() == (FIX / "arg_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "arg_before.py", {"ARG-008"})
    assert out2 == out
    assert diff2 == []


def test_log_idempotent() -> None:
    out, _ = _patch_file("log_before.py", {"LOG-010"})
    assert out.strip() == (FIX / "log_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "log_before.py", {"LOG-010"})
    assert out2 == out
    assert diff2 == []


def test_err_idempotent() -> None:
    out, _ = _patch_file("err_before.py", {"ERR-011"})
    assert out.strip() == (FIX / "err_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "err_before.py", {"ERR-011"})
    assert out2 == out
    assert diff2 == []


def test_path_idempotent() -> None:
    out, _ = _patch_file("path_before.py", {"PATH-014"})
    assert out.strip() == (FIX / "path_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "path_before.py", {"PATH-014"})
    assert out2 == out
    assert diff2 == []


def test_yaml_idempotent() -> None:
    out, _ = _patch_file("yaml_before.py", {"YAML-015"})
    assert out.strip() == (FIX / "yaml_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "yaml_before.py", {"YAML-015"})
    assert out2 == out
    assert diff2 == []


def test_json_idempotent() -> None:
    out, _ = _patch_file("json_before.py", {"JSON-016"})
    assert out.strip() == (FIX / "json_after.py").read_text(encoding="utf-8").strip()
    out2, diff2 = apply_all(out, "json_before.py", {"JSON-016"})
    assert out2 == out
    assert diff2 == []

