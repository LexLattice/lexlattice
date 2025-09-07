import json
from pathlib import Path

from tools.hdae.agent_bridge import emit

ROOT = Path('.')


def _clean_tasks() -> None:
    tdir = ROOT / '.hdae' / 'tasks'
    if tdir.exists():
        for p in tdir.glob('*.json'):
            try:
                p.unlink()
            except OSError:
                pass


def test_emit_filters_and_writes(tmp_path: Path) -> None:
    _clean_tasks()
    a = tmp_path / 'a.py'
    b = tmp_path / 'b.py'
    a.write_text('pass\n', encoding='utf-8')
    b.write_text('pass\n', encoding='utf-8')
    findings = [
        {
            'pack': 'SQL-007',
            'file': str(a),
            'line': 1,
            'message': 'sql',
            'hint_tokens': ['execute'],
        },
        {
            'pack': 'TYP-009',
            'file': str(b),
            'line': 1,
            'message': 'typ',
            'hint_tokens': [],
        },
        {
            'pack': 'BEX-001',
            'file': str(a),
            'line': 1,
            'message': 'bex',
            'hint_tokens': [],
        },
    ]
    written = emit(findings)
    assert len(written) == 2
    names = {Path(w).name for w in written}
    assert names == {'SQL-007-001.json', 'TYP-009-001.json'}
    for w in written:
        data = json.loads(Path(w).read_text(encoding='utf-8'))
        assert set(data) == {
            'tf_id',
            'file',
            'line',
            'message',
            'hints',
            'proposed_actions',
        }
        assert isinstance(data['proposed_actions'], list)


def test_emit_pack_filter(tmp_path: Path) -> None:
    _clean_tasks()
    f = {
        'pack': 'SQL-007',
        'file': str(tmp_path / 'x.py'),
        'line': 1,
        'message': 'x',
        'hint_tokens': [],
    }
    written = emit([f], packs={'TYP-009'})
    assert written == []
