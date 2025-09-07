# ruff: noqa: I001
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import argparse
import glob
import json
import os
import re
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
TF_DIR = os.path.join(ROOT, "tools", "hdae", "tf")
SCHEMA_PATH = os.path.join(ROOT, "tools", "hdae", "schema", "tf.schema.json")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_schema() -> Dict[str, Any]:
    try:
        return json.loads(_read(SCHEMA_PATH))
    except Exception as e:  # pragma: no cover
        print(f"schema load error: {e}", file=sys.stderr)
        return {}


def _load_yaml_minimal(s: str) -> Any:
    """Minimal YAML subset loader (mappings + lists of scalars/maps).

    Supports:
    - top-level mappings
    - nested object mappings (e.g., meta:, E:, ...)
    - lists of scalars and lists of small mappings
    """
    data: Dict[str, Any] = {}
    current_key: str | None = None
    # note: no list-of-maps used in our TFs, so we keep lists scalar-only
    current_obj: Dict[str, Any] | None = None  # last object mapping (e.g., meta/E/...)
    nested_list_parent: Dict[str, Any] | None = None  # object that owns current_key as list
    for raw in s.splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # list item under current_key (top-level or nested under object)
        if re.match(r"^\s*-\s", line) and current_key is not None:
            item_text = line.strip()[1:].strip()
            # Prefer nested list under an object if set
            if nested_list_parent is not None and isinstance(nested_list_parent.get(current_key), list):
                container = nested_list_parent[current_key]
            else:
                container = data.setdefault(current_key, [])
                if not isinstance(container, list):
                    container = []
            # Treat list items as scalars, even if they contain ':'
            container.append(item_text.strip().strip("'\""))
            # write back if we created a new top-level list container
            if nested_list_parent is None:
                data[current_key] = container
            else:
                nested_list_parent[current_key] = container
            continue
        # continuation mapping lines under last list item
        # no mapping continuation under list items (not needed for TF files)

        # continuation mapping lines under last object mapping (e.g., meta: ...)
        if current_obj is not None:
            m3 = re.match(r"^\s+([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
            if m3:
                ck, cv = m3.group(1), m3.group(2)
                v = cv.strip()
                if v in ("", "[]"):
                    current_obj[ck] = []
                    current_key = ck
                    nested_list_parent = current_obj
                elif v == "{}":
                    current_obj[ck] = {}
                else:
                    current_obj[ck] = v.strip("'\"")
                    nested_list_parent = None
                # Do not change current_key here; lists under this key will update current_key later
                continue

        # top-level mapping
        m2 = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m2:
            k, v = m2.group(1), m2.group(2)
            v_stripped = v.strip()
            if v_stripped in ("", "[]", "{}"):
                # For top-level keys, prefer object when blank unless explicit []
                if v_stripped == "[]":
                    data[k] = []
                else:
                    data[k] = {}
            else:
                data[k] = v_stripped.strip("'\"")
            current_key = k
            current_obj = data[k] if isinstance(data[k], dict) else None
            nested_list_parent = None
    return data


def _load_tf(path: str) -> Dict[str, Any]:
    try:
        return _load_yaml_minimal(_read(path)) or {}
    except Exception as e:  # pragma: no cover
        raise ValueError(f"failed to load YAML: {path}: {e}")


def _type_name(x: Any) -> str:
    return type(x).__name__


def _must_be_str(x: Any) -> bool:  # small helpers for clarity
    return isinstance(x, str)


def _must_be_bool(x: Any) -> bool:
    return str(x).lower() in ("true", "false") or isinstance(x, bool)


def _to_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    return str(x).lower() == "true"


def _must_be_list_of_str(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def _validate_tf(tf: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    # required top-level fields
    for k in ("tf_id", "name", "meta", "E", "O", "L", "IO", "verify", "links"):
        if k not in tf:
            errors.append(f"missing field: {k}")
    if errors:
        return errors

    if not _must_be_str(tf["tf_id"]):
        errors.append(f"tf_id must be string (got {_type_name(tf['tf_id'])})")
    if not _must_be_str(tf["name"]):
        errors.append(f"name must be string (got {_type_name(tf['name'])})")

    # meta
    meta = tf.get("meta", {})
    if not isinstance(meta, dict):
        errors.append("meta must be object")
    else:
        for k in ("severity", "auto", "detect"):
            if k not in meta:
                errors.append(f"meta.{k} required")
        sev = meta.get("severity")
        if sev not in ("low", "medium", "high"):
            errors.append("meta.severity must be one of low|medium|high")
        if not _must_be_bool(meta.get("auto")):
            errors.append("meta.auto must be boolean")
        if not _must_be_bool(meta.get("detect")):
            errors.append("meta.detect must be boolean")

    # E
    epistem = tf.get("E", {})
    if not isinstance(epistem, dict):
        errors.append("E must be object")
    else:
        if not _must_be_list_of_str(epistem.get("detect_signals", [])):
            errors.append("E.detect_signals must be list[string]")
        if not _must_be_list_of_str(epistem.get("hints", [])):
            errors.append("E.hints must be list[string]")
        # Accept numeric confidence; our minimal YAML parser yields strings; allow numeric-like
        conf = epistem.get("confidence")
        try:
            float(str(conf))
        except Exception:
            errors.append("E.confidence must be number")

    # O
    onto = tf.get("O", {})
    if not isinstance(onto, dict):
        errors.append("O must be object")
    else:
        if not _must_be_list_of_str(onto.get("entities", [])):
            errors.append("O.entities must be list[string]")
        if not _must_be_list_of_str(onto.get("relations", [])):
            errors.append("O.relations must be list[string]")
        if not _must_be_str(onto.get("scope", "")):
            errors.append("O.scope must be string")

    # L
    L = tf.get("L", {})
    if not isinstance(L, dict):
        errors.append("L must be object")
    else:
        if not _must_be_list_of_str(L.get("constraints", [])):
            errors.append("L.constraints must be list[string]")
        if not _must_be_list_of_str(L.get("transforms", [])):
            errors.append("L.transforms must be list[string]")
        if not _must_be_str(L.get("decision_rule", "")):
            errors.append("L.decision_rule must be string")

    # IO
    IO = tf.get("IO", {})
    if not isinstance(IO, dict):
        errors.append("IO must be object")
    else:
        if not _must_be_list_of_str(IO.get("input", [])):
            errors.append("IO.input must be list[string]")
        if not _must_be_list_of_str(IO.get("output", [])):
            errors.append("IO.output must be list[string]")

    # verify
    verify = tf.get("verify", {})
    if not isinstance(verify, dict):
        errors.append("verify must be object")
    else:
        if not _must_be_list_of_str(verify.get("checks", [])):
            errors.append("verify.checks must be list[string]")

    # links
    links = tf.get("links", {})
    if not isinstance(links, dict):
        errors.append("links must be object")
    else:
        if not _must_be_list_of_str(links.get("related", [])):
            errors.append("links.related must be list[string]")

    return errors


def _load_all_tfs() -> List[Tuple[str, Dict[str, Any]]]:
    out: List[Tuple[str, Dict[str, Any]]] = []
    for path in sorted(glob.glob(os.path.join(TF_DIR, "*.yaml"))):
        out.append((path, _load_tf(path)))
    return out


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hdae",
        description=(
            "H-DAE CLI skeleton (L1/L2 tie into Rulebook/DoD). "
            "Subcommands are placeholders; see PR-2 for detectors/patchers."
        ),
    )
    ap.add_argument("command", choices=["scan", "propose", "apply", "verify"], help="Pipeline stage")
    cmd = ap.parse_args(argv).command

    # Always validate TFs for any subcommand
    tfs = _load_all_tfs()
    errors: List[str] = []
    for path, tf in tfs:
        es = _validate_tf(tf)
        if es:
            errors.append(path + "\n  - " + "\n  - ".join(es))
    if errors:
        print("TF schema errors:")
        print("\n".join(errors))
        return 2

    print(f"Loaded {len(tfs)} TF(s): schema OK")
    print(f"{cmd}: NYI; see PR-2")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
