# ruff: noqa: I001
import json


def risky(path: str) -> dict:
    try:
        data = json.loads(open(path).read())
        return data
    except Exception:
        # ambiguous: which exact exceptions should be caught here?
        return {}

