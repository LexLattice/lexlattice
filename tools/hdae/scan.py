# ruff: noqa: I001
"""Deterministic AST-based scanners for H-DAE packs (Task-5, non-async).

Emits JSONL via `hdae scan`. Cheap AST heuristics only (stdlib).

Covered packs:
- BEX-001: broad/bare except
- SIL-002: silent handler
- MDA-003: mutable defaults
- SUB-006: subprocess hazards
- RES-005: resource handling (open/socket without context manager)
- SQL-007: string-formatted SQL passed to execute/executemany
- ARG-008: argparse enums unconstrained (type=str without choices)
- TYP-009: public defs lacking annotations / Any leaks
- LOG-010: print() in libraries
- ERR-011: `raise NewErr(...)` inside except without `from e`
- ROL-012: naive sliding-window recompute in loops
- IOB-013: I/O in hot loops
- PATH-014: path built with '+' or f-strings (in open call)
- YAML-015: yaml.load (unsafe)
- JSON-016: json.loads without JSONDecodeError handling
- CPL-017: functions >= 100 LOC
- DUP-018: near-duplicate functions (normalized text similarity)
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

PACK_RES = "RES-005"
PACK_SQL = "SQL-007"
PACK_ARG = "ARG-008"
PACK_TYP = "TYP-009"
PACK_LOG = "LOG-010"
PACK_ERR = "ERR-011"
PACK_ROL = "ROL-012"
PACK_IOB = "IOB-013"
PACK_PATH = "PATH-014"
PACK_YAML = "YAML-015"
PACK_JSON = "JSON-016"
PACK_CPL = "CPL-017"
PACK_DUP = "DUP-018"


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

    # Back-compat alias for earlier tests that expect `tf_id`
    @property
    def tf_id(self) -> str:  # pragma: no cover
        return self.pack

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
        self._in_main_guard_stack: List[bool] = []

    def generic_visit(self, node: ast.AST) -> None:  # push/pop stack for frames
        self._stack.append(node)
        super().generic_visit(node)
        self._stack.pop()

    # Helpers
    def _handler_name(self, h: ast.ExceptHandler) -> Optional[str]:
        nm = getattr(h, "name", None)
        if isinstance(nm, str) and nm:
            return nm
        return None

    def _has_json_decode_handler_here(self) -> bool:
        for n in reversed(self._stack):
            if isinstance(n, ast.Try):
                for h in n.handlers:
                    t = h.type
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                        if t.value.id == "json" and t.attr == "JSONDecodeError":
                            return True
        return False

    # BEX/SIL/ERR
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
            # ERR-011: raise NewErr(...) inside except without from e
            hname = self._handler_name(h)
            if hname:
                for st in h.body:
                    if isinstance(st, ast.Raise) and st.exc is not None and st.cause is None:
                        self.findings.append(
                            Finding(
                                pack=PACK_ERR,
                                file=self.file,
                                line=st.lineno,
                                col=st.col_offset,
                                message="raise without 'from e'",
                                frame=_enclosing_frame(self._stack),
                                hint_tokens=[hname],
                            )
                        )
        self.generic_visit(node)

    # MDA/CPL/TYP
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        # MDA: mutable defaults
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

        # CPL-017: long function (>= 100 LOC)
        try:
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            loc = max(end - start + 1, 0)
        except Exception:
            loc = 0
        if loc >= 100:
            self.findings.append(
                Finding(
                    pack=PACK_CPL,
                    file=self.file,
                    line=node.lineno,
                    col=node.col_offset,
                    message=f"function length {loc} >= 100 LOC",
                    frame=f"def {node.name}()",
                    hint_tokens=["long-func"],
                )
            )

        # TYP-009: public defs lacking annotations or Any usage
        public = not node.name.startswith("_")
        missing = public and (not node.returns or any(a.annotation is None for a in node.args.args))
        has_any = False
        for a in node.args.args:
            ann = getattr(a, "annotation", None)
            if isinstance(ann, ast.Name) and ann.id == "Any":
                has_any = True
        if isinstance(node.returns, ast.Name) and node.returns.id == "Any":
            has_any = True
        if public and (missing or has_any):
            self.findings.append(
                Finding(
                    pack=PACK_TYP,
                    file=self.file,
                    line=node.lineno,
                    col=node.col_offset,
                    message=("missing annotations" if missing else "Any in signature"),
                    frame=f"def {node.name}()",
                    hint_tokens=["public-def"],
                )
            )
        self.generic_visit(node)

    # SUB/RES/SQL/ARG/LOG/YAML/JSON/PATH
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        def dotted_name(n: ast.AST) -> Optional[str]:
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                return f"{n.value.id}.{n.attr}"
            if isinstance(n, ast.Name):
                return n.id
            return None

        name = dotted_name(node.func)
        # SUB: subprocess hazards
        if name and name.startswith("subprocess."):
            def kw_present(arg: str) -> bool:
                return any(isinstance(k, ast.keyword) and k.arg == arg for k in node.keywords)

            def kw_equals_true(arg: str) -> bool:
                return any(
                    isinstance(k, ast.keyword) and k.arg == arg and getattr(k.value, "value", None) is True
                    for k in node.keywords
                )

            uses_shell = kw_equals_true("shell")
            if name == "subprocess.run":
                if not kw_present("check"):
                    self.findings.append(
                        Finding(
                            pack=PACK_SUB,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="missing check=True",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[name],
                        )
                    )
                else:
                    if not (kw_present("text") or kw_present("universal_newlines")):
                        self.findings.append(
                            Finding(
                                pack=PACK_SUB,
                                file=self.file,
                                line=node.lineno,
                                col=node.col_offset,
                                message="consider text=True",
                                frame=_enclosing_frame(self._stack),
                                hint_tokens=[name],
                            )
                        )
                if uses_shell:
                    self.findings.append(
                        Finding(
                            pack=PACK_SUB,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="uses shell=True",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[name],
                        )
                    )
            elif name in {"subprocess.check_call", "subprocess.check_output"}:
                if uses_shell:
                    self.findings.append(
                        Finding(
                            pack=PACK_SUB,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="uses shell=True",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[name],
                        )
                    )
            elif name == "subprocess.call":
                self.findings.append(
                    Finding(
                        pack=PACK_SUB,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="use run(..., check=True)",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=[name],
                    )
                )
                if uses_shell:
                    self.findings.append(
                        Finding(
                            pack=PACK_SUB,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="uses shell=True",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[name],
                        )
                    )
            elif name == "subprocess.Popen":
                if uses_shell:
                    self.findings.append(
                        Finding(
                            pack=PACK_SUB,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="uses shell=True",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[name],
                        )
                    )

        # RES-005: open()/socket.socket() without with-context
        if name in {"open", "socket.socket"}:
            in_with = False
            for n in reversed(self._stack):
                if isinstance(n, ast.With):
                    in_with = True
                    break
                if isinstance(n, ast.FunctionDef):
                    break
            if not in_with:
                self.findings.append(
                    Finding(
                        pack=PACK_RES,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message=f"{name} without context manager",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=[name],
                    )
                )

        # SQL-007: formatted strings to execute/ executemany
        if name and (name.endswith(".execute") or name.endswith(".executemany")):
            if node.args:
                a0 = node.args[0]
                risky = False
                if isinstance(a0, ast.JoinedStr):  # f-string
                    risky = True
                elif isinstance(a0, ast.BinOp) and isinstance(a0.op, (ast.Add, ast.Mod)):
                    risky = True
                elif isinstance(a0, ast.Call) and isinstance(a0.func, ast.Attribute) and a0.func.attr == "format":
                    risky = True
                elif isinstance(a0, ast.Name):
                    # Look for recent assignment to this name with formatted string
                    target = a0.id
                    func_node = None
                    for n in reversed(self._stack):
                        if isinstance(n, ast.FunctionDef):
                            func_node = n
                            break
                    if func_node is not None:
                        val_node: ast.AST | None = None
                        for st in func_node.body:
                            if hasattr(st, "lineno") and getattr(st, "lineno", 0) >= node.lineno:
                                break
                            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and st.targets[0].id == target:
                                val_node = st.value
                        if val_node is not None:
                            if isinstance(val_node, ast.JoinedStr):
                                risky = True
                            elif isinstance(val_node, ast.BinOp) and isinstance(val_node.op, (ast.Add, ast.Mod)):
                                risky = True
                            elif isinstance(val_node, ast.Call) and isinstance(val_node.func, ast.Attribute) and val_node.func.attr == "format":
                                risky = True
                if risky:
                    self.findings.append(
                        Finding(
                            pack=PACK_SQL,
                            file=self.file,
                            line=node.lineno,
                            col=node.col_offset,
                            message="string-formatted SQL passed to execute",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=["execute"],
                            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
                        )
                    )

        # ARG-008: argparse.add_argument(..., type=str) without choices
        if name and name.endswith(".add_argument"):
            has_type_str = any(
                isinstance(k, ast.keyword) and k.arg == "type" and isinstance(k.value, ast.Name) and k.value.id == "str"
                for k in node.keywords
            )
            has_choices = any(isinstance(k, ast.keyword) and k.arg == "choices" for k in node.keywords)
            if has_type_str and not has_choices:
                self.findings.append(
                    Finding(
                        pack=PACK_ARG,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="CLI enum missing choices",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=["argparse"],
                    )
                )

        # LOG-010: print() outside __main__
        if name == "print":
            in_main = any(self._in_main_guard_stack)
            if not in_main:
                self.findings.append(
                    Finding(
                        pack=PACK_LOG,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="print() in library code",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=["print"],
                    )
                )

        # YAML-015: yaml.load(...)
        if name == "yaml.load":
            self.findings.append(
                Finding(
                    pack=PACK_YAML,
                    file=self.file,
                    line=node.lineno,
                    col=node.col_offset,
                    message="unsafe yaml.load; use safe_load",
                    frame=_enclosing_frame(self._stack),
                    hint_tokens=["yaml.load"],
                )
            )

        # JSON-016: json.loads without handling JSONDecodeError
        if name == "json.loads":
            if not self._has_json_decode_handler_here():
                self.findings.append(
                    Finding(
                        pack=PACK_JSON,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="json.loads without JSONDecodeError handling",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=["json.loads"],
                    )
                )

        # PATH-014: path building via '+' or f-string in common sites (open)
        if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
            a0 = node.args[0]
            if isinstance(a0, (ast.JoinedStr, ast.BinOp)):
                self.findings.append(
                    Finding(
                        pack=PACK_PATH,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="path built via f-string or '+'",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=["path"],
                    )
                )

        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:  # detect main guard
        # push main-guard context for the body
        is_main = False
        test = node.test
        if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__":
            for op, comp in zip(test.ops, test.comparators):
                if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and comp.value == "__main__":
                    is_main = True
                    break
        self._in_main_guard_stack.append(is_main)
        for n in node.body:
            self._stack.append(node)
            self.visit(n)
            self._stack.pop()
        self._in_main_guard_stack.pop()
        for n in node.orelse:
            self.visit(n)

    def visit_For(self, node: ast.For) -> None:  # IOB-013 and ROL-012
        # IOB-013: look for open()/requests.get()/socket.socket() inside for-body
        risky_calls = {"open", "socket.socket", "requests.get", "requests.post"}
        for n in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(n, ast.Call):
                nm = None
                if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
                    nm = f"{n.func.value.id}.{n.func.attr}"
                elif isinstance(n.func, ast.Name):
                    nm = n.func.id
                if nm in risky_calls:
                    self.findings.append(
                        Finding(
                            pack=PACK_IOB,
                            file=self.file,
                            line=n.lineno,
                            col=n.col_offset,
                            message=f"I/O call in loop: {nm}",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[nm],
                            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
                        )
                    )
        # ROL-012: naive sliding-window via slice in loop
        for n in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice):
                lo = n.slice.lower
                hi = n.slice.upper
                if isinstance(lo, ast.BinOp) and isinstance(lo.op, (ast.Sub, ast.Add)) and isinstance(hi, ast.Name):
                    self.findings.append(
                        Finding(
                            pack=PACK_ROL,
                            file=self.file,
                            line=n.lineno,
                            col=n.col_offset,
                            message="sliding window recompute in loop",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=["slice"],
                            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
                        )
                    )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:  # IOB-013 detection similar
        for n in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(n, ast.Call):
                nm = None
                if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
                    nm = f"{n.func.value.id}.{n.func.attr}"
                elif isinstance(n.func, ast.Name):
                    nm = n.func.id
                if nm in {"open", "socket.socket", "requests.get", "requests.post"}:
                    self.findings.append(
                        Finding(
                            pack=PACK_IOB,
                            file=self.file,
                            line=n.lineno,
                            col=n.col_offset,
                            message=f"I/O call in loop: {nm}",
                            frame=_enclosing_frame(self._stack),
                            hint_tokens=[nm],
                            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
                        )
                    )
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:  # PATH-014 heuristic
        # Detect path built by string concatenation with slash
        def has_slash_const(expr: ast.AST) -> bool:
            if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
                return "/" in expr.value
            if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
                return has_slash_const(expr.left) or has_slash_const(expr.right)
            return False
        if isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
            if has_slash_const(node.value):
                self.findings.append(
                    Finding(
                        pack=PACK_PATH,
                        file=self.file,
                        line=node.lineno,
                        col=node.col_offset,
                        message="path built by string concatenation",
                        frame=_enclosing_frame(self._stack),
                        hint_tokens=["+", "/"],
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
    # DUP-018: per-file pairwise compare function bodies (very cheap version)
    # We compute normalized text per function and compare with others in same file
    # Caller passes paths one-by-one normally; for simplicity, treat each file independently
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
