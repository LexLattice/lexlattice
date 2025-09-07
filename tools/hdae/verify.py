from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Tuple


def run_verify(cwd: str | None = None) -> Tuple[bool, str]:
    """Run ruff + mypy + pytest and return (ok, combined_stdout).

    Deterministic: no randomness or wall-clock branching.
    To avoid recursive pytest during outer pytest runs, set env
    HDAE_SKIP_INNER_PYTEST=1 to skip the pytest stage.
    """
    py = os.environ.get("HDAE_PY", sys.executable)
    # Scope selection (tools-only vs all)
    scope = os.environ.get("HDAE_VERIFY_SCOPE", "all")
    if scope == "tools":
        ruff_targets = ["tools/hdae"]
        mypy_targets = ["tools/hdae"]
    else:
        # Exclude fixtures from linting to avoid false positives on golden files
        ruff_targets = ["tools/hdae", "tests/hdae"]
        mypy_targets = ["tools/hdae", "tests/hdae"]
    checks: List[List[str]] = [
        [py, "-m", "ruff", "check", *ruff_targets],
        [py, "-m", "mypy", "--explicit-package-bases", *mypy_targets],
    ]
    if os.environ.get("HDAE_SKIP_INNER_PYTEST") not in {"1", "true", "True"}:
        checks.append([py, "-m", "pytest", "-q"])

    out_parts: List[str] = []
    for cmd in checks:
        try:
            r = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
            out_parts.append(r.stdout)
        except subprocess.CalledProcessError as e:  # deterministic failure path
            out_parts.append(e.stdout or "")
            out_parts.append(e.stderr or "")
            return False, "".join(out_parts)
    return True, "".join(out_parts)
