from __future__ import annotations

# ruff: noqa: I001
from pathlib import Path
import json

from tools.hdae.agent_bridge import emit_tasks


ROOT = Path('.')


def _clean_tasks_dir() -> None:
    tdir = ROOT / '.hdae' / 'tasks'
    if tdir.exists():
        for p in tdir.glob('*.json'):
            try:
                p.unlink()
            except OSError:
                pass


def test_emit_for_suggest_only(tmp_path: Path) -> None:
    _clean_tasks_dir()
    findings = [
        {
            'pack': 'SQL-007',
            'file': str(tmp_path / 'x.py'),
            'line': 3,
            'frame': 'def do()',
            'hint_tokens': ['execute'],
            'span': (1, 5),
        },
        {
            'pack': 'ROL-012',
            'file': str(tmp_path / 'y.py'),
            'line': 10,
            'frame': 'for i in range(n):',
            'hint_tokens': ['slice'],
            'span': (8, 14),
        },
    ]
    written = emit_tasks(findings)
    assert written, 'no packets produced'
    for w in written:
        data = json.loads(Path(w).read_text(encoding='utf-8'))
        for k in ('tf_id', 'file', 'lineno', 'code_frame', 'allowed_transforms', 'decision_rule', 'hints'):
            assert k in data
