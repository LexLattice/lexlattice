---
title: EOL of Coding — Meta Axioms, Operators, and TF Calculus
severity: advice
scope: repo
---

# EOL of Coding (v0.2, H-DAE layer)

This document defines the E–O–L lens for tooling and enforcement in LexLattice. It anchors to the Rulebook with clear precedence and a minimal calculus for Task Functions (TFs).

## Meta-Axioms (L0 → L1 → L2)
- L0: Determinism first; small diffs; fail fast with narrow exceptions only.
- L1: Codex IDE invariants: no blanket `except Exception`, predictable argparse/flags, reproducible behavior, PR hygiene.
- L2: Definition of Done gates: ruff, mypy, pytest, docs; Rulebook compiled; journals emitted.

Precedence: L0 > L1 > L2. Any conflict is resolved by the higher layer.

## Operators
- APPLY: run a TF (detector/transform) against a concrete target; effect is deterministic or rejected.
- WAIVE: narrowly bypass a rule/TF under controlled scope/time; waivers index renders into the Compiled Rulebook.
- COMPOSE: sequence TFs; composition must be associative where effects are independent; order must be specified when not.
- ELEVATE: promote a TF or rule to stricter enforcement (e.g., from advisory to hard) once it proves stable.

## Quality Lattice Q(P)
Given process stats `P`, define:
Q(P) = (-L1_violations, -L2_misses, -lint_type_fails, +perf_async_wins)

Ordered lexicographically: higher is better. Monotonicity: fixing an L1 violation strictly improves quality; secondary dimensions only compare when earlier ones tie.

## TF Object (sextuple)
Each TF is modeled as a sextuple: (E, O, L, Apply, Verify, Footprint)
- E (Epistemology): detect signals, hints, confidence.
- O (Ontology): entities, relations, scope.
- L (Logic): constraints, transforms, decision rule.
- Apply: IO contract (input/output), idempotence, determinism notes.
- Verify: checks and acceptance conditions; integrates with Rulebook gates.
- Footprint: touched files/paths and journaling hooks.

Minimum fields for TF YAML are specified by `tools/hdae/schema/tf.schema.json` and validated by the H-DAE CLI.

## Calculus Rules
- Apply: If constraints hold and decision rule fires, APPLY yields a deterministic patch or no-op. Otherwise, reject.
- Waive: WAIVE requires scope, expiry, reason; entries surface in the waivers index of the Compiled Rulebook.
- Compose: For independent TFs, COMPOSE(A,B) = COMPOSE(B,A). If dependence exists, the sequence must be declared and validated.
- Order: Q(after) >= Q(before) is required unless an approved WAIVE exists. Breaking monotonicity requires explicit waiver rationale.

## Notes on Determinism
- No wall-clock or RNG-based branching in TFs.
- IO must be explicit and scoped; no network calls unless declared and reproducible.
- All CLIs must be argparse-driven with `choices=` where applicable.

## References
- L0/L1/L2 are defined in the Rulebook (`docs/agents/Compiled.Rulebook.md`) and Norms (`docs/norms/README.md`).
- Waivers are documented under `docs/agents/waivers/` and compiled via `Meta.yaml`.

