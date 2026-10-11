#!/usr/bin/env python3
"""Compare required-checks.json to jobs published by CI workflows.

Single source of truth for required check *names* is the repository instance
of required-checks.json (hub: governance/, adopter: .governance/). This gate
fails when a required name is missing from the workflow that publishes it, or
when that workflow publishes a job that is not declared.

Published names are the job ``name:`` field when present, otherwise the job
key. GitHub rulesets require the display name.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = "new-project.required-checks/v1"
JOB_LINE = re.compile(r"^  ([A-Za-z0-9][A-Za-z0-9_-]*):\s*(?:#.*)?$")
JOB_NAME_LINE = re.compile(r"^    name:\s*(.+?)\s*$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def yaml_scalar(raw: str) -> str:
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


def resolve_source(root: Path, script_path: Path) -> tuple[Path | None, list[Path]]:
    candidates: list[Path] = []
    for raw in (
        script_path.resolve().parent / "required-checks.json",
        root / "governance" / "required-checks.json",
        root / ".governance" / "required-checks.json",
    ):
        resolved = raw.resolve()
        if resolved not in candidates:
            candidates.append(resolved)
    for path in candidates:
        if path.is_file():
            return path, candidates
    return None, candidates


def bound_check_pairs(required_checks: list) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in required_checks:
        if not isinstance(item, dict):
            raise SystemExit("requiredChecks entries must be objects")
        name = item.get("name")
        workflow = item.get("workflowFile")
        if not isinstance(name, str) or not name.strip():
            raise SystemExit("requiredChecks.name missing or empty")
        if not isinstance(workflow, str) or not workflow.strip():
            raise SystemExit("requiredChecks.workflowFile missing or empty")
        pairs.append((name, workflow))
    return pairs


def declared_checks(data: dict) -> list[tuple[str, str]]:
    has_legacy = "workflowFile" in data or "requiredCheckNames" in data
    has_bound = "requiredChecks" in data
    if has_legacy and has_bound:
        raise SystemExit(
            "required-checks must declare exactly one shape: "
            "workflowFile+requiredCheckNames or requiredChecks"
        )
    required_checks = data.get("requiredChecks")
    if isinstance(required_checks, list) and required_checks:
        return bound_check_pairs(required_checks)
    names = data.get("requiredCheckNames")
    workflow = data.get("workflowFile")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
        raise SystemExit("requiredCheckNames missing or empty")
    if not isinstance(workflow, str) or not workflow.strip():
        raise SystemExit("workflowFile missing")
    return [(name, workflow) for name in names]


def load_source(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SystemExit(f"unsupported required-checks schema in {path}")
    declared_checks(data)
    return data


def workflow_job_names(workflow_path: Path, root: Path | None = None) -> list[str]:
    text = workflow_path.read_text(encoding="utf-8")
    active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
    if re.search(r'^    (?:uses:|[\'\"]uses[\'\"]:)|^  [A-Za-z0-9][A-Za-z0-9_-]*:\s*\{.*\buses\b', active, re.M):
        # Both scripts are managed package members. Direct-job-only fixtures
        # keep their standalone checker behavior without requiring this import.
        import importlib.util
        generator_path = Path(__file__).resolve().with_name('generate_required_checks.py')
        spec = importlib.util.spec_from_file_location('required_checks_resolver', generator_path)
        if spec is None or spec.loader is None:
            raise SystemExit('managed reusable workflow resolver is missing')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        callers: list[str] = []
        names = generator.resolved_checks_text(
            text, generator.reusable_sources(root or workflow_path.parents[2]), callers)
        if callers:
            raise SystemExit('unresolved reusable workflow callers: ' + ', '.join(callers))
        return names
    lines = text.splitlines()
    in_jobs = False
    jobs: list[str] = []
    current_key: str | None = None
    current_name: str | None = None

    def flush() -> None:
        nonlocal current_key, current_name
        if current_key is None:
            return
        jobs.append(current_name or current_key)
        current_key = None
        current_name = None

    for line in lines:
        if re.match(r"^jobs:\s*(?:#.*)?$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" ") and not line.startswith("\t") and line.strip() and not line.lstrip().startswith("#"):
            break
        match = JOB_LINE.match(line)
        if match:
            flush()
            current_key = match.group(1)
            continue
        name_match = JOB_NAME_LINE.match(line)
        if name_match and current_key is not None and current_name is None:
            current_name = yaml_scalar(name_match.group(1))
    flush()
    if not jobs:
        raise SystemExit(f"no jobs parsed from {workflow_path}")
    return jobs


def compare(required: list[str], published: list[str]) -> list[str]:
    errors: list[str] = []
    req_set = set(required)
    pub_set = set(published)
    for name in required:
        if name not in pub_set:
            errors.append(
                f"required check {name!r} is missing from workflow jobs "
                f"(published={sorted(pub_set)})"
            )
    for name in published:
        if name not in req_set:
            errors.append(
                f"workflow job {name!r} is not listed in requiredCheckNames "
                f"(required={required})"
            )
    if len(required) != len(set(required)):
        errors.append(f"requiredCheckNames contains duplicates: {required}")
    if len(published) != len(set(published)):
        errors.append(f"workflow jobs contain duplicates: {published}")
    return errors


UNRESOLVED_ADOPTER = "unresolved/adopter"
REMOTE_IDENTITY = re.compile(
    r"(?:git@|https://|ssh://git@)(?:[^/:]+)[/:]([^/]+)/(.+?)(?:\.git)?/?$"
)


def own_identity(root: Path) -> str | None:
    """Resolve owner/name for this checkout from Git, then from CI.

    The origin remote is what every other participant addresses this
    repository by, so it outranks the directory name, which is a local
    convenience. GITHUB_REPOSITORY is the fallback for a CI checkout whose
    remote was not configured.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        match = REMOTE_IDENTITY.match(completed.stdout.strip())
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    # GITHUB_REPOSITORY names the checkout the workflow runs on, so it answers
    # for that checkout and nothing else. Pointing the gate at a fixture or a
    # second repository must not inherit the workflow's identity and report a
    # mismatch that does not exist.
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace and Path(workspace).resolve() == root.resolve():
        return os.environ.get("GITHUB_REPOSITORY") or None
    return None


def check_instance_identity(root: Path, data: dict, source_path: Path) -> list[str]:
    """Refuse an instance that describes a different repository.

    required-checks.json is per-repository instance data seeded from a
    template. A seed kept verbatim names the repository it came from, so its
    check names are that repository's job names and can never turn green here.
    Measured on 2026-09-09 across 88 governed checkouts: 30 declared another
    repository and 22 required a check no local workflow publishes.

    Silence here is not neutral. The declared names are what a branch ruleset
    enforces, so an unadapted instance blocks every pull request in the
    repository while looking configured.
    """
    declared = data.get("repository")
    if not isinstance(declared, str) or not declared:
        return []
    if declared == UNRESOLVED_ADOPTER:
        return [
            f"{source_path} still carries the unadapted template identity "
            f"{UNRESOLVED_ADOPTER!r}; set repository, workflowFile and the check "
            "names this repository's own workflows publish"
        ]
    own = own_identity(root)
    if own is None or declared.casefold() == own.casefold():
        return []
    return [
        f"{source_path} declares repository {declared!r} but this checkout is "
        f"{own!r}; the instance was seeded and never adapted, so its check names "
        "are another repository's job names"
    ]


def source_for_check(root: Path, source_override: Path | None) -> Path | None:
    looked: list[Path] = []
    if source_override is not None:
        source_path = source_override
        if not source_path.is_file():
            print(
                "required-checks gate FAILED: source file not found. looked in:\n"
                f"  - {source_path}",
                file=sys.stderr,
            )
            return None
    else:
        source_path, looked = resolve_source(root, Path(__file__))
        if source_path is None:
            print(
                "required-checks gate FAILED: source file not found. looked in:",
                file=sys.stderr,
            )
            for path in looked:
                print(f"  - {path}", file=sys.stderr)
            return None
    return source_path


def print_check_success(root, source_path, required_names, published_names) -> None:
    try:
        source_label = source_path.relative_to(root)
    except ValueError:
        source_label = source_path
    print(
        "required-checks gate OK: "
        f"source={source_label} "
        f"required={required_names} published={published_names}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: parent of this script)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="override path to required-checks.json",
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=None,
        help="override path to a single workflow YAML",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else repo_root()
    source_path = source_for_check(root, args.source)
    if source_path is None:
        return 2
    data = load_source(source_path)
    identity_errors = check_instance_identity(root, data, source_path)
    if identity_errors:
        print("required-checks gate FAILED:", file=sys.stderr)
        for message in identity_errors:
            print(f"  - {message}", file=sys.stderr)
        return 1
    pairs = declared_checks(data)
    if args.workflow is not None:
        workflow_path = args.workflow
        if not workflow_path.is_file():
            print(f"workflow file not found: {workflow_path}", file=sys.stderr)
            return 2
        required = [name for name, _workflow in pairs]
        published = workflow_job_names(workflow_path, root)
        errors = compare(required, published)
        published_names = published
    else:
        by_workflow: dict[str, list[str]] = defaultdict(list)
        for name, workflow in pairs:
            by_workflow[workflow].append(name)
        errors = []
        published_names: list[str] = []
        for workflow, required in by_workflow.items():
            workflow_path = root / workflow
            if not workflow_path.is_file():
                print(f"workflow file not found: {workflow_path}", file=sys.stderr)
                return 2
            published = workflow_job_names(workflow_path, root)
            published_names.extend(published)
            errors.extend(compare(required, published))
    if errors:
        print("required-checks gate FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    required_names = [name for name, _workflow in pairs]
    if __name__ == "__main__":
        print_check_success(root, source_path, required_names, published_names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
