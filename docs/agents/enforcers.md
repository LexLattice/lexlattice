# Hybrid Deterministic + Agent Enforcers (H-DAE)

Pipeline overview and plumbing for the Task Function (TF) toolchain. This is a skeleton for PR-2..6 to extend.

## Pipeline
- scan → propose → apply → verify → waiver

Descriptions:
- scan: load TFs, detect opportunities (no patching).
- propose: synthesize candidate patches with full context (dry-run only).
- apply: apply selected patches deterministically; idempotent where possible.
- verify: run checks (ruff/mypy/pytest/docs) and TF-specific assertions.
- waiver: register narrow exceptions with scope and expiry; render in Rulebook index.

## TFs — Source and Layout
- Location: `tools/hdae/tf/*.yaml`
- Schema: `tools/hdae/schema/tf.schema.json`
- Status: `status: {active|stub|disabled}` — only active TFs participate in scan/apply.
- Four baseline TF packs are fully populated in this PR: BEX-001, SIL-002, MDA-003, SUB-006. Others are `status: stub` placeholders for later PRs.

## Waivers → Rulebook
Waivers are defined in `Meta.yaml` under the `waivers:` list. The Rulebook compiler (`urs.py`) merges active waivers into the compiled output, and an index appears under each affected rule. For discoverability, waiver notes and rationale are mirrored at `docs/agents/waivers/`.

## Agent Bridge & Waivers
When deterministic auto-fixes are unsafe or ambiguous, the Agent Bridge can package sites for an external agent and then verify proposed diffs deterministically:
- emit: `hdae agent emit` writes JSON task packets under `.hdae/tasks/` for ambiguous findings (e.g., SUB-006 with `shell=True`). Each packet includes the TF id, code frame, allowed transforms, decision rule, and hints.
- ingest: `hdae agent ingest --from <dir>` applies one or more unified diffs in a temporary worktree, runs `ruff + mypy + pytest`, and if verification passes, applies them to the main tree idempotently. If verification fails, a waiver note is appended to `docs/agents/waivers/PR-<n>.md`.

Lifecycle: scan → propose(auto) → agent(emit/ingest) → verify → commit | waiver.

### PR-footprint L1 Gating
- CI gates only on L1 invariants within the PR footprint (by default: BEX-001, SIL-002).
- The gate script (`tools/hdae/meta/gate_l1.py`) loads `tools/hdae/meta/gate_config.yaml`, filters `hdae-scan.jsonl` to files changed in the PR, subtracts waivers for this PR (`docs/agents/waivers/PR-<n>.md`), and decides pass/fail deterministically.
- Add a waiver by creating `docs/agents/waivers/PR-<n>.md` with lines like `tf_id: BEX-001` or `tf_id: SIL-002` and a rationale/context.

## Determinism & DoD
- L0/L1/L2 precedence applies: L0 (determinism) > L1 (IDE invariants) > L2 (DoD gates).
- No wall-clock or RNG branching in this pipeline.
- CLIs are argparse-driven; unsupported subcommands fail fast with helpful `--help`.

## Extending in PR-2..6
- Core four packs implemented in Task-2 (PR#8):
  - BEX-001 (broad/bare except), SIL-002 (silent handler),
    MDA-003 (mutable defaults), SUB-006 (subprocess hazards).
  - Pipeline commands: `scan | propose | apply | verify`.
  - Idempotent transforms; deterministic outputs.
- Add detectors/patchers for additional packs in later PRs.
- YAML-015: replace yaml.load with yaml.safe_load (auto-fix; format-preserving; idempotent).
- Wire CI enforcement and agent bridge.
- Expand schema and verification hooks as needed.
