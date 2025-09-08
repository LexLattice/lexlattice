#!/usr/bin/env bash
set -euo pipefail

# Single source of truth for H-DAE CI steps.
# Commands: preflight | verify | scan | propose-dry | gate | comment | artifacts

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
cd "$ROOT_DIR"

ART_DIR=".hdae-artifacts"
PY="${HDAE_PY:-$(command -v python3 || command -v python)}"

cmd="${1:-}"

preflight() {
  echo "[hdae-ci] preflight: install dev tools"
  "$PY" -m pip install --upgrade pip
  if [[ -f requirements-dev.txt ]]; then
    "$PY" -m pip install -r requirements-dev.txt
  else
    "$PY" -m pip install ruff mypy pytest pyyaml jsonschema libcst
  fi
  if [[ -x scripts/dev/codex_session_doctor.sh ]]; then
    scripts/dev/codex_session_doctor.sh --fix || true
  fi
}

verify() {
  echo "[hdae-ci] verify"
  make hdae-verify
}

scan() {
  echo "[hdae-ci] scan → hdae-scan.jsonl"
  "$PY" -m tools.hdae.cli scan > hdae-scan.jsonl || true
}

propose_dry() {
  echo "[hdae-ci] propose --dry-run → hdae-diff.txt"
  "$PY" -m tools.hdae.cli propose --dry-run > hdae-diff.txt || true
}

gate() {
  local pr="${PR_NUMBER:-0}"
  local base="${BASE_REF:-main}"
  echo "[hdae-ci] gate (PR=$pr base=$base)"
  set +e
  "$PY" tools/hdae/meta/gate_l1.py --pr "$pr" --base "$base" | tee gate.json
  rc=${PIPESTATUS[0]}
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "[hdae-ci] gate failed (remaining L1 > 0)"
    return $rc
  fi
}

comment() {
  echo "[hdae-ci] PR comment (guarded)"
  local pr="${PR_NUMBER:-}"; local token="${GITHUB_TOKEN:-}"; local allow="${CI_ALLOW_PR_COMMENT:-0}"
  if [[ -z "$pr" || "$allow" != "1" || -z "$token" ]]; then
    echo "[hdae-ci] skipping PR comment (PR_NUMBER/CI_ALLOW_PR_COMMENT/GITHUB_TOKEN not set)"
    # print markdown summary to stdout for local visibility
    if [[ -f gate.json ]]; then
      "$PY" - <<'PY'
import json, sys
with open('gate.json','r',encoding='utf-8') as f:
    j=json.load(f)
body = [
  '### H-DAE Summary',
  f"- Findings (all scan): **{j.get('total_all',0)}**",
  f"- L1 in PR footprint ({', '.join(j.get('gate_tf_ids', []))}): **{j.get('l1_in_pr',0)}**",
  f"- Waivers (this PR): **{j.get('waivers',0)}**",
  f"- Remaining L1 (unwaived): **{j.get('remaining_l1',0)}**",
  '',
  f"- Changed files: {j.get('changed_files',0)}",
  '',
  '> L1 invariants outrank all else; unresolved L1 issues without waivers fail CI.',
]
print("\n".join(body))
PY
    fi
    return 0
  fi
  if [[ -f gate.json ]]; then
    local repo="${GITHUB_REPOSITORY:-}"; local api="https://api.github.com/repos/$repo/issues/$pr/comments"
    local body
    body=$("$PY" - <<'PY'
import json
with open('gate.json','r',encoding='utf-8') as f:
    j=json.load(f)
print('\n'.join([
  '### H-DAE Summary',
  f"- Findings (all scan): **{j.get('total_all',0)}**",
  f"- L1 in PR footprint ({', '.join(j.get('gate_tf_ids', []))}): **{j.get('l1_in_pr',0)}**",
  f"- Waivers (this PR): **{j.get('waivers',0)}**",
  f"- Remaining L1 (unwaived): **{j.get('remaining_l1',0)}**",
  '',
  f"- Changed files: {j.get('changed_files',0)}",
  '',
  '> L1 invariants outrank all else; unresolved L1 issues without waivers fail CI.',
]))
PY
    )
    echo "[hdae-ci] posting comment to PR #$pr"
    curl -sS -H "Authorization: token $token" -H 'Content-Type: application/json' \
      -d "$(printf '%s' "{\"body\": $(printf '%s' "$body" | "$PY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))') }")" \
      "$api" >/dev/null || true
  fi
}

artifacts() {
  echo "[hdae-ci] collect artifacts → $ART_DIR"
  mkdir -p "$ART_DIR"
  for f in hdae-scan.jsonl hdae-diff.txt gate.json; do
    [[ -f "$f" ]] && cp -f "$f" "$ART_DIR/" || true
  done
}

case "$cmd" in
  preflight) preflight ;;
  verify) verify ;;
  scan) scan ;;
  propose-dry) propose_dry ;;
  gate) gate ;;
  comment) comment ;;
  artifacts) artifacts ;;
  *) echo "Usage: $0 {preflight|verify|scan|propose-dry|gate|comment|artifacts}" >&2; exit 2 ;;
esac

