#!/usr/bin/env bash
# Universal ticket scaffolder for target System X repositories.

set -euo pipefail

TITLE="New Task Ticket"
USERS=""
AGENT="antigravity"
WRITER_ACTOR=""
WRITER_SESSION=""
WRITER_IDENTITY_EXPLICIT=false
SEED_BASELINE_REQUEST=""
SEED_MODE=false

if [[ "${NEW_PROJECT_WRITER_ACTOR+set}" == "set" || "${NEW_PROJECT_WRITER_SESSION+set}" == "set" ]]; then
  WRITER_ACTOR="${NEW_PROJECT_WRITER_ACTOR:-}"
  WRITER_SESSION="${NEW_PROJECT_WRITER_SESSION:-}"
  WRITER_IDENTITY_EXPLICIT=true
fi
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
RECOVERY_HELPER=ticket_recovery
LOCAL_RESTORATION=false
RECOVERY_LEASE_STORE=""
WORKTREE_SLUG=""
BOOTSTRAP_ADOPTION_DIGEST=""
STANDARD_ADOPTION_PLAN=""
ADOPTION_PROJECTION=""
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
      --writer-actor ID Explicit allocating actor (or NEW_PROJECT_WRITER_ACTOR)
      --writer-session ID Explicit session (or NEW_PROJECT_WRITER_SESSION)
      --seed-baseline-request FILE
                          Exact external authority/state for one governance-only unborn seed
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
      --restore-request FILE
                          Exact request restoring an already reserved ticket checkout
      --restore-local-request FILE
                          Restore under the explicit live local writer and exact reservation digest
      --recovery-lease-store DIR
                          Existing external local controller store (recovery/restoration)
      --bootstrap-adoption-digest SHA
                          Confirm ownership of exact first scaffold adoption delta
      --standard-adoption-plan FILE
                          Recompute an exact published upgrade plan before local allocation
      --worktree-slug SLUG
                          Canonical linked-worktree slug; defaults to a stable title slug

Accepted classification values come from the work classification contract,
not hardcoded here. The defaults for an unclassified new ticket follow that
contract (rule W-CLASS-006 plus the service priority default); declare the
three explicitly for a defect or new behavior.

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
    --writer-actor)
      require_value "$@"; WRITER_ACTOR="$2"; WRITER_IDENTITY_EXPLICIT=true; shift 2 ;;
    --writer-session)
      require_value "$@"; WRITER_SESSION="$2"; WRITER_IDENTITY_EXPLICIT=true; shift 2 ;;
    --seed-baseline-request)
      require_value "$@"; SEED_BASELINE_REQUEST="$2"; shift 2 ;;
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
    --recover-request|--restore-request|--restore-local-request)
      require_value "$@"
      if [[ -n "$RECOVER_REQUEST" ]]; then
        echo "GOV-TICKET-ALLOCATION-003: pass exactly one recovery or restoration request." >&2
        exit 5
      fi
      [[ "$1" != --recover-request ]] && RECOVERY_HELPER=ticket_restoration
      [[ "$1" == --restore-local-request ]] && LOCAL_RESTORATION=true
      RECOVER_REQUEST="$2"; shift 2 ;;
    --recovery-lease-store)
      require_value "$@"; RECOVERY_LEASE_STORE="$2"; shift 2 ;;
    --bootstrap-adoption-digest)
      require_value "$@"; BOOTSTRAP_ADOPTION_DIGEST="$2"; shift 2 ;;
    --standard-adoption-plan)
      require_value "$@"; STANDARD_ADOPTION_PLAN="$2"; shift 2 ;;
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

if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
  STANDARD_ADOPTION_PLAN="$(python3 -B -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$STANDARD_ADOPTION_PLAN")"
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
if [[ -n "$STANDARD_ADOPTION_PLAN" && ( "$TICKET_STORAGE" != files || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || -n "$BOOTSTRAP_ADOPTION_DIGEST" || -n "$SNAPSHOT_PROPOSAL" || -n "$SNAPSHOT_MATERIALIZE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" || -n "$RECOVER_REQUEST" || -n "$RECOVERY_LEASE_STORE" ) ]]; then
  echo "GOV-TICKET-ALLOCATION-003: adoption plans require exclusive local file allocation without bootstrap or recovery overrides." >&2
  exit 5
fi
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

# Validate caller identity before any reservation, refresh or scaffold effect.
# Provider names and timestamps are not session identity.
if [[ -z "$SNAPSHOT_PROPOSAL$SNAPSHOT_MATERIALIZE$RECOVER_REQUEST" ]]; then
  if [[ "$WRITER_IDENTITY_EXPLICIT" == true ]]; then
    if [[ ! "$WRITER_ACTOR" =~ ^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$ ||
          ! "$WRITER_SESSION" =~ ^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$ ]]; then
      echo "GOV-CHANGE-LEASE-001: allocation requires explicit valid writer actor and session." >&2
      exit 2
    fi
  else
    WRITER_ACTOR="agent:${AGENT}"
    WRITER_SESSION="allocation-$(date -u +"%Y-%m-%dT%H:%M:%SZ")-$$-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
  fi
fi

is_active_ticket() {
  local directory="$1" resolver status arguments=() runner=() candidates=()
  if [[ "$TICKET_STORAGE" != sqlite ]]; then
    [[ -f "$directory/README.md" ]] || return 1
  fi
  candidates=(.governance/ticket_activity.py scripts/ticket_activity.py)
  if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
    candidates+=("$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_activity.py")
  fi
  for resolver in "${candidates[@]}"; do
    [[ -f "$resolver" && ! -L "$resolver" ]] && break
  done
  if [[ ! -f "$resolver" || -L "$resolver" ]]; then
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
  if ! allowed="$(python3 -c 'import json,sys
data = json.load(open(sys.argv[1]))
values = data["dimensions"][sys.argv[2]]
print("\n".join(values))
raise SystemExit(0 if sys.argv[3] in values else 1)' "$dsl" "$dimension" "$value")"; then
    echo "GOV-CLASS-001: '$value' is not a declared $dimension in $dsl." >&2
    echo "  accepted: $(printf '%s' "$allowed" | tr '\n' ' ')" >&2
    exit 1
  fi
}

require_classification_value kind "$KIND"
require_classification_value priority "$PRIORITY"
require_classification_value origin "$ORIGIN"

# The incoming immutable package owns its verifier; the plan never names code.
# Old adopters invoke this published source package's native allocator from
# their primary checkout. A partial installed package is not a fallback.
verify_standard_adoption() {
  local runtime="$ALLOCATOR_PACKAGE_ROOT/scripts/create_adoption_lock.py"
  if [[ ! -f "$runtime" || -L "$runtime" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: adoption allocation requires the complete immutable source package." >&2
    return 5
  fi
  python3 -B - "$runtime" "$STANDARD_ADOPTION_PLAN" "$PWD" "$WORKSTREAM" "${SCOPE_ARGUMENTS[@]}" <<'PYADOPTION'
import importlib.util, json, sys
from pathlib import Path
runtime, plan_path, root, workstream, *scope = sys.argv[1:]
spec = importlib.util.spec_from_file_location("native_adoption_plan", runtime)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
plan = module.verify_allocation_plan(Path(plan_path), Path(root), workstream,
    [argument.removeprefix("--path=") for argument in scope] or None)
print(json.dumps({key: plan[key] for key in ("allowedPaths", "delivery", "digest")}))
PYADOPTION
}

# Validate the explicit scope before any identity reservation or registered
# allocation request. The same argv is used for admission and both stores.
if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
  if ! ADOPTION_PROJECTION="$(verify_standard_adoption)"; then
    echo "GOV-TICKET-ALLOCATION-003: adoption allocation proof is invalid; preserve the target and recompute the exact published plan." >&2
    exit 5
  fi
  if [[ -z "$TICKET_STORAGE_HELPER" && -f "$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_storage.py" && ! -L "$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_storage.py" ]]; then
    TICKET_STORAGE_HELPER="$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_storage.py"
  fi
  mapfile -t adoption_paths < <(python3 -B -c 'import json,sys; print("\n".join(json.load(sys.stdin)["allowedPaths"]))' <<< "$ADOPTION_PROJECTION")
  SCOPE_ARGUMENTS=()
  for adoption_path in "${adoption_paths[@]}"; do SCOPE_ARGUMENTS+=("--path=$adoption_path"); done
elif (( ${#SCOPE_ARGUMENTS[@]} )); then
  if [[ -z "$TICKET_STORAGE_HELPER" ]]; then
    echo "GOV-WORK-START-001: explicit scope requires the managed ticket storage bridge." >&2
    exit 3
  fi
  scope_bootstrap_arguments=()
  if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
    scope_bootstrap_arguments+=(--bootstrap-adoption-digest "$BOOTSTRAP_ADOPTION_DIGEST")
  fi
  python3 "$TICKET_STORAGE_HELPER" scope --root "$PWD" --workstream "$WORKSTREAM" \
    "${scope_bootstrap_arguments[@]}" "${SCOPE_ARGUMENTS[@]}" >/dev/null
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
  local candidate candidates=()
  if [[ -n "$SNAPSHOT_PROPOSAL" || -n "$SNAPSHOT_MATERIALIZE" || -n "$MIGRATION_AUTHORIZATION" || -n "$MIGRATION_AUTHORIZATION_SHA256" ]]; then
    for candidate in "$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_allocation.py" "$ALLOCATOR_PACKAGE_ROOT/.governance/ticket_allocation.py"; do
      if [[ -f "$candidate" ]]; then printf '%s' "$candidate"; return 0; fi
    done
    return 1
  fi
  candidates=(.governance/ticket_allocation.py scripts/ticket_allocation.py)
  if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
    candidates+=("$ALLOCATOR_PACKAGE_ROOT/scripts/ticket_allocation.py")
  fi
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" && ! -L "$candidate" ]]; then
      printf '%s' "$(cd "$(dirname "$candidate")" && pwd -P)/$(basename "$candidate")"
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
if [[ -n "$PRIMARY_CHECKOUT" && -z "$ALLOCATION_RUNTIME" ]]; then
  ALLOCATION_RUNTIME="$(allocation_runtime || true)"
fi
if [[ "$ALLOCATION_MODE" == "local-single-clone" && ( -n "$ALLOCATION_KEY" || -n "$ALLOCATION_RECEIPT" ) ]]; then
  echo "GOV-TICKET-ALLOCATION-003: registered allocation inputs are forbidden in local-single-clone mode." >&2
  echo "  remediation: remove the inputs or adopt a registered allocator policy." >&2
  exit 5
fi

if [[ -n "$SEED_BASELINE_REQUEST" ]]; then
  if [[ "$ALLOCATION_MODE" != local-single-clone || "$TICKET_STORAGE" != files \
      || -z "$PRIMARY_CHECKOUT" || "$WRITER_IDENTITY_EXPLICIT" != true \
      || -n "$RECOVER_REQUEST" || -n "$STANDARD_ADOPTION_PLAN" \
      || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true ]]; then
    echo "GOV-TICKET-ALLOCATION-003: seed requires explicit local file allocation and writer identity only." >&2
    exit 5
  fi
  SEED_RUNNER="$PRIMARY_CHECKOUT/.governance/seed_baseline.py"
  python3 -B "$SEED_RUNNER" preflight --root "$PRIMARY_CHECKOUT" \
    --request "$SEED_BASELINE_REQUEST" --actor "$WRITER_ACTOR" --session "$WRITER_SESSION"
  SEED_MODE=true
fi
if [[ -n "$STANDARD_ADOPTION_PLAN" && "$ALLOCATION_MODE" != local-single-clone ]]; then
  echo "GOV-TICKET-ALLOCATION-003: adoption plans do not support registered allocation." >&2
  exit 5
fi

if [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" ]]; then
  if [[ ! "$BOOTSTRAP_ADOPTION_DIGEST" =~ ^[0-9a-f]{64}$ || "$TICKET_STORAGE" != files || "$ALLOCATION_MODE" != local-single-clone || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -eq 0 || -n "$RECOVER_REQUEST$SNAPSHOT_PROPOSAL$SNAPSHOT_MATERIALIZE$MIGRATION_AUTHORIZATION$MIGRATION_AUTHORIZATION_SHA256" ]]; then
    echo "GOV-WORK-START-001: bootstrap acknowledgement requires exclusive first bounded file allocation." >&2
    exit 3
  fi
fi
if [[ -n "$TICKET_STORAGE_HELPER" && -f "$TICKET_STORAGE_HELPER" ]]; then
  # Keep the validated bridge for metadata rendering after entering the new
  # checkout; its base may not yet contain native governance.
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
  if [[ -z "$RECOVER_REQUEST" || "$TICKET_STORAGE" != files || "$ALLOCATION_MODE" != local-single-clone || "$REFRESH_REMOTE" == true || "$FORCE_NEW" == true || ${#SCOPE_ARGUMENTS[@]} -ne 0 ]] \
      || { [[ "$LOCAL_RESTORATION" == false ]] && [[ -z "$RECOVERY_LEASE_STORE" ]]; } \
      || { [[ "$LOCAL_RESTORATION" == true ]] && [[ -n "$RECOVERY_LEASE_STORE" || "$WRITER_IDENTITY_EXPLICIT" != true || -z "$WRITER_ACTOR" || -z "$WRITER_SESSION" ]]; }; then
    echo "GOV-TICKET-ALLOCATION-003: recovery requires both inputs, file storage and local allocation; scope comes only from the bound request." >&2
    exit 5
  fi
  # Recovery is deliberately different from normal allocation: its request
  # binds an already-existing canonical linked checkout. Resolve normal
  # allocation from primary, but execute this bounded recovery at the caller
  # checkout so its exact ticket branch and managed helper remain available.
  # Restoration re-registers an already reserved identity whose checkout is
  # lost; it shares these inputs and exclusions but never reserves a number.
  cd "$CALLER_CHECKOUT"
  restoration_authority=(--lease-store "$RECOVERY_LEASE_STORE")
  if [[ "$LOCAL_RESTORATION" == true ]]; then
    restoration_authority=(--local-reservation --actor "$WRITER_ACTOR" --session "$WRITER_SESSION")
  fi
  for candidate in ".governance/$RECOVERY_HELPER.py" "scripts/$RECOVERY_HELPER.py"; do
    if [[ -f "$candidate" ]]; then
      exec python3 "$candidate" --root . --request "$RECOVER_REQUEST" "${restoration_authority[@]}" --workstream "$WORKSTREAM"
    fi
  done
  echo "GOV-TICKET-ALLOCATION-003: restore the managed recovery helper." >&2
  exit 5
fi

# Fail before clone locking, identity reservation or worktree creation when
# the host cannot provide race-resistant directory-relative lease writes.
if [[ "$TICKET_STORAGE" != sqlite ]]; then
  python3 - <<'PY_LEASE_CAPABILITIES'
import os
if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd):
    raise SystemExit("GOV-TICKET-ALLOCATION-003: race-resistant lease creation is unsupported on this host")
PY_LEASE_CAPABILITIES
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
if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
  if ! rechecked_projection="$(verify_standard_adoption)"; then
    echo "GOV-TICKET-ALLOCATION-003: adoption allocation proof changed under the clone lock." >&2
    exit 5
  fi
  if [[ "$rechecked_projection" != "$ADOPTION_PROJECTION" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: adoption plan changed before reservation." >&2
    exit 5
  fi
fi
if git rev-parse --verify HEAD >/dev/null 2>&1; then
  start_runtime=""
  start_candidates=(.governance/work_start_check.py scripts/work_start_check.py)
  if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
    start_candidates+=("$ALLOCATOR_PACKAGE_ROOT/scripts/work_start_check.py")
  fi
  for candidate in "${start_candidates[@]}"; do
    if [[ -f "$candidate" && ! -L "$candidate" ]]; then
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
if [[ -n "$PRIMARY_CHECKOUT" && "$SEED_MODE" != true ]]; then
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
  worktree_candidates=(.governance/worktree_path_check.py subprojects/worktrees/conformance.py)
  if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
    worktree_candidates+=("$ALLOCATOR_PACKAGE_ROOT/subprojects/worktrees/conformance.py")
  fi
  for candidate in "${worktree_candidates[@]}"; do
    if [[ -f "$candidate" && ! -L "$candidate" ]]; then
      WORKTREE_CONTRACT="$(cd "$(dirname "$candidate")" && pwd -P)/$(basename "$candidate")"
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
  observe_primary_base() {
    local branch head target remote
    branch="$(git -C "$PRIMARY_CHECKOUT" symbolic-ref --quiet HEAD 2>/dev/null)" || return 1
    head="$(git -C "$PRIMARY_CHECKOUT" rev-parse --verify 'HEAD^{commit}')" || return 1
    target="$(git -C "$PRIMARY_CHECKOUT" rev-parse --verify "refs/heads/$TARGET_BRANCH^{commit}")" || return 1
    remote="$(git -C "$PRIMARY_CHECKOUT" rev-parse --verify "refs/remotes/origin/$TARGET_BRANCH^{commit}" 2>/dev/null || true)"
    [[ "$head" == "$target" ]] || return 1
    if [[ "$branch" != "refs/heads/$TARGET_BRANCH" ]]; then
      # A named alias is safe only with a complete, identical observed target.
      # This does not refresh refs, switch primary or release active scope.
      [[ "$branch" == refs/heads/* && "$remote" == "$head" ]] || return 1
    fi
    printf '%s\t%s\t%s\t%s\n' "$branch" "$head" "$target" "$remote"
  }
  if ! primary_base_observation="$(observe_primary_base)"; then
    echo "GOV-TICKET-ALLOCATION-003: primary must be on $TARGET_BRANCH or a named alias exactly matching local and origin target commits." >&2
    exit 5
  fi
  base_sha="$(cut -f2 <<< "$primary_base_observation")"
  # Leases bind the canonical owner/repository identity; path planning binds a
  # separate local label that never becomes repositoryRef.
  origin_url="$(git -C "$PRIMARY_CHECKOUT" config --get remote.origin.url 2>/dev/null || true)"
  if [[ -n "$origin_url" && -n "$ALLOCATION_RUNTIME" ]]; then
    canonical_origin="$(python3 "$ALLOCATION_RUNTIME" repository-ref --url "$origin_url" 2>/dev/null || true)"
  else
    canonical_origin=""
  fi
  if [[ -n "$canonical_origin" ]]; then
    repository_ref="$(python3 - "$canonical_origin" <<'PY'
from urllib.parse import urlparse
import sys
value = urlparse(sys.argv[1])
parts = value.path.strip('/').split('/')
if len(parts) == 2 and value.netloc and all(part not in ('', '.', '..') for part in parts):
    print('/'.join(parts))
PY
)"
  else
    repository_ref=""
  fi
  if [[ -z "${repository_ref:-}" ]]; then
    repository_ref="local/$(python3 - "$PRIMARY_CHECKOUT" <<'PY'
import hashlib
from pathlib import Path
import sys
print(hashlib.sha256(str(Path(sys.argv[1]).resolve(strict=True)).encode('utf-8')).hexdigest())
PY
)" || exit 5
  fi
  layout_repository_name="$(basename "$PRIMARY_CHECKOUT")"
  if ! layout="$(python3 "$WORKTREE_CONTRACT" plan --repository "$layout_repository_name" \
      --repository-name "$layout_repository_name" --ticket "$ticket_id" \
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

  if [[ -n "$STANDARD_ADOPTION_PLAN" && "$(verify_standard_adoption)" != "$ADOPTION_PROJECTION" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: adoption plan changed at the identity boundary." >&2
    exit 5
  fi
  if ! rechecked_primary_base="$(observe_primary_base)" \
      || [[ "$rechecked_primary_base" != "$primary_base_observation" ]]; then
    echo "GOV-TICKET-ALLOCATION-003: primary branch or target changed before ticket reservation." >&2
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

ticket_parent="$(dirname "$ticket_dir")"
if [[ "$ticket_parent" != "." ]]; then
  if [[ -L "$ticket_parent" || ( -e "$ticket_parent" && ! -d "$ticket_parent" ) ]]; then
    echo "GOV-TICKET-LOCK-003: ticket directory already exists or cannot be created: $ticket_dir" >&2
    exit 4
  fi
  mkdir -p "$ticket_parent"
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
  "ticket": "$(json_escape "$ticket_id")",
  "summary": "$(json_escape "$TITLE")",
  "workstream": "$(json_escape "$WORKSTREAM")",
  "classification": {
    "kind": "$(json_escape "$KIND")",
    "priority": "$(json_escape "$PRIORITY")",
    "origin": "$(json_escape "$ORIGIN")"
  },
  "allowedPaths": ["project/$(json_escape "$ticket_id")/**", "TODO.md", "project/TICKETS.md"],
  "forbiddenPaths": ["project/ticket-*/user-*.md"],
  "stacks": [],
  "dependsOn": [],
  "conflictsWith": [],
  "integrationTicket": null
}
EOF
fi

if (( ${#SCOPE_ARGUMENTS[@]} )); then
  if [[ -n "$STANDARD_ADOPTION_PLAN" ]]; then
    # Full accepted delivery is written BEFORE native reservation hashes.
    python3 -B - "$ticket_dir/intent.json" "$ticket_id" "$WORKSTREAM" "$ADOPTION_PROJECTION" <<'PYADOPTIONINTENT'
import json, sys
from pathlib import Path
path, ticket, workstream, raw = sys.argv[1:]
projection = json.loads(raw)
intent = json.loads(Path(path).read_text())
if intent["ticket"] != ticket or intent["workstream"] != workstream:
    raise SystemExit("allocated adoption identity mismatch")
intent["allowedPaths"] = [f"project/{ticket}/**", "TODO.md", "project/TICKETS.md", *projection["allowedPaths"]]
intent["delivery"] = projection["delivery"]
Path(path).write_text(json.dumps(intent, indent=2) + "\n")
PYADOPTIONINTENT
  elif [[ -n "$BOOTSTRAP_ADOPTION_DIGEST" || ! -f .governance/manifest.base.json ]]; then
    # The identical scope was validated against primary before reservation.
    # Only generated ticket metadata is written here, never adoption/source.
    python3 - "$ticket_dir/intent.json" "$ticket_id" "$WORKSTREAM" "${SCOPE_ARGUMENTS[@]}" <<'PYBOOT'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
intent = json.loads(path.read_text())
if intent["ticket"] != sys.argv[2] or intent["workstream"] != sys.argv[3]:
    raise SystemExit("allocated intent identity mismatch")
intent["allowedPaths"] = list(dict.fromkeys([
    f'project/{sys.argv[2]}/**', 'TODO.md', 'project/TICKETS.md',
    *[arg.removeprefix("--path=") for arg in sys.argv[4:]]
]))
path.write_text(json.dumps(intent, indent=2) + "\n")
PYBOOT
  else
    python3 "$TICKET_STORAGE_HELPER" scope --root "$PWD" --workstream "$WORKSTREAM" \
      --ticket "$ticket_id" "${SCOPE_ARGUMENTS[@]}" >/dev/null
  fi
fi

if [[ "$TICKET_STORAGE" != "sqlite" ]]; then
  # Assess the actual declared scope before writer-reservation hashes are made.
  # The external product is advisory; its absence is recorded in the README.
  # Helpers older than the radar subcommand must degrade to the same advisory
  # marker instead of failing the allocation (forward compatibility).
  if [[ -n "$TICKET_STORAGE_HELPER" ]]; then
    if ! python3 -B "$TICKET_STORAGE_HELPER" radar --root "$PWD" --ticket "$ticket_id" 2>/dev/null; then
      echo "ticket-radar advisory: storage helper declined the assessment; README records it." >&2
      cat >> "$ticket_dir/README.md" <<'RADAR'

<!-- ticket-radar:start -->
## Ticket Radar

Assessment unavailable: managed ticket storage bridge declined the radar assessment.
Advisory only; no execution or merge approval.
<!-- ticket-radar:end -->
RADAR
    fi
  else
    cat >> "$ticket_dir/README.md" <<'RADAR'

<!-- ticket-radar:start -->
## Ticket Radar

Assessment unavailable: managed ticket storage bridge is not installed.
Advisory only; no execution or merge approval.
<!-- ticket-radar:end -->
RADAR
  fi
fi

if [[ "$SEED_MODE" == true ]]; then
  # Only the seed's own ticket carriers may precede a real baseline. Ordinary
  # implementation still receives a canonical linked checkout and lease.
  python3 -B "$SEED_RUNNER" prepare --root "$PRIMARY_CHECKOUT" \
    --request "$SEED_BASELINE_REQUEST" --actor "$WRITER_ACTOR" \
    --session "$WRITER_SESSION" --ticket "$ticket_id"
  python3 -B "$SEED_RUNNER" commit --root "$PRIMARY_CHECKOUT" \
    --request "$SEED_BASELINE_REQUEST" --actor "$WRITER_ACTOR" --session "$WRITER_SESSION"
  base_sha="$(git rev-parse HEAD)"
  if [[ -z "$WORKTREE_SLUG" ]]; then
    WORKTREE_SLUG="$(printf '%s' "$TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  fi
  origin_url="$(git -C "$PRIMARY_CHECKOUT" config --get remote.origin.url 2>/dev/null || true)"
  if [[ -n "$origin_url" && -n "$ALLOCATION_RUNTIME" ]]; then
    canonical_origin="$(python3 "$ALLOCATION_RUNTIME" repository-ref --url "$origin_url" 2>/dev/null || true)"
  else
    canonical_origin=""
  fi
  if [[ -n "$canonical_origin" ]]; then
    repository_ref="$(python3 - "$canonical_origin" <<'PY'
from urllib.parse import urlparse
import sys
value = urlparse(sys.argv[1])
parts = value.path.strip('/').split('/')
if len(parts) == 2 and value.netloc and all(part not in ('', '.', '..') for part in parts):
    print('/'.join(parts))
PY
)"
  else
    repository_ref=""
  fi
  if [[ -z "${repository_ref:-}" ]]; then
    repository_ref="local/$(python3 - "$PRIMARY_CHECKOUT" <<'PY'
import hashlib
from pathlib import Path
import sys
print(hashlib.sha256(str(Path(sys.argv[1]).resolve(strict=True)).encode('utf-8')).hexdigest())
PY
)" || exit 5
  fi
  layout_repository_name="$(basename "$PRIMARY_CHECKOUT")"
  layout="$(python3 .governance/worktree_path_check.py plan --repository "$layout_repository_name" \
    --repository-name "$layout_repository_name" --ticket "$ticket_id" --slug "$WORKTREE_SLUG" \
    --from-worktree "$PRIMARY_CHECKOUT" --path-style posix)"
  python3 .governance/worktree_path_check.py validate - --check-filesystem <<< "$layout" >/dev/null
  mapfile -t layout_values < <(python3 -c 'import json,sys; v=json.load(sys.stdin); print(v["branch"]); print(v["worktreePath"]); print(v["leasePath"])' <<< "$layout")
  WORKTREE_BRANCH="${layout_values[0]}"
  WORKTREE_PATH="${layout_values[1]}"
  LEASE_PATH="${layout_values[2]}"
  git worktree add --relative-paths -b "$WORKTREE_BRANCH" "$WORKTREE_PATH" "$base_sha"
  cd "$WORKTREE_PATH"
fi

if [[ -n "$LEASE_PATH" ]]; then
  # A lease is local operational state, deliberately ignored by Git. Its
  # identity and scope bind the new branch/worktree before any implementation
  # begins; O_EXCL means a stale or competing lease is never overwritten.
  python3 - "$ticket_dir/intent.json" "$LEASE_PATH" "$ticket_id" "$WORKSTREAM" \
    "$WORKTREE_BRANCH" "$WORKTREE_SLUG" "$repository_ref" "$TARGET_BRANCH" \
    "$base_sha" "$WRITER_ACTOR" "$WRITER_SESSION" "$timestamp" <<'PY'
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

(intent_path, lease_path, ticket, workstream, branch, slug, repository,
 target_branch, head, actor, session, issued_at) = sys.argv[1:]
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
    "ownerActor": actor,
    "ownerSession": session,
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
# Bind every directory lookup to an already-open directory descriptor. A
# pathname check followed by pathname creation can follow a replaced ancestor.
if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd):
    raise SystemExit("race-resistant lease creation is unsupported on this host")
if not lease_file.is_absolute() or ".." in lease_file.parts:
    raise SystemExit("lease path must be an absolute canonical path")
directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
parent_descriptor = os.open(lease_file.anchor, directory_flags)
try:
    for component in lease_file.parts[1:-1]:
        try:
            os.mkdir(component, mode=0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        child_descriptor = os.open(component, directory_flags, dir_fd=parent_descriptor)
        os.close(parent_descriptor)
        parent_descriptor = child_descriptor
    payload = json.dumps(lease, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor = os.open(lease_file.name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_descriptor)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
finally:
    os.close(parent_descriptor)
PY
fi

if [[ -n "$USERS" ]]; then
  echo "warning: --users=$USERS did not create user-* files; human-owned input must come from a human or trusted intake boundary" >&2
fi

# The older adopter's index generator may require a different carrier format.
# A plan allocates untracked metadata only; leave existing index bytes intact
# until the separately authorized material upgrade installs its pinned tool.
if [[ -z "$STANDARD_ADOPTION_PLAN" && -f project/readme.sh ]]; then
  T2C_TICKET_INDEX_OWN="project/$ticket_id" bash ./project/readme.sh
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
