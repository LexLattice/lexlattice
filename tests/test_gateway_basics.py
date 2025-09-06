import pathlib
import sys

# Ensure project root is on sys.path for imports when running with testpaths
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gateway.apply_bundle import (
    ASK_SIGNAL,
    STOP_SIGNAL,
    preflight,
    should_ask_stop,
)


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
    # No gates: should not raise
    preflight({"layers": {"L2": {"gates": []}}})

    # A clearly non-existent tool triggers a failure deterministically
    try:
        preflight({"layers": {"L2": {"gates": ["__definitely_missing_tool__"]}}})
        raised = False
    except ValueError:
        raised = True
    assert raised is True
