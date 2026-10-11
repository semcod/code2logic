#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$repo_root/.governance/governance_check.py" ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/.governance/governance_check.py" \
    --root "$repo_root" \
    --manifest .governance/manifest.json \
    --lock .governance/manifest.lock.json \
    --stack-profiles .governance/stack-profiles.json \
    "$@"
else
  PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/scripts/governance_check.py" \
    --root "$repo_root" \
    --manifest governance/manifest.hub.json \
    --stack-profiles governance/stack-profiles.json \
    --work-classification governance/work-classification.dsl.json \
    "$@"
fi
