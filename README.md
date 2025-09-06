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

## Roadmap

* v0.2: remote sources (`remote:git@…`), JSONL export, richer scopes
* v0.3: first-class adapters (Codex/Jules), coverage report per PR

```
