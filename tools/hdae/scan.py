# ruff: noqa: I001
"""Deterministic AST-based scanners for H-DAE packs.

Findings are emitted as JSONL from `hdae scan`.
Packs: BEX-001 (broad/bare except), SIL-002 (silent handler),
       MDA-003 (mutable defaults), SUB-006 (subprocess hazards).
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional, Tuple


PACK_BEX = "BEX-001"
PACK_SIL = "SIL-002"
PACK_MDA = "MDA-003"
PACK_SUB = "SUB-006"


@dataclass
class Finding:
    pack: str
    file: str
    line: int
    col: int
    message: str
    frame: str
    hint_tokens: List[str]
    span: Optional[Tuple[int, int]] = None  # start,end lines (inclusive)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _enclosing_frame(stack: List[ast.AST]) -> str:
    for node in reversed(stack):
        if isinstance(node, ast.FunctionDef):
            return f"def {node.name}()"
        if isinstance(node, ast.AsyncFunctionDef):
            return f"async def {node.name}()"
        if isinstance(node, ast.ClassDef):
            return f"class {node.name}"
    return "<module>"


def _tokens_in_try(try_node: ast.Try, source: str) -> List[str]:
    lines = source.splitlines()
    s = try_node.body[0].lineno if try_node.body else try_node.lineno
    e = (try_node.body[-1].end_lineno if try_node.body and hasattr(try_node.body[-1], "end_lineno") else try_node.lineno)
    text = "\n".join(lines[s - 1 : e])
    tokens = []
    for t in ("json.load", "json.loads", "open(", "Path(", "os.", "shutil.", "int(", "float(", "Decimal(", "datetime."):
        if t in text:
            tokens.append(t)
    if "[" in text and "]" in text:
        tokens.append("[]-indexing")
    if ".run(" in text or ".Popen(" in text or ".call(" in text:
        tokens.append("subprocess.*")
    return tokens


class _Visitor(ast.NodeVisitor):
    def __init__(self, file: str, src: str) -> None:
        self.file = file
        self.src = src
        self.findings: List[Finding] = []
        self._stack: List[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:  # push/pop stack for frames
        self._stack.append(node)
        super().generic_visit(node)
        self._stack.pop()

    # BEX/SIL
    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802 (ast API)
        for h in node.handlers:
            # BEX: bare or broad except
            if h.type is None or (
                isinstance(h.type, ast.Name) and h.type.id in {"Exception", "BaseException"}
            ):
                frame = _enclosing_frame(self._stack)
                hint = _tokens_in_try(node, self.src)
                start = node.body[0].lineno if node.body else node.lineno
                if node.body:
                    last = node.body[-1]
                    end_ln: int = getattr(last, "end_lineno", getattr(last, "lineno", node.lineno))
                else:
                    end_ln = node.lineno
                self.findings.append(
                    Finding(
                        pack=PACK_BEX,
                        file=self.file,
                        line=h.lineno or node.lineno,
                        col=h.col_offset or 0,
                        message="broad/bare except detected",
                        frame=frame,
                        hint_tokens=hint,
                        span=(start, end_ln),
                    )
                )
            # SIL: handler is pass/continue only (ignore tests/ files at caller)
            body = h.body
            if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Continue)):
                frame = _enclosing_frame(self._stack)
                self.findings.append(
                    Finding(
                        pack=PACK_SIL,
                        file=self.file,
                        line=body[0].lineno or h.lineno or 1,
                        col=body[0].col_offset or 0,
                        message="silent handler (pass/continue)",
                        frame=frame,
                        hint_tokens=[],
                    )
                )
        self.generic_visit(node)

    # MDA: mutable defaults
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        for arg, default in zip(node.args.args[-len(node.args.defaults) :], node.args.defaults):
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                frame = _enclosing_frame(self._stack)
                self.findings.append(
                    Finding(
                        pack=PACK_MDA,
                        file=self.file,
                        line=getattr(default, "lineno", node.lineno),
                        col=getattr(default, "col_offset", 0),
                        message=f"mutable default for '{arg.arg}'",
                        frame=frame,
                        hint_tokens=[type(default).__name__],
                    )
                )
        self.generic_visit(node)

    # SUB: subprocess hazards
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        def dotted_name(n: ast.AST) -> Optional[str]:
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                return f"{n.value.id}.{n.attr}"
            return None

        name = dotted_name(node.func)
        if name in {"subprocess.run", "subprocess.call", "subprocess.Popen"}:
            has_check = any(isinstance(k, ast.keyword) and k.arg == "check" for k in node.keywords)
            uses_shell = any(isinstance(k, ast.keyword) and k.arg == "shell" and getattr(k.value, "value", None) is True for k in node.keywords)
            if (not has_check) or uses_shell:
                self.findings.append(
                    Finding(
                        pack=PACK_SUB,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message=("missing check=True" if not has_check else "uses shell=True"),
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=[name or "subprocess"],
                    )
                )
        self.generic_visit(node)


def scan_paths(paths: Iterable[str]) -> List[Finding]:
    out: List[Finding] = []
    for path in paths:
        if not path.endswith(".py"):
            continue
        if os.path.relpath(path).startswith("tests/"):
            continue
        try:
            src = _read_text(path)
            tree = ast.parse(src)
        except (SyntaxError, OSError):
            raise
        vis = _Visitor(path, src)
        vis.visit(tree)
        out.extend([f for f in vis.findings if not os.path.relpath(f.file).startswith("tests/")])
    return out


def list_repo_py_files(root: str = ".") -> List[str]:
    pyfiles: List[str] = []
    for base, _dirs, files in os.walk(root):
        if "/.venv" in base or "/.git" in base or base.startswith("./.venv"):
            continue
        for fn in files:
            if fn.endswith(".py"):
                pyfiles.append(os.path.join(base, fn))
    return sorted(pyfiles)
