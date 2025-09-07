# ruff: noqa: I001
import subprocess

def run_ls():
    return subprocess.run(["echo", "hi"], check=True, text=True)  # missing check/text
