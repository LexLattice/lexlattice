import pytest

from gateway import ASK_SIGNAL, STOP_SIGNAL, preflight, should_ask_stop


def test_should_ask_stop_returns_constant() -> None:
    bundle = {
        "ask_stop": {
            "ask_if": ["gh auth missing"],
            "stop_if": ["would violate L1"],
        }
    }
    assert should_ask_stop(bundle, "gh auth missing") == ASK_SIGNAL
    assert should_ask_stop(bundle, "would violate L1") == STOP_SIGNAL


def test_preflight_checks_only_declared_gates() -> None:
    # No gates: should not raise and returns empty list
    assert preflight({"layers": {"L2": {"gates": []}}}) == []

    # Non-CLI or logical gates should be ignored and not raise; returns empty list
    assert preflight({"layers": {"L2": {"gates": ["__definitely_missing_tool__", "docs_updated"]}}}) == []


def test_preflight_missing_cli_tool_raises(monkeypatch) -> None:
    # Simulate missing CLI tools by patching detection to always fail
    import gateway.apply_bundle as ab

    monkeypatch.setattr(ab.shutil, "which", lambda name: None)

    orig_exists = ab.pathlib.Path.exists

    def fake_exists(self):  # type: ignore[no-redef]
        if self.name in {"ruff", "mypy", "pytest"} and self.parent.name == "bin" and self.parent.parent.name == ".venv":
            return False
        return orig_exists(self)

    monkeypatch.setattr(ab.pathlib.Path, "exists", fake_exists, raising=False)

    with pytest.raises(ValueError):
        preflight({"layers": {"L2": {"gates": ["ruff"]}}})
