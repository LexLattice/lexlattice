---
id: URS-L4-AGT-CODEX-010
title: Agent Adapter — Codex (E–O–L + Ask/Stop)
severity: advice
scope: agent:codex
rationale: "Make agent behaviors predictable and queryable."
checks:
  - type: agent
    ask_if:
      - "blocking ambiguity"
      - "missing schema/flags/secrets"
      - "test uncertainty >10%"
    stop_if:
      - "determinism compromised"
      - "requires golden overwrite"
      - "DB writes without requires_db"
---
### Reasoning anchor (E–O–L Mini)
O (Ontology): Entities=…, Relations=…, Invariants=…, Scope=…  
E (Epistemology): Sources=…, Assumptions=…, Verification=…  
L (Logic): Constraints=…, Allowed transforms=…, Decision rule=…, Guardrails=…

**Ask if** any ambiguity blocks deterministic progress.  
**Stop if** proceeding would break determinism or exceed allowed I/O.

