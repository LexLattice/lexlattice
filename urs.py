#!/usr/bin/env python3
# MIT License — see LICENSE in repo root
# Copyright (c) 2025 LexLattice
# LexLattice v0.1 — compile + enforce
# Stdlib-only except optional PyYAML for nicer YAML parsing.

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, NoReturn, Optional, cast

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

HERE = os.path.abspath(os.path.dirname(__file__))

def die(msg: str, code: int = 1) -> NoReturn:
    print(f"[lexlattice] {msg}", file=sys.stderr)
    sys.exit(code)

def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write(path: str, s: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]

def load_yaml(s: str) -> Any:
    if yaml is not None:
        try:
            return yaml.safe_load(s) or {}
        except Exception:
            # Fall back to minimal parser on any YAML load error
            pass
    # minimal fallback parser
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_item: Optional[Dict[str, Any]] = None
    for line in s.splitlines():
        if not line.strip():
            continue
        if (
            re.match(r"^\s*-\s", line)
            and current_key is not None
            and isinstance(data.get(current_key), list)
        ):
            item_line = line.strip()[1:].strip()
            if ":" in item_line:
                k, v = item_line.split(":", 1)
                lst = cast(List[Any], data[current_key])
                current_item = {k.strip(): v.strip().strip('\"\'')}
                lst.append(current_item)
                data[current_key] = lst
            else:
                lst = cast(List[Any], data[current_key])
                lst.append(item_line.strip().strip('\"\''))
                data[current_key] = lst
                current_item = None
            continue
        # Support continued mapping lines under the last list item
        if (
            current_key is not None
            and isinstance(data.get(current_key), list)
            and isinstance(current_item, dict)
        ):
            cont = re.match(r"^\s+([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
            if cont:
                ck, cv = cont.group(1), cont.group(2)
                current_item[ck] = cv.strip().strip('\"\'')
                continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2)
            v_stripped = v.strip()
            if v_stripped in ("", "[]", "{}"):
                # Treat blank / [] as list (sufficient for our tiny schema)
                data[k] = [] if v_stripped in ("", "[]") else {}
                current_key = k
                continue
            data[k] = v_stripped.strip('\"\'')
            current_key = k
    return data

def load_meta(path: str) -> Dict[str, Any]:
    try:
        meta = load_yaml(read(path))
        if not isinstance(meta, dict):
            die("Meta.yaml must map keys to values.")
        meta["layers"] = meta.get("layers", []) or []
        meta["waivers"] = meta.get("waivers", []) or []
        return meta
    except FileNotFoundError:
        die(f"Meta file not found: {path}")

FRONT_MAT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S | re.M)

def parse_rules_from_markdown(path: str) -> List[Dict[str, Any]]:
    content = read(path)
    rules, idx = [], 0
    while True:
        m = FRONT_MAT_RE.search(content, idx)
        if not m:
            break
        fm, body_start = m.group(1), m.end()
        m2 = FRONT_MAT_RE.search(content, body_start)
        body_end = m2.start() if m2 else len(content)
        body = content[body_start:body_end].strip()
        meta = load_yaml(fm) or {}
        rid = meta.get("id") or f"AUTO-{sha256(fm)[:6]}"
        rules.append({
            "id": rid,
            "title": meta.get("title", rid),
            "severity": (meta.get("severity") or "advice").lower(),
            "scope": meta.get("scope", "repo"),
            "rationale": meta.get("rationale", ""),
            "checks": meta.get("checks", []),
            "layer": None,
            "source_file": path,
            "body": body,
        })
        idx = body_end
    if not rules:
        rid = f"AUTO-{os.path.basename(path)}"
        rules.append({
            "id": rid, "title": rid, "severity": "advice", "scope": "repo",
            "rationale": "", "checks": [], "layer": None, "source_file": path,
            "body": content.strip()
        })
    return rules

def resolve_source(spec: str) -> str:
    if spec.startswith("local:"):
        rel = spec.split(":", 1)[1]
        return os.path.abspath(os.path.join(HERE, rel))
    die(f"Unsupported source scheme in '{spec}'. Only 'local:' is supported in v0.1.")

def compile_rulebook(meta_path: str, out_path: str, stamp: bool = False) -> Dict[str, Any]:
    meta = load_meta(meta_path)
    layers = meta.get("layers", [])
    waivers = meta.get("waivers", [])
    compiled: Dict[str, Dict[str, Any]] = {}
    layer_order: Dict[str, int] = {lay["id"]: i for i, lay in enumerate(layers)}
    for lay in layers:
        lid = lay["id"]
        severity_hint = (lay.get("severity") or "").lower()
        src = resolve_source(lay["source"])
        if not os.path.exists(src):
            print(f"[lexlattice] note: missing optional layer source {src}; skipping.")
            continue
        for r in parse_rules_from_markdown(src):
            r = dict(r)
            r["layer"] = lid
            sev = (r.get("severity") or severity_hint or "advice").lower()
            r["severity"] = sev
            rid = r["id"]
            if rid in compiled:
                curr = compiled[rid]
                curr_layer_idx = layer_order.get(curr["layer"], -1)
                new_layer_idx = layer_order.get(lid, -1)
                if curr["severity"] == "hard":  # hard rules are non-overrideable
                    continue
                if new_layer_idx >= curr_layer_idx:
                    compiled[rid] = r
            else:
                compiled[rid] = r

    today = dt.date.today()
    for w in waivers:
        try:
            wid = w["id"]
            expires = w.get("expires")
            active = True
            if expires:
                try:
                    exp_date = dt.date.fromisoformat(str(expires))
                    active = today <= exp_date
                except ValueError:
                    active = False
                    print(
                        f"[lexlattice] waiver '{w.get('id','?')}' has invalid expires; ignoring",
                        file=sys.stderr,
                    )
            if wid in compiled and active:
                compiled[wid].setdefault("_waivers", []).append(w)
        except (KeyError, TypeError):
            continue

    groups: Dict[str, List[Dict[str, Any]]] = {"hard": [], "soft": [], "advice": []}
    for r in compiled.values():
        sev = r.get("severity", "advice").lower()
        groups.setdefault(sev, []).append(r)
    for k in groups:
        groups[k].sort(key=lambda x: (x["layer"], x["id"]))

    total = sum(len(v) for v in groups.values())
    header = (f"# Compiled Rulebook\n\n" +
              (f"Generated: {dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n\n" if stamp else "") +
              f"Total rules: {total}  •  hard={len(groups['hard'])}  •  soft={len(groups['soft'])}  •  advice={len(groups['advice'])}\n\n" +
              "## Index by severity\n")
    for sev in ("hard","soft","advice"):
        header += f"\n### {sev.upper()}\n"
        for r in groups[sev]:
            header += f"- [{r['id']}] {r['title']}  _(layer: {r['layer']}, scope: {r['scope']})_\n"

    parts = []
    for sev in ("hard","soft","advice"):
        parts.append(f"\n\n## {sev.upper()} RULES\n")
        for r in groups[sev]:
            parts.append(f"### {r['id']} — {r['title']}\n")
            parts.append(f"- Severity: **{r['severity']}**  •  Layer: **{r['layer']}**  •  Scope: `{r['scope']}`\n")
            if r.get("rationale"):
                parts.append(f"- Rationale: {r['rationale']}\n")
            if r.get("checks"):
                parts.append("- Checks:\n")
                for c in r["checks"]:
                    parts.append(f"  - `{json.dumps(c, ensure_ascii=False)}`\n")
            if r.get("_waivers"):
                parts.append("- Active waivers:\n")
                for w in r["_waivers"]:
                    parts.append(f"  - {w.get('reason','(no reason)')} — scope={w.get('scope','*')} expires={w.get('expires','*')}\n")
            if r["body"].strip():
                parts.append("\n" + r["body"].strip() + "\n")

    out = header + "".join(parts) + "\n"
    write(out_path, out)
    print(f"[lexlattice] compiled {total} rule(s) → {out_path}")
    return {"groups": groups, "out_path": out}

def enforce(meta_path: str, level: str, out_path: str) -> int:
    result = compile_rulebook(meta_path, out_path)
    hard_rules = result["groups"].get("hard", [])
    if not hard_rules:
        die("No hard rules found. Add at least one L0 'hard' rule.", code=2)
    print(f"[lexlattice] hard rules present: {len(hard_rules)}")
    print("[lexlattice] v0 structural enforcement only (drift/presence).")
    return 0

def main():
    ap = argparse.ArgumentParser(prog="lexlattice", description="Portable rulebook compiler & enforcer")
    ap.add_argument("command", choices=["compile","enforce"])
    ap.add_argument("--meta", default="Meta.yaml")
    ap.add_argument("--out", default="docs/agents/Compiled.Rulebook.md")
    ap.add_argument("--json-out", default=None, help="Optional: also emit JSON bundle to this path")
    ap.add_argument("--level", default="hard", choices=["hard","soft","advice"])
    ap.add_argument("--stamp", action="store_true", help="Include timestamp in compiled output (off by default)")
    args = ap.parse_args()
    if args.command == "compile":
        compile_rulebook(args.meta, args.out, stamp=bool(args.stamp))
        if args.json_out:
            # Call the bundle emitter (stdlib-only).
            tool_id = f"lexlattice/urs@{hashlib.sha256(read(__file__).encode('utf-8')).hexdigest()[:12]}"
            cmd = [
                sys.executable,
                "tools/bundle_emit.py",
                "--meta",
                args.meta,
                "--out",
                args.json_out,
                "--tool",
                tool_id,
            ]
            subprocess.check_call(cmd)
    else:
        enforce(args.meta, args.level, args.out)

if __name__ == "__main__":
    main()
