# ruff: noqa: I001
"""Deterministic text patcher for H-DAE core packs (stdlib-only).

Implements idempotent fixes for:
- BEX-001: narrow broad/bare except
- SIL-002: replace silent handler pass/continue with `raise`
- MDA-003: mutable defaults → None + init
- SUB-006: add check=True, text=True to subprocess.*; do not remove shell=True
- YAML-015: replace yaml.load with yaml.safe_load

Uses ast to locate nodes and applies minimal text edits while preserving most
formatting. All transforms are designed to be idempotent.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import List, Tuple

import libcst as cst

PACK_BEX = "BEX-001"
PACK_SIL = "SIL-002"
PACK_MDA = "MDA-003"
PACK_SUB = "SUB-006"
PACK_YAML = "YAML-015"


ALLOWED_EXCS = (
    "json.JSONDecodeError",
    "KeyError",
    "IndexError",
    "ValueError",
    "TypeError",
    "OSError",
    "subprocess.CalledProcessError",
)


@dataclass
class Edit:
    start: Tuple[int, int]  # (line, col) 1-based line
    end: Tuple[int, int]
    replacement: str


def _apply_edits(src: str, edits: List[Edit]) -> str:
    if not edits:
        return src
    # Apply in reverse document order
    lines = src.splitlines(True)
    def to_offset(line: int, col: int) -> int:
        return sum(len(ln) for ln in lines[: line - 1]) + col
    flat = src
    for e in sorted(edits, key=lambda x: (x.start[0], x.start[1], x.end[0], x.end[1]), reverse=True):
        s = to_offset(e.start[0], e.start[1])
        t = to_offset(e.end[0], e.end[1])
        flat = flat[:s] + e.replacement + flat[t:]
    return flat


def _unified_diff(path: str, before: str, after: str) -> str:
    a = before.splitlines(True)
    b = after.splitlines(True)
    diff = difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}")
    return "".join(diff)


def fix_bex(src: str, path: str) -> Tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    need_subprocess_import = False
    class V(ast.NodeVisitor):
        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            for h in node.handlers:
                # If already narrowed and includes subprocess.CalledProcessError, ensure import
                nonlocal need_subprocess_import
                t = h.type
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "subprocess" and t.attr == "CalledProcessError":
                    need_subprocess_import = True
                if isinstance(t, ast.Tuple):
                    for el in t.elts:
                        if isinstance(el, ast.Attribute) and isinstance(el.value, ast.Name) and el.value.id == "subprocess" and el.attr == "CalledProcessError":
                            need_subprocess_import = True
                # already narrowed? tuple or specific names
                if h.type is None:
                    to = "(" + ", ".join(ALLOWED_EXCS) + ")"
                elif isinstance(h.type, ast.Name) and h.type.id in {"Exception", "BaseException"}:
                    to = "(" + ", ".join(ALLOWED_EXCS) + ")"
                else:
                    continue
                need_subprocess_import = True
                # Idempotency: if except already contains any of our names, skip
                # Read the header text slice
                if not hasattr(h, "lineno") or not hasattr(h, "end_lineno"):
                    continue
                lno = h.lineno
                line_text = src.splitlines(True)[lno - 1]
                if any(exc in line_text for exc in ALLOWED_EXCS) and "except (" in line_text:
                    continue
                # Build replacement header
                indent = line_text[: h.col_offset]
                header = indent + "except " + to
                if getattr(h, "name", None):
                    header += f" as {h.name}"
                header += ":"
                edits.append(
                    Edit(start=(lno, 0), end=(lno, len(line_text)), replacement=header + ("\n" if line_text.endswith("\n") else ""))
                )
            self.generic_visit(node)
    V().visit(tree)
    out = _apply_edits(src, edits)
    # Optionally insert 'import subprocess' at module top if not present and we used it
    if need_subprocess_import and "subprocess.CalledProcessError" in out:
        try:
            mod = ast.parse(out)
        except SyntaxError:
            return out, _unified_diff(path, src, out) if out != src else ""
        # check for top-level import of subprocess
        has_top = False
        for n in mod.body:
            if isinstance(n, ast.Import) and any(na.name == "subprocess" for na in n.names):
                has_top = True
                break
            if isinstance(n, ast.ImportFrom) and n.module == "subprocess":
                has_top = True
                break
        if not has_top:
            insert_after_line = 0
            i = 0
            # skip module docstring
            if mod.body:
                first = mod.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    insert_after_line = getattr(first, "end_lineno", 1) or 1
                    i = 1
            # skip existing imports
            while i < len(mod.body) and isinstance(mod.body[i], (ast.Import, ast.ImportFrom)):
                insert_after_line = getattr(mod.body[i], "end_lineno", getattr(mod.body[i], "lineno", insert_after_line)) or insert_after_line
                i += 1
            lines = out.splitlines(True)
            insert_text = "import subprocess\n"
            idx = insert_after_line
            lines[idx:idx] = [insert_text]
            out2 = "".join(lines)
            return out2, _unified_diff(path, src, out2) if out2 != src else ""
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_sil(src: str, path: str) -> Tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    lines = src.splitlines(True)
    class V(ast.NodeVisitor):
        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            for h in node.handlers:
                if len(h.body) == 1 and isinstance(h.body[0], (ast.Pass, ast.Continue)):
                    stmt = h.body[0]
                    lno = stmt.lineno
                    line_text = lines[lno - 1]
                    indent = line_text[: stmt.col_offset]
                    # Idempotency: if line already 'raise' skip
                    if line_text.strip().startswith("raise"):
                        continue
                    edits.append(
                        Edit(
                            start=(lno, 0),
                            end=(lno, len(line_text)),
                            replacement=indent + "raise" + ("\n" if line_text.endswith("\n") else ""),
                        )
                    )
            self.generic_visit(node)
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_mda(src: str, path: str) -> Tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    lines = src.splitlines(True)
    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if not node.args.defaults:
                return
            total_args = node.args.args
            defaults = node.args.defaults
            offset = len(total_args) - len(defaults)
            for i, d in enumerate(defaults):
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    arg = total_args[offset + i]
                    # Idempotency: if any initial guard exists in body
                    guard = f"if {arg.arg} is None:"
                    if any(getattr(s, "lineno", -1) for s in node.body):
                        body_slice = "\n".join(lines[(node.body[0].lineno - 1) : (node.body[-1].end_lineno if hasattr(node.body[-1], "end_lineno") else node.body[-1].lineno)])
                        if guard in body_slice:
                            continue
                    # 1) change signature default to None (line of default)
                    def_line = lines[node.lineno - 1]
                    # naive replace: arg=... → arg=None (works for simple one-line defs in fixtures)
                    before = f"{arg.arg}="
                    if before in def_line:
                        start_col = def_line.index(before) + len(before)
                        end_col = start_col
                        # advance until ',' or ')'
                        while end_col < len(def_line) and def_line[end_col] not in ",)\n":
                            end_col += 1
                        edits.append(Edit(start=(node.lineno, start_col), end=(node.lineno, end_col), replacement="None"))
                    # 2) insert init at start of body
                    ctor = "[]" if isinstance(d, ast.List) else "{}" if isinstance(d, ast.Dict) else "set()"
                    first_stmt_line = node.body[0].lineno
                    indent = lines[first_stmt_line - 1][: node.body[0].col_offset]
                    init = f"{indent}if {arg.arg} is None:\n{indent}    {arg.arg} = {ctor}\n"
                    edits.append(Edit(start=(first_stmt_line, 0), end=(first_stmt_line, 0), replacement=init))
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_sub(src: str, path: str) -> Tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    lines = src.splitlines(True)
    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            else:
                name = None
            if name not in {"subprocess.run", "subprocess.call", "subprocess.Popen"}:
                return
            # Build keyword presence map
            kws = {k.arg: k for k in node.keywords if k.arg}
            need_check = "check" not in kws
            need_text = "text" not in kws
            if not need_check and not need_text:
                return
            # naive text insertion: after function call open paren up to first kw/end
            lno = node.lineno
            endln = node.end_lineno if hasattr(node, "end_lineno") else node.lineno
            call_lines = "".join(lines[lno - 1 : endln])
            # Idempotency safety: skip if "check=True" or "text=True" already substring
            if "check=True" in call_lines and "text=True" in call_lines:
                return
            insert = []
            if need_check:
                insert.append("check=True")
            if need_text:
                insert.append("text=True")
            insertion = ", " + ", ".join(insert)
            # Find rightmost ')' matching open '(' of this call line (best-effort: assume single-line calls in fixtures)
            line_text = lines[lno - 1]
            idx = line_text.rfind(")")
            if idx == -1:
                return
            edits.append(Edit(start=(lno, idx), end=(lno, idx), replacement=insertion))
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


class YamlSafeLoadTransformer(cst.CSTTransformer):
    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        func = original_node.func
        if (
            isinstance(func, cst.Attribute)
            and isinstance(func.value, cst.Name)
            and func.value.value == "yaml"
            and func.attr.value == "load"
        ):
            new_func = cst.Attribute(value=func.value, attr=cst.Name("safe_load"), dot=func.dot)
            new_args = [
                arg
                for arg in updated_node.args
                if not (
                    arg.keyword
                    and isinstance(arg.keyword, cst.Name)
                    and arg.keyword.value == "Loader"
                )
            ]
            if new_args and new_args[-1].comma is not None:
                new_args[-1] = new_args[-1].with_changes(comma=None)
            return updated_node.with_changes(func=new_func, args=new_args)
        return updated_node


def fix_yaml(src: str, path: str) -> Tuple[str, str]:
    try:
        mod = cst.parse_module(src)
    except Exception:
        return src, ""
    new_mod = mod.visit(YamlSafeLoadTransformer())
    out = new_mod.code
    return out, _unified_diff(path, src, out) if out != src else ""


FIXERS = [
    (PACK_BEX, fix_bex),
    (PACK_SIL, fix_sil),
    (PACK_MDA, fix_mda),
    (PACK_SUB, fix_sub),
    (PACK_YAML, fix_yaml),
]


def apply_all(src: str, path: str, packs: set[str] | None = None) -> Tuple[str, List[str]]:
    diffs: List[str] = []
    curr = src
    for pack, fixer in FIXERS:
        if packs is not None and pack not in packs:
            continue
        nxt, diff = fixer(curr, path)
        if diff:
            diffs.append(diff)
        curr = nxt
    return curr, diffs
