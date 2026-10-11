#!/usr/bin/env bash
# Universal ticket scaffolder for target System X repositories.

set -euo pipefail

TITLE="New Task Ticket"
USERS=""
AGENT="antigravity"
WORKSTREAM=""
SCOPE_ARGUMENTS=()
FORCE_NEW=false
ALLOCATION_KEY=""
ALLOCATION_RECEIPT=""
REFRESH_REMOTE=false
TICKET_STORAGE=""
STORE_ROOT=""
STORE_SHA256=""
SNAPSHOT_PROPOSAL=""
SNAPSHOT_MATERIALIZE=""
MIGRATION_AUTHORIZATION=""
MIGRATION_AUTHORIZATION_SHA256=""
RECOVER_REQUEST=""
RECOVERY_LEASE_STORE=""
WORKTREE_SLUG=""
BOOTSTRAP_ADOPTION_DIGEST=""
CALLER_CHECKOUT="$(pwd -P)"
ALLOCATOR_PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Work classification for intent/v3. The defaults are the contract's own answer
# for an unclassified new ticket: rule W-CLASS-006 (work-request / maintenance)
# assigns SERVICE and health, and priorityDerivation.serviceDefault is P2.
# Declare --kind/--priority/--origin when the ticket is a defect or new behavior.
KIND="SERVICE"
PRIORITY="P2"
ORIGIN="health"

usage() {
  cat <<'EOF'
Usage: ./project/new-ticket.sh [options]

  -t, --title TITLE       Ticket title
  -a, --agent ID         Agent provider/id used for ai-{ID}.md
  -w, --workstream ID    Required workstream from the governance registry
      --path PATTERN     Repeatable owned implementation scope; persisted in intent
  -u, --users IDS        Compatibility input only; human files are not created
  -k, --kind KIND        Work kind; default SERVICE
  -p, --priority P       Work priority; default P2
  -o, --origin ORIGIN    Work origin; default health
      --allocation-key K Stable Supervisor/task correlation for registered mode
      --allocation-receipt FILE
                          Receipt returned by the registered allocator process
      --force-new        Create a new ticket despite an unfinished ticket
      --refresh-remote   Fetch/prune origin before allocating; local refs are used by default
      --storage MODE     files (default) or sqlite; may come from local Git configuration
      --ticket-store-root DIR
                          Installed Registry ticket writer package
      --ticket-store-sha256 SHA
                          Independent digest of the complete writer package
  -h, --help             Show this help
      --snapshot-proposal FILE
                          Reserve a snapshot identity; no writer or approval
      --snapshot-materialize FILE
                          External exact proposal and controller CAS request
      --migration-authorization FILE
                          Protected import grant (materialization only)
      --migration-authorization-sha256 SHA
                          Independently pinned grant digest
      --recover-request FILE
                          Explicit exact-state pre-adoption recovery request
      --recovery-lease-store DIR
                          Existing external local controller store (recovery only)
      --bootstrap-adoption-digest SHA
                          Confirm ownership of exact first scaffold adoption delta
      --worktree-slug SLUG
                          Canonical linked-worktree slug; defaults to a stable title slug

Accepted classification values are read from the work classification contract,
not hardcoded here. The defaults are that contract's own answer for an
unclassified new ticket (rule W-CLASS-006 plus the service priority default);
declare the three explicitly for a defect or new behavior.

Only a human may authorize --force-new. Human-owned user-*.md files must be
created and written by that human or by a trusted intake boundary.
--force-new never bypasses repository work-start admission.
EOF
}

require_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Missing value for $1" >&2
    usage >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--title)
      require_value "$@"
      TITLE="$2"
      shift 2
      ;;
    -u|--users)
      require_value "$@"
      USERS="$2"
      shift 2
      ;;
    -a|--agent)
      require_value "$@"
      AGENT="$2"
      shift 2
      ;;
    -w|--workstream)
      require_value "$@"
      WORKSTREAM="$2"
      shift 2
      ;;
    --path)
      require_value "$@"
      SCOPE_ARGUMENTS+=("--path=$2")
      shift 2
      ;;
    -k|--kind)
      require_value "$@"
      KIND="$2"
      shift 2
      ;;
    -p|--priority)
      require_value "$@"
      PRIORITY="$2"
      shift 2
      ;;
    -o|--origin)
      require_value "$@"
      ORIGIN="$2"
      shift 2
      ;;
    --storage)
      require_value "$@"; TICKET_STORAGE="$2"; shift 2 ;;
    --snapshot-proposal)
      require_value "$@"; SNAPSHOT_PROPOSAL="$2"; shift 2 ;;
    --snapshot-materialize)
      require_value "$@"; SNAPSHOT_MATERIALIZE="$2"; shift 2 ;;
    --migration-authorization)
      require_value "$@"; MIGRATION_AUTHORIZATION="$2"; shift 2 ;;
    --migration-authorization-sha256)
      require_value "$@"; MIGRATION_AUTHORIZATION_SHA256="$2"; shift 2 ;;
    --recover-request)
      require_value "$@"; RECOVER_REQUEST="$2"; shift 2 ;;
    --recovery-lease-store)
      require_value "$@"; RECOVERY_LEASE_STORE="$2"; shift 2 ;;
    --bootstrap-adoption-digest)
      require_value "$@"; BOOTSTRAP_ADOPTION_DIGEST="$2"; shift 2 ;;
    --worktree-slug)
      require_value "$@"; WORKTREE_SLUG="$2"; shift 2 ;;
    --ticket-store-root)
      require_value "$@"; STORE_ROOT="$2"; shift 2 ;;
    --ticket-store-sha256)
      require_value "$@"; STORE_SHA256="$2"; shift 2 ;;
    --allocation-key)
      require_value "$@"
      ALLOCATION_KEY="$2"
      shift 2
      ;;
    --allocation-receipt)
      require_value "$@"
      ALLOCATION_RECEIPT="$2"
      shift 2
      ;;
    --force-new)
      FORCE_NEW=true
      shift
      ;;
    --refresh-remote)
      REFRESH_REMOTE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$TITLE" == *$'\n'* || "$TITLE" == *$'\r'* ]]; then
  echo "Ticket title must fit on one line" >&2
  exit 2
fi
if ! python3 - "$TITLE" <<'PY'
import sys
raise SystemExit(any(ord(character) < 32 or ord(character) == 127 for character in sys.argv[1]))
PY
then
  echo "Ticket title must not contain ASCII control characters" >&2
  exit 2
fi

AGENT="$(printf '%s' "$AGENT" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$AGENT" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "Agent id must match [a-z0-9][a-z0-9._-]*" >&2
  exit 2
fi

# Allocation may be requested from a linked checkout, but the clone's primary
# checkout is the only valid authority for admission and canonical layout. Do
# not infer it from $PWD: Git's registered-worktree order is the durable
# observation, and all later relative reads intentionally happen from primary.
PRIMARY_CHECKOUT=""
if git rev-parse --git-dir >/dev/null 2>&1; then
  PRIMARY_CHECKOUT="$(git worktree list --porcelain | sed -n 's/^worktree //p' | sed -n '1p')"
  if [[ -z "$PRIMARY_CHECKOUT" || ! -d "$PRIMARY_CHECKOUT" || -L "$PRIMARY_CHECKOUT" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: registered primary checkout is unavailable or symlinked." >&2
    exit 5
  fi
  PRIMARY_CHECKOUT="$(cd "$PRIMARY_CHECKOUT" && pwd -P)"
  cd "$PRIMARY_CHECKOUT"
fi

TICKET_STORAGE="${TICKET_STORAGE:-$(git config --local --get new-project.ticketStorage 2>/dev/null || true)}"
TICKET_STORAGE="${TICKET_STORAGE:-files}"
if [[ "$TICKET_STORAGE" != files && "$TICKET_STORAGE" != sqlite ]]; then
  echo "GOV-TICKET-ALLOCATION-003: unknown ticket storage mode." >&2
  exit 1
fi
# Reject incompatible snapshot inputs before any candidate executable bridge.
if [[ -n "$SNAPSHOT_PROPOSAL" || -n "$SNAPSHOT_MATERIALIZE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
  if [[ "$TICKET_STORAGE" != files || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -ne 0 || -n "$RECOVER_REQUEST" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: snapshot inputs require local file allocation and an exclusive bounded request." >&2
    exit 5
  fi
fi

TICKET_STORAGE_HELPER=""
for candidate in .governance/ticket_storage.py scripts/ticket_storage.py; do
  if [[ -f "$candidate" ]]; then TICKET_STORAGE_HELPER="$candidate"; break; fi
done
if [[ "$TICKET_STORAGE" == sqlite ]]; then
  STORE_ROOT="${STORE_ROOT:-$(git config --local --get new-project.ticketStoreRoot 2>/dev/null || true)}"
  STORE_SHA256="${STORE_SHA256:-$(git config --local --get new-project.ticketStoreSha256 2>/dev/null || true)}"
  if [[ -z "$TICKET_STORAGE_HELPER" || -z "$STORE_ROOT" || -z "$STORE_SHA256" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: SQLite allocation requires the managed bridge and an independently pinned Registry writer." >&2
    exit 1
  fi
  python3 "$TICKET_STORAGE_HELPER" verify --runtime-root "$STORE_ROOT" --runtime-sha256 "$STORE_SHA256"
fi

governance_manifest() {
  local candidate
  for candidate in .governance/manifest.json .governance/manifest.base.json governance/manifest.hub.json; do
    if [[ -f "$candidate" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

if ! GOVERNANCE_MANIFEST="$(governance_manifest)"; then
  echo "GOV-MANIFEST-001: governance registry not found; cannot allocate a ticket." >&2
  echo "  remediation: restore .governance/manifest.json in an adopter or governance/manifest.hub.json in the hub." >&2
  exit 1
fi

if ! REGISTRY_VALUES="$(python3 - "$GOVERNANCE_MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
ticket = manifest.get("ticket")
coordination = manifest.get("coordination")
delivery = manifest.get("delivery")
statuses = ticket.get("activeStatuses") if isinstance(ticket, dict) else None
workstreams = coordination.get("workstreams") if isinstance(coordination, dict) else None
targets = delivery.get("targetBranches") if isinstance(delivery, dict) else None
if (
    manifest.get("schema") != "new-project.governance/v2"
    or not isinstance(statuses, list)
    or not statuses
    or any(not isinstance(item, str) or not item for item in statuses)
    or len(statuses) != len(set(statuses))
    or not isinstance(workstreams, dict)
    or not workstreams
    or any(not isinstance(item, str) or not item for item in workstreams)
    or not isinstance(targets, list)
    or len(targets) != 1
    or not isinstance(targets[0], str)
    or not targets[0]
):
    raise SystemExit(1)
for status in statuses:
    print(f"status\t{status}")
for workstream in sorted(workstreams):
    print(f"workstream\t{workstream}")
print(f"target\t{targets[0]}")
PY
)"; then
  echo "GOV-MANIFEST-001: governance registry is invalid: $GOVERNANCE_MANIFEST" >&2
  echo "  remediation: restore a valid governance/v2 ticket and coordination registry." >&2
  exit 1
fi

ACTIVE_STATUSES="$(printf '%s\n' "$REGISTRY_VALUES" | sed -n 's/^status[[:space:]]//p')"
WORKSTREAM_REGISTRY="$(printf '%s\n' "$REGISTRY_VALUES" | sed -n 's/^workstream[[:space:]]//p')"
TARGET_BRANCH="$(printf '%s\n' "$REGISTRY_VALUES" | sed -n 's/^target[[:space:]]//p')"

if [[ -z "$WORKSTREAM" ]]; then
  echo "Workstream is required; choose an id declared in $GOVERNANCE_MANIFEST" >&2
  exit 2
fi

WORKSTREAM="$(printf '%s' "$WORKSTREAM" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$WORKSTREAM" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "Workstream id must match [a-z0-9][a-z0-9-]*" >&2
  exit 2
fi
if ! grep -Fxq -- "$WORKSTREAM" <<< "$WORKSTREAM_REGISTRY"; then
  echo "GOV-WORKSTREAM-001: workstream '$WORKSTREAM' is not declared in $GOVERNANCE_MANIFEST." >&2
  echo "  accepted: $(printf '%s' "$WORKSTREAM_REGISTRY" | tr '\n' ' ')" >&2
  exit 1
fi

is_active_ticket() {
  local directory="$1" resolver status arguments=() runner=()
  if [[ "$TICKET_STORAGE" != sqlite ]]; then
    [[ -f "$directory/README.md" ]] || return 1
  fi
  for resolver in .governance/ticket_activity.py scripts/ticket_activity.py; do
    [[ -f "$resolver" ]] && break
  done
  if [[ ! -f "$resolver" ]]; then
    echo "GOV-TICKET-ACTIVITY-001: managed ticket activity resolver is missing." >&2
    echo "  remediation: restore the complete pinned governance package before allocating." >&2
    exit 1
  fi
  while IFS= read -r status; do
    arguments+=(--active-status "$status")
  done <<< "$ACTIVE_STATUSES"
  if [[ "$TICKET_STORAGE" == sqlite ]]; then
    runner=(python3 "$TICKET_STORAGE_HELPER" active --root "$PWD" --ticket "${directory##*/}")
  else
    runner=(python3 "$resolver" --root . resolve --ticket-dir "$directory")
  fi
  if "${runner[@]}" "${arguments[@]}" >/dev/null; then
    status=0
  else
    status=$?
  fi
  case "$status" in
    0) return 0 ;;
    1) return 1 ;;
    *) exit 1 ;;
  esac
}

# The dimension vocabularies live in the work classification contract, which is
# shipped to targets as .governance/ and kept at governance/ in the hub. Reading
# them keeps this script from drifting away from the contract it must satisfy.
classification_dsl() {
  local candidate
  for candidate in .governance/work-classification.dsl.json governance/work-classification.dsl.json; do
    if [[ -f "$candidate" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

require_classification_value() {
  local dimension="$1" value="$2" dsl
  if ! dsl="$(classification_dsl)"; then
    echo "GOV-CLASS-000: work classification contract not found; cannot validate --$dimension." >&2
    echo "  remediation: restore .governance/work-classification.dsl.json from the pinned package." >&2
    exit 1
  fi
  local allowed
  allowed="$(python3 -c 'import json,sys
data = json.load(open(sys.argv[1]))
print("\n".join(data["dimensions"][sys.argv[2]]))' "$dsl" "$dimension")"
  if ! grep -Fxq -- "$value" <<< "$allowed"; then
    echo "GOV-CLASS-001: '$value' is not a declared $dimension in $dsl." >&2
    echo "  accepted: $(printf '%s' "$allowed" | tr '\n' ' ')" >&2
    exit 1
  fi
}

require_classification_value kind "$KIND"
require_classification_value priority "$PRIORITY"
require_classification_value origin "$ORIGIN"

# Validate the explicit scope before any identity reservation or registered
# allocation request. The same argv is used for admission and both stores.
if (( ${#SCOPE_ARGUMENTS[@]} )); then
  if [[ -z "$TICKET_STORAGE_HELPER" ]]; then
    echo "GOV-WORK-START-001: explicit scope requires the managed ticket storage bridge." >&2
    exit 3
  fi
  python3 "$TICKET_STORAGE_HELPER" scope --root "$PWD" --workstream "$WORKSTREAM" "${SCOPE_ARGUMENTS[@]}" >/dev/null
fi

allocation_config() {
  local candidate
  for candidate in .governance/ticket-allocation.json governance/ticket-allocation.json; do
    if [[ -f "$candidate" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

allocation_runtime() {
  local candidate
  if [[ -n "$SNAPSHOT_PROPOSAL" || -n "$SNAPSHOT_MATERIALIZE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
    for candidate in "$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_allocation.py" "$ALLOCATOR_PACKAGE_ROOT/.governance/ticket_allocation.py"; do
      if [[ -f "$candidate" ]]; then printf '%s' "$candidate"; return 0; fi
    done
    return 1
  fi
  for candidate in .governance/ticket_allocation.py scripts/ticket_allocation.py; do
    if [[ -f "$candidate" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

ALLOCATION_MODE="local-single-clone"
ALLOCATION_CONFIG=""
ALLOCATION_RUNTIME=""
if ALLOCATION_CONFIG="$(allocation_config)"; then
  if ! ALLOCATION_RUNTIME="$(allocation_runtime)"; then
    echo "GOV-TICKET-ALLOCATION-003: ticket allocation policy exists but its managed validator is missing." >&2
    echo "  remediation: restore the complete pinned governance package before allocating." >&2
    exit 5
  fi
  if ! ALLOCATION_MODE="$(python3 "$ALLOCATION_RUNTIME" mode --config "$ALLOCATION_CONFIG")"; then
    echo "  remediation: restore a valid managed ticket-allocation/v1 policy." >&2
    exit 5
  fi
fi
if [[ "$ALLOCATION_MODE" == "local-single-clone" && ( -n "$ALLOCATION_KEY" || -n "$ALLOCATION_RECEIPT" ) ]]; then
  echo "GOV-TICKET-ALLOCATION-003: registered allocation inputs are forbidden in local-single-clone mode." >&2
  echo "  remediation: remove the inputs or adopt a registered allocator policy." >&2
  exit 5
fi

if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
  if [[ ! "$BOOTSTRAP_ADOPTION_DIGEST" =~ ^[0-9a-f]{64}$ || "$TICKET_STORAGE" != files || "$ALLOCATION_MODE" != local-single-clone || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -eq 0 || -n "$RECOVER_REQUEST$SNAPSHOT_PROPOSAL$SNAPSHOT_MATERIALIZE$MIGRATION_AUTHORIZATION$MIGRATION_AUTHORIZATION_SHA256" ]]; then
    echo "GOV-WORK-START-001: bootstrap acknowledgement requires exclusive first bounded file allocation." >&2
    exit 3
  fi
  # Keep the validated bridge for metadata rendering after entering the new
  # checkout; its base deliberately does not yet contain native governance.
  TICKET_STORAGE_HELPER="$(cd "$(dirname "$TICKET_STORAGE_HELPER")" && pwd -P)/$(basename "$TICKET_STORAGE_HELPER")"
fi

# Serialize allocation across every worktree sharing this clone. The high-water
# mark reserves a number even before its ticket is committed and therefore
# remains visible when another worktree cannot see the new directory.
if [[ -n "$SNAPSHOT_PROPOSAL" || -n "$SNAPSHOT_MATERIALIZE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
  if [[ "$TICKET_STORAGE" != files || "$ALLOCATION_MODE" != local-single-clone || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -ne 0 || -n "$RECOVER_REQUEST" || ( -n "$SNAPSHOT_PROPOSAL" && -n "$SNAPSHOT_MATERIALIZE" ) ]]; then
    echo "GOV-TICKET-ALLOCATION-003: snapshot inputs require local file allocation and an exclusive bounded request." >&2
    exit 5
  fi
  snapshot_arguments=(--root "$CALLER_CHECKOUT" --workstream "$WORKSTREAM")
  if [[ -n "$SNAPSHOT_PROPOSAL" ]]; then
    if [[ -n "$RECOVERY_LEASE_STORE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
      echo "GOV-TICKET-ALLOCATION-003: proposal reservation has no authority inputs." >&2
      exit 5
    fi
    snapshot_arguments+=(--prepare "$SNAPSHOT_PROPOSAL")
  elif [[ -n "$SNAPSHOT_MATERIALIZE" && -n "$RECOVERY_LEASE_STORE" && -n "$MIGRATION_AUTHORIZATION" && -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
    snapshot_arguments+=(--materialize "$SNAPSHOT_MATERIALIZE" --lease-store "$RECOVERY_LEASE_STORE" --authorization "$MIGRATION_AUTHORIZATION" --authorization-sha256 "$MIGRATION_AUTHORIZATION_SHA256")
  else
    echo "GOV-TICKET-ALLOCATION-003: incomplete protected materialization inputs." >&2
    exit 5
  fi
  cd "$CALLER_CHECKOUT"
  for candidate in "$ALLOCATOR_PACKAGE_ROOT/scripts/snapshot_allocation.py" "$ALLOCATOR_PACKAGE_ROOT/.governance/snapshot_allocation.py"; do
    if [[ -f "$candidate" ]]; then
      exec python3 "$candidate" "${snapshot_arguments[@]}"
    fi
  done
  echo "GOV-TICKET-ALLOCATION-003: restore the managed snapshot allocator." >&2
  exit 5
fi

if [[ -n "$RECOVER_REQUEST" || -n "$RECOVERY_LEASE_STORE" ]]; then
  if [[ -z "$RECOVER_REQUEST" || -z "$RECOVERY_LEASE_STORE" || "$TICKET_STORAGE" != files || "$ALLOCATION_MODE" != local-single-clone || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -ne 0 ]]; then
    echo "GOV-TICKET-ALLOCATION-003: recovery requires both inputs, file storage and local allocation; scope comes only from the bound request." >&2
    exit 5
  fi
  # Recovery is deliberately different from normal allocation: its request
  # binds an already-existing canonical linked checkout. Resolve normal
  # allocation from primary, but execute this bounded recovery at the caller
  # checkout so its exact ticket branch and managed helper remain available.
  cd "$CALLER_CHECKOUT"
  for candidate in .governance/ticket_recovery.py scripts/ticket_recovery.py; do
    if [[ -f "$candidate" ]]; then
      exec python3 "$candidate" --root . --request "$RECOVER_REQUEST" --lease-store "$RECOVERY_LEASE_STORE" --workstream "$WORKSTREAM"
    fi
  done
  echo "GOV-TICKET-ALLOCATION-003: restore the managed recovery helper." >&2
  exit 5
fi

allocation_lock=""
allocation_state=""
release_allocation_lock() {
  if [[ -n "$allocation_lock" ]]; then
    rmdir "$allocation_lock" 2>/dev/null || true
  fi
}
if git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
  allocation_lock="$git_common_dir/new-project-ticket-allocation.lock"
  allocation_state="$git_common_dir/new-project-ticket-high-water"
  if ! mkdir "$allocation_lock" 2>/dev/null; then
    echo "GOV-TICKET-LOCK-001: another ticket allocation is active in this clone." >&2
    echo "  remediation: wait for it to finish; remove a stale lock only after confirming no allocator is running." >&2
    exit 4
  fi
  trap release_allocation_lock EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
fi

# Remote refresh is explicit. The start check below uses only observed refs.
if [[ "$REFRESH_REMOTE" == true ]] \
  && git rev-parse --git-dir >/dev/null 2>&1 \
  && git remote get-url origin >/dev/null 2>&1; then
  if ! git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*' >/dev/null 2>&1; then
    echo "GOV-TICKET-LOCK-004: remote ticket refs could not be refreshed safely." >&2
    echo "  remediation: restore origin connectivity and retry, or omit --refresh-remote and rely on local refs plus protected merge collision detection." >&2
    exit 4
  fi
fi

# Before reserving an ID or contacting the registered allocator, inspect all
# registered worktrees and local branches, not just this checkout's ticket.
# The clone allocation lock covers this observation and the identity effect;
# it is NOT a writer lease. Recheck admission and fencing before development.
# Unborn/non-Git bootstrap has no branch history yet and retains seed behavior.
if git rev-parse --verify HEAD >/dev/null 2>&1; then
  start_runtime=""
  for candidate in .governance/work_start_check.py scripts/work_start_check.py; do
    if [[ -f "$candidate" ]]; then
      start_runtime="$candidate"
      break
    fi
  done
  if [[ -z "$start_runtime" ]]; then
    echo "GOV-WORK-START-001: managed work-start checker is missing; restore the complete pinned package." >&2
    exit 3
  fi
  bootstrap_arguments=()
  if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
    bootstrap_arguments+=(--bootstrap-adoption-digest "$BOOTSTRAP_ADOPTION_DIGEST")
  fi
  if ! start_report="$(python3 "$start_runtime" --root . --workstream "$WORKSTREAM" --storage "$TICKET_STORAGE" "${SCOPE_ARGUMENTS[@]}" "${bootstrap_arguments[@]}" --allocation-check)"; then
    printf '%s\n' "$start_report" >&2
    echo "GOV-WORK-START-001: reuse, assist, hand off or serialize existing work before new allocation; preserve all checkouts." >&2
    exit 3
  fi
fi

# A ticket number taken on a branch is invisible on disk in another worktree.
# Consult every local and fetched remote branch known to this clone.
refs_highest() {
  local highest_ref=0 ref number decimal
  while read -r ref; do
    [[ -n "$ref" ]] || continue
    while read -r number; do
      decimal=$((10#$number))
      (( decimal > highest_ref )) && highest_ref=$decimal
    done < <(
      git ls-tree -d -r --name-only "$ref" -- project 2>/dev/null \
        | sed -nE 's|^project/ticket-([0-9]+)$|\1|p'
    )
  done < <(git for-each-ref --format='%(refname)' refs/heads refs/remotes 2>/dev/null)
  printf '%s' "$highest_ref"
}

highest=0
conflicting_ticket=""
current_branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "$current_branch" =~ ticket[-/]([0-9]{3,}) ]]; then
  current_ticket="project/ticket-${BASH_REMATCH[1]}"
  if is_active_ticket "$current_ticket"; then
    conflicting_ticket="$current_ticket"
  fi
fi
if git rev-parse --git-dir >/dev/null 2>&1; then
  highest="$(refs_highest)"
  if [[ -n "$TICKET_STORAGE_HELPER" ]]; then
    database_highest="$(python3 "$TICKET_STORAGE_HELPER" highest --root "$PWD")"
    (( database_highest > highest )) && highest=$database_highest
  fi
  if [[ -n "$allocation_state" && -f "$allocation_state" ]]; then
    read -r reserved_highest < "$allocation_state"
    if [[ ! "$reserved_highest" =~ ^[0-9]+$ ]]; then
      echo "GOV-TICKET-LOCK-002: ticket allocation state is invalid." >&2
      exit 4
    fi
    reserved_decimal=$((10#$reserved_highest))
    (( reserved_decimal > highest )) && highest=$reserved_decimal
  fi
fi
if [[ -d project ]]; then
  for dir in project/ticket-*; do
    [[ -d "$dir" ]] || continue
    number="${dir##*-}"
    [[ "$number" =~ ^[0-9]+$ ]] || continue
    decimal=$((10#$number))
    (( decimal > highest )) && highest=$decimal
    if [[ -z "$current_branch" ]] && is_active_ticket "$dir"; then
      active_workstream="$(sed -nE 's/^[[:space:]]*"workstream"[[:space:]]*:[[:space:]]*"([a-z0-9-]+)".*/\1/p' "$dir/intent.json" 2>/dev/null | head -n 1)"
      if [[ -z "$active_workstream" || "$active_workstream" == "unresolved" || "$WORKSTREAM" == "unresolved" || "$active_workstream" == "$WORKSTREAM" ]]; then
        conflicting_ticket="$dir"
      fi
    fi
  done
fi

if [[ -n "$conflicting_ticket" && "$FORCE_NEW" != true ]]; then
  echo "Active ticket conflicts with workstream '$WORKSTREAM': $conflicting_ticket" >&2
  echo "Continue it, or return to the default branch before allocating a distinct workstream." >&2
  exit 3
fi

if [[ "$ALLOCATION_MODE" == "registered" ]]; then
  if [[ -z "$ALLOCATION_KEY" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: registered mode requires --allocation-key from the Supervisor correlation." >&2
    echo "  remediation: retry with the stable task correlation; never invent a local sequence." >&2
    exit 5
  fi
  if ! origin_url="$(git config --get remote.origin.url 2>/dev/null)"; then
    echo "GOV-TICKET-ALLOCATION-003: registered mode requires a canonical origin repository." >&2
    exit 5
  fi
  if ! repository_ref="$(python3 "$ALLOCATION_RUNTIME" repository-ref --url "$origin_url")"; then
    exit 5
  fi
  allocation_arguments=(
    --config "$ALLOCATION_CONFIG"
    --repository-ref "$repository_ref"
    --allocation-key "$ALLOCATION_KEY"
    --title "$TITLE"
    --agent "$AGENT"
    --workstream "$WORKSTREAM"
    --kind "$KIND"
    --priority "$PRIORITY"
    --origin "$ORIGIN"
  )
  if [[ -z "$ALLOCATION_RECEIPT" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: registered allocation receipt is required; submit this request to the configured process URI." >&2
    python3 "$ALLOCATION_RUNTIME" request "${allocation_arguments[@]}"
    exit 5
  fi
  if ! ticket_num="$(python3 "$ALLOCATION_RUNTIME" validate "${allocation_arguments[@]}" --receipt "$ALLOCATION_RECEIPT")"; then
    echo "  remediation: obtain a fresh receipt from the configured process URI for this exact request." >&2
    exit 5
  fi
  next_num=$((10#$ticket_num))
  if (( next_num <= highest )); then
    echo "GOV-TICKET-ALLOCATION-004: registered ticket $ticket_num is already visible in repository state." >&2
    echo "  remediation: continue the existing claim or request a fresh fenced allocation; do not recreate or rename it." >&2
    exit 5
  fi
else
  next_num=$((highest + 1))
  ticket_num="$(printf '%03d' "$next_num")"
fi
ticket_num="$(printf '%03d' "$next_num")"
ticket_id="ticket-$ticket_num"
ticket_dir="project/$ticket_id"
timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
date_only="${timestamp%%T*}"

reserve_ticket_number() {
  [[ -n "$allocation_state" ]] || return 0
  allocation_state_tmp="$allocation_state.$$"
  printf '%s\n' "$next_num" > "$allocation_state_tmp"
  mv "$allocation_state_tmp" "$allocation_state"
}

if [[ "$TICKET_STORAGE" == sqlite ]]; then
  # Retain the existing private clone counter for older allocators. Ticket
  # contents and revisions are stored only in SQLite, never in this cache.
  reserve_ticket_number
  python3 "$TICKET_STORAGE_HELPER" create --root "$PWD" --ticket "$ticket_id" \
    --title "$TITLE" --workstream "$WORKSTREAM" --kind "$KIND" --priority "$PRIORITY" --origin "$ORIGIN" \
    --allocation-key "${ALLOCATION_KEY:-local:$ticket_id}" \
    --runtime-root "$STORE_ROOT" --runtime-sha256 "$STORE_SHA256" "${SCOPE_ARGUMENTS[@]}"
  exit 0
fi

WORKTREE_PATH=""
LEASE_PATH=""
if [[ -n "$PRIMARY_CHECKOUT" ]]; then
  # Filesystem-backed ticket content must never be materialized in the primary
  # checkout. Plan and verify the exact v5 path before reserving identity;
  # after reservation every later failure remains observable for recovery.
  if [[ -z "$WORKTREE_SLUG" ]]; then
    WORKTREE_SLUG="$(printf '%s' "$TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  fi
  if [[ ! "$WORKTREE_SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "GOV-TICKET-ALLOCATION-003: --worktree-slug must contain lowercase ASCII words separated by hyphens." >&2
    exit 5
  fi

  WORKTREE_CONTRACT=""
  for candidate in .governance/worktree_path_check.py subprojects/worktrees/conformance.py; do
    if [[ -f "$candidate" ]]; then
      WORKTREE_CONTRACT="$candidate"
      break
    fi
  done
  if [[ -z "$WORKTREE_CONTRACT" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: Worktrees v5 conformance checker is missing." >&2
    exit 5
  fi
  if ! probe="$(python3 "$WORKTREE_CONTRACT" feature-probe --from-worktree "$PRIMARY_CHECKOUT")"; then
    echo "GOV-TICKET-ALLOCATION-003: unable to probe Git Worktrees v5 support." >&2
    exit 5
  fi
  if ! python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("supported") is True else 1)' <<< "$probe"; then
    echo "GOV-TICKET-ALLOCATION-003: Git 2.51+ with relative worktree add and repair support is required." >&2
    exit 5
  fi
  # The mandatory work-start check above rejects overlapping dirty changes
  # and reservations. With an explicit admitted scope, unrelated primary
  # changes are preserved: the new worktree starts from the committed base.
  # Without a bounded scope, retain the conservative dirty-primary refusal.
  if (( ${#SCOPE_ARGUMENTS[@]} == 0 )) \
      && [[ -n "$(git -C "$PRIMARY_CHECKOUT" status --porcelain=v1 --untracked-files=all)" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: dirty primary requires an explicit disjoint --path scope admitted by work-start; preserve existing changes." >&2
    exit 5
  fi
  if [[ "$(git -C "$PRIMARY_CHECKOUT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)" != "$TARGET_BRANCH" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: allocation requires the registered primary checkout on $TARGET_BRANCH." >&2
    exit 5
  fi
  if ! base_sha="$(git -C "$PRIMARY_CHECKOUT" rev-parse --verify "refs/heads/$TARGET_BRANCH^{commit}")"; then
    echo "GOV-TICKET-ALLOCATION-003: observed target branch is unavailable." >&2
    exit 5
  fi
  # The layout contract needs a stable label, not a remote URL (which may
  # contain credentials in misconfigured clones).
  repository_ref="$(basename "$PRIMARY_CHECKOUT")"
  if ! layout="$(python3 "$WORKTREE_CONTRACT" plan --repository "$repository_ref" \
      --repository-name "$(basename "$PRIMARY_CHECKOUT")" --ticket "$ticket_id" \
      --slug "$WORKTREE_SLUG" --from-worktree "$PRIMARY_CHECKOUT" \
      --path-style "$(python3 -c 'import os; print("windows" if os.name == "nt" else "posix")')")"; then
    echo "GOV-TICKET-ALLOCATION-003: canonical Worktrees v5 layout could not be planned." >&2
    exit 5
  fi
  if ! python3 "$WORKTREE_CONTRACT" validate - --check-filesystem <<< "$layout" >/dev/null; then
    echo "GOV-TICKET-ALLOCATION-003: canonical worktree or lease path is unsafe." >&2
    exit 5
  fi
  mapfile -t layout_values < <(python3 -c '
import json, sys
value = json.load(sys.stdin)
for key in ("branch", "worktreePath", "leasePath"):
    # Bash mapfile requires LF delimiters even with native Windows Python.
    sys.stdout.buffer.write((value[key] + "\n").encode("utf-8"))
' <<< "$layout")
  WORKTREE_BRANCH="${layout_values[0]:-}"
  WORKTREE_PATH="${layout_values[1]:-}"
  LEASE_PATH="${layout_values[2]:-}"
  branch_exists=false
  if git -C "$PRIMARY_CHECKOUT" show-ref --verify --quiet "refs/heads/$WORKTREE_BRANCH"; then
    branch_exists=true
  fi
  if [[ -z "$WORKTREE_BRANCH" || -z "$WORKTREE_PATH" || -z "$LEASE_PATH" \
      || -e "$WORKTREE_PATH" || -e "$LEASE_PATH" \
      || "$branch_exists" == true ]]; then
    echo "GOV-TICKET-ALLOCATION-004: canonical ticket identity is already present or invalid." >&2
    exit 5
  fi

  reserve_ticket_number
  if ! git -C "$PRIMARY_CHECKOUT" worktree add --relative-paths -b "$WORKTREE_BRANCH" "$WORKTREE_PATH" "$base_sha"; then
    echo "GOV-TICKET-ALLOCATION-004: ticket number remains reserved; preserve and reconcile the failed worktree allocation." >&2
    exit 5
  fi
  cd "$WORKTREE_PATH"
  ticket_dir="project/$ticket_id"
fi

if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
  mkdir -p project
fi

if ! mkdir "$ticket_dir" 2>/dev/null; then
  echo "GOV-TICKET-LOCK-003: ticket directory already exists or cannot be created: $ticket_dir" >&2
  exit 4
fi
reserve_ticket_number

escape_sed() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//&/\\&}"
  value="${value//|/\\|}"
  printf '%s' "$value"
}

render_template() {
  local source="$1"
  local target="$2"
  sed \
    -e "s|{TICKET_ID}|$(escape_sed "$ticket_id")|g" \
    -e "s|{NNN}|$(escape_sed "$ticket_num")|g" \
    -e "s|{SHORT_TITLE}|$(escape_sed "$TITLE")|g" \
    -e "s|{TIMESTAMP}|$(escape_sed "$timestamp")|g" \
    -e "s|{YYYY-MM-DD}|$(escape_sed "$date_only")|g" \
    -e "s|{OWNER_NAME}|unresolved:human|g" \
    -e "s|{PROVIDER}|$(escape_sed "$AGENT")|g" \
    -e "s|{WORKSTREAM}|$(escape_sed "$WORKSTREAM")|g" \
    "$source" > "$target"
}

json_escape() {
  # JSON escaping is syntax, not title interpretation. ASCII output preserves
  # Unicode scalars without depending on the host's stdout encoding.
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1])[1:-1], end="")' "$1"
}

render_json_template() {
  local source="$1"
  local target="$2"
  sed \
    -e "s|{TICKET_ID}|$(escape_sed "$(json_escape "$ticket_id")")|g" \
    -e "s|{NNN}|$(escape_sed "$(json_escape "$ticket_num")")|g" \
    -e "s|{SHORT_TITLE}|$(escape_sed "$(json_escape "$TITLE")")|g" \
    -e "s|{TIMESTAMP}|$(escape_sed "$(json_escape "$timestamp")")|g" \
    -e "s|{YYYY-MM-DD}|$(escape_sed "$(json_escape "$date_only")")|g" \
    -e "s|{PROVIDER}|$(escape_sed "$(json_escape "$AGENT")")|g" \
    -e "s|{WORKSTREAM}|$(escape_sed "$(json_escape "$WORKSTREAM")")|g" \
    -e "s|{KIND}|$(escape_sed "$(json_escape "$KIND")")|g" \
    -e "s|{PRIORITY}|$(escape_sed "$(json_escape "$PRIORITY")")|g" \
    -e "s|{ORIGIN}|$(escape_sed "$(json_escape "$ORIGIN")")|g" \
    "$source" > "$target"
}

if [[ -f template/files/ticket.template.md ]]; then
  render_template template/files/ticket.template.md "$ticket_dir/README.md"
else
  cat > "$ticket_dir/README.md" <<EOF
# Ticket $ticket_num: $TITLE

- **ID**: $ticket_id
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: $date_only

## Goal and scope

To be completed from human-owned input.

## Acceptance criteria

- [ ] AC-01: Scope is approved by a human owner.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
EOF
fi

if [[ -f template/files/intent.template.json ]]; then
  render_json_template template/files/intent.template.json "$ticket_dir/intent.json"
else
  cat > "$ticket_dir/intent.json" <<EOF
{
  "schema": "new-project.intent/v3",
  "ticket": "$ticket_id",
  "summary": "$(json_escape "$TITLE")",
  "workstream": "$WORKSTREAM",
  "classification": {
    "kind": "$KIND",
    "priority": "$PRIORITY",
    "origin": "$ORIGIN"
  },
  "allowedPaths": ["project/$ticket_id/**", "TODO.md", "project/TICKETS.md"],
  "forbiddenPaths": ["project/ticket-*/user-*.md"],
  "stacks": [],
  "dependsOn": [],
  "conflictsWith": [],
  "integrationTicket": null
}
EOF
fi

if (( ${#SCOPE_ARGUMENTS[@]} )); then
  if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
    # The identical scope was validated against primary before reservation.
    # Only generated ticket metadata is written here, never adoption/source.
    python3 - "$ticket_dir/intent.json" "$ticket_id" "$WORKSTREAM" "${SCOPE_ARGUMENTS[@]}" <<'PYBOOT'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
intent = json.loads(path.read_text())
if intent["ticket"] != sys.argv[2] or intent["workstream"] != sys.argv[3]:
    raise SystemExit("allocated intent identity mismatch")
intent["allowedPaths"] = [f'project/{sys.argv[2]}/**', 'TODO.md', 'project/TICKETS.md',
                          *[arg.removeprefix("--path=") for arg in sys.argv[4:]]]
path.write_text(json.dumps(intent, indent=2) + "\n")
PYBOOT
  else
    python3 "$TICKET_STORAGE_HELPER" scope --root "$PWD" --workstream "$WORKSTREAM" \
      --ticket "$ticket_id" "${SCOPE_ARGUMENTS[@]}" >/dev/null
  fi
fi

if [[ -n "$LEASE_PATH" ]]; then
  # A lease is local operational state, deliberately ignored by Git. Its
  # identity and scope bind the new branch/worktree before any implementation
  # begins; O_EXCL means a stale or competing lease is never overwritten.
  python3 - "$ticket_dir/intent.json" "$LEASE_PATH" "$ticket_id" "$WORKSTREAM" \
    "$WORKTREE_BRANCH" "$WORKTREE_SLUG" "$repository_ref" "$TARGET_BRANCH" \
    "$base_sha" "$AGENT" "$timestamp" <<'PY'
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

(intent_path, lease_path, ticket, workstream, branch, slug, repository,
 target_branch, head, agent, issued_at) = sys.argv[1:]
intent_file = Path(intent_path)
lease_file = Path(lease_path)
if intent_file.is_symlink() or lease_file.exists() or lease_file.is_symlink():
    raise SystemExit("ticket intent or lease identity is unsafe")
intent = json.loads(intent_file.read_text(encoding="utf-8"))
allowed = intent.get("allowedPaths")
if not isinstance(allowed, list) or not all(isinstance(path, str) and path for path in allowed):
    raise SystemExit("allocated intent scope is invalid")
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
lease = {
    "schema": "wellmanifest.change-lease/v1",
    "leaseId": f"allocation-{ticket}-{slug}",
    # This ignored allocator projection is advisory local state, not a
    # controller grant or a claim about a remote organization. The layout
    # label may be a basename; scope that case explicitly to this primary.
    "repositoryRef": repository if "/" in repository else "local/" + hashlib.sha256(
        str(lease_file.parent.parent.parent.resolve()).encode("utf-8")).hexdigest(),
    "targetBranch": target_branch,
    "ticketId": ticket,
    "workstream": workstream,
    "scopeHash": hashlib.sha256(canonical(allowed)).hexdigest(),
    "branchRef": "refs/heads/" + branch,
    "worktreeId": f"{ticket}--{slug}",
    "ownerActor": "agent:" + agent,
    "ownerSession": f"allocation-{ticket}-{issued_at}",
    "phase": "claimed",
    "leaseRevision": 1,
    "fencingToken": 1,
    "issuedAt": issued_at,
    "expiresAt": (issued + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
    "heartbeatAt": issued_at,
    "headSha": head,
    "pullRequest": None,
    "validatorRunId": None,
    "publicationFrozen": False,
    "planHash": hashlib.sha256(canonical(intent)).hexdigest(),
    "previousReceiptRef": None,
    "eventSequence": 1,
}
lease_file.parent.mkdir(parents=True, exist_ok=True)
for parent in (lease_file.parent, *lease_file.parent.parents):
    if parent == Path(parent.anchor):
        break
    if parent.is_symlink():
        raise SystemExit("lease parent is symlinked")
payload = json.dumps(lease, indent=2, sort_keys=True).encode("utf-8") + b"\n"
descriptor = os.open(lease_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as stream:
    stream.write(payload)
PY
fi

if [[ -n "$USERS" ]]; then
  echo "warning: --users=$USERS did not create user-* files; human-owned input must come from a human or trusted intake boundary" >&2
fi

if [[ -f project/readme.sh ]]; then
  bash ./project/readme.sh
fi

if [[ -n "$WORKTREE_PATH" ]]; then
  echo "Successfully allocated $ticket_id for '$TITLE' in $WORKTREE_PATH."
else
  echo "Successfully scaffolded $ticket_dir for '$TITLE'."
fi
# Additive result: consumers select the returned identity, never a directory
# glob or the last ticket number. Emit only after every allocation step passes.
# The allocator's ignored lease projection does not grant controller authority.
python3 - "$ticket_id" "${WORKTREE_BRANCH:-}" "$WORKTREE_PATH" "$LEASE_PATH" <<'PY'
import json
import sys

ticket, branch, worktree, lease = sys.argv[1:]
print(json.dumps({
    "schema": "new-project.ticket-allocation-result/v1",
    "ticket": ticket,
    "branch": branch or None,
    "worktreePath": worktree or None,
    "leasePath": lease or None,
    "storage": "files",
    "kind": "delivery" if worktree else "scaffold-only",
    "executionAuthorized": False,
}, ensure_ascii=True, sort_keys=True))
PY
