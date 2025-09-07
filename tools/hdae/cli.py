# ruff: noqa: I001
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import argparse
import glob
import json
import os
import re
import sys
import subprocess


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
TF_DIR = os.path.join(ROOT, "tools", "hdae", "tf")
SCHEMA_PATH = os.path.join(ROOT, "tools", "hdae", "schema", "tf.schema.json")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_schema() -> Dict[str, Any]:
    try:
        return json.loads(_read(SCHEMA_PATH))
    except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError, OSError, subprocess.CalledProcessError) as e:
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
    except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError, OSError, subprocess.CalledProcessError) as e:
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
        except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError, OSError, subprocess.CalledProcessError):
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
            "H-DAE CLI (scan/propose/apply/verify/agent). "
            "Deterministic, stdlib-only tooling."
        ),
    )
    ap.add_argument(
        "command",
        choices=["scan", "propose", "apply", "verify", "agent"],
        help="Pipeline stage",
    )
    ap.add_argument("--packs", default="", help="Comma-separated TF ids to include")
    ap.add_argument("--dry-run", action="store_true", help="For propose: print unified diffs")
    ap.add_argument("--apply", action="store_true", help="For propose: apply patches in-place")
    # Parse known args to allow agent subcommands
    cmd, rest = ap.parse_known_args(argv)

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

    packs: set[str] | None = None
    if cmd.packs:
        packs = {p.strip() for p in cmd.packs.split(",") if p.strip()}

    if cmd.command == "scan":
        from .scan import list_repo_py_files, scan_paths

        files = list_repo_py_files(".")
        findings = scan_paths(files)
        for f in findings:
            if packs and getattr(f, "pack", getattr(f, "tf_id", "")) not in packs:
                continue
            print(f.to_json())
        return 0

    if cmd.command in ("propose", "apply"):
        from .scan import list_repo_py_files
        from .patch_cst import apply_all

        dry = bool(cmd.dry_run) or cmd.command == "propose"
        do_apply = bool(cmd.apply) or cmd.command == "apply"
        rc = 0
        for p in list_repo_py_files("."):
            if os.path.relpath(p).startswith("tests/"):
                continue
            try:
                s = _read(p)
            except OSError:
                raise
            new, diffs = apply_all(s, p)
            if diffs:
                for d in diffs:
                    if dry:
                        print(d, end="")
                if do_apply:
                    with open(p, "w", encoding="utf-8") as fp:
                        fp.write(new)
                rc = rc or 0
        return rc

    if cmd.command == "verify":
        from .verify import run_verify

        ok, out = run_verify(cwd=None)
        if out:
            print(out)
        return 0 if ok else 1

    if cmd.command == "agent":
        ag = argparse.ArgumentParser(prog="hdae agent", description="Agent bridge commands")
        ag.add_argument("sub", choices=["emit", "ingest"], help="Agent action")
        ag.add_argument("--from", dest="from_dir", default=".hdae/diffs", help="Ingest diffs from dir")
        ag.add_argument("--packs", default=cmd.packs or "", help="Suggest-only packs to include")
        args = ag.parse_args(rest)
        if args.sub == "emit":
            from .agent_bridge import emit as emit_packets

            data: List[Dict[str, Any]] = []
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            only: set[str] | None = None
            if args.packs:
                only = {p.strip() for p in args.packs.split(',') if p.strip()}
            written = emit_packets(data, only)
            if written:
                print("\n".join(written))
            return 0
        if args.sub == "ingest":
            from .agent_bridge import ingest_diffs

            res = ingest_diffs(args.from_dir)
            print(json.dumps(res))
            # Exit code 0 if all accepted, 1 if any waived
            return 0 if res.get("waived", 0) == 0 else 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
