# ruff: noqa: I001
from __future__ import annotations

import difflib
import os
from pathlib import Path

from tools.hdae.cli import main


FIX = Path("tests/fixtures/packs")


def test_yaml015_cli(tmp_path: Path, capsys) -> None:  # type: ignore[override]
    before = (FIX / "yaml_before.py").read_text(encoding="utf-8")
    after = (FIX / "yaml_after.py").read_text(encoding="utf-8")
    test_file = tmp_path / "yaml_before.py"
    test_file.write_text(before, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        main(["scan", "--packs", "YAML-015"])
        scan_out = capsys.readouterr().out.strip().splitlines()
        assert any("YAML-015" in line for line in scan_out)

        main(["propose", "--dry-run", "--packs", "YAML-015"])
        diff_out = capsys.readouterr().out
        rel = f"./{test_file.name}"
        expected = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
        assert diff_out == expected

        main(["propose", "--apply", "--packs", "YAML-015"])
        capsys.readouterr()
        assert test_file.read_text(encoding="utf-8") == after

        main(["propose", "--dry-run", "--packs", "YAML-015"])
        idemp = capsys.readouterr().out
        assert idemp == ""
    finally:
        os.chdir(cwd)


def test_err011_cli(tmp_path: Path, capsys) -> None:  # type: ignore[override]
    before = (FIX / "err_before.py").read_text(encoding="utf-8")
    after = (FIX / "err_after.py").read_text(encoding="utf-8")
    test_file = tmp_path / "err_before.py"
    test_file.write_text(before, encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        main(["scan", "--packs", "ERR-011"])
        scan_out = capsys.readouterr().out.strip().splitlines()
        assert any("ERR-011" in line for line in scan_out)

        main(["propose", "--dry-run", "--packs", "ERR-011"])
        diff_out = capsys.readouterr().out
        rel = f"./{test_file.name}"
        expected = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
        assert diff_out == expected

        main(["propose", "--apply", "--packs", "ERR-011"])
        capsys.readouterr()
        assert test_file.read_text(encoding="utf-8") == after

        main(["propose", "--dry-run", "--packs", "ERR-011"])
        idemp = capsys.readouterr().out
        assert idemp == ""
    finally:
        os.chdir(cwd)

