# ruff: noqa: I001
"""Deterministic text patcher for H-DAE packs (stdlib-only, idempotent).

Implements idempotent fixes for:
- BEX-001: narrow broad/bare except
- SIL-002: replace silent handler pass/continue with `raise`
- MDA-003: mutable defaults → None + init
- SUB-006: add check=True, text=True to subprocess.run
- RES-005: wrap simple open(...) patterns in with; remove matching close()
- ARG-008: add choices=[...] to argparse.add_argument when finite list literal present
- LOG-010: replace print(...) in libs with logger.info(...); add logger if absent
- ERR-011: add `from e` in raise inside except ... as e
- PATH-014: replace string path concatenation with Path(...).joinpath(...); add import
- YAML-015: replace yaml.load with yaml.safe_load
- JSON-016: wrap simple json.loads in try/except JSONDecodeError and return None/assign None

Transforms are conservative and only target simple, fixture-friendly shapes. All
edits are minimal textual replacements and strive for idempotency.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import List, Tuple


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


def fix_bex(src: str, path: str) -> tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    need_subprocess_import = False
    lines = src.splitlines(True)
    class V(ast.NodeVisitor):
        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            nonlocal need_subprocess_import
            for h in node.handlers:
                t = h.type
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "subprocess" and t.attr == "CalledProcessError":
                    need_subprocess_import = True
                if isinstance(t, ast.Tuple):
                    for el in t.elts:
                        if isinstance(el, ast.Attribute) and isinstance(el.value, ast.Name) and el.value.id == "subprocess" and el.attr == "CalledProcessError":
                            need_subprocess_import = True
                if h.type is None or (isinstance(h.type, ast.Name) and h.type.id in {"Exception", "BaseException"}):
                    to = "(" + ", ".join(ALLOWED_EXCS) + ")"
                else:
                    continue
                need_subprocess_import = True
                if not hasattr(h, "lineno"):
                    return
                lno = h.lineno
                line_text = lines[lno - 1]
                if any(exc in line_text for exc in ALLOWED_EXCS) and "except (" in line_text:
                    return
                indent = line_text[: h.col_offset]
                header = indent + "except " + to
                if getattr(h, "name", None):
                    header += f" as {h.name}"
                header += ":"
                edits.append(Edit((lno, 0), (lno, len(line_text)), header + ("\n" if line_text.endswith("\n") else "")))
            self.generic_visit(node)
    V().visit(tree)
    out = _apply_edits(src, edits)
    if need_subprocess_import and "subprocess.CalledProcessError" in out and "import subprocess" not in out:
        # insert after module docstring or top
        try:
            mod = ast.parse(out)
        except SyntaxError:
            return out, _unified_diff(path, src, out) if out != src else ""
        insert_after = 0
        if mod.body and isinstance(mod.body[0], ast.Expr) and isinstance(mod.body[0].value, ast.Constant) and isinstance(mod.body[0].value.value, str):
            insert_after = getattr(mod.body[0], "end_lineno", 1) or 1
        lines2 = out.splitlines(True)
        ins = "import subprocess\n"
        lines2.insert(insert_after, ins)
        out2 = "".join(lines2)
        return out2, _unified_diff(path, src, out2) if out2 != src else ""
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_sil(src: str, path: str) -> tuple[str, str]:
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
                    if line_text.strip().startswith("raise"):
                        continue
                    edits.append(Edit((lno, 0), (lno, len(line_text)), indent + "raise" + ("\n" if line_text.endswith("\n") else "")))
            self.generic_visit(node)
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_mda(src: str, path: str) -> tuple[str, str]:
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
                    guard = f"if {arg.arg} is None:"
                    if node.body:
                        body_slice = "\n".join(lines[(node.body[0].lineno - 1) : (node.body[-1].end_lineno if hasattr(node.body[-1], "end_lineno") else node.body[-1].lineno)])
                        if guard in body_slice:
                            continue
                    def_line = lines[node.lineno - 1]
                    before = f"{arg.arg}="
                    if before in def_line:
                        start_col = def_line.index(before) + len(before)
                        end_col = start_col
                        while end_col < len(def_line) and def_line[end_col] not in ",)\n":
                            end_col += 1
                        edits.append(Edit((node.lineno, start_col), (node.lineno, end_col), "None"))
                    ctor = "[]" if isinstance(d, ast.List) else "{}" if isinstance(d, ast.Dict) else "set()"
                    first_stmt_line = node.body[0].lineno if node.body else (node.lineno + 1)
                    indent = lines[first_stmt_line - 1][: node.body[0].col_offset] if node.body else (" " * (node.col_offset + 4))
                    init = f"{indent}if {arg.arg} is None:\n{indent}    {arg.arg} = {ctor}\n"
                    edits.append(Edit((first_stmt_line, 0), (first_stmt_line, 0), init))
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_sub(src: str, path: str) -> tuple[str, str]:
    tree = ast.parse(src)
    edits: List[Edit] = []
    lines = src.splitlines(True)
    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            else:
                return
            if name != "subprocess.run":
                return
            kws = {k.arg: k for k in node.keywords if k.arg}
            need_check = "check" not in kws
            need_text = "text" not in kws and "universal_newlines" not in kws
            if not (need_check or need_text):
                return
            lno = node.lineno
            line_text = lines[lno - 1]
            if "check=True" in line_text and "text=True" in line_text:
                return
            idx = line_text.rfind(")")
            if idx == -1:
                return
            parts = []
            if need_check:
                parts.append("check=True")
            if need_text:
                parts.append("text=True")
            insertion = ", " + ", ".join(parts)
            edits.append(Edit((lno, idx), (lno, idx), insertion))
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_res(src: str, path: str) -> tuple[str, str]:
    """Wrap very simple `f = open(...); ...; f.close()` into a with-block.

    Only handles patterns where `f` is a Name and a matching `f.close()` appears
    shortly after within the same body (module or function).
    """
    mod = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []

    def process_body(body: List[ast.stmt]) -> None:
        for i, st in enumerate(body):
            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and isinstance(st.value, ast.Call):
                if isinstance(st.value.func, ast.Name) and st.value.func.id == "open":
                    var = st.targets[0].id
                else:
                    continue
                # search forward for var.close()
                close_ln = None
                j = i + 1
                while j < len(body):
                    nxt = body[j]
                    if isinstance(nxt, ast.Expr) and isinstance(nxt.value, ast.Call):
                        c = nxt.value
                        if isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name) and c.func.value.id == var and c.func.attr == "close":
                            close_ln = nxt.lineno
                            break
                    j += 1
                if not close_ln:
                    continue
                start_ln = st.lineno
                end_ln = close_ln
                indent = lines[start_ln - 1][: st.col_offset]
                assign_line = lines[start_ln - 1]
                eq = assign_line.find("=")
                call_text = assign_line[eq + 1 :].strip()
                header = f"{indent}with {call_text} as {var}:\n"
                edits.append(Edit((start_ln, 0), (start_ln, len(assign_line)), header))
                close_line_text = lines[end_ln - 1]
                edits.append(Edit((end_ln, 0), (end_ln, len(close_line_text)), ""))
                for ln in range(start_ln + 1, end_ln):
                    edits.append(Edit((ln, 0), (ln, 0), "    "))

    # Process module and function-level bodies
    process_body(mod.body)
    for st in mod.body:
        if isinstance(st, ast.FunctionDef):
            process_body(st.body)

    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_arg(src: str, path: str) -> tuple[str, str]:
    """Add choices=[...] when a finite list literal is present at module top.

    Heuristic: looks for a top-level assignment to a list of str constants (e.g., MODES = ["a","b"])
    and adds choices to parser.add_argument("--mode", type=str) calls that lack it.
    """
    tree = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []
    choices_list: list[str] | None = None
    # Find a candidate list literal at top-level
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.List):
            vals: list[str] = []
            ok = True
            for el in n.value.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    vals.append(el.value)
                else:
                    ok = False
                    break
            if ok and vals:
                choices_list = vals
                break

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
                return
            kws = {k.arg for k in node.keywords if k.arg}
            has_type_str = any(
                isinstance(k, ast.keyword) and k.arg == "type" and isinstance(k.value, ast.Name) and k.value.id == "str"
                for k in node.keywords
            )
            if not has_type_str or "choices" in kws or not choices_list:
                return
            lno = node.lineno
            line_text = lines[lno - 1]
            if "choices=" in line_text:
                return
            idx = line_text.rfind(")")
            if idx == -1:
                return
            insertion = ", choices=[" + ", ".join(repr(s) for s in choices_list) + "]"
            edits.append(Edit((lno, idx), (lno, idx), insertion))
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_log(src: str, path: str) -> tuple[str, str]:
    """Replace print(...) with logger.info(...) and ensure `logger` exists.

    Does not touch inside `if __name__ == "__main__"` blocks.
    """
    tree = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []
    main_blocks: list[tuple[int, int]] = []

    class Vis(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:  # noqa: N802
            if isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__":
                for op, cmp in zip(node.test.ops, node.test.comparators):
                    if isinstance(op, ast.Eq) and isinstance(cmp, ast.Constant) and cmp.value == "__main__":
                        s = node.lineno
                        e = getattr(node, "end_lineno", node.lineno)
                        main_blocks.append((s, e))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                lno = node.lineno
                # skip if inside main guard
                for s, e in main_blocks:
                    if s <= lno <= e:
                        return
                # Replace `print(` with `logger.info(`
                line = lines[lno - 1]
                idx = line.find("print(")
                if idx != -1 and "logger.info(" not in line:
                    edits.append(Edit((lno, idx), (lno, idx + len("print(")), "logger.info("))
            self.generic_visit(node)

    Vis().visit(tree)
    out = _apply_edits(src, edits)
    if out != src:
        # Ensure logger exists
        try:
            mod = ast.parse(out)
        except SyntaxError:
            return out, _unified_diff(path, src, out)
        need_import = True
        need_logger = True
        for n in mod.body:
            if isinstance(n, ast.Import) and any(na.name == "logging" for na in n.names):
                need_import = False
            if isinstance(n, ast.Assign):
                # logger = logging.getLogger(__name__)
                try:
                    if (
                        isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == "logger"
                        and isinstance(n.value, ast.Call)
                        and isinstance(n.value.func, ast.Attribute)
                        and isinstance(n.value.func.value, ast.Name)
                        and n.value.func.value.id == "logging"
                        and n.value.func.attr == "getLogger"
                    ):
                        need_logger = False
                except Exception:
                    pass
        lines2 = out.splitlines(True)
        insert_after = 0
        if mod.body and isinstance(mod.body[0], ast.Expr) and isinstance(mod.body[0].value, ast.Constant) and isinstance(mod.body[0].value.value, str):
            insert_after = getattr(mod.body[0], "end_lineno", 1) or 1
        ins_parts: List[str] = []
        if need_import:
            ins_parts.append("import logging\n")
        if need_logger:
            ins_parts.append("logger = logging.getLogger(__name__)\n")
        if ins_parts:
            lines2.insert(insert_after, "".join(ins_parts))
        out2 = "".join(lines2)
        return out2, _unified_diff(path, src, out2)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_err(src: str, path: str) -> tuple[str, str]:
    """Add `from e` to `raise ...` inside `except ... as e` blocks (simple case)."""
    tree = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []
    class V(ast.NodeVisitor):
        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            for h in node.handlers:
                nm = getattr(h, "name", None)
                if not isinstance(nm, str) or not nm:
                    continue
                for st in h.body:
                    if isinstance(st, ast.Raise) and st.exc is not None and st.cause is None:
                        lno = st.lineno
                        line = lines[lno - 1]
                        if " from " in line:
                            continue
                        # append " from e" at line end, before newline
                        end = len(line.rstrip("\n"))
                        edits.append(Edit((lno, end), (lno, end), f" from {nm}"))
            self.generic_visit(node)
    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_path(src: str, path: str) -> tuple[str, str]:
    """Replace simple path concatenation with Path(...).joinpath(...)."""
    tree = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []
    class V(ast.NodeVisitor):
        def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
            if isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
                # very naive: base + "/" + name → Path(base).joinpath(name)
                lno = node.lineno
                text = lines[lno - 1]
                if "+" in text and "/" in text and "Path(" not in text:
                    # Replace everything after return with Path(...).joinpath(...)
                    # best-effort: grab tokens between 'return ' and end
                    m = re_return_binop(text)
                    if m:
                        base, name = m
                        indent = lines[lno - 1][: node.col_offset]
                        repl = f"{indent}return Path({base}).joinpath({name})\n"
                        edits.append(Edit((lno, 0), (lno, len(text)), repl))
            self.generic_visit(node)
    def re_return_binop(line: str) -> tuple[str, str] | None:
        # crude parser: return <a> + "/" + <b>
        m = re.compile(r"^\s*return\s+([^+]+)\+\s*[\"\']\/[\"\']\s*\+\s*(.+?)\s*$").match(line.strip())
        if not m:
            return None
        return m.group(1).strip(), m.group(2).strip().rstrip("\n")
    import re  # local import for the helper above
    V().visit(tree)
    out = _apply_edits(src, edits)
    if out != src and "from pathlib import Path" not in out and "Path(" in out:
        out = "from pathlib import Path\n" + out
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_yaml(src: str, path: str) -> tuple[str, str]:
    out = src
    if "yaml.load(" in out and "yaml.safe_load(" not in out:
        out = out.replace("yaml.load(", "yaml.safe_load(")
    return out, _unified_diff(path, src, out) if out != src else ""


def fix_json(src: str, path: str) -> tuple[str, str]:
    """Wrap simple json.loads in try/except returning None (or assigning None)."""
    tree = ast.parse(src)
    lines = src.splitlines(True)
    edits: List[Edit] = []

    class V(ast.NodeVisitor):
        def _inside_json_try(self) -> bool:
            # Walk up the stack by re-parsing around current node is complex; use source text containment heuristic
            # Simpler: if any parent Try in the current function has a handler for json.JSONDecodeError, skip
            return False  # stackless visitor fallback

        def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                if isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "json" and node.value.func.attr == "loads":
                    # Idempotency: skip if already inside a try/except for JSONDecodeError by scanning surrounding block text
                    block_text = lines[max(0, node.lineno - 5) : min(len(lines), node.lineno + 5)]
                    if any("JSONDecodeError" in ln for ln in block_text):
                        return
                    # Wrap the whole return in try/except by replacing this single line
                    lno = node.lineno
                    indent = lines[lno - 1][: node.col_offset]
                    arg_text = lines[lno - 1].split("json.loads(", 1)[1]
                    arg_text = arg_text.rsplit(")", 1)[0]
                    block = (
                        f"{indent}try:\n"
                        f"{indent}    return json.loads({arg_text})\n"
                        f"{indent}except json.JSONDecodeError:\n"
                        f"{indent}    return None\n"
                    )
                    edits.append(Edit((lno, 0), (lno, len(lines[lno - 1])), block))
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                if isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "json" and node.value.func.attr == "loads":
                    block_text = lines[max(0, node.lineno - 5) : min(len(lines), node.lineno + 5)]
                    if any("JSONDecodeError" in ln for ln in block_text):
                        return
                    lno = node.lineno
                    indent = lines[lno - 1][: node.col_offset]
                    # text after '=' is loads(...)
                    left = lines[lno - 1].split("=", 1)[0].rstrip()
                    arg_text = lines[lno - 1].split("json.loads(", 1)[1]
                    arg_text = arg_text.rsplit(")", 1)[0]
                    block = (
                        f"{indent}try:\n"
                        f"{indent}    {left} = json.loads({arg_text})\n"
                        f"{indent}except json.JSONDecodeError:\n"
                        f"{indent}    {left} = None\n"
                    )
                    edits.append(Edit((lno, 0), (lno, len(lines[lno - 1])), block))
            self.generic_visit(node)

    V().visit(tree)
    out = _apply_edits(src, edits)
    return out, _unified_diff(path, src, out) if out != src else ""


def apply_all(src: str, path: str, packs: set[str] | None = None) -> tuple[str, list[str]]:
    """Apply all relevant fixers (optionally filtered by `packs`)."""
    diffs: List[str] = []
    curr = src
    order = [
        ("BEX-001", fix_bex),
        ("SIL-002", fix_sil),
        ("MDA-003", fix_mda),
        ("SUB-006", fix_sub),
        ("RES-005", fix_res),
        ("ARG-008", fix_arg),
        ("LOG-010", fix_log),
        ("ERR-011", fix_err),
        ("PATH-014", fix_path),
        ("YAML-015", fix_yaml),
        ("JSON-016", fix_json),
    ]
    for tf_id, fixer in order:
        if packs is not None and tf_id not in packs:
            continue
        nxt, diff = fixer(curr, path)
        if diff:
            diffs.append(diff)
        curr = nxt
    return curr, diffs
