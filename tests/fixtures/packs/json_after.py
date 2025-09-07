# ruff: noqa: I001
import json
def parse(s):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None
