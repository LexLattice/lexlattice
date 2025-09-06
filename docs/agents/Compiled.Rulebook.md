# Compiled Rulebook

Generated: 2025-09-06T12:27:17Z

Total rules: 5  •  hard=4  •  soft=0  •  advice=1

## Index by severity

### HARD
- [URS-L0-DET-001] Deterministic outputs  _(layer: L0, scope: repo)_
- [URS-L0-LIC-001] License headers present  _(layer: L0, scope: path:**/*.{py,ts,tsx,go,rs})_
- [URS-L0-PR-003] CI must be green  _(layer: L0, scope: ci:github)_
- [URS-L0-SEC-002] No secrets in repo  _(layer: L0, scope: repo)_

### SOFT

### ADVICE
- [URS-L4-AGT-CODEX-010] Agent Adapter — Codex (E–O–L + Ask/Stop)  _(layer: L4, scope: agent:codex)_


## HARD RULES
### URS-L0-DET-001 — Deterministic outputs
- Severity: **hard**  •  Layer: **L0**  •  Scope: **repo**
- Rationale: Reproducible behavior across machines/agents.
- Checks:
  - `{"type": "ci", "gate": "tests && lint && build"}`

**Principle.** Builds, tests, and generated artifacts must be deterministic under the pinned toolchain.
Seed randomness; disallow time-dependent outputs in artifacts; document any unavoidable nondeterminism.
### URS-L0-LIC-001 — License headers present
- Severity: **hard**  •  Layer: **L0**  •  Scope: **path:**/*.{py,ts,tsx,go,rs}**
- Rationale: Clear IP/licensing for reuse.
- Checks:
  - `{"type": "static", "rule": "files include project license header"}`

Source files MUST include the project’s license header template.
### URS-L0-PR-003 — CI must be green
- Severity: **hard**  •  Layer: **L0**  •  Scope: **ci:github**
- Rationale: Gate broken changes; protect main.
- Checks:
  - `{"type": "ci", "gate": "all required jobs succeed"}`

All required CI jobs MUST pass before merge.
### URS-L0-SEC-002 — No secrets in repo
- Severity: **hard**  •  Layer: **L0**  •  Scope: **repo**
- Rationale: Prevent credential leakage.
- Checks:
  - `{"type": "scan", "tool": "git history + high-entropy + known token patterns"}`

Commit history MUST NOT contain credentials or long-lived tokens. Use env vars and secret stores.


## SOFT RULES


## ADVICE RULES
### URS-L4-AGT-CODEX-010 — Agent Adapter — Codex (E–O–L + Ask/Stop)
- Severity: **advice**  •  Layer: **L4**  •  Scope: **agent:codex**
- Rationale: Make agent behaviors predictable and queryable.
- Checks:
  - `{"type": "agent", "ask_if": ["blocking ambiguity", "missing schema/flags/secrets", "test uncertainty >10%"], "stop_if": ["determinism compromised", "requires golden overwrite", "DB writes without requires_db"]}`

### Reasoning anchor (E–O–L Mini)
O (Ontology): Entities=…, Relations=…, Invariants=…, Scope=…  
E (Epistemology): Sources=…, Assumptions=…, Verification=…  
L (Logic): Constraints=…, Allowed transforms=…, Decision rule=…, Guardrails=…

**Ask if** any ambiguity blocks deterministic progress.  
**Stop if** proceeding would break determinism or exceed allowed I/O.

