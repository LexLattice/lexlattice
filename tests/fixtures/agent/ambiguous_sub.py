# ruff: noqa: I001
import subprocess


def run_cmd(cmd: str) -> int:
    # ambiguous: uses shell=True which is risky
    return subprocess.run(cmd, shell=True).returncode

