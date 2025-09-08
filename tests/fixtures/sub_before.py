# ruff: noqa: I001
import subprocess

def run_ls():
    return subprocess.run(["echo", "hi"])  # missing check/text
