#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then echo "not inside a git repo" >&2; exit 1; fi
cd "$ROOT"

BR="$(git rev-parse --abbrev-ref HEAD)"
PR_NUM="$(gh pr view --json number -q .number 2>/dev/null || true)"
if [[ -z "$PR_NUM" ]]; then
  PR_NUM="$(gh pr list --head "$BR" --json number -q '.[0].number' 2>/dev/null || true)"
fi
if [[ -z "$PR_NUM" ]]; then
  echo "No PR detected for branch '$BR' — skipping journals."
  exit 0
fi

# Run Norm Audit first; do not block on errors.
python scripts/dev/norm_audit.py --pr "$PR_NUM" --branch "$BR" || true
echo "Norm Audit appended (PR #$PR_NUM)."

