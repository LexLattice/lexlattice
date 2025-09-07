#!/usr/bin/env python3
# MIT License — see LICENSE in repo root
# Copyright (c) 2025 LexLattice
"""
Emit a canonical, deterministic JSON Rulebook Bundle from Meta.yaml + layers.
- No timestamps in the bundle (determinism).
- Hash = sha256 over the canonical JSON **without** the 'hash' field.
- Stdlib-only (PyYAML optional).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

HERE = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
ROOT = HERE  # repo root (script lives in tools/)

# Optional PyYAML; fall back to tiny parser if unavailable
yaml: Any = None
try:
    import yaml as _yaml  # type: ignore
    yaml = _yaml
except Exception:  # pragma: no cover - fallback used if PyYAML absent
    yaml = None  # fallback parser below

FRONT_MAT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S | re.M)


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def file_sha256(path: str) -> str:
    return hashlib.sha256(read_bytes(path)).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def die(msg: str, code: int = 1) -> None:
    print(f"[bundle_emit] {msg}", file=sys.stderr)
    sys.exit(code)


def load_yaml(s: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(s)
    # extremely small fallback (sufficient for Meta.yaml in this repo)
    data: Dict[str, Any] = {}
    current_key = None
    for line in s.splitlines():
        if not line.strip():
            continue
        # list item
        if re.match(r"^\s*-\s", line) and current_key is not None and isinstance(data.get(current_key), list):
            item_line = line.strip()[1:].strip()
            if ":" in item_line:
                k, v = item_line.split(":", 1)
                data[current_key].append({k.strip(): v.strip().strip('\"\'')})
            else:
                data[current_key].append(item_line.strip().strip('\"\''))
            continue
        # key: value
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2)
            v = v.strip()
            if v in ("", "[]"):
                data[k] = []
                current_key = k
            elif v == "{}":
                data[k] = {}
                current_key = k
            else:
                data[k] = v.strip().strip('\"\'')
                current_key = k
    return data


def resolve_source(spec: str) -> str:
    if spec.startswith("local:"):
        rel = spec.split(":", 1)[1]
        return os.path.abspath(os.path.join(ROOT, rel))
    die(f"Unsupported source scheme: {spec}. Only 'local:' is supported in rb-emit-1.")
    return ""


def load_meta(meta_path: str) -> Dict[str, Any]:
    try:
        meta = load_yaml(read(meta_path)) or {}
        if not isinstance(meta, dict):
            die("Meta.yaml must be a mapping")
        layers = meta.get("layers") or []
        waivers = meta.get("waivers") or []
        if not isinstance(layers, list):
            die("Meta.yaml: 'layers' must be a list")
        if not isinstance(waivers, list):
            die("Meta.yaml: 'waivers' must be a list")
        meta["layers"], meta["waivers"] = layers, waivers
        return meta
    except FileNotFoundError:
        die(f"Meta file not found: {meta_path}")
        return {}


def parse_rules_from_markdown(path: str) -> List[Dict[str, Any]]:
    content = read(path)
    rules: List[Dict[str, Any]] = []
    idx = 0
    while True:
        m = FRONT_MAT_RE.search(content, idx)
        if not m:
            break
        fm, body_start = m.group(1), m.end()
        m2 = FRONT_MAT_RE.search(content, body_start)
        body_end = m2.start() if m2 else len(content)
        body = content[body_start:body_end].strip()
        meta = load_yaml(fm) or {}
        rid = meta.get("id") or f"AUTO-{sha256_bytes(fm.encode())[:6]}"
        r = {
            "id": rid,
            "title": meta.get("title", rid),
            "severity": (meta.get("severity") or "advice").lower(),
            "scope": meta.get("scope", "repo"),
            "rationale": meta.get("rationale", ""),
            "checks": meta.get("checks", []),
            "source_file": path,
            "body": body,
        }
        rules.append(r)
        idx = body_end
    if not rules:
        rid = f"AUTO-{os.path.basename(path)}"
        rules.append(
            {
                "id": rid,
                "title": rid,
                "severity": "advice",
                "scope": "repo",
                "rationale": "",
                "checks": [],
                "source_file": path,
                "body": content.strip(),
            }
        )
    return rules


def canonical_json(d: Any) -> bytes:
    # Stable, whitespace-free JSON (UTF-8) — deterministic across runs
    return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def collect(meta_path: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    meta = load_meta(meta_path)
    meta_sha = file_sha256(meta_path)
    layers_out: List[Dict[str, Any]] = []
    rules_out: List[Dict[str, Any]] = []
    ask_if_agg: List[str] = []
    stop_if_agg: List[str] = []

    for lay in meta.get("layers", []):
        lid = lay["id"]
        severity_hint = (lay.get("severity") or "").lower()
        src = resolve_source(lay["source"])
        src_sha = file_sha256(src) if os.path.exists(src) else None
        layers_out.append(
            {
                "id": lid,
                "name": lay.get("name", lid),
                "severity": severity_hint or "advice",
                "source": lay["source"],
                "resolved": src,
                "sourceSha": src_sha,
            }
        )
        if not os.path.exists(src):
            continue
        for r in parse_rules_from_markdown(src):
            sev = (r.get("severity") or severity_hint or "advice").lower()
            checks = r.get("checks") or []
            # Aggregate ask/stop from agent checks
            for c in checks:
                if isinstance(c, dict) and c.get("type") == "agent":
                    ask_if_agg.extend(c.get("ask_if", []) or [])
                    stop_if_agg.extend(c.get("stop_if", []) or [])
            rules_out.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "severity": sev,
                    "scope": r.get("scope", "repo"),
                    "layer": lid,
                    "checks": checks,
                    "sourceFile": os.path.relpath(r["source_file"], ROOT),
                    "sourceSha": file_sha256(r["source_file"]) if os.path.exists(r["source_file"]) else None,
                }
            )

    source = {
        "metaPath": os.path.relpath(meta_path, ROOT),
        "metaSha": meta_sha,
        "files": [
            {"path": os.path.relpath(x.get("resolved", ""), ROOT), "sha": x.get("sourceSha")}
            for x in layers_out
            if x.get("resolved")
        ],
    }
    ask_stop = {
        "ask_if": sorted(set(ask_if_agg)),
        "stop_if": sorted(set(stop_if_agg)),
    }
    return meta, source, layers_out, rules_out, ask_stop


def emit_bundle(meta_path: str, out_path: str, tool_id: str) -> str:
    meta, source, layers, rules, ask_stop = collect(meta_path)
    bundle = {
        "schema": "1.0",
        "tool": tool_id,
        "source": source,
        "layers": layers,
        "rules": rules,
        "ask_stop": ask_stop,
        "waivers": meta.get("waivers", []),
    }
    # Compute content-hash over bundle **without** hash field
    pre_hash_bytes = canonical_json(bundle)
    h = sha256_bytes(pre_hash_bytes)
    bundle["hash"] = f"sha256:{h}"
    final_bytes = canonical_json(bundle)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(final_bytes)
    print(f"[bundle_emit] wrote {out_path} ({len(final_bytes)} bytes)")
    print(f"[bundle_emit] hash={bundle['hash']}")
    return bundle["hash"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Emit deterministic Rulebook Bundle (JSON)")
    ap.add_argument("--meta", default="Meta.yaml")
    ap.add_argument("--out", default="docs/bundles/base.llbundle.json")
    ap.add_argument("--tool", default=None, help="Tool identifier to embed (e.g., lexlattice/urs@<sha>)")
    args = ap.parse_args()

    tool_id = args.tool
    if not tool_id:
        # Best-effort: reference urs.py short SHA if present, else static
        urs_path = os.path.join(ROOT, "urs.py")
        if os.path.exists(urs_path):
            tool_id = f"lexlattice/urs@{file_sha256(urs_path)[:12]}"
        else:
            tool_id = "lexlattice/urs@unknown"

    emit_bundle(args.meta, args.out, tool_id)


if __name__ == "__main__":
    main()
