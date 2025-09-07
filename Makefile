.PHONY: venv dev-install preflight lint type test audit all

VENV_DIR := .venv
DEV_SENTINEL := $(VENV_DIR)/.dev-deps-installed

venv: $(VENV_DIR)/bin/python

$(VENV_DIR)/bin/python:
	python3 -m venv $(VENV_DIR)

$(DEV_SENTINEL): requirements-dev.txt | venv
	$(VENV_DIR)/bin/pip install -r requirements-dev.txt
	@# Sentinel marks an idempotent install; updates when requirements change
	@date > $(DEV_SENTINEL)

dev-install: $(DEV_SENTINEL)

preflight: dev-install
	@if [ -x scripts/dev/codex_session_doctor.sh ]; then scripts/dev/codex_session_doctor.sh --fix || true; fi

lint: dev-install
	$(VENV_DIR)/bin/ruff check

type: dev-install
	$(VENV_DIR)/bin/mypy .

test: dev-install
	$(VENV_DIR)/bin/pytest -q

audit: dev-install
	$(VENV_DIR)/bin/python scripts/dev/norm_audit.py || true
	@if [ -z "$(PR)" ]; then echo "PR=<n> required"; exit 1; fi
	$(VENV_DIR)/bin/python tools/norm_audit.py --pr $(PR) --sha $$(git rev-parse --short HEAD) --bundle docs/bundles/base.llbundle.json --event compile --notes "emit-bundle"
	@echo "audit appended for PR $(PR)"

all: preflight lint type test audit

# --- Norms & Bundles ---
.PHONY: validate-norms emit-bundle compile ensure-dirs

validate-norms: dev-install
	$(VENV_DIR)/bin/python scripts/dev/validate_norms.py


emit-bundle: dev-install
	$(VENV_DIR)/bin/python scripts/urs_emit.py --format json --out docs/bundles/base.json

# Optional compile target (for v0.1 rulebook)
.PHONY: ensure-dirs compile

ensure-dirs:
	mkdir -p docs/agents docs/bundles docs/audit

compile: ensure-dirs dev-install
	$(VENV_DIR)/bin/python urs.py compile --meta Meta.yaml --out docs/agents/Compiled.Rulebook.md --json-out docs/bundles/base.llbundle.json

# --- H-DAE ---
.PHONY: hdae-verify journals-template

hdae-verify: dev-install
	$(VENV_DIR)/bin/python -m tools.hdae.meta.quality --selftest
	$(VENV_DIR)/bin/python -m tools.hdae.cli scan
	@echo "TF schema OK"

journals-template:
	@# Emit activity/self-assessment journal entries when PR context is present
	@if [ -x scripts/dev/auto_journals.sh ]; then scripts/dev/auto_journals.sh || true; else echo "journal helper not found"; fi
