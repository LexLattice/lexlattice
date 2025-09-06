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
