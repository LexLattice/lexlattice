# ruff: noqa: I001
import json

def load_data(path):
    try:
        with open(path) as f:
            return json.loads(f.read())
    except Exception:
        return {}
