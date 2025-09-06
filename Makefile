.PHONY: venv dev-install preflight lint type test audit all

venv:
	python3 -m venv .venv

dev-install: venv
	. .venv/bin/activate && pip install -r requirements-dev.txt

preflight:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	@if [ -f requirements-dev.txt ]; then . .venv/bin/activate && pip install -r requirements-dev.txt; fi
	@if [ -x scripts/dev/codex_session_doctor.sh ]; then scripts/dev/codex_session_doctor.sh --fix || true; fi

lint:
	. .venv/bin/activate && ruff check

type:
	. .venv/bin/activate && mypy .

test:
	. .venv/bin/activate && pytest -q

audit:
	. .venv/bin/activate && python scripts/dev/norm_audit.py || true

all: preflight lint type test audit
