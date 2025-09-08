# ruff: noqa: I001
# ruff: noqa: I001
from __future__ import annotations

from tools.hdae.cli import _load_packs, _render_pack_table, _render_pack_block, main


def test_load_registry() -> None:
    packs = _load_packs()
    assert "BEX-001" in packs
    assert packs["BEX-001"]["name"] == "Ban blanket except Exception"


def test_cli_list(capsys) -> None:  # type: ignore[override]
    main(["packs", "--list"])
    out = capsys.readouterr().out
    expected = _render_pack_table(_load_packs())
    assert out == expected


def test_cli_explain(capsys) -> None:  # type: ignore[override]
    main(["packs", "--explain", "BEX-001"])
    out = capsys.readouterr().out
    packs = _load_packs()
    expected = _render_pack_block("BEX-001", packs["BEX-001"])
    assert out == expected

