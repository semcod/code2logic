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

# Validate the complete selected package before copying anything. The caller
# owns the target checkout exclusively; observed path changes fail closed.
bootstrap_host_files() {
  python3 - "$1" "$2" "$3" "${4:-bootstrap}" <<'PY'
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
import tempfile


def fail(message):
    raise SystemExit("GOV-AGENT-HOST-004: " + message)


def alias(metadata):
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, 'st_file_attributes', 0) & 0x400)


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        fail('invalid host package path')
    path = PurePosixPath(value)
    if (path.is_absolute() or PureWindowsPath(value).drive or path.as_posix() != value
            or any(part in {'', '.', '..'} or part.casefold() == '.git'
                   or part.endswith(('.', ' ')) for part in value.split('/'))):
        fail('host package paths must be canonical and repository-relative')
    return path.parts


def directory_root(value):
    path = Path(value).absolute()
    for item in (path, *path.parents):
        metadata = item.lstat()
        if alias(metadata) or not stat.S_ISDIR(metadata.st_mode):
            fail('bootstrap roots must be regular directories without aliases')
    return path.resolve()


def checked(root, name, *, required=False, directory=False):
    parts = relative(name)
    path = root
    for index, part in enumerate(parts):
        path /= part
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if required:
                fail('a required host package file is missing')
            continue
        if alias(metadata):
            fail('symlink or reparse point in host package path')
        expect_directory = index < len(parts) - 1 or directory
        if not (stat.S_ISDIR(metadata.st_mode) if expect_directory else stat.S_ISREG(metadata.st_mode)):
            fail('unsupported host package filesystem entry')
    return path


def identity(metadata):
    return metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size, metadata.st_mtime_ns


def source_bytes(root, name):
    path = checked(root, name, required=True)
    before = path.lstat()
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if alias(opened) or not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
            fail('host package source changed before reading')
        data = stream.read()
        after = os.fstat(stream.fileno())
    observed = checked(root, name, required=True).lstat()
    if identity(before) != identity(after) or identity(before) != identity(observed):
        fail('host package source changed while reading')
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('duplicate host package JSON key')
        result[key] = value
    return result


def document(data):
    value = json.loads(data.decode('utf-8'), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        fail('host package metadata must be an object')
    return value


try:
    source, target = directory_root(sys.argv[1]), directory_root(sys.argv[2])
    contract_names = ('governance/agent-hosts.json', '.governance/agent-hosts.json')
    contract_source = next((name for name in contract_names if (source / name).exists() or (source / name).is_symlink()), None)
    if contract_source is None:
        fail('source host contract is missing')
    frozen = {contract_source: source_bytes(source, contract_source)}
    contract = document(frozen[contract_source])
    hook = contract['hook']
    if not isinstance(hook, dict):
        fail('host hook declaration must be an object')
    hosts = [host['file'] for host in contract['hosts']]
    additional = hook.get('additionalHooks', [])
    allowed = {'.githooks/commit-msg', '.githooks/prepare-commit-msg', '.githooks/pre-push'}
    if not isinstance(additional, list) or len(set(additional)) != len(additional) or any(name not in allowed for name in additional):
        fail('invalid additional hook declaration')
    runtime = hook['runtimeFiles']
    if not isinstance(runtime, list):
        fail('host runtime files must be an array')
    governed = set(hosts + [hook['path']] + additional + runtime)
    for name in governed:
        relative(name)
    relative(hook['hooksPathConfig'])
    if PurePosixPath(hook['path']).parent.as_posix() != hook['hooksPathConfig']:
        fail('hook path and hooksPathConfig disagree')
    if len(sys.argv) > 4 and sys.argv[4] == 'in-place':
        source_paths = {}
        if (source / 'governance/manifest.hub.json').is_file():
            package = document(source_bytes(source, 'governance/package-manifest.json'))
            if not isinstance(package['files'], list):
                fail('host package mappings must be an array')
            for item in package['files']:
                relative(item['target'])
                relative(item['source'])
                source_paths[item['target']] = item['source']
        activation = [(name, False) for name in hosts]
        activation += [(hook['path'], True), *((name, True) for name in additional)]
        activation += [(source_paths.get(name, name), False) for name in runtime]
        checked(target, hook['hooksPathConfig'], required=True, directory=True)
        for name, _ in activation:
            checked(target, name, required=True)
        # Return only this validated snapshot; activation never re-reads the contract.
        print(hook['hooksPathConfig'])
        for name, executable in activation:
            print(name + '\t' + ('1' if executable else '0'))
        raise SystemExit(0)
    frozen['governance/package-manifest.json'] = source_bytes(source, 'governance/package-manifest.json')
    manifest = document(frozen['governance/package-manifest.json'])
    selected, targets, plan, contracts = [], set(), [], []
    if not isinstance(manifest['files'], list):
        fail('host package mappings must be an array')
    for item in manifest['files']:
        if not isinstance(item, dict):
            fail('host package mappings must be objects')
        if item['target'] in governed or item['source'] == contract_source:
            relative(item['source'])
            relative(item['target'])
            folded = item['target'].casefold()
            if folded in targets or not isinstance(item['executable'], bool):
                fail('duplicate target or invalid executable flag')
            targets.add(folded)
            checked(target, item['target'])
            if item['source'] not in frozen:
                frozen[item['source']] = source_bytes(source, item['source'])
            data = frozen[item['source']]
            plan.append((item['target'], data, item['executable']))
            selected.append(item['target'])
            if item['source'] == contract_source:
                contracts.append(item['target'])
    if governed - set(selected) or len(contracts) != 1 or contracts[0] not in contract_names:
        fail('incomplete or ambiguous host package mapping')
    # Activation prefers governance/ over .governance/. Preserve an unrelated
    # existing contract rather than copying files and activating another one.
    for name in contract_names:
        if name in selected:
            break
        if (target / name).exists() or (target / name).is_symlink():
            if document(source_bytes(target, name)) != contract:
                fail('existing target host contract differs from the selected package')
            break
    if sys.argv[3] != 'true':
        for name, data, executable in plan:
            parts = relative(name)
            for index in range(1, len(parts)):
                parent_name = '/'.join(parts[:index])
                parent = checked(target, parent_name, directory=True)
                parent.mkdir(exist_ok=True)
                checked(target, parent_name, required=True, directory=True)
            destination = checked(target, name)
            descriptor, temporary = tempfile.mkstemp(prefix='.host-bootstrap.', dir=destination.parent)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(data)
                os.chmod(temporary, 0o755 if executable else 0o644)
                checked(target, name)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
except (OSError, ValueError, TypeError, KeyError):
    fail('host package is invalid, unreadable or changed during bootstrap')
PY
}

activate_in_place() {
  local dest="$1"
  dest="$(cd "$dest" && pwd)"
  local activation hooks targets
  activation="$(bootstrap_host_files "$dest" "$dest" true in-place)" || return 1
  hooks="${activation%%$'\n'*}"
  targets="${activation#*$'\n'}"
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
    if [[ -f "$dest/$candidate" && ! -L "$dest/$candidate" ]]; then
      driver_path="$candidate"
      break
    fi
  done
  if [[ -n "$driver_path" ]]; then
    for driver_key in "wellmanifest-ticket-index" "ticket-index"; do
      git -C "$dest" config "merge.${driver_key}.name" "Wellmanifest Ticket Index Merge Driver" || return 1
      git -C "$dest" config "merge.${driver_key}.driver" "python3 $driver_path %O %A %B" || return 1
    done
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
  bootstrap_host_files "$SOURCE" "$dest" "$CHECK_ONLY" || return 1
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
    "Put every final result in the owning repository through its ticket:",
    "reports and analyses under `docs/` per `wellmanifest/docs` (`check.py --prepare`",
    "before writing, `--deliverable` after commit), error runbooks under `errors/`",
    "per `wellmanifest/logs`. Never leave a final result only in /tmp, a scratchpad,",
    "`$HOME/.local/state` or the chat. Before claiming done run",
    "`./project/governance-check.sh` and the Wellman standards check (`wellman check`);",
    "a required standard that is not installed is an error to fix, not to skip.",
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
