# ruff: noqa: I001
from __future__ import annotations

from pathlib import Path
import textwrap
import json

from tools.hdae.scan import scan_paths


FIX = Path("tests/fixtures/packs")


def _write_tmp(tmp: Path, name: str, content: str) -> str:
    p = tmp / name
    p.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return str(p)


def test_scan_new_packs(tmp_path: Path) -> None:
    files = []
    # RES-005
    files.append(_write_tmp(tmp_path, "res.py", """
    def read_first(p):
        f = open(p, 'r')
        d = f.read()
        f.close()
        return d
    """))
    # SQL-007
    files.append(_write_tmp(tmp_path, "sql.py", """
    def do(c, x):
        q = f"select * from t where id={x}"
        c.execute(q)
    """))
    # ARG-008
    files.append(_write_tmp(tmp_path, "arg.py", """
    import argparse
    MODES = ['fast','slow']
    def build():
        p = argparse.ArgumentParser()
        p.add_argument('--mode', type=str)
        return p
    """))
    # TYP-009
    files.append(_write_tmp(tmp_path, "typ.py", """
    def public(x):
        return x
    """))
    # LOG-010
    files.append(_write_tmp(tmp_path, "log.py", """
    def lib():
        print('hi')
    """))
    # ERR-011
    files.append(_write_tmp(tmp_path, "err.py", """
    def f():
        try:
            g()
        except ValueError as e:
            raise RuntimeError('bad')
    """))
    # ROL-012 and IOB-013 in one file
    files.append(_write_tmp(tmp_path, "loop.py", """
    def roll(a, w):
        s = 0
        for i in range(len(a)):
            s += sum(a[i-w:i])
            open('x.txt')
        return s
    """))
    # PATH-014
    files.append(_write_tmp(tmp_path, "path.py", """
    def j(base, name):
        return base + '/' + name
    """))
    # YAML-015
    files.append(_write_tmp(tmp_path, "yamlx.py", """
    import yaml
    def loadit(s):
        return yaml.load(s)
    """))
    # JSON-016
    files.append(_write_tmp(tmp_path, "jsonx.py", """
    import json
    def parse(s):
        return json.loads(s)
    """))

    findings = scan_paths(files)
    by_pack: dict[str, int] = {}
    for f in findings:
        by_pack.setdefault(f.pack, 0)
        by_pack[f.pack] += 1

    assert by_pack.get('RES-005', 0) >= 1
    assert by_pack.get('SQL-007', 0) >= 1
    assert by_pack.get('ARG-008', 0) >= 1
    assert by_pack.get('TYP-009', 0) >= 1
    assert by_pack.get('LOG-010', 0) >= 1
    assert by_pack.get('ERR-011', 0) >= 1
    assert by_pack.get('ROL-012', 0) >= 1
    assert by_pack.get('IOB-013', 0) >= 1
    assert by_pack.get('PATH-014', 0) >= 1
    assert by_pack.get('YAML-015', 0) >= 1
    assert by_pack.get('JSON-016', 0) >= 1

    # JSONL serializable
    js = [json.loads(f.to_json()) for f in findings]
    assert all('pack' in j and 'file' in j for j in js)
