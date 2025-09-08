#!/usr/bin/env bash
set -euo pipefail

pr="${1:-10}"
base="${2:-main}"

export CI_LOCAL=1

if ! command -v act >/dev/null 2>&1; then
  echo "act is not installed. See https://github.com/nektos/act" >&2
  exit 2
fi

token="$(gh auth token 2>/dev/null || echo dummy)"

act pull_request \
  -W .github/workflows/hdae.yml \
  -s GITHUB_TOKEN="$token" \
  -e <(jq -n --arg n "$pr" --arg b "$base" '{pull_request:{number:($n|tonumber), base:{ref:$b}}}')

