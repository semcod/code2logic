#!/usr/bin/env bash
# Managed adopter hook: bind implementation to an active ticket. The payload
# is separate from the hub's live hook so later runtime composition does not
# mutate the standard source's own enforcement while it is executing.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"

run_worktree_guard() {
  local runner="$root/.governance/worktree_guard.py"
  if [[ -f "$runner" ]]; then
    python3 "$runner" --root "$root" --once
    return
  fi

  echo "worktree-guard: the managed pre-commit hook cannot find worktree_guard.py." >&2
  echo "  Restore the managed package or reinstall the repository guard:" >&2
  echo "    ./scripts/install-worktree-guard.sh --target $root --wire-hook" >&2
  return 1
}

run_local_standard_pin_check() {
  local runner="$root/.governance/work_continuity.py"
  if [[ ! -f "$runner" ]]; then
    # A host-files-only bootstrap predates full standard adoption and has no
    # local pin to check. Once either pin file exists, the runtime is required.
    if [[ ! -e "$root/.subactor/manifest.json" && ! -e "$root/.governance/manifest.lock.json" ]]; then
      return 0
    fi
    echo "GOV-CONTINUITY-001: the managed pre-commit hook cannot validate the local standard pin." >&2
    echo "  Restore the managed package with the explicit standard updater; the hook never fetches." >&2
    return 1
  fi

  # Commits read only staged local manifests and managed digests. Resolve a
  # newer release explicitly in its adoption ticket, outside this boundary.
  python3 "$runner" verify-pin --root "$root" --staged >/dev/null
}

run_commit_guards() {
  run_local_standard_pin_check
  run_worktree_guard
}

policy_runner="$root/.governance/repository_policy.py"
if [[ -f "$policy_runner" ]]; then
  repository_profile="$(PYTHONDONTWRITEBYTECODE=1 python3 "$policy_runner" --root "$root" --profile 2>/dev/null || true)"
  if [[ "$repository_profile" == "local-audit" ]]; then
    PYTHONDONTWRITEBYTECODE=1 python3 "$policy_runner" --root "$root" --staged >/dev/null || true
    exit 0
  fi
  if [[ "$repository_profile" == "main-only-planfile" || "$repository_profile" == "main-only-files" ]]; then
    if [[ -z "$branch" || "$branch" == "HEAD" ]]; then
      echo "GOV-AGENT-HOST-001: detached HEAD is not allowed by the main-only delivery profile." >&2
      exit 1
    fi
    if ! PYTHONDONTWRITEBYTECODE=1 python3 "$policy_runner" --root "$root" --staged; then
      echo "GOV-AGENT-HOST-002: staged change rejected by the repository delivery profile." >&2
      exit 1
    fi
    run_commit_guards
    exit 0
  fi
fi

if [[ -z "$branch" || "$branch" == "HEAD" ]]; then
  echo "GOV-AGENT-HOST-001: detached HEAD is not bound to ticket-NNN." >&2
  exit 1
fi

if [[ ! "$branch" =~ ticket[-/]([0-9]{3,}) ]]; then
  echo "GOV-AGENT-HOST-001: branch '$branch' is not bound to ticket-NNN." >&2
  echo "  Allocate with ./project/new-ticket.sh and commit on a ticket branch." >&2
  exit 1
fi

ticket="ticket-${BASH_REMATCH[1]}"
readme_rel="project/$ticket/README.md"

ticket_storage="$(git config --local --get new-project.ticketStorage 2>/dev/null || true)"
if [[ "${ticket_storage:-files}" == sqlite ]]; then
  reader="$root/.governance/ticket_input.py"
  [[ -f "$reader" ]] || reader="$root/scripts/ticket_input.py"
  if ! staged_readme="$(PYTHONDONTWRITEBYTECODE=1 python3 "$reader" read --root "$root" --ticket "$ticket" --file README.md)"; then
    echo "GOV-AGENT-HOST-002: active SQLite ticket content is unavailable." >&2
    exit 1
  fi
elif [[ "${ticket_storage:-files}" == files ]]; then
  if ! staged_readme="$(git show ":$readme_rel" 2>/dev/null)"; then
    echo "GOV-AGENT-HOST-002: $root/$readme_rel is missing from the staged snapshot." >&2
    echo "  Allocate with ./project/new-ticket.sh; do not invent a ticket number." >&2
    exit 1
  fi
else
  echo "GOV-AGENT-HOST-002: unknown ticket storage mode." >&2
  exit 1
fi

governance_only_transition() {
  # SQLite transitions never require a Git carrier commit.
  [[ "${ticket_storage:-files}" == files ]] || return 1
  if git diff --cached --quiet -- "$readme_rel"; then
    return 1
  fi
  if ! git diff --cached --quiet --diff-filter=DRC --; then
    return 1
  fi

  while IFS= read -r -d '' path; do
    case "$path" in
      "project/$ticket/"*|TODO.md|project/TICKETS.md|config/artifact-registry.json) ;;
      *) return 1 ;;
    esac
  done < <(git diff --cached --name-only -z --diff-filter=AM --)
}

if grep -Eiq '^-[[:space:]]+\*\*Status\*\*:[[:space:]]*IN_PROGRESS([[:space:]]|$)' <<<"$staged_readme"; then
  head_readme="$(git show "HEAD:$readme_rel" 2>/dev/null || true)"
  if grep -Eiq '^-[[:space:]]+\*\*Status\*\*:[[:space:]]*(BACKLOG|PLAN|BLOCKED)([[:space:]]|$)' <<<"$head_readme" \
    && governance_only_transition; then
    run_commit_guards
    exit 0
  fi

  material=false
  while IFS= read -r -d '' path; do
    case "$path" in
      project/ticket-*/*|TODO.md|project/TICKETS.md|config/artifact-registry.json) ;;
      *) material=true; break ;;
    esac
  done < <(git diff --cached --name-only -z --diff-filter=AM --)
  if [[ "$material" != true ]]; then
    echo "GOV-AGENT-HOST-007: staged change contains only ticket tracking carriers." >&2
    echo "  Add a material deliverable, or emit an external no-change receipt without committing." >&2
    exit 1
  fi
  run_commit_guards
  exit 0
fi

if grep -Eiq '^-[[:space:]]+\*\*Status\*\*:[[:space:]]*(BACKLOG|PLAN|BLOCKED)([[:space:]]|$)' <<<"$staged_readme"; then
  if governance_only_transition; then
    run_commit_guards
    exit 0
  fi
  echo "GOV-AGENT-HOST-003: $ticket non-active transition is not governance-only." >&2
  echo "  Stage the ticket README and only bounded governance evidence; keep implementation on IN_PROGRESS." >&2
  exit 1
fi

if grep -Eiq '^-[[:space:]]+\*\*Status\*\*:[[:space:]]*(DONE|CANCELLED)([[:space:]]|$)' <<<"$staged_readme"; then
  echo "GOV-AGENT-HOST-003: repository terminal closure commits are forbidden." >&2
  echo "  The protected delivery controller must emit the external terminal receipt without a repository write." >&2
  exit 1
fi

echo "GOV-AGENT-HOST-003: $ticket is neither IN_PROGRESS nor a valid staged non-active transition." >&2
echo "  Use BACKLOG, PLAN or BLOCKED only for bounded governance evidence; terminal state belongs to the protected external receipt." >&2
exit 1
