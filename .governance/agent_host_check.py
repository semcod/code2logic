#!/usr/bin/env python3
"""Prove that the host-agnostic agent contract is installed, not just documented.

Instruction files are advisory: any model may ignore them. This validator checks
the parts that execute anyway — the fail-closed git hook, and the packaging
lifecycle hooks that `npm install` and `pytest` run without asking the agent.

Hub reads `governance/agent-hosts.json`; adopters read `.governance/agent-hosts.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on 3.10 runners
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        # An adopter may declare requires-python >=3.10, where neither reader
        # exists. Import must still succeed: governance_check.py reports an
        # ImportError here as a missing managed validator, which turns an
        # interpreter gap into a false sync defect.
        tomllib = None  # type: ignore[assignment]

SCHEMA = "new-project.agent-hosts/v1"
CONTRACT_CANDIDATES = ("governance/agent-hosts.json", ".governance/agent-hosts.json")
LOCK_CANDIDATES = ("governance/manifest.lock.json", ".governance/manifest.lock.json")
SOURCE_LINK_MARKER = "<!-- wellmanifest:source-links:v1 -->"


@dataclass(order=True)
class Finding:
    code: str
    message: str
    remediation: str
    paths: list[str] = field(default_factory=list)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first_existing(root: Path, candidates: tuple[str, ...]) -> Path | None:
    for candidate in candidates:
        path = root / candidate
        if path.is_file():
            return path
    return None


def git_config(root: Path, key: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--get", key],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_work_tree(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def check_hosts(root: Path, contract: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for host in contract["hosts"]:
        relative = str(host["file"])
        if not (root / relative).is_file():
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host instruction file for '{host['id']}' is missing: {relative}",
                "Bootstrap with ./scripts/install-agent-hosts.sh --source <hub> --target <repo>, or adopt the current standard package.",
                [relative],
            ))
    return findings


LOCAL_SOURCE_SETS = {
    "governance/agent-hosts.json": {
        "hub-manifest": "governance/manifest.hub.json",
        "hub-package": "governance/package-manifest.json",
    },
    ".governance/agent-hosts.json": {
        "adopter-manifest": ".governance/manifest.json",
        "adopter-lock": ".governance/manifest.lock.json",
        "adopter-package": ".governance/package-manifest.json",
    },
}


def _local_source_paths(
    root: Path, local: Any, contract_path: str | None,
) -> tuple[list[str], list[Finding]]:
    """Check the selected layout; missing files must never select a weaker one."""
    def fail(message: str, paths: list[str]) -> tuple[list[str], list[Finding]]:
        return [], [Finding(
            "GOV-AGENT-HOST-004", message,
            "Restore the complete local source contract through pinned standard adoption.", paths,
        )]

    selected = first_existing(root, CONTRACT_CANDIDATES) if contract_path is None else Path(contract_path)
    if selected is not None and contract_path is not None and not selected.is_absolute():
        selected = root / selected
    try:
        layout = selected.relative_to(root).as_posix() if selected is not None else ""
    except ValueError:
        layout = ""
    expected = LOCAL_SOURCE_SETS.get(layout)
    if expected is None:
        return fail("Local sources require a canonical hub or adopter host-contract location.", ["sourceLinks"])
    if not isinstance(local, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str)
        or not item["id"] or not isinstance(item.get("path"), str) or not item["path"]
        for item in local
    ):
        return fail("Agent host local source declaration is malformed.", ["sourceLinks"])
    by_id = {item["id"]: item["path"] for item in local}
    if len(by_id) != len(local):
        return fail("Agent host local source declaration contains duplicate ids.", ["sourceLinks"])
    missing = [path for identifier, path in expected.items() if by_id.get(identifier) != path]
    if missing:
        return fail("Agent host local source declaration omits or changes required layout sources.", missing)
    inactive = {identifier for candidate, group in LOCAL_SOURCE_SETS.items() if candidate != layout for identifier in group}
    paths = [item["path"] for item in local if item["id"] not in inactive]
    unsafe = [path for path in paths if not safe_declared_gate(root, path)]
    if unsafe:
        return fail("Declared local sources are missing, unsafe or not regular checkout files.", unsafe)
    return paths, []


def check_source_links(root: Path, contract: dict[str, Any], *, contract_path: str | None = None) -> list[Finding]:
    """Require every managed host projection to expose its bounded sources.

    The local files prove which package is adopted. Remote links are deliberately
    navigation-only and point to concrete files on the current standard branch;
    no validator fetches them and they never replace the local lock/digests.
    """
    findings: list[Finding] = []
    source_links = contract.get("sourceLinks")
    if not isinstance(source_links, dict):
        return [Finding(
            "GOV-AGENT-HOST-004",
            "Agent host contract has no source-links declaration.",
            "Adopt the current standard package with its managed source-links contract.",
            ["sourceLinks"],
        )]

    local = source_links.get("local", [])
    remote = source_links.get("remote", [])
    remote_ids = [
        item.get("id") for item in remote
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    duplicate_ids = sorted({identifier for identifier in remote_ids if remote_ids.count(identifier) > 1})
    if duplicate_ids:
        return [Finding(
            "GOV-AGENT-HOST-004",
            "Agent host source-links declaration contains duplicate remote ids: "
            + ", ".join(duplicate_ids),
            "Restore unique remote source identifiers in the managed host contract.",
            ["sourceLinks"],
        )]
    by_id = {
        item.get("id"): item for item in remote
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    required_every = source_links.get("requiredInEveryHost", [])
    required_agents = source_links.get("requiredInAgents", [])
    required_ids = set(required_every) | set(required_agents)
    missing_ids = sorted(identifier for identifier in required_ids if identifier not in by_id)
    if missing_ids:
        findings.append(Finding(
            "GOV-AGENT-HOST-004",
            "Agent host source-links declaration references unknown remote ids: "
            + ", ".join(missing_ids),
            "Restore the managed source-links contract from the standard package.",
            ["sourceLinks"],
        ))
        return findings

    malformed_urls = []
    for identifier, item in by_id.items():
        repository = item.get("repository")
        path = item.get("path")
        url = item.get("url")
        expected = f"https://github.com/{repository}/blob/main/{path}"
        if not isinstance(url, str) or url != expected:
            malformed_urls.append(identifier)
    if malformed_urls:
        findings.append(Finding(
            "GOV-AGENT-HOST-004",
            "Agent host source-links declaration contains non-canonical URLs: "
            + ", ".join(sorted(malformed_urls)),
            "Use the concrete main-branch URL derived from each declared repository and path.",
            ["sourceLinks"],
        ))
        return findings

    local_paths, local_findings = _local_source_paths(root, local, contract_path)
    if local_findings:
        return findings + local_findings

    for host in contract["hosts"]:
        relative = str(host["file"])
        path = root / relative
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host source links are unreadable in {relative}: {error}",
                "Restore the managed host projection through standard adoption.",
                [relative],
            ))
            continue
        if SOURCE_LINK_MARKER not in content:
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host instruction file has no managed source-links marker: {relative}",
                "Regenerate managed host instructions from the pinned standard package.",
                [relative],
            ))
        for local_path in local_paths:
            if local_path not in content:
                findings.append(Finding(
                    "GOV-AGENT-HOST-004",
                    f"Host instruction file omits local source link {local_path}: {relative}",
                    "Regenerate managed host instructions from the pinned standard package.",
                    [relative, local_path],
                ))
        remote_ids = required_agents if relative == "AGENTS.md" else required_every
        for identifier in remote_ids:
            url = by_id[identifier].get("url")
            if not isinstance(url, str) or url not in content:
                findings.append(Finding(
                    "GOV-AGENT-HOST-004",
                    f"Host instruction file omits remote source link {identifier}: {relative}",
                    "Regenerate managed host instructions from the pinned standard package.",
                    [relative, identifier],
                ))
    return findings


def check_hook(root: Path, contract: dict[str, Any], actor: str) -> list[Finding]:
    findings: list[Finding] = []
    hook_relative = str(contract["hook"]["path"])
    hook_path = root / hook_relative
    if not hook_path.is_file():
        findings.append(Finding(
            "GOV-AGENT-HOST-005",
            f"Fail-closed pre-commit hook is missing: {hook_relative}",
            "Bootstrap with ./scripts/install-agent-hosts.sh --source <hub> --target <repo>, or adopt the current standard package.",
            [hook_relative],
        ))
    elif os.name != "nt" and not hook_path.stat().st_mode & 0o111:
        findings.append(Finding(
            "GOV-AGENT-HOST-005",
            f"Fail-closed pre-commit hook is not executable: {hook_relative}",
            f"Restore the executable bit with chmod +x {hook_relative}.",
            [hook_relative],
        ))

    additional = contract["hook"].get("additionalHooks", [])
    if (not isinstance(additional, list)
            or any(not isinstance(path, str) or path not in {
                ".githooks/commit-msg", ".githooks/prepare-commit-msg",
            } for path in additional)
            or len(additional) != len(set(additional))):
        findings.append(Finding(
            "GOV-AGENT-HOST-004", "Invalid additional hook declaration.",
            "Restore the pinned host contract.", ["hook.additionalHooks"],
        ))
        return findings
    for relative in additional:
        path = root / relative
        if not path.is_file() or (os.name != "nt" and not path.stat().st_mode & 0o111):
            findings.append(Finding(
                "GOV-AGENT-HOST-005",
                f"Managed additional hook is missing or not executable: {relative}",
                "Adopt the complete pinned package and run scripts/install-agent-hosts.sh.",
                [relative],
            ))

    # A CI checkout never runs local hooks; only a developer or agent clone can.
    if actor == "ci" or not is_work_tree(root):
        return findings
    expected = str(contract["hook"]["hooksPathConfig"])
    configured = git_config(root, "core.hooksPath")
    if configured != expected:
        findings.append(Finding(
            "GOV-AGENT-HOST-006",
            f"core.hooksPath is {configured or 'unset'}; the managed hook is not active.",
            f"Activate the managed hook: git config core.hooksPath {expected} in this clone.",
            [hook_relative],
        ))
    return findings


def adopted_standard(root: Path) -> dict[str, Any]:
    lock_path = first_existing(root, LOCK_CANDIDATES)
    if lock_path is None:
        return {}
    try:
        lock = load_json(lock_path)
    except (OSError, json.JSONDecodeError):
        return {}
    standard = lock.get("standard")
    return standard if isinstance(standard, dict) else {}


def python_declaration(marker: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if tomllib is None:
        return None, {}
    try:
        document = tomllib.loads(marker.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None, {}
    declaration = document.get("tool", {}).get("wellmanifest")
    return (declaration if isinstance(declaration, dict) else None), document


def node_declaration(marker: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        document = load_json(marker)
    except (OSError, json.JSONDecodeError):
        return None, {}
    if not isinstance(document, dict):
        return None, {}
    declaration = document.get("wellmanifest")
    return (declaration if isinstance(declaration, dict) else None), document


def lifecycle_value(kind: str, document: dict[str, Any]) -> str:
    if kind == "npm-script":
        scripts = document.get("scripts")
        value = scripts.get("prepare") if isinstance(scripts, dict) else None
    else:
        options = document.get("tool", {}).get("pytest", {}).get("ini_options", {})
        value = options.get("addopts") if isinstance(options, dict) else None
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return value if isinstance(value, str) else ""


def check_packaging(root: Path, contract: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    standard = adopted_standard(root)
    for ecosystem, binding in sorted(contract["packaging"].items()):
        marker_relative = str(binding["marker"])
        marker = root / marker_relative
        if not marker.is_file():
            continue  # The ecosystem is not present in this repository.
        if ecosystem == "python" and tomllib is None:
            continue  # No TOML reader on this interpreter; 3.11+ jobs enforce it.
        reader = python_declaration if ecosystem == "python" else node_declaration
        declaration, document = reader(marker)
        if declaration is None:
            findings.append(Finding(
                "GOV-PACKAGING-001",
                f"{marker_relative} declares no '{binding['declaration']}' governance block.",
                "Declare the adopted standard version, revision and gate in the package metadata.",
                [marker_relative],
            ))
        else:
            findings.extend(check_declaration(root, marker_relative, declaration, standard))

        lifecycle = binding["lifecycle"]
        if lifecycle["mustContain"] not in lifecycle_value(str(lifecycle["kind"]), document):
            findings.append(Finding(
                "GOV-PACKAGING-003",
                f"{marker_relative} {lifecycle['field']} does not run '{lifecycle['mustContain']}'.",
                "Bind the governance gate to the packaging lifecycle so the tooling runs it unprompted.",
                [marker_relative],
            ))
    return findings


def safe_declared_gate(root: Path, relative: str) -> bool:
    """Observe an existing repository-relative regular file without link escapes.

    This is a path/declaration check, not permission to execute the gate.
    """
    if re.fullmatch('^(?!.*(?:^|/)\\.\\.(?:/|$))[^/\\\\:\\x00-\\x1f\\x7f]+(?:/[^/\\\\:\\x00-\\x1f\\x7f]+)*$', relative) is None:
        return False
    try:
        base = root.resolve(strict=True)
        path = base
        for part in relative.split("/"):
            path = path / part
            if path.is_symlink():
                return False
        resolved = path.resolve(strict=True)
        resolved.relative_to(base)
        return resolved.is_file()
    except (OSError, ValueError):
        return False


def check_declaration(
    root: Path,
    marker_relative: str,
    declaration: dict[str, Any],
    standard: dict[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []
    for key in ("standard", "revision", "gate"):
        if not isinstance(declaration.get(key), str) or not declaration[key].strip():
            findings.append(Finding(
                "GOV-PACKAGING-001",
                f"{marker_relative} governance block is missing the '{key}' field.",
                "Declare the adopted standard version, revision and gate in the package metadata.",
                [marker_relative],
            ))
    gate = declaration.get("gate")
    if isinstance(gate, str) and gate.strip() and not safe_declared_gate(root, gate):
        findings.append(Finding(
            "GOV-PACKAGING-002",
            f"{marker_relative} declares gate '{gate}', which is missing or unsafe.",
            "Point the declaration at an existing repository-relative regular governance gate without parent traversal, drive paths or symbolic links.",
            [marker_relative, gate],
        ))
    if not standard:
        return findings
    for key, locked in (("standard", "version"), ("revision", "sourceRevision")):
        expected = standard.get(locked)
        actual = declaration.get(key)
        if isinstance(expected, str) and isinstance(actual, str) and actual != expected:
            findings.append(Finding(
                "GOV-PACKAGING-002",
                f"{marker_relative} declares {key} '{actual}' but the adoption lock pins '{expected}'.",
                "Regenerate the package declaration from .governance/manifest.lock.json.",
                [marker_relative],
            ))
    return findings


def workflow_job_names(path: Path) -> list[str]:
    """Use the adjacent managed validator for the offline workflow contract.

    Load by the package path, never by a target-controlled import search path.
    This shares direct-job names and digest-bound reusable callee resolution.
    Missing or unsupported contracts remain refusals, not guessed check names.
    """
    import importlib.util

    checker_path = Path(__file__).resolve().with_name("check_required_checks.py")
    spec = importlib.util.spec_from_file_location("agent_host_required_checks", checker_path)
    if spec is None or spec.loader is None:
        raise ImportError("managed required-checks validator is missing")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker.workflow_job_names(path)


def check_guidance_anomalies(root: Path, contract: dict[str, Any]) -> list[Finding]:
    """Catch bounded-session and impossible-CI hazards before model work begins.

    This is intentionally static and offline. It does not fetch remote links,
    infer intent from prose, or retry a failed command. A finding is a stop
    signal with a concrete path, not an invitation to keep experimenting.
    """
    config = contract.get("anomalyChecks")
    if not isinstance(config, dict):
        return [Finding(
            "GOV-AGENT-HOST-004",
            "Agent host contract has no deterministic anomaly-check declaration.",
            "Adopt the current standard package with its bounded-session audit contract.",
            ["anomalyChecks"],
        )]

    findings: list[Finding] = []
    max_bytes = config.get("maxInstructionBytes")
    required_terms = config.get("requiredTerms", [])
    contradictions = config.get("contradictions", [])
    if not isinstance(max_bytes, int) or max_bytes < 1:
        return [Finding(
            "GOV-AGENT-HOST-004",
            "Agent host anomaly contract has an invalid instruction-size limit.",
            "Declare a positive maxInstructionBytes value in the managed contract.",
            ["anomalyChecks"],
        )]

    for host in contract["hosts"]:
        relative = str(host["file"])
        path = root / relative
        if not path.is_file():
            continue  # check_hosts emits the more direct missing-file finding.
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host guidance cannot be audited in {relative}: {error}",
                "Restore the managed host projection from the pinned package.",
                [relative],
            ))
            continue
        size = len(content.encode("utf-8"))
        if size > max_bytes:
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host guidance exceeds the bounded instruction size ({size} > {max_bytes} bytes): {relative}",
                "Split or shorten the managed guidance before the host truncates its instruction chain.",
                [relative],
            ))
        folded = content.casefold()
        missing = [
            str(term) for term in required_terms
            if isinstance(term, str) and term.casefold() not in folded
        ]
        if missing:
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"Host guidance lacks bounded-session controls {', '.join(missing)}: {relative}",
                "Restore checkpoint, handoff and stop conditions so a blocked session cannot retry indefinitely.",
                [relative],
            ))
        for rule in contradictions:
            if not isinstance(rule, dict):
                continue
            patterns = rule.get("patterns")
            if not isinstance(patterns, list) or len(patterns) < 2:
                continue
            present = [str(pattern) for pattern in patterns
                       if isinstance(pattern, str) and pattern.casefold() in folded]
            if len(present) == len(patterns):
                identifier = str(rule.get("id", "unnamed"))
                findings.append(Finding(
                    "GOV-AGENT-HOST-004",
                    f"Host guidance contains contradictory directives ({identifier}): {relative}",
                    "Remove one directive or split the rules by an explicit, machine-checkable scope.",
                    [relative],
                ))

    ci = config.get("ci")
    if not isinstance(ci, dict):
        return findings
    candidates = ci.get("requiredChecksCandidates", [])
    checks_path = next(
        (root / str(candidate) for candidate in candidates
         if isinstance(candidate, str) and (root / candidate).is_file()),
        None,
    )
    if checks_path is None:
        findings.append(Finding(
            "GOV-AGENT-HOST-004",
            "CI anomaly audit cannot find a required-checks declaration.",
            "Restore governance/required-checks.json or .governance/required-checks.json.",
            ["required-checks"],
        ))
        return findings
    try:
        declaration = load_json(checks_path)
    except (OSError, json.JSONDecodeError) as error:
        findings.append(Finding(
            "GOV-AGENT-HOST-004",
            f"CI required-checks declaration is unreadable: {error}",
            "Restore a valid managed required-checks declaration.",
            [str(checks_path.relative_to(root))],
        ))
        return findings
    if not isinstance(declaration, dict):
        return findings
    pairs: list[tuple[str, str]] = []
    bound = declaration.get("requiredChecks")
    if isinstance(bound, list) and bound:
        for item in bound:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("workflowFile"), str):
                pairs.append((item["name"], item["workflowFile"]))
    elif isinstance(declaration.get("requiredCheckNames"), list) and isinstance(declaration.get("workflowFile"), str):
        pairs = [(str(name), declaration["workflowFile"])
                 for name in declaration["requiredCheckNames"]
                 if isinstance(name, str)]
    if not pairs:
        findings.append(Finding(
            "GOV-AGENT-HOST-004",
            "CI required-checks declaration has no usable check/workflow pairs.",
            "Declare requiredCheckNames with workflowFile, or bound requiredChecks entries.",
            [str(checks_path.relative_to(root))],
        ))
        return findings
    for workflow in sorted({workflow for _, workflow in pairs}):
        workflow_path = root / workflow
        if not workflow_path.is_file():
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"CI required-checks declaration names a missing workflow: {workflow}",
                "Point workflowFile at a workflow present in this checkout.",
                [workflow, str(checks_path.relative_to(root))],
            ))
            continue
        try:
            published = workflow_job_names(workflow_path)
        except (OSError, UnicodeDecodeError, ImportError, ValueError, SystemExit):
            findings.append(Finding(
                "GOV-AGENT-HOST-004",
                f"CI workflow contract cannot be resolved: {workflow}.",
                "Restore the managed validator and an immutable digest-bound reusable source; run check_required_checks.py for the precise refusal.",
                [workflow, str(checks_path.relative_to(root))],
            ))
            continue
        for name, declared_workflow in pairs:
            if declared_workflow != workflow:
                continue
            if name not in published:
                findings.append(Finding(
                    "GOV-AGENT-HOST-004",
                    f"CI required check {name!r} is not published by {workflow}.",
                    "Add the job or change the declaration to a job this workflow actually publishes; do not retry a permanently impossible gate.",
                    [workflow, str(checks_path.relative_to(root))],
                ))
    return findings


def load_contract(root: Path, explicit: str | None) -> tuple[dict[str, Any] | None, Finding | None]:
    if explicit is not None:
        path = root / explicit if not Path(explicit).is_absolute() else Path(explicit)
        if not path.is_file():
            return None, Finding(
                "GOV-AGENT-HOST-004", f"Agent host contract is missing: {explicit}",
                "Adopt the current standard package or pass an existing --contract path.", [explicit],
            )
    else:
        found = first_existing(root, CONTRACT_CANDIDATES)
        if found is None:
            # The repository has not received the managed contract yet, so there
            # is nothing to verify. Deleting it later is not an escape hatch:
            # agent-hosts.json is a managed file and GOV-SYNC-001 catches its
            # removal against the adoption lock.
            return None, None
        path = found
    try:
        contract = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return None, Finding(
            "GOV-AGENT-HOST-004", f"Agent host contract is unreadable: {error}",
            "Restore the pinned host contract through a standard upgrade.", [str(path.name)],
        )
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        return None, Finding(
            "GOV-AGENT-HOST-004", f"Agent host contract must declare schema {SCHEMA}.",
            "Restore the pinned host contract through a standard upgrade.", [str(path.name)],
        )
    for key in ("hook", "hosts", "sourceLinks", "packaging", "anomalyChecks"):
        if key not in contract:
            return None, Finding(
                "GOV-AGENT-HOST-004", f"Agent host contract has no '{key}' section.",
                "Restore the pinned host contract through a standard upgrade.", [str(path.name)],
            )
    return contract, None


def audit(root: Path, actor: str = "agent", contract_path: str | None = None) -> dict[str, Any]:
    contract, failure = load_contract(root, contract_path)
    if contract is None:
        findings = [failure] if failure is not None else []
    else:
        findings = (
            check_hosts(root, contract)
            + check_source_links(root, contract, contract_path=contract_path)
            + check_hook(root, contract, actor)
            + check_packaging(root, contract)
            + check_guidance_anomalies(root, contract)
        )
    findings.sort()
    return {
        "schema": "new-project.agent-host-report/v1",
        "actor": actor,
        "findings": [
            {
                "code": item.code,
                "message": item.message,
                "remediation": item.remediation,
                "paths": item.paths,
            }
            for item in findings
        ],
        "ok": not findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(repo_root()))
    parser.add_argument("--contract", default=None, help="Explicit agent-hosts.json path")
    parser.add_argument(
        "--actor", choices=("agent", "human", "ci"), default="agent",
        help="'ci' skips checks that only a developer or agent clone can satisfy",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv or sys.argv[1:])

    report = audit(Path(args.root).resolve(), args.actor, args.contract)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "GOV-AGENT-HOST-PASS" if report["ok"] else "GOV-AGENT-HOST-FAIL"
        print(f"{status}: {len(report['findings'])} findings")
        for finding in report["findings"]:
            print(f"{finding['code']}: {finding['message']}")
            print(f"  -> {finding['remediation']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
