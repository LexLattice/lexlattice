# Normative Engineering (LL)

**What:** A first-class, versioned set of norms that constrain agent behavior and make intention well-typed.  
**Why:** Turn implicit patterns into explicit gates so runs are auditable, comparable, and reproducible.

## Layers
- **L0 Principles:** determinism first; small diffs; narrow exceptions.
- **L1 Invariants:** hard rules (e.g., ban blanket `except Exception`, guard I/O).
- **L2 DoD:** validators/gates (ruff, mypy, pytest, docs).
- **L3 Reporting:** journals (activity + self-assessment) per PR.

See: `docs/agents/Compiled.Rulebook.md` and `docs/agents/DoD.md`.

## NormSet
Pinned at `docs/norms/NormSet.base.yaml` (id: `NormSet.base.v1`).  
Swap or compose NormSets to A/B different priorities (future work).

## Audit
On PR branches, `scripts/dev/norm_audit.py` runs and appends a **Norm Audit** block to `docs/codex/reports/PR-<n>.md` with:
- **Conformance:** L0/L1/L2/L3 roll-up
- **Metrics:** `NormPass@1`, `RepairDepth`, `ViolationMix`, `DeterminismScore`, `WaiverCount`
- **JSON payload** for machine analysis

This rides the existing journal flow (`scripts/dev/auto_journals.sh`).

