# Gateway Demo

```bash
python - <<'PY'
from gateway.apply_bundle import load_bundle, preflight, should_ask_stop
b = load_bundle("docs/bundles/base.json")
checked = preflight(b)
print("checked tools:", checked)
print("ask/stop?", should_ask_stop(b, "gh auth missing"))
PY
```
