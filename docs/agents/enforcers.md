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
- Wire CI enforcement and agent bridge.
- Expand schema and verification hooks as needed.
