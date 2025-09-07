# LexLattice
Portable rulebook compiler & enforcer — from universal invariants → user/org conventions → project charter → agent adapters.

## Why
Different projects share the same bones. LexLattice makes those bones explicit and portable:
- **L0** Invariants (universal, non-overrideable)
- **L1** Conventions (user/org profile, overrideable w/ waivers)
- **L2** Project Charter (repo-specific)
- **L4** Agent Adapter (tool binding, ask/stop gates)

> Precedence: L0 > L1 > L2 > L4 at compile time.  
> L3 (Task/PR contract) is ephemeral per PR and lives outside this repo.

## Quickstart
```bash
python3 urs.py compile --meta Meta.yaml --out docs/agents/Compiled.Rulebook.md
python3 urs.py enforce --meta Meta.yaml --level hard
```

If you see an error about PyYAML, install it:

```bash
python -m pip install pyyaml
```

## Files

* `urs.py` – single-file CLI (compile + enforce)
* `Meta.yaml` – layer manifest + waivers
* `docs/urs/L0.md` – tiny universal L0 (“hard” rules)
* `examples/CodexAdapter.md` – example L4 adapter (advice)
* `docs/agents/EOL-of-Coding.md` – E–O–L spec (operators, lattice, TF calculus)
* `docs/agents/enforcers.md` – H-DAE pipeline overview
* `tools/hdae/` – H-DAE skeleton (CLI, schema, TFs)

## Roadmap

* v0.2: remote sources (`remote:git@…`), JSONL export, richer scopes
* v0.3: first-class adapters (Codex/Jules), coverage report per PR

## Dev Setup

To set up a consistent local Python dev environment with linting, typing, and tests:

```bash
make dev-install  # first step: create .venv and install dev tools
make preflight    # optional: runs doctor if present
make lint         # ruff (style/imports)
make type         # mypy (static types)
make test         # pytest (unit tests)
```

Notes:
- Tools run from `.venv` to ensure determinism across machines.
- `make all` also runs an optional norm audit if present.
 - Imports are auto-sortable with `ruff` (run `ruff check --fix`).

## Agent Enforcers (H-DAE) ![H-DAE CI](https://github.com/LexLattice/lexlattice/actions/workflows/hdae.yml/badge.svg)

This repo includes the skeleton for Hybrid Deterministic + Agent Enforcers:
- Read the spec: `docs/agents/EOL-of-Coding.md`
- See pipeline details: `docs/agents/enforcers.md`
- Validate TFs and run lattice self-test:

```bash
make hdae-verify
```
Run detectors and patchers for the core four packs:

```bash
# list findings (JSONL)
make hdae-scan

# preview diffs without changing files
make hdae-propose

# apply fixes and verify with ruff + mypy + pytest
make hdae-apply
```

The scanner now supports the following detection packs:
- `RES-005`: Resource handling (e.g., `open` without `with`)
- `SQL-007`: SQL injection (e.g., f-string in `execute`)
- `ARG-008`: Argparse `type=str` without `choices`
- `TYP-009`: Missing type annotations
- `LOG-010`: `print()` in library code
- `ERR-011`: `raise` without `from` in `except` block
- `ROL-012`: Naive sliding window recompute in loops
- `IOB-013`: I/O in hot loops
- `PATH-014`: Path built with `+` or f-strings
- `YAML-015`: Unsafe `yaml.load`
- `JSON-016`: `json.loads` without `JSONDecodeError` handling
- `CPL-017`: Long functions
- `DUP-018`: Duplicate code

You can filter the scan to specific packs using the `ARGS` variable with make:
```bash
# scan for specific packs
make hdae-scan ARGS="--packs RES-005,ARG-008"
```

CI & H-DAE:
- Every PR in the `track/hdae/**` stack runs: `hdae-verify` → `scan` → `propose --dry-run` → `verify`.
- CI uploads artifacts (scan JSONL, dry-run diffs, gate.json) and comments a summary from a single source of truth.
- CI gates only on L1 invariants within the PR footprint (default: BEX-001, SIL-002). Add justified waivers in `docs/agents/waivers/PR-<n>.md`.

Run CI locally (parity):
- Fast path (no containers):
  - `make ci-local PR_NUMBER=0 BASE_REF=track/hdae/pr9-agent-bridge`
- Exact GitHub runner via act (optional):
  - `scripts/ci/run_act_pr.sh 10 track/hdae/pr9-agent-bridge`
- Local runs won’t post PR comments unless `CI_ALLOW_PR_COMMENT=1` and a valid `GITHUB_TOKEN` are set.
- On push to `main`, the Rulebook compiles and the Waivers Index stays fresh.

Using the Agent Bridge for ambiguous sites:

```bash
# generate task packets for ambiguous findings only
make hdae-agent-emit

# ingest proposed diffs from an agent (unified patches)
make hdae-agent-ingest  # defaults to .hdae/diffs
```
