# ruff: noqa: I001
import json
import subprocess

def load_data(path):
    try:
        with open(path) as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError, OSError, subprocess.CalledProcessError):
        return {}
