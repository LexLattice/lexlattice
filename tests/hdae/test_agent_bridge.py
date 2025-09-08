from __future__ import annotations
# ruff: noqa: I001

from pathlib import Path
import json

from tools.hdae.agent_bridge import emit_tasks, ingest_diffs


ROOT = Path('.')
FIX = ROOT / 'tests' / 'fixtures' / 'agent'


def _clean_tasks_dir() -> None:
    tdir = ROOT / '.hdae' / 'tasks'
    if tdir.exists():
        for p in tdir.glob('*.json'):
            try:
                p.unlink()
            except OSError:
                pass


def test_emit_generates_packets(tmp_path: Path) -> None:
    _clean_tasks_dir()
    # Two synthetic ambiguous findings
    findings = [
        {
            'pack': 'BEX-001',
            'file': str(FIX / 'ambiguous_bex.py'),
            'line': 7,
            'frame': 'def risky()',
            'hint_tokens': ['json.loads'],
            'span': (5, 10),
        },
        {
            'pack': 'SUB-006',
            'file': str(FIX / 'ambiguous_sub.py'),
            'line': 4,
            'frame': 'def run_cmd()',
            'hint_tokens': ['subprocess.run'],
            'span': (1, 6),
            'message': 'uses shell=True',
        },
    ]
    written = emit_tasks(findings)
    assert written, 'no task packets produced'
    # Validate fields
    for w in written:
        data = json.loads(Path(w).read_text(encoding='utf-8'))
        for k in ('tf_id', 'code_frame', 'allowed_transforms', 'decision_rule', 'hints'):
            assert k in data


def test_ingest_ok_then_idempotent(monkeypatch) -> None:
    # Avoid recursive pytest during verify from inside pytest
    monkeypatch.setenv('HDAE_SKIP_INNER_PYTEST', '1')
    # Ensure target file from ok diff does not already exist
    marker = ROOT / 'docs' / 'agents' / 'BRIDGE_MARKER.txt'
    if marker.exists():
        try:
            marker.unlink()
        except OSError:
            pass
    res = ingest_diffs(str(FIX / 'diffs_ok'))
    assert res['accepted'] >= 1 and res['waived'] == 0
    # Re-ingest same diff should be a no-op
    res2 = ingest_diffs(str(FIX / 'diffs_ok'))
    assert res2['accepted'] == 0 and res2['waived'] == 0


def test_ingest_bad_yields_waiver(monkeypatch) -> None:
    monkeypatch.setenv('HDAE_SKIP_INNER_PYTEST', '1')
    # Ensure waiver file does not yet exist or start clean
    wfile = ROOT / 'docs' / 'agents' / 'waivers' / 'PR-0.md'
    if wfile.exists():
        try:
            wfile.unlink()
        except OSError:
            pass
    res = ingest_diffs(str(FIX / 'diffs_bad'))
    assert res['accepted'] == 0 and res['waived'] == 1
    assert wfile.exists()
    content = wfile.read_text(encoding='utf-8')
    assert content.strip() != ''
