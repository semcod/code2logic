#!/usr/bin/env bash
# Git invokes this before a push. Delivery reaches the declared target branch only
# through a reviewed pull request merged by the validator; a direct push skips
# review, required checks and CI (GOV-PUSH-001). Repositories whose delivery
# profile is main-only or local-audit commit on the target branch by design.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
allow_target=false
policy_runner="$root/.governance/repository_policy.py"
[[ -f "$policy_runner" ]] || policy_runner="$root/scripts/repository_policy.py"
if [[ -f "$policy_runner" ]]; then
  profile="$(PYTHONDONTWRITEBYTECODE=1 python3 "$policy_runner" --root "$root" --profile 2>/dev/null || true)"
  case "$profile" in
    local-audit|main-only-planfile|main-only-files) allow_target=true ;;
  esac
fi

if ! targets="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$root" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
try:
    for rel in (".governance/manifest.json", ".governance/manifest.base.json", "governance/manifest.hub.json"):
        path = root / rel
        if not path.exists():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        delivery = manifest.get("delivery", {})
        if not isinstance(delivery, dict):
            raise ValueError("delivery must be an object")
        if "targetBranches" not in delivery:
            continue
        branches = delivery["targetBranches"]
        if not isinstance(branches, list) or not branches or not all(isinstance(b, str) and b and not any(c.isspace() for c in b) for b in branches):
            raise ValueError("target branches must be a nonempty list of branch names")
        print("\n".join(branches))
        break
    else:
        print("main")
except (OSError, UnicodeError, ValueError):
    print("GOV-PUSH-001: invalid or unreadable target-branch policy; restore the declared manifest before pushing.", file=sys.stderr)
    sys.exit(1)
PY
)"; then
  exit 1
fi

refused=0
while read -r local_ref local_sha remote_ref remote_sha; do
  [[ -n "${remote_ref:-}" ]] || continue
  for ref in "$local_ref" "$remote_ref"; do
    if [[ "$ref" =~ ^refs/heads/(.*/)?ticket[-/][0-9]{3,} ]]; then
      writer_runner="$root/.governance/change_lease_check.py"
      [[ -f "$writer_runner" ]] || writer_runner="$root/scripts/change_lease_check.py"
      if [[ ! -f "$writer_runner" ]]; then
        echo "GOV-CHANGE-LEASE-001: writer-lease checker is missing; restore the managed installation." >&2
        refused=1
      elif ! python3 -B "$writer_runner" writer-check --root "$root" --operation push --ref "$ref"; then
        refused=1
      fi
    fi
  done
  [[ "$allow_target" == true ]] && continue
  while IFS= read -r target; do
    if [[ "$remote_ref" == "refs/heads/$target" ]]; then
      echo "GOV-PUSH-001: direct push to '$target' refused ($local_ref -> $remote_ref)." >&2
      echo "  Push the ticket branch and open a pull request; the validator merges it." >&2
      refused=1
    fi
  done <<< "$targets"
done

exit "$refused"
