#!/usr/bin/env bash
# Git invokes this after the message is available and before creating a commit.
# Staged scope and active-ticket checks remain in the pre-commit hook.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
policy_runner="$root/.governance/repository_policy.py"
[[ -f "$policy_runner" ]] || policy_runner="$root/scripts/repository_policy.py"
if [[ -f "$policy_runner" ]]; then
  profile="$(PYTHONDONTWRITEBYTECODE=1 python3 "$policy_runner" --root "$root" --profile 2>/dev/null || true)"
  case "$profile" in
    local-audit|main-only-planfile|main-only-files) exit 0 ;;
  esac
fi

branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
if [[ ! "$branch" =~ ticket[-/]([0-9]{3,}) ]]; then
  echo "GOV-AGENT-HOST-001: commit subject cannot bind branch '$branch' to ticket-NNN." >&2
  exit 1
fi
ticket="ticket-${BASH_REMATCH[1]}"
if [[ $# != 1 || ! -f "$1" ]]; then
  echo "GOV-AGENT-HOST-001: commit message file is unavailable." >&2
  exit 1
fi
subject=""
IFS= read -r subject < "$1" || true
if ! printf '%s\n' "$subject" | grep -Eq -- "(^|[^[:alnum:]_-])${ticket}([^[:alnum:]_-]|$)"; then
  echo "GOV-AGENT-HOST-001: commit subject must include the branch ticket '$ticket'." >&2
  echo "  Example: fix(component): repair behavior ($ticket)" >&2
  exit 1
fi
