#!/usr/bin/env python3
"""Derive a repository's required-checks declaration from its own workflows.

Every adopter currently ships the hub's copy verbatim: repository
`wellmanifest/new-project`, workflowFile `.github/workflows/ci.yml`, checks
`test` and `windows-governance`. Twenty of them do not have that workflow at
all, so the declared single source of truth for check names is false almost
everywhere, and `GOV-SYNC-001` blocks adoption until it is corrected by hand.

The truth is already in the repository: the job names its pull-request
workflows publish. This derives the declaration from them.

Read-only unless --write is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "new-project.required-checks/v1"
JOB_LINE = re.compile(r"^  ([A-Za-z0-9][A-Za-z0-9_-]*):\s*(?:#.*)?$")
JOB_NAME_LINE = re.compile(r"^    name:\s*(.+?)\s*$")
TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")
REUSABLE_CALL = re.compile(r"^    (?:uses:|['\"]uses['\"]:)")
IMMUTABLE_CALL = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml@[0-9a-f]{40}")
CONTRACT_PATH = Path('.github/reusable-workflows.lock.json')
CONTRACT_SCHEMA = 'new-project.reusable-workflows/v1'
DECLARATION_CANDIDATES = (
    Path(".governance/required-checks.json"),
    Path("governance/required-checks.json"),
)
IGNORED_FIELD = "circularGovernanceChecksIgnoredByValidator"
HUB_REPOSITORY = "wellmanifest/new-project"


def scalar(raw: str) -> str:
    value = raw.strip()
    if value.startswith('"'):
        try:
            decoded, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as exc:
            raise SystemExit('unsupported double-quoted workflow scalar') from exc
        if value[end:].strip() and not value[end:].lstrip().startswith('#'):
            raise SystemExit('invalid trailing workflow scalar content')
        return decoded
    if value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
        if match is None:
            raise SystemExit('unsupported single-quoted workflow scalar')
        return match.group(1).replace("''", "'")
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SystemExit(f'duplicate reusable workflow contract key: {key}')
        result[key] = value
    return result


def contained_source(root: Path, relative: str) -> Path:
    path = Path(relative)
    if (path.is_absolute() or '..' in path.parts or '\\' in relative
            or not re.fullmatch(r'\.github/reusable-workflows/[A-Za-z0-9_.-]+\.ya?ml', relative)
            or path.as_posix() != relative):
        raise SystemExit('unsafe reusable workflow source path')
    candidate = root
    for part in path.parts:
        candidate /= part
        if candidate.is_symlink():
            raise SystemExit('symlinked reusable workflow source')
    if not candidate.is_file():
        raise SystemExit('missing reusable workflow source')
    return candidate


def reusable_sources(root: Path) -> dict[str, str]:
    """Read reviewed source bindings; this never fetches or executes workflows.

    The SHA binds the callee reference and the digest binds its reviewed bytes.
    Neither the lock nor these bytes are independent publication approval.
    """
    path = root / CONTRACT_PATH
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or (root / '.github').is_symlink():
        raise SystemExit('symlinked reusable workflow contract')
    try:
        document = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f'invalid reusable workflow contract: {exc}') from exc
    if (not isinstance(document, dict) or set(document) != {'schema', 'workflows'}
            or document['schema'] != CONTRACT_SCHEMA
            or not isinstance(document['workflows'], list) or not document['workflows']):
        raise SystemExit('invalid reusable workflow contract shape')
    sources = {}
    for item in document['workflows']:
        if not isinstance(item, dict) or set(item) != {'uses', 'sourceFile', 'sourceSha256'}:
            raise SystemExit('invalid reusable workflow source binding')
        ref, relative, digest = item['uses'], item['sourceFile'], item['sourceSha256']
        if not isinstance(ref, str) or not IMMUTABLE_CALL.fullmatch(ref):
            raise SystemExit('reusable workflow must use a full immutable commit SHA')
        if ref in sources:
            raise SystemExit('duplicate reusable workflow reference')
        if not isinstance(relative, str) or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise SystemExit('invalid reusable workflow source digest or path')
        source = contained_source(root, relative).read_bytes()
        if hashlib.sha256(source).hexdigest() != digest:
            raise SystemExit('reusable workflow source digest mismatch')
        try:
            sources[ref] = source.decode('utf-8')
        except UnicodeError as exc:
            raise SystemExit('reusable workflow source must be UTF-8') from exc
    return sources


def literal_jobs(text: str) -> list[tuple[str, str]]:
    """Only literal block-mapping job declarations have an offline contract."""
    jobs = []
    current = None
    body = []
    in_jobs = False
    top_keys = set()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '\t' in line[:len(line) - len(line.lstrip())]:
            raise SystemExit('unsupported reusable workflow indentation')
        if not line.startswith(' '):
            if not TOP_LEVEL_KEY.match(line):
                raise SystemExit('unsupported reusable workflow top-level mapping')
            key = line.split(':', 1)[0]
            if key in top_keys:
                raise SystemExit('duplicate reusable workflow top-level key')
            top_keys.add(key)
        if TOP_LEVEL_KEY.match(line):
            if current is not None:
                jobs.append((current, '\n'.join(body)))
            current, body = None, []
            in_jobs = bool(re.fullmatch(r'jobs:\s*(?:#.*)?', line))
            continue
        if not in_jobs or not line.strip() or line.lstrip().startswith('#'):
            continue
        match = JOB_LINE.match(line)
        if match:
            if current is not None:
                jobs.append((current, '\n'.join(body)))
            current, body = match.group(1), []
        elif line.startswith('  ') and not line.startswith('    '):
            raise SystemExit('unsupported reusable workflow job mapping')
        elif current is not None:
            if line.startswith('    ') and not line.startswith('     '):
                if not re.match(r'^    [A-Za-z_][A-Za-z0-9_-]*:', line):
                    raise SystemExit('unsupported reusable workflow job fields')
            body.append(line)
        else:
            raise SystemExit('unsupported reusable workflow jobs')
    if current is not None:
        jobs.append((current, '\n'.join(body)))
    if not jobs or len({key for key, _ in jobs}) != len(jobs):
        raise SystemExit('missing or duplicate reusable workflow jobs')
    return jobs


def literal_name(key: str, body: str) -> str:
    names = [scalar(m.group(1)) for line in body.splitlines() if (m := JOB_NAME_LINE.match(line))]
    name = names[0] if names else key
    if len(names) > 1 or not name or '${{' in name or name.startswith(('*', '&', '|', '>')):
        raise SystemExit('unsupported reusable workflow job name')
    return name


def callee_names(text: str) -> list[str]:
    active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
    if not re.search(r'^on:\s*(?:workflow_call\s*(?:#.*)?$|\n\s+workflow_call:)', active, re.M):
        raise SystemExit('source is not a reusable workflow_call workflow')
    names = []
    for key, body in literal_jobs(text):
        fields = [line.split(':', 1)[0].strip() for line in body.splitlines()
                  if re.match(r'^    [A-Za-z_][A-Za-z0-9_-]*:', line)]
        if len(fields) != len(set(fields)):
            raise SystemExit('duplicate reusable workflow job field')
        if re.search(r'^    (?:uses|strategy|if):', body, re.M):
            raise SystemExit('nested, matrix or conditional reusable jobs are unsupported')
        names.append(literal_name(key, body))
    if len(names) != len(set(names)):
        raise SystemExit('duplicate reusable workflow check names')
    return names


def resolved_checks_text(text: str, sources: dict[str, str], callers: list[str]) -> list[str]:
    if not pull_request_gating(text):
        return []
    unresolved = []
    names = published_checks_text(text, unresolved)
    active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
    if (not unresolved and re.search(
            r'^  [A-Za-z0-9][A-Za-z0-9_-]*:\s*\{.*\buses\b', active, re.M)):
        raise SystemExit('unsupported reusable workflow caller mapping')
    if not unresolved:
        return names
    for key, body in literal_jobs(text):
        calls = [scalar(line.split('uses:', 1)[1]) for line in body.splitlines()
                 if REUSABLE_CALL.match(line)]
        if not calls:
            continue
        name = literal_name(key, body)
        if len(calls) != 1:
            raise SystemExit('duplicate reusable workflow uses')
        source = sources.get(calls[0])
        if source is None:
            callers.append(name)
            continue
        if re.search(r'^    (?:strategy|if):', body, re.M):
            raise SystemExit('matrix or conditional reusable callers are unsupported')
        names.extend(f'{name} / {leaf}' for leaf in callee_names(source))
    if len(names) != len(set(names)):
        raise SystemExit('duplicate published reusable check names')
    return names


def pull_request_gating(text: str) -> bool:
    """Keep after-merge-only callers out of pre-merge declarations."""
    if "pull_request" not in text:
        return False  # A workflow that never runs on a PR cannot gate one.
    # A pull_request trigger with exclusively the 'closed' type publishes
    # checks that run after the merge decision, never before.  They cannot
    # gate a pull request and must not inflate the required-checks declaration.
    has_closed_type = bool(re.search(r"\btypes:\s*\[\s*closed\s*\]", text)) or bool(
        re.search(r"\btypes:\s*\n\s*-\s*closed\b", text)
    )
    has_gating_types = bool(
        re.search(r"\btypes:\s*\[.*\b(?:opened|synchronize|reopened|ready_for_review)\b", text)
    ) or bool(
        re.search(r"\btypes:\s*\n(?:\s*-[^\n]*\n)*\s*-\s*(?:opened|synchronize|reopened|ready_for_review)\b", text)
    )
    return not (has_closed_type and not has_gating_types)


def published_checks_text(text: str, callers: list[str]) -> list[str]:
    """Direct display names and unresolved reusable caller display names."""
    if not pull_request_gating(text):
        return []
    names: list[str] = []
    current: str | None = None
    calls_reusable = False
    in_jobs = False

    def flush() -> None:
        if current is None:
            return
        (callers if calls_reusable else names).append(current)

    for line in text.splitlines():
        if TOP_LEVEL_KEY.match(line):
            # Only the jobs mapping publishes check contexts; on:, env: and the
            # rest use the same two-space indentation for their own keys.
            flush()
            current, calls_reusable = None, False
            in_jobs = line.startswith("jobs:")
            continue
        if not in_jobs:
            continue
        job = JOB_LINE.match(line)
        if job:
            flush()
            current, calls_reusable = job.group(1), False
            continue
        if current is None:
            continue
        display = JOB_NAME_LINE.match(line)
        if display:
            current = scalar(display.group(1))
            continue
        if REUSABLE_CALL.match(line):
            calls_reusable = True
    flush()
    return names


def published_checks(workflow: Path, callers: list[str]) -> list[str]:
    return published_checks_text(workflow.read_text(encoding="utf-8"), callers)


def repository_name(root: Path) -> str | None:
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=False, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def declaration_for(
    root: Path,
    ignored: tuple[str, ...] = (),
    workflow_payloads: dict[str, bytes] | None = None,
) -> dict[str, Any] | None:
    repository = repository_name(root)
    if repository is None:
        return None
    directory = root / ".github/workflows"
    overlays = workflow_payloads or {}
    workflows: dict[str, tuple[Path, bytes | None]] = {}
    if directory.is_dir():
        for workflow in sorted(directory.glob("*.y*ml")):
            relative = workflow.relative_to(root).as_posix()
            workflows[relative] = (workflow, None)
    for relative, content in overlays.items():
        if not relative.startswith(".github/workflows/") or not relative.endswith((".yml", ".yaml")):
            continue
        workflows[relative] = (root / relative, content)
    if not workflows:
        return None
    checks: list[dict[str, str]] = []
    callers: list[str] = []
    sources = reusable_sources(root)
    for relative, (workflow, content) in sorted(workflows.items()):
        text = content.decode('utf-8') if content is not None else workflow.read_text(encoding='utf-8')
        names = resolved_checks_text(text, sources, callers)
        for name in names:
            checks.append({"name": name, "workflowFile": relative})
    if not checks and not callers:
        return None
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "version": 1,
        "repository": repository,
        "requiredChecks": checks,
    }
    if callers:
        document["reusableWorkflowCallers"] = sorted(set(callers))
    return document


def declaration_path(root: Path) -> Path:
    """The hub keeps its instance in governance/, adopters in .governance/."""
    for candidate in DECLARATION_CANDIDATES:
        if (root / candidate).is_file():
            return root / candidate
    return root / DECLARATION_CANDIDATES[0]


def current_declaration(root: Path) -> dict[str, Any] | None:
    path = declaration_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def declared_names(document: dict[str, Any] | None) -> list[str]:
    if not document:
        return []
    names = document.get("requiredCheckNames")
    if names is None:
        names = [item.get("name") for item in document.get("requiredChecks", [])]
    return sorted(str(name) for name in names or [])


def inspect_declaration(root: Path, write: bool) -> dict[str, Any]:
    current = current_declaration(root)
    inherited_hub_declaration = (current or {}).get("repository") == HUB_REPOSITORY
    ignored = () if inherited_hub_declaration else tuple((current or {}).get(IGNORED_FIELD, ()) or ())
    derived = declaration_for(root)
    if derived is not None and ignored:
        derived[IGNORED_FIELD] = list(ignored)
    entry = {
        "repository": root.name,
        "derived": derived,
        "currentRepository": (current or {}).get("repository"),
        "currentNames": declared_names(current),
        "derivedNames": declared_names(derived),
    }
    entry["agrees"] = (
        derived is not None
        and entry["currentRepository"] == derived["repository"]
        and entry["currentNames"] == entry["derivedNames"]
    )
    entry["reusableWorkflowCallers"] = (derived or {}).get("reusableWorkflowCallers", [])
    if write and derived is not None and not entry["agrees"]:
        if entry["reusableWorkflowCallers"]:
            entry["written"] = False  # A caller's context name cannot be derived here.
        else:
            declaration_path(root).write_text(
                json.dumps(derived, indent=2) + "\n", encoding="utf-8"
            )
            entry["written"] = True
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", help="Repository roots to inspect")
    parser.add_argument("--write", action="store_true", help="Rewrite each declaration in place")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv or sys.argv[1:])

    report: list[dict[str, Any]] = []
    for raw in args.roots:
        entry = inspect_declaration(Path(raw).resolve(), args.write)
        report.append(entry)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        for entry in report:
            state = "agrees" if entry["agrees"] else "DIFFERS"
            print(f"{entry['repository']:<24} {state}")
            if not entry["agrees"]:
                print(f"  declared {entry['currentRepository']} {entry['currentNames']}")
                derived_repo = (entry["derived"] or {}).get("repository")
                print(f"  derived  {derived_repo} {entry['derivedNames']}")
                if entry["reusableWorkflowCallers"]:
                    print(
                        "  callers  "
                        f"{entry['reusableWorkflowCallers']} publish "
                        "<caller> / <callee job>; confirm those names by hand"
                    )
        print(f"\n{sum(1 for e in report if e['agrees'])} of {len(report)} agree")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
