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

all: preflight lint type test audit

# --- Norms & Bundles ---
.PHONY: validate-norms emit-bundle

validate-norms:
	@python -c "import sys,re,pathlib; p=pathlib.Path('docs/norms/NormSet.base.yaml'); print(f'validating {p}…'); txt=p.read_text(encoding='utf-8'); assert re.search(r'^id:\\s+\\S+', txt, re.M), 'missing id in NormSet.base.yaml'; assert 'layers:' in txt, 'missing layers: in NormSet.base.yaml'; print('OK')"

emit-bundle: dev-install
	$(VENV_DIR)/bin/python scripts/urs_emit.py --format json --out docs/bundles/base.json
