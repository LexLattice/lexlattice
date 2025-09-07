from __future__ import annotations
# ruff: noqa: I001

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


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


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_frame(file: str, span: Tuple[int, int] | None, fallback: str) -> str:
    try:
        text = _read(file)
    except OSError:
        return fallback
    lines = text.splitlines()
    if not span:
        return "\n".join(lines[:8])
    s, e = span
    s = max(1, s)
    e = min(len(lines), e)
    pre = max(1, s - 2)
    post = min(len(lines), e + 2)
    return "\n".join(lines[pre - 1 : post])


SUGGEST_ONLY = {
    "SQL-007",
    "TYP-009",
    "ROL-012",
    "IOB-013",
    "CPL-017",
    "DUP-018",
}


def emit_tasks(findings: Iterable[Dict[str, Any]]) -> List[str]:
    """Emit JSON task packets for suggest-only packs under .hdae/tasks/.

    Returns list of generated file paths.
    """
    out_dir = os.path.join(ROOT, ".hdae", "tasks")
    _ensure_dir(out_dir)
    written: List[str] = []
    n = 0
    for f in findings:
        tf_id = str(f.get("pack") or f.get("tf_id") or "")
        if tf_id not in SUGGEST_ONLY:
            continue
        n += 1
        packet = TaskPacket(
            tf_id=tf_id,
            file=str(f.get("file", "")),
            lineno=int(f.get("line", 1)),
            code_frame=_extract_frame(str(f.get("file", "")), f.get("span"), str(f.get("frame", ""))),
            # keep generic placeholders
            allowed_transforms=["refactor", "extract-function", "rewrite"],
            decision_rule="preserve behavior; reduce risk; parametrize inputs",
            hints=[str(h) for h in f.get("hint_tokens", [])],
        )
        path = os.path.join(out_dir, f"task_{n:03d}_{tf_id}.json")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(packet.to_json())
        written.append(path)
    return written


def ingest_diffs(from_dir: str) -> Dict[str, int]:  # minimal stub for Task-5
    files = [p for p in os.listdir(from_dir) if p.endswith((".diff", ".patch", ".txt"))]
    return {"accepted": 0, "waived": 0, "ingested": len(files)}  # type: ignore[return-value]

