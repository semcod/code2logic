#!/usr/bin/env bash
# Activate the host-agnostic new-project contract in a clone, and optionally
# bootstrap it into another checkout or into user-level LLM host directories.
#
# The file list is not hardcoded here: it is read from the agent host contract
# (governance/agent-hosts.json or .governance/agent-hosts.json) and, when
# bootstrapping a different checkout, from governance/package-manifest.json.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/install-agent-hosts.sh [options]

  --source DIR    Hub or already-populated checkout (default: this script's repo)
  --target DIR    Git clone that should receive host files and hooksPath
  --user          Also install user-level Cursor / Gemini / Claude pointers
  --check         Report what is missing and exit non-zero; change nothing
  -h, --help      Show this help

With no --target and no --user the current git work tree is activated in place:
host files already delivered by adoption are verified, the hook is made
executable and core.hooksPath is set. Nothing is copied over itself.
EOF
}

SOURCE=""
TARGET=""
USER_INSTALL=false
CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "Missing value for --source" >&2; exit 2; }
      SOURCE="$2"; shift 2 ;;
    --target)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "Missing value for --target" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --user) USER_INSTALL=true; shift ;;
    --check) CHECK_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$SOURCE" ]]; then
  SOURCE="$(cd "$script_dir/.." && pwd)"
fi
SOURCE="$(cd "$SOURCE" && pwd)"

if [[ -z "$TARGET" && "$USER_INSTALL" == false ]]; then
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    TARGET="$(git rev-parse --show-toplevel)"
  else
    echo "No --target and current directory is not a git work tree." >&2
    usage >&2
    exit 2
  fi
fi

contract_path() {
  local root="$1"
  for candidate in "governance/agent-hosts.json" ".governance/agent-hosts.json"; do
    if [[ -f "$root/$candidate" ]]; then
      python3 - "$root/$candidate" <<'PY' || return 1
import json, sys
contract = json.load(open(sys.argv[1], encoding="utf-8"))
hooks = contract.get("hook", {}).get("additionalHooks", [])
allowed = {".githooks/commit-msg", ".githooks/prepare-commit-msg"}
if (not isinstance(hooks, list)
        or any(not isinstance(hook, str) or hook not in allowed for hook in hooks)
        or len(hooks) != len(set(hooks))):
    raise SystemExit("GOV-AGENT-HOST-004: invalid additional hook declaration")
PY
      printf '%s\n' "$root/$candidate"
      return 0
    fi
  done
  echo "Agent host contract not found under $root" >&2
  return 1
}

# Emits "<target-path>\t<is-hook>" lines for every file the contract governs.
contract_targets() {
  python3 - "$1" "$2" <<'PY'
import json, pathlib, sys
contract = json.load(open(sys.argv[1], encoding="utf-8"))
root = pathlib.Path(sys.argv[2])
hub = root / "governance/manifest.hub.json"
source_paths = {}
if hub.is_file():
    package = json.loads((root / "governance/package-manifest.json").read_text())
    source_paths = {item["target"]: item["source"] for item in package["files"]}
for host in contract["hosts"]:
    print(f"{host['file']}\t0")
print(f"{contract['hook']['path']}\t1")
for hook in contract["hook"].get("additionalHooks", []):
    print(f"{hook}\t1")
for runtime_file in contract["hook"]["runtimeFiles"]:
    # The hub owns package sources; adopters own the managed target paths.
    relative = source_paths.get(runtime_file, runtime_file)
    print(f"{relative}\t0")
PY
}

hooks_path_config() {
  python3 - "$1" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["hook"]["hooksPathConfig"])
PY
}

# Emits "<source>\t<target>\t<executable>" for every file the host contract
# needs in a target checkout: the instruction files, the hook, and the contract
# itself, because activate_in_place reads the contract from the target.
package_host_files() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
contract = json.load(open(sys.argv[2], encoding="utf-8"))
contract_source = sys.argv[3]
governed = (
    {host["file"] for host in contract["hosts"]}
    | {contract["hook"]["path"]}
    | set(contract["hook"].get("additionalHooks", []))
    | set(contract["hook"]["runtimeFiles"])
)
selected = [item for item in manifest["files"]
            if item["target"] in governed or item["source"] == contract_source]
missing = governed - {item["target"] for item in selected}
if missing or not any(item["source"] == contract_source for item in selected):
    raise SystemExit("Incomplete host package mapping")
for item in selected:
    print(f"{item['source']}\t{item['target']}\t{int(bool(item['executable']))}")
PY
}

activate_in_place() {
  local dest="$1"
  dest="$(cd "$dest" && pwd)"
  local contract hooks targets
  contract="$(contract_path "$dest")" || return 1
  hooks="$(hooks_path_config "$contract")" || return 1
  targets="$(contract_targets "$contract" "$dest")" || return 1
  local missing=()

  while IFS=$'\t' read -r target is_hook; do
    if [[ ! -f "$dest/$target" ]]; then
      missing+=("$target")
      continue
    fi
  done <<< "$targets"

  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf 'GOV-AGENT-HOST-004: missing host files in %s:\n' "$dest" >&2
    printf '  %s\n' "${missing[@]}" >&2
    echo "  Adopt the current standard package, or bootstrap with --source <hub> --target $dest" >&2
    return 1
  fi

  if [[ "$CHECK_ONLY" == true ]]; then
    while IFS=$'\t' read -r target is_hook; do
      if [[ "$is_hook" == "1" && ! -x "$dest/$target" ]]; then
        echo "GOV-AGENT-HOST-005: hook is not executable: $dest/$target" >&2
        return 1
      fi
    done <<< "$targets"
    local configured; configured="$(git -C "$dest" config --get core.hooksPath || true)"
    if [[ "$configured" != "$hooks" ]]; then
      echo "GOV-AGENT-HOST-006: core.hooksPath is '${configured:-unset}', expected '$hooks'" >&2
      return 1
    fi
    echo "Host contract is active in $dest"
    return 0
  fi

  while IFS=$'\t' read -r target is_hook; do
    if [[ "$is_hook" == "1" ]]; then
      chmod +x "$dest/$target" || return 1
    fi
  done <<< "$targets"
  git -C "$dest" config core.hooksPath "$hooks" || return 1

  local driver_path=""
  for candidate in ".governance/ticket_index_merge_driver.py" "scripts/ticket_index_merge_driver.py"; do
    if [[ -f "$dest/$candidate" ]]; then
      driver_path="$candidate"
      break
    fi
  done
  if [[ -n "$driver_path" ]]; then
    git -C "$dest" config merge.wellmanifest-ticket-index.name "Wellmanifest Ticket Index Merge Driver" || true
    git -C "$dest" config merge.wellmanifest-ticket-index.driver "python3 $driver_path %O %A %B %P" || true
  fi

  echo "Activated host contract and core.hooksPath=$hooks in $dest"
}

bootstrap_into() {
  local dest="$1"
  dest="$(cd "$dest" && pwd)"
  if ! git -C "$dest" rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "Target is not a git work tree: $dest" >&2
    exit 1
  fi
  local contract files
  contract="$(contract_path "$SOURCE")" || return 1
  local manifest="$SOURCE/governance/package-manifest.json"
  if [[ ! -f "$manifest" ]]; then
    echo "Source has no governance/package-manifest.json: $SOURCE" >&2
    exit 1
  fi

  files="$(package_host_files "$manifest" "$contract" "${contract#"$SOURCE/"}")" || return 1
  # Validate the entire input before the first destination write.
  while IFS=$'\t' read -r source target executable; do
    if [[ ! -f "$SOURCE/$source" ]]; then
      echo "Source file missing: $SOURCE/$source" >&2
      return 1
    fi
  done <<< "$files"
  if [[ "$CHECK_ONLY" == true ]]; then
    activate_in_place "$dest"
    return $?
  fi
  while IFS=$'\t' read -r source target executable; do
    mkdir -p "$dest/$(dirname "$target")" || return 1
    cp -f "$SOURCE/$source" "$dest/$target" || return 1
    if [[ "$executable" == "1" ]]; then
      chmod +x "$dest/$target" || return 1
    fi
  done <<< "$files"

  activate_in_place "$dest"
}

install_user_files() {
  local task_user_home="${HOME:-}"
  if [[ -z "$task_user_home" || ! -d "$task_user_home" ]]; then
    echo "HOME is not a directory; skipping --user" >&2
    return 1
  fi
  if [[ "$CHECK_ONLY" == true ]]; then
    echo "--check does not inspect user-level pointers"
    return 0
  fi
  local rule="$SOURCE/.cursor/rules/new-project-standard.mdc"
  [[ -f "$rule" ]] || { echo "Source file missing: $rule" >&2; return 1; }

  mkdir -p "$task_user_home/.cursor/rules" "$task_user_home/.gemini" "$task_user_home/.claude" "$task_user_home/.config/aider" || return 1
  cp -f "$rule" "$task_user_home/.cursor/rules/new-project-standard.mdc" || return 1

  local marker="wellmanifest/new-project host contract"
  for pointer in "$task_user_home/.gemini/GEMINI.md" "$task_user_home/.claude/CLAUDE.md"; do
    # Governance can exist only in a registered ticket worktree until its
    # adoption merges, so discovery must not depend on the current checkout.
    # Replace only the managed paragraph after the marker; keep other text.
    python3 - "$pointer" "$marker" <<'PY' || return 1
import os, pathlib, sys, tempfile
path, marker = pathlib.Path(sys.argv[1]), sys.argv[2]
paragraph = [
    "When the current Git checkout, or any checkout listed by `git worktree list`,",
    "has `./project/new-ticket.sh`, or its primary checkout has",
    "`.subactor/leases/*.json`, follow the host contract and `AGENTS.md` of the",
    "ticket checkout that owns the work, even if the current checkout lacks them.",
    "Allocate tickets only through that script. Never commit on main or a dirty",
    "primary checkout. Run `./scripts/install-agent-hosts.sh` once per clone so",
    "the git hook is active.",
]
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
heading = f"# {marker}"
if lines.count(heading) > 1:
    raise SystemExit("Duplicate managed host contract heading; preserve the file and repair its boundary.")
if heading in lines:
    start = lines.index(heading)
    body = start + 1
    while body < len(lines) and not lines[body].strip():
        body += 1
    if body >= len(lines) or not lines[body].startswith("When the current "):
        raise SystemExit("Malformed managed host contract paragraph; preserve the file and repair its boundary.")
    if body < len(lines) and lines[body].startswith("When the current "):
        end = body
        while end < len(lines) and lines[end].strip() and not lines[end].startswith("#"):
            end += 1
        lines[start:end] = [heading, "", *paragraph]
    updated = "\n".join(lines) + "\n"
else:
    updated = text + ("" if not text or text.endswith("\n") else "\n") + "\n" + "\n".join([heading, "", *paragraph]) + "\n"
if updated != text:
    fd, temporary = tempfile.mkstemp(prefix=".host-pointer.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(updated)
    os.replace(temporary, path)
PY
  done
  echo "Installed user-level host pointers under $task_user_home/.cursor $task_user_home/.gemini $task_user_home/.claude"
}

status=0
if [[ -n "$TARGET" ]]; then
  target_abs="$(cd "$TARGET" && pwd)"
  if [[ "$target_abs" == "$SOURCE" ]]; then
    activate_in_place "$target_abs" || status=1
  else
    bootstrap_into "$target_abs" || status=1
  fi
fi
if [[ "$USER_INSTALL" == true ]]; then
  install_user_files || status=1
fi
exit "$status"
