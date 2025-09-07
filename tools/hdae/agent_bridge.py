from __future__ import annotations
# ruff: noqa: I001

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
import logging
from typing import Any, Dict, Iterable, List, Tuple

from .cli import _load_all_tfs, _read
from .verify import run_verify


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
LOG = logging.getLogger(__name__)


@dataclass
class TaskPacket:
    tf_id: str
    file: str
    lineno: int
    code_frame: str
    allowed_transforms: List[str]
    decision_rule: str
    hints: List[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "tf_id": self.tf_id,
                "file": self.file,
                "lineno": self.lineno,
                "code_frame": self.code_frame,
                "allowed_transforms": self.allowed_transforms,
                "decision_rule": self.decision_rule,
                "hints": self.hints,
            },
            ensure_ascii=False,
        )


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _extract_frame(file: str, span: Tuple[int, int] | None, fallback: str) -> str:
    try:
        text = _read(file)
    except OSError:
        return fallback
    lines = text.splitlines()
    if not span:
        # first 8 lines as a small frame
        return "\n".join(lines[:8])
    s, e = span
    s = max(1, s)
    e = min(len(lines), e)
    pre = max(1, s - 2)
    post = min(len(lines), e + 2)
    return "\n".join(lines[pre - 1 : post])


def _load_tf_index() -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for _path, tf in _load_all_tfs():
        tf_id = str(tf.get("tf_id", ""))
        if tf_id:
            idx[tf_id] = tf
    return idx


def _is_ambiguous_finding(f: Dict[str, Any]) -> bool:
    # Ambiguity heuristic (kept deterministic):
    # - SUB-006 with message "uses shell=True" → ambiguous (not auto-fixed)
    # - BEX-001 with tokens that imply domain-specific exceptions → require human guidance
    pack = str(f.get("pack", ""))
    msg = str(f.get("message", ""))
    hints = [str(h) for h in f.get("hint_tokens", [])]
    if pack == "SUB-006" and "shell=True" in msg:
        return True
    if pack == "BEX-001" and any(h in hints for h in ["json.load", "json.loads", "[]-indexing", "subprocess.*"]):
        return True
    return False


def emit_tasks(findings: Iterable[Dict[str, Any]]) -> List[str]:
    """Emit JSON task packets for ambiguous findings under .hdae/tasks/.

    Returns list of generated file paths.
    """
    out_dir = os.path.join(ROOT, ".hdae", "tasks")
    _ensure_dir(out_dir)

    tf_by_id = _load_tf_index()
    written: List[str] = []
    n = 0
    for f in findings:
        if not _is_ambiguous_finding(f):
            continue
        tf_id = str(f.get("pack", ""))
        tf = tf_by_id.get(tf_id, {})
        L = tf.get("L", {}) if isinstance(tf, dict) else {}
        E = tf.get("E", {}) if isinstance(tf, dict) else {}
        packet = TaskPacket(
            tf_id=tf_id,
            file=str(f.get("file", "")),
            lineno=int(f.get("line", 1)),
            code_frame=_extract_frame(str(f.get("file", "")), f.get("span"), str(f.get("frame", ""))),
            allowed_transforms=[str(t) for t in L.get("transforms", [])] if isinstance(L, dict) else [],
            decision_rule=str(L.get("decision_rule", "")) if isinstance(L, dict) else "",
            hints=[str(h) for h in E.get("hints", [])] if isinstance(E, dict) else [],
        )
        n += 1
        path = os.path.join(out_dir, f"task_{n:03d}_{tf_id}.json")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(packet.to_json())
        written.append(path)
    return written


def _git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, check=True, capture_output=True)


def _parse_diff_targets(diff_text: str) -> List[str]:
    targets: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            # formats: +++ b/path or +++ path
            m = re.match(r"^\+\+\+\s+(?:b/)?(.+)$", line)
            if m:
                p = m.group(1).strip()
                # exclude /dev/null
                if p != "/dev/null":
                    targets.append(p)
    return targets


def _apply_patches_in(cwd: str, diffs: List[str]) -> Tuple[bool, str]:
    """Apply a list of unified diffs in a git worktree.

    Returns (ok, log). Uses `git apply` for determinism.
    """
    logs: List[str] = []
    for i, diff in enumerate(diffs, 1):
        patch_path = os.path.join(cwd, f".hdae.patch.{i}.diff")
        with open(patch_path, "w", encoding="utf-8") as fp:
            fp.write(diff)
        try:
            _git("apply", "--check", patch_path, cwd=cwd)
            _git("apply", patch_path, cwd=cwd)
            logs.append(f"applied: {os.path.basename(patch_path)}")
        except subprocess.CalledProcessError as e:
            logs.append(e.stdout or "")
            logs.append(e.stderr or "")
            return False, "".join(logs)
    return True, "".join(logs)


def ingest_diffs(from_dir: str) -> Dict[str, int]:
    """Ingest unified diffs from a directory, verify, and accept or waive.

    Strategy:
    - Create a temporary git worktree at HEAD
    - Apply all diffs in that worktree
    - Run verify there
    - If verify passes, apply diffs to main tree idempotently (skip if already applied)
    - If verify fails, emit a waiver file under docs/agents/waivers/PR-<N>.md
    Returns a summary dict: {accepted: n, waived: m}
    """
    # Collect diff texts
    diffs: List[str] = []
    for name in sorted(os.listdir(from_dir)):
        if not name.endswith(('.diff', '.patch', '.txt')):
            continue
        p = os.path.join(from_dir, name)
        try:
            diffs.append(_read(p))
        except OSError:
            raise
    if not diffs:
        return {"accepted": 0, "waived": 0}

    # Prepare worktree
    with tempfile.TemporaryDirectory(prefix="hdae-wt-") as tmp:
        # ensure tmp exists and is clean dir
        _git("worktree", "add", "--detach", tmp, "HEAD")
        # Overlay any uncommitted changes from the working tree so verification reflects current code
        try:
            changed = subprocess.run(["git", "diff", "--name-only"], cwd=ROOT, check=True, text=True, capture_output=True)
            for rel in [p for p in changed.stdout.splitlines() if p.strip()]:
                src = os.path.join(ROOT, rel)
                dst = os.path.join(tmp, rel)
                if os.path.isfile(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    try:
                        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                            fdst.write(fsrc.read())
                    except OSError as e:
                        LOG.debug("agent_bridge: overlay copy failed for %s: %s", rel, e)
        except subprocess.CalledProcessError as e:
            LOG.debug("agent_bridge: listing uncommitted changes failed: %s", e)
        try:
            ok, _log = _apply_patches_in(tmp, diffs)
            if not ok:
                _waive_for_diffs(diffs, reason="patch apply failed in worktree")
                _git("worktree", "remove", "--force", tmp)
                return {"accepted": 0, "waived": 1}
            # Run verify (skip nested pytest if configured). Prefer project venv python.
            vpy = os.path.join(ROOT, ".venv", "bin", "python")
            old_py = os.environ.get("HDAE_PY")
            old_scope = os.environ.get("HDAE_VERIFY_SCOPE")
            if os.path.exists(vpy):
                os.environ["HDAE_PY"] = vpy
            # During nested verify, focus on tools only to avoid local uncommitted test changes
            os.environ["HDAE_VERIFY_SCOPE"] = "tools"
            ok, _verify_out = run_verify(cwd=tmp)
            if old_py is None:
                os.environ.pop("HDAE_PY", None)
            else:
                os.environ["HDAE_PY"] = old_py
            if old_scope is None:
                os.environ.pop("HDAE_VERIFY_SCOPE", None)
            else:
                os.environ["HDAE_VERIFY_SCOPE"] = old_scope
            if ok:
                accepted = _accept_into_main(diffs)
                _git("worktree", "remove", "--force", tmp)
                return {"accepted": accepted, "waived": 0}
            _waive_for_diffs(diffs, reason="verify failed")
            _git("worktree", "remove", "--force", tmp)
            return {"accepted": 0, "waived": 1}
        finally:
            # In case worktree remove failed, ensure tmp is gone
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError as e:
                LOG.debug("agent_bridge: cleanup failed: %s", e)


def _accept_into_main(diffs: List[str]) -> int:
    """Apply diffs to the main working tree idempotently. Returns count applied."""
    applied = 0
    for i, diff in enumerate(diffs, 1):
        patch_path = os.path.join(ROOT, f".hdae.accept.{i}.diff")
        with open(patch_path, "w", encoding="utf-8") as fp:
            fp.write(diff)
        # Idempotency: if reverse-apply check succeeds, patch is already applied
        already = False
        try:
            _git("apply", "--reverse", "--check", patch_path, cwd=ROOT)
            already = True
        except subprocess.CalledProcessError:
            already = False
        if already:
            continue
        _git("apply", patch_path, cwd=ROOT)
        applied += 1
        try:
            os.remove(patch_path)
        except OSError as e:
            LOG.debug("agent_bridge: remove patch temp failed: %s", e)
    return applied


def _waive_for_diffs(diffs: List[str], reason: str) -> None:
    pr_num = os.environ.get("HDAE_PR", "0")
    wdir = os.path.join(ROOT, "docs", "agents", "waivers")
    _ensure_dir(wdir)
    out_path = os.path.join(wdir, f"PR-{pr_num}.md")
    snippets: List[str] = []
    for d in diffs:
        targets = _parse_diff_targets(d)
        for t in targets:
            frame = _extract_frame(os.path.join(ROOT, t), None, f"<file {t}>")
            snippets.append(f"### {t}\n\n```\n{frame}\n```\n")
    body = [
        f"WAIVER (reason: {reason})\n",
        "\n".join(snippets) if snippets else "(no frames)",
        "\n",
    ]
    with open(out_path, "a", encoding="utf-8") as fp:
        fp.write("\n".join(body))


def waive(find: Dict[str, Any], reason: str, pr: int = 0) -> str:
    """Append a waiver entry for a single finding and return path."""
    wdir = os.path.join(ROOT, "docs", "agents", "waivers")
    _ensure_dir(wdir)
    out_path = os.path.join(wdir, f"PR-{pr}.md")
    file = str(find.get("file", ""))
    span = find.get("span")
    frame = _extract_frame(file, span, str(find.get("frame", "")))
    block = [
        f"## {find.get('pack', 'TF')} at {os.path.relpath(file, ROOT)}:{find.get('line', 0)}\n",
        f"Reason: {reason}\n\n",
        "```\n" + frame + "\n```\n",
    ]
    with open(out_path, "a", encoding="utf-8") as fp:
        fp.write("\n".join(block))
    return out_path
