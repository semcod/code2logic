#!/usr/bin/env python3
"""Deterministic policy-as-code validator for new-project target repositories."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# Managed validators are read-only checks. Importing adjacent managed modules
# must not create `__pycache__` inside the repository and turn a clean checkout
# into an implementation diff on the next validation pass.
_previous_bytecode_policy = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    try:
        from ticket_activity import ActivityError, delivery_landed, resolve as resolve_ticket_activity
    except ModuleNotFoundError:
        _activity_spec = importlib.util.spec_from_file_location(
            "ticket_activity", Path(__file__).with_name("ticket_activity.py")
        )
        if _activity_spec is None or _activity_spec.loader is None:
            raise
        _activity_module = importlib.util.module_from_spec(_activity_spec)
        sys.modules[_activity_spec.name] = _activity_module
        _activity_spec.loader.exec_module(_activity_module)
        ActivityError = _activity_module.ActivityError
        delivery_landed = _activity_module.delivery_landed
        resolve_ticket_activity = _activity_module.resolve
finally:
    sys.dont_write_bytecode = _previous_bytecode_policy

_previous_bytecode_policy = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    try:
        from repository_policy import load_adapter, policy_error, selected_policy
    except ModuleNotFoundError:
        _policy_spec = importlib.util.spec_from_file_location(
            "repository_policy", Path(__file__).with_name("repository_policy.py")
        )
        if _policy_spec is None or _policy_spec.loader is None:
            raise
        _policy_module = importlib.util.module_from_spec(_policy_spec)
        sys.modules[_policy_spec.name] = _policy_module
        _policy_spec.loader.exec_module(_policy_module)
        load_adapter = _policy_module.load_adapter
        policy_error = _policy_module.policy_error
        selected_policy = _policy_module.selected_policy
finally:
    sys.dont_write_bytecode = _previous_bytecode_policy

RUNTIME_VERSION = "0.11.0"
POLICY_DSL_LOCK = {
    "schema": "new-project.policy-dsl-lock/v1",
    "dependency": {
        "id": "wellmanifest/policy-dsl",
        "version": "0.1.0-dev",
        "sourceRepository": "wellmanifest/policy-dsl",
        "sourceRevision": "daaf7b7b96312a2469de1b4799f2f81c7396de4e",
        "sourcePath": "tests/policy_dsl_check.py",
        "sourceSha256": "1ebed8ada3f687bf82de235b352ec1ce94b606887ad2a1657d66bd58f04314e8",
    },
    "installation": {
        "packageSourcePath": "scripts/policy_dsl_check.py",
        "managedTargetPath": ".governance/policy_dsl_check.py",
        "lockTargetPath": ".governance/policy-dsl.lock.json",
        "networkRequired": False,
    },
}
ACTIVE_DEFAULT = {"IN_PROGRESS"}
TICKET_ACTIVITY_ERROR = "GOV-TICKET-ACTIVITY-001"
EXECUTABLE_SUFFIXES = {
    ".bat", ".c", ".cc", ".cmd", ".cpp", ".go", ".java", ".js", ".jsx",
    ".mjs", ".php", ".ps1", ".py", ".rb", ".rs", ".sh", ".ts", ".tsx",
}
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?key|client[_-]?secret|password|private[_-]?key|token)"
    r"[ \t]*[:=][ \t]*['\"]?([A-Za-z0-9_./+=-]{12,})"
)
SECRET_FIELD_NAME_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?key|client[_-]?secret|password|private[_-]?key|token)"
)
SAFE_SECRET_VALUES = re.compile(r"(?i)^(example|placeholder|changeme|your[_-]|\$\{|<|xxx|test)")
GENERATED_SECRET_PLACEHOLDER_RE = re.compile(r"^__GENERATE_[A-Z0-9_]+__$")
LOCAL_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/](?:Users|Documents|Desktop)[\\/]|/(?:home|Users)/[^/\s]+/)")
IMMUTABLE_IMAGE_RE = re.compile(r"^[^@\s]+@sha256:[a-f0-9]{64}$")
COMPOSE_IMAGE_RE = re.compile(
    r"^\s*image\s*:\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s#]+))"
)
DOMAIN_CONTRACTS_CQRS = {
    "mode": "cqrs",
    "commandsAndQueries": "operations/index.json",
    "events": "events/index.json",
    "errors": "error/index.json",
    "models": "operations/index.json#/models",
}


@dataclass(order=True)
class Finding:
    code: str
    severity: str
    message: str
    remediation: str
    paths: list[str] = field(default_factory=list, compare=False)
    evidence: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class TicketRecord:
    directory: Path
    status: str | None
    workflow: str | None
    intent: dict[str, Any] | None
    intent_error: str | None
    files: dict[str, tuple[bytes, str]] | None = None
    external: bool = False


class Report:
    def __init__(self, root: Path, timing: bool = False) -> None:
        self.root = root
        self.timing = timing
        self.timings: dict[str, float] = {}
        self.findings: list[Finding] = []
        self.snapshot_migrations: dict[str, dict[str, Any]] = {}
        self.cached: bool = False

    def record_timing(self, phase: str, duration: float) -> None:
        if self.timing:
            self.timings[phase] = round(duration, 4)

    def add(
        self,
        code: str,
        message: str,
        remediation: str,
        paths: Iterable[str] = (),
        evidence: dict[str, Any] | None = None,
        severity: str = "error",
    ) -> None:
        self.findings.append(Finding(
            code=code,
            severity=severity,
            message=message,
            remediation=remediation,
            paths=sorted(set(paths)),
            evidence=evidence or {},
        ))

    @property
    def errors(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    def payload(self) -> dict[str, Any]:
        findings = sorted(self.findings)
        data = {
            "schema": "new-project.governance-report/v1",
            "runtimeVersion": RUNTIME_VERSION,
            "root": ".",
            "status": "passed" if self.errors == 0 else "failed",
            "summary": {
                "errors": self.errors,
                "warnings": sum(item.severity == "warning" for item in findings),
                "findings": len(findings),
            },
            "findings": [asdict(item) for item in findings],
        }
        if self.cached:
            data["cached"] = True
        if self.timings:
            data["timings"] = self.timings
        return data


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def work_classification_header_error(value: Any) -> str | None:
    fields = {"$schema", "schema", "dimensions", "ordering", "priorityDerivation", "evaluation", "rules"}
    if not isinstance(value, dict) or set(value) != fields:
        return "work classification contract fields are invalid"
    if value.get("$schema") != "./work-classification.schema.json":
        return "work classification schema reference drifted"
    if value.get("schema") != "new-project.work-classification/v1":
        return "unsupported work classification schema"
    if value.get("dimensions") != {
        "kind": ["BUG", "FEATURE", "SERVICE"],
        "priority": ["P0", "P1", "P2", "P3"],
        "origin": ["regression", "requested", "health"],
    }:
        return "work classification dimensions or order drifted"
    ordering = value.get("ordering")
    if ordering != {
        "precedence": ["dependencies", "kind", "priority", "stableId"],
        "kindOrder": ["BUG", "FEATURE", "SERVICE"],
        "priorityOrder": ["P0", "P1", "P2", "P3"],
        "dependencyPolicy": "topological-before-ranking",
        "stableIdPolicy": "lexicographic",
    }:
        return "work classification precedence drifted"
    if value.get("priorityDerivation") != {
        "impact": {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"},
        "declaredPolicy": "require-valid-priority",
        "serviceDefault": "P2",
    }:
        return "work classification priority derivation drifted"
    evaluation = value.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation != {
        "mode": "first-match", "unmatchedPolicy": "reject", "llmRole": "advisory-only",
    }:
        return "work classification evaluation policy drifted"
    return None


def complexity_rule_assignment(when: dict[str, Any]) -> tuple[tuple[str, str] | None, str | None]:
    if when.get("baseline") == "measured" and (
        when.get("delta") == "increased" or when.get("threshold") == "crossed"
    ):
        return ("BUG", "regression"), "impact"
    if when == {
        "signal": "cyclomatic-complexity",
        "baseline": "pre-existing",
        "delta": "not-increased",
    }:
        return ("SERVICE", "health"), "service-default"
    return None, None


def expected_rule_assignment(when: dict[str, Any]) -> tuple[tuple[str, str] | None, str | None]:
    signal = when.get("signal")
    if signal == "defect" and when.get("impact") in {"outage-or-security", "functional"}:
        return ("BUG", "regression"), "impact"
    if signal == "cyclomatic-complexity":
        return complexity_rule_assignment(when)
    if signal == "work-request" and when.get("request") == "new-behavior":
        return ("FEATURE", "requested"), "declared"
    if signal == "work-request" and when.get("request") == "maintenance":
        return ("SERVICE", "health"), "service-default"
    return None, None


def work_classification_rule_error(rule: dict[str, Any]) -> str | None:
    if set(rule) != {"id", "when", "assign", "prioritySource"}:
        return "work classification rule fields are invalid"
    when = rule.get("when")
    assignment = rule.get("assign")
    if not isinstance(when, dict) or not isinstance(assignment, dict):
        return "work classification rule condition or assignment is invalid"
    expected_when_fields = {
        "defect": [{"signal", "impact"}],
        "cyclomatic-complexity": [
            {"signal", "baseline", "delta"},
            {"signal", "baseline", "threshold"},
        ],
        "work-request": [{"signal", "request"}],
    }.get(when.get("signal"))
    if expected_when_fields is None or set(when) not in expected_when_fields:
        return f"work classification rule {rule['id']} mixes incompatible signal fields"
    expected_assignment, expected_priority_source = expected_rule_assignment(when)
    if expected_assignment is None:
        return f"work classification rule {rule['id']} has invalid condition values"
    if set(assignment) != {"kind", "origin"}:
        return f"work classification rule {rule['id']} has an invalid assignment"
    actual_assignment = assignment.get("kind"), assignment.get("origin")
    if actual_assignment != expected_assignment:
        return f"work classification rule {rule['id']} has an invalid assignment"
    if rule.get("prioritySource") != expected_priority_source:
        return f"work classification rule {rule['id']} has an invalid priority source"
    return None


def work_classification_error(value: Any) -> str | None:
    header_error = work_classification_header_error(value)
    if header_error:
        return header_error
    assert isinstance(value, dict)
    rules = value.get("rules")
    if not isinstance(rules, list) or len(rules) != 7:
        return "work classification must contain exactly seven rules"
    identifiers = [rule.get("id") for rule in rules if isinstance(rule, dict)]
    expected_identifiers = [f"W-CLASS-{index:03d}" for index in range(1, 8)]
    if identifiers != expected_identifiers:
        return "work classification rule identifiers or first-match order drifted"
    for rule in rules:
        assert isinstance(rule, dict)
        rule_error = work_classification_rule_error(rule)
        if rule_error:
            return rule_error
    return None


def load_work_classification(
    root: Path,
    report: Report,
    raw_path: str = ".governance/work-classification.dsl.json",
) -> dict[str, Any] | None:
    try:
        path = safe_repo_path(root, raw_path)
        if not path.is_file() and raw_path == ".governance/work-classification.dsl.json":
            hub_path = safe_repo_path(root, "governance/work-classification.dsl.json")
            if hub_path.is_file():
                path = hub_path
        value = load_json(path)
        error = work_classification_error(value)
        if error:
            raise ValueError(error)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report.add(
            "GOV-MANIFEST-001",
            f"Work classification contract is invalid: {error}",
            "Restore the managed work-classification DSL from the pinned standard release.",
            [raw_path],
        )
        return None
    return value


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def safe_repo_path(root: Path, raw: str) -> Path:
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path escapes repository: {raw}") from error
    return candidate


def resolve_policy_dsl_dependency(root: Path) -> tuple[Path, dict[str, Any]]:
    """Resolve and byte-verify the reviewed Policy DSL runtime without network I/O."""
    managed_lock = root / POLICY_DSL_LOCK["installation"]["lockTargetPath"]
    if managed_lock.is_file():
        lock_path = managed_lock
        checker_path = root / POLICY_DSL_LOCK["installation"]["managedTargetPath"]
    else:
        lock_path = root / "governance/policy-dsl.lock.json"
        checker_path = root / POLICY_DSL_LOCK["installation"]["packageSourcePath"]

    lock = load_json(lock_path)
    if lock != POLICY_DSL_LOCK:
        raise ValueError("Policy DSL lock differs from the reviewed closed dependency record")
    if not checker_path.is_file():
        raise ValueError("Policy DSL checker is missing")
    actual = hashlib.sha256(checker_path.read_bytes()).hexdigest()
    expected = POLICY_DSL_LOCK["dependency"]["sourceSha256"]
    if actual != expected:
        raise ValueError(f"Policy DSL checker digest differs: expected={expected}, actual={actual}")
    return checker_path, lock


def load_policy_dsl_module(root: Path) -> Any:
    checker_path, _ = resolve_policy_dsl_dependency(root)
    name_digest = hashlib.sha256(str(checker_path).encode("utf-8")).hexdigest()[:16]
    module_name = f"_new_project_policy_dsl_{name_digest}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, checker_path)
    if spec is None or spec.loader is None:
        raise ValueError("Policy DSL checker cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def check_required_checks_declaration(root: Path, report: Report) -> None:
    script = next(
        (
            candidate
            for candidate in (
                root / "scripts" / "check_required_checks.py",
                root / ".governance" / "check_required_checks.py",
            )
            if candidate.is_file()
        ),
        None,
    )
    if script is None:
        return
    try:
        spec = importlib.util.spec_from_file_location("_new_project_required_checks", script)
        if spec is None or spec.loader is None:
            raise ValueError("required-checks gate cannot be imported")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        code = module.main(["--root", str(root)])
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
    except Exception as error:
        report.add(
            "GOV-SYNC-001",
            f"Required-checks gate could not run: {error}",
            "Restore scripts/check_required_checks.py or .governance/check_required_checks.py.",
            [rel(root, script)],
        )
        return
    if code:
        report.add(
            "GOV-SYNC-001",
            "Required-checks declaration does not match published workflow job names.",
            "Write the repository instance with the check names the ruleset enforces, using each job's name: field.",
            ["governance/required-checks.json", ".governance/required-checks.json"],
        )


def check_policy_dsl(root: Path, report: Report) -> None:
    contributing = root / "CONTRIBUTING.md"
    if not contributing.is_file():
        return
    try:
        policy_dsl = load_policy_dsl_module(root)
        policy_dsl.parse_markdown(contributing.read_text(encoding="utf-8"))
    except Exception as error:
        report.add(
            "GOV-POLICY-DSL-001",
            f"CONTRIBUTING.md or its pinned Policy DSL runtime is invalid: {error}",
            "Restore the managed Policy DSL files or correct the selected dsl fences, then rerun the governance gate.",
            ["CONTRIBUTING.md"],
        )


def string_list(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def relative_pattern(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        not normalized.startswith("/")
        and not re.match(r"^[A-Za-z]:/", normalized)
        and ".." not in normalized.split("/")
    )


def approval_evidence_config_valid(value: Any) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and set(value) == {
            "schema", "requiredBindings", "reviewVerificationMethod",
            "signedAttestationPredicateType",
        }
        and value.get("schema") == "new-project.approval-evidence/v1"
        and value.get("requiredBindings") == [
            "repository", "pullRequest", "headSha", "ticket", "actor",
        ]
        and value.get("reviewVerificationMethod") == "github-api-allowlist"
        and value.get("signedAttestationPredicateType")
        == "https://wellmanifest.com/attestations/validator/v1"
    )


BRANCH_NAME = re.compile('^(?!@?$)(?!HEAD$)(?![-/])(?![\\s\\S]*(?:\\.\\.|//|@\\{|[ ~^:?*\\[\\\\\\x00-\\x1f\\x7f]))(?![\\s\\S]*(?:^|/)\\.)(?![\\s\\S]*(?:^|/)[^/]*\\.lock(?:/|$))(?![\\s\\S]*[/.]$)[\\s\\S]+$')


def branch_name(value: Any) -> bool:
    return isinstance(value, str) and BRANCH_NAME.fullmatch(value) is not None


def integer_fields_valid(value: dict[str, Any], fields: Iterable[str]) -> bool:
    return all(
        isinstance(value.get(name), int) and not isinstance(value[name], bool)
        for name in fields
    )


def relative_pattern_list(value: Any, *, nonempty: bool = False) -> bool:
    return string_list(value, nonempty=nonempty) and all(relative_pattern(item) for item in value)


def delivery_limits_valid(value: dict[str, Any]) -> bool:
    return all([
        isinstance(value.get("requiredForImplementation"), bool),
        1 <= value["maxActiveMinutes"] <= 240,
        1 <= value["checkpointMinutes"] < value["maxActiveMinutes"],
        value["maxImplementationFiles"] >= 1,
        value["maxAffectedComponents"] >= 1,
        value["maxPublicInterfaceChanges"] >= 0,
        value["maxRuntimeDependencies"] >= 0,
    ])


DELIVERY_BUDGET_FIELDS = {
    "maxImplementationFiles", "maxAffectedComponents",
    "maxPublicInterfaceChanges", "maxRuntimeDependencies",
}


def delivery_profile_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != DELIVERY_BUDGET_FIELDS:
        return False
    if not integer_fields_valid(value, DELIVERY_BUDGET_FIELDS):
        return False
    return (
        value["maxImplementationFiles"] >= 1
        and value["maxAffectedComponents"] >= 1
        and value["maxPublicInterfaceChanges"] >= 0
        and value["maxRuntimeDependencies"] >= 0
    )


def delivery_classes_valid(value: Any) -> bool:
    return (
        string_list(value, nonempty=True)
        and len(set(value)) == len(value)
        and set(value) <= {"XS", "S", "M", "L"}
    )


def delivery_profiles_valid(value: dict[str, Any], classes_valid: bool) -> bool:
    profiles = value.get("profiles")
    return profiles is None or (
        classes_valid
        and isinstance(profiles, dict)
        and set(profiles) == set(value["allowedComplexityClasses"])
        and all(delivery_profile_valid(profile) for profile in profiles.values())
        and all(
            profile[field] <= value[field]
            for profile in profiles.values()
            for field in DELIVERY_BUDGET_FIELDS
        )
    )


def delivery_policy_valid(value: Any) -> bool:
    fields = {
        "requiredForImplementation", "maxActiveMinutes", "checkpointMinutes",
        "allowedComplexityClasses", "maxImplementationFiles",
        "maxAffectedComponents", "maxPublicInterfaceChanges",
        "maxRuntimeDependencies", "targetBranches", "publicInterfacePaths",
        "dependencyManifestPaths",
    }
    allowed_fields = {frozenset(fields), frozenset(fields | {"profiles"})}
    if not isinstance(value, dict) or frozenset(value) not in allowed_fields:
        return False
    integer_limits = (
        "maxActiveMinutes", "checkpointMinutes", "maxImplementationFiles",
        "maxAffectedComponents", "maxPublicInterfaceChanges",
        "maxRuntimeDependencies",
    )
    if not integer_fields_valid(value, integer_limits):
        return False
    limits_valid = delivery_limits_valid(value)
    classes_valid = delivery_classes_valid(value.get("allowedComplexityClasses"))
    profiles_valid = delivery_profiles_valid(value, classes_valid)
    targets_valid = (
        string_list(value.get("targetBranches"), nonempty=True)
        and all(branch_name(item) for item in value["targetBranches"])
    )
    paths_valid = relative_pattern_list(value.get("publicInterfacePaths")) and relative_pattern_list(
        value.get("dependencyManifestPaths")
    )
    return limits_valid and classes_valid and profiles_valid and targets_valid and paths_valid


def effective_delivery_policy(policy: dict[str, Any], complexity: str) -> dict[str, Any]:
    profile = policy.get("profiles", {}).get(complexity)
    return policy if profile is None else {**policy, **profile}


def field_set_hint(value: Any, required: set[str], optional: set[str] = frozenset()) -> str:
    """Name the missing and unexpected keys so an agent can repair an intent in one edit."""
    if not isinstance(value, dict):
        return f" (expected an object with {', '.join(sorted(required))}; got {type(value).__name__})"
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - required - set(optional))
    parts = [f"missing: {', '.join(missing)}"] if missing else []
    if unexpected:
        parts.append(f"unexpected: {', '.join(unexpected)}")
    return f" ({'; '.join(parts)})" if parts else ""


def delivery_header_error(value: dict[str, Any]) -> str | None:
    if not isinstance(value.get("acceptedBaseSha"), str) or re.fullmatch(r"[0-9a-f]{40}", value["acceptedBaseSha"]) is None:
        return "delivery acceptedBaseSha must be a full lowercase commit SHA"
    if not branch_name(value.get("targetBranch")):
        return "delivery targetBranch is invalid"
    if not isinstance(value.get("outcome"), str) or not value["outcome"].strip():
        return "delivery outcome is blank"
    if not string_list(value.get("nonGoals"), nonempty=True):
        return "delivery nonGoals must be an explicit non-empty list"
    if value.get("complexity") not in {"XS", "S", "M", "L"}:
        return f"delivery complexity must be XS, S, M or L (got {value.get('complexity')!r})"
    minutes = value.get("estimatedMinutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 240:
        return "delivery estimatedMinutes must be between 1 and 240"
    return None


def delivery_budgets_error(budgets: Any) -> str | None:
    fields = {
        "maxImplementationFiles", "maxAffectedComponents",
        "maxPublicInterfaceChanges", "maxRuntimeDependencies",
    }
    if not isinstance(budgets, dict) or set(budgets) != fields:
        return "delivery budgets are incomplete" + field_set_hint(budgets, fields)
    if not integer_fields_valid(budgets, fields):
        return "delivery budgets must be integers"
    if budgets["maxImplementationFiles"] < 1 or budgets["maxAffectedComponents"] < 1:
        return "delivery file and component budgets must be positive"
    if budgets["maxPublicInterfaceChanges"] < 0 or budgets["maxRuntimeDependencies"] < 0:
        return "delivery interface and dependency budgets cannot be negative"
    return None


def delivery_components_error(components: Any) -> str | None:
    if not isinstance(components, list) or not components:
        return "delivery architecture requires at least one component"
    names: list[str] = []
    for component in components:
        if not isinstance(component, dict) or set(component) != {"name", "paths"}:
            return "delivery component must contain name and paths" + field_set_hint(component, {"name", "paths"})
        if not isinstance(component.get("name"), str) or not component["name"].strip():
            return "delivery component name is blank"
        if not relative_pattern_list(component.get("paths"), nonempty=True):
            return "delivery component paths must be repository-relative patterns"
        names.append(component["name"])
    return "delivery component names must be unique" if len(names) != len(set(names)) else None


def delivery_ui_error(ui: Any) -> str | None:
    if not isinstance(ui, dict) or set(ui) != {"impact", "states", "evidence"}:
        return ("delivery UI decision is incomplete" + field_set_hint(ui, {"impact", "states", "evidence"})
                + '; for non-UI work use {"impact": "none", "states": [], "evidence": []}')
    if ui.get("impact") not in {"none", "single-state", "multi-state"}:
        return f"delivery UI impact is invalid (got {ui.get('impact')!r}; allowed: none, single-state, multi-state)"
    if not string_list(ui.get("states")) or not set(ui["states"]) <= {"loading", "empty", "error", "success"}:
        return (f"delivery UI states are invalid (got {ui.get('states')!r}; "
                "expected a unique list drawn from loading, empty, error, success)")
    if not string_list(ui.get("evidence")):
        return "delivery UI evidence must be a unique string list"
    return delivery_ui_impact_error(ui["impact"], ui["states"], ui["evidence"])


def delivery_ui_impact_error(impact: str, states: list[str], evidence: list[str]) -> str | None:
    if impact == "none" and (states or evidence):
        return ("delivery UI states/evidence must be empty when impact is none "
                f"(got states={states!r}, evidence={evidence!r}; set both to [] or choose a UI impact)")
    if impact == "single-state" and (len(states) != 1 or not evidence):
        return (f"single-state UI work requires one state and planned evidence "
                f"(got {len(states)} state(s), {len(evidence)} evidence item(s))")
    if impact == "multi-state" and (len(states) < 2 or not evidence):
        return (f"multi-state UI work requires at least two states and planned evidence "
                f"(got {len(states)} state(s), {len(evidence)} evidence item(s))")
    return None


DATA_CHANGE_KINDS = {
    "component-local-state", "schema-migration", "cross-component-migration",
    "ownership-transfer", "unknown",
}


def delivery_data_changes_error(changes: Any, components: Any) -> str | None:
    """Legacy prose stays conservative; local state needs an explicit owner."""
    if not isinstance(changes, list):
        return "delivery architecture dataChanges must be a list"
    names = [item.get("name") for item in components if isinstance(item, dict)] if isinstance(components, list) else []
    seen = set()
    for change in changes:
        if isinstance(change, str):
            if not change.strip():
                return "delivery data change description is blank"
        elif isinstance(change, dict):
            if set(change) != {"kind", "component", "description"}:
                return "delivery data change requires kind, component and description"
            if not isinstance(change["kind"], str) or change["kind"] not in DATA_CHANGE_KINDS:
                return "delivery data change kind is unknown"
            if not isinstance(change["component"], str) or names.count(change["component"]) != 1:
                return "delivery data change component must resolve to one declared component"
            if not isinstance(change["description"], str) or not change["description"].strip():
                return "delivery data change description is blank"
        else:
            return "delivery data change must be legacy prose or a typed record"
        key = json.dumps(change, sort_keys=True)
        if key in seen:
            return "delivery data changes must be unique"
        seen.add(key)
    return None


def integration_data_changes(changes: list[Any]) -> list[Any]:
    # Do not infer an exemption from prose, spelling or an unknown record.
    return [change for change in changes if not (
        isinstance(change, dict) and change.get("kind") == "component-local-state"
    )]


def delivery_architecture_error(architecture: Any) -> str | None:
    fields = {
        "status", "decision", "components", "responsibilityChanges",
        "interfaceChanges", "dataChanges", "ui", "rollback",
    }
    if not isinstance(architecture, dict) or set(architecture) != fields:
        return "delivery architecture decision is incomplete" + field_set_hint(architecture, fields)
    if architecture.get("status") != "accepted":
        return f"delivery architecture status must be accepted before implementation (got {architecture.get('status')!r})"
    for name in ("decision", "rollback"):
        if not isinstance(architecture.get(name), str) or not architecture[name].strip():
            return f"delivery architecture {name} is blank"
    if not isinstance(architecture.get("responsibilityChanges"), bool):
        return "delivery responsibilityChanges must be boolean"
    if not string_list(architecture.get("interfaceChanges")):
        return "delivery architecture interfaceChanges must be a unique string list"
    return (delivery_components_error(architecture.get("components"))
            or delivery_data_changes_error(architecture.get("dataChanges"), architecture.get("components"))
            or delivery_ui_error(architecture.get("ui")))


def delivery_validation_error(validation: Any) -> str | None:
    if not isinstance(validation, list) or not validation:
        return "delivery validation must map at least one acceptance criterion"
    criteria: list[str] = []
    for item in validation:
        if not isinstance(item, dict) or set(item) != {"criterion", "commands", "evidence"}:
            return "delivery validation entry is incomplete" + field_set_hint(item, {"criterion", "commands", "evidence"})
        if not isinstance(item.get("criterion"), str) or re.fullmatch(r"AC-[0-9]+", item["criterion"]) is None:
            return "delivery validation criterion is invalid"
        if not string_list(item.get("commands"), nonempty=True):
            return "delivery validation commands cannot be empty"
        if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            return "delivery validation evidence is blank"
        criteria.append(item["criterion"])
    return "delivery validation criteria must be unique" if len(criteria) != len(set(criteria)) else None


PHYSICAL_CONTRACT_FILES = (".governance/physical-contracts.json", "governance/physical-contracts.json")
PHYSICAL_PROPERTIES = {
    "pin-assignment", "active-level", "pull", "capability-set",
    "unit-scale", "limit-range", "timing", "none",
}
PHYSICAL_HAZARDS = {"motion", "pressure", "electrical", "thermal", "none"}


def physical_contracts_error(value: Any) -> str | None:
    """Adopter declaration of files whose values carry physical meaning."""
    if not isinstance(value, dict) or set(value) != {"schema", "contracts"}:
        return "physical contracts must contain exactly schema and contracts"
    if value.get("schema") != "new-project.physical-contracts/v1":
        return "physical contracts schema is unsupported"
    contracts = value.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return "physical contracts must declare at least one contract"
    ids: list[str] = []
    for contract in contracts:
        if not isinstance(contract, dict) or set(contract) != {"id", "paths", "properties", "hazard", "acceptance"}:
            return "physical contract requires id, paths, properties, hazard and acceptance"
        if not isinstance(contract["id"], str) or re.fullmatch(r"[a-z0-9][a-z0-9.-]*", contract["id"]) is None:
            return "physical contract id is invalid"
        if not relative_pattern_list(contract["paths"], nonempty=True):
            return "physical contract paths must be repository-relative patterns"
        if len(contract["paths"]) != len(set(contract["paths"])):
            return "physical contract paths must be unique"
        if not string_list(contract["properties"], nonempty=True) or not set(contract["properties"]) <= PHYSICAL_PROPERTIES - {"none"}:
            return "physical contract properties are invalid"
        if len(contract["properties"]) != len(set(contract["properties"])):
            return "physical contract properties must be unique"
        if not isinstance(contract["hazard"], str) or contract["hazard"] not in PHYSICAL_HAZARDS:
            return "physical contract hazard is invalid"
        if not isinstance(contract["acceptance"], str) or not contract["acceptance"].strip():
            return "physical contract acceptance procedure is blank"
        ids.append(contract["id"])
    return "physical contract ids must be unique" if len(ids) != len(set(ids)) else None


def physical_changes_error(changes: Any) -> str | None:
    """Every changed physical property is declared on its own, before and after.

    A pin move and a polarity flip are two entries, so neither can hide
    inside the other. Each exact contract/property/signal has one claim;
    "none" is exclusive with changed properties of the same contract.
    """
    if not isinstance(changes, list) or not changes:
        return "intent physicalChanges must be a non-empty list"
    seen = set()
    claims = set()
    unchanged_contracts = set()
    changed_contracts = set()
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("property"), str) or change["property"] not in PHYSICAL_PROPERTIES:
            return "physical change property is invalid"
        if change["property"] == "none":
            if set(change) != {"contract", "property", "rationale"}:
                return "a no-semantics physical change requires contract, property and rationale"
            if not isinstance(change["rationale"], str) or not change["rationale"].strip():
                return "physical change rationale is blank"
        else:
            if set(change) != {"contract", "property", "signal", "before", "after", "acceptance"}:
                return "physical change requires contract, property, signal, before, after and acceptance"
            for name in ("signal", "before", "after"):
                if not isinstance(change[name], str) or not change[name].strip():
                    return f"physical change {name} is blank"
            if change["before"] == change["after"]:
                return "physical change before and after must differ; use property none"
            if not string_list(change["acceptance"], nonempty=True):
                return "physical change acceptance must list observable hardware checks"
        if not isinstance(change["contract"], str) or not change["contract"].strip():
            return "physical change contract is blank"
        key = json.dumps(change, sort_keys=True)
        if key in seen:
            return "physical changes must be unique"
        seen.add(key)
        identity = (change["contract"], change["property"], change.get("signal"))
        if identity in claims:
            return "physical change contract, property and signal must be unique"
        claims.add(identity)
        if change["property"] == "none":
            if change["contract"] in changed_contracts:
                return "physical change property none cannot coexist with changes to the same contract"
            unchanged_contracts.add(change["contract"])
        else:
            if change["contract"] in unchanged_contracts:
                return "physical change property none cannot coexist with changes to the same contract"
            changed_contracts.add(change["contract"])
    return None


def load_physical_contracts(root: Path) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    for raw in PHYSICAL_CONTRACT_FILES:
        path = root / raw
        if path.is_file():
            try:
                value = load_json(path)
            except (OSError, json.JSONDecodeError) as error:
                return path, None, str(error)
            return path, value, physical_contracts_error(value)
    return None, None, None


def check_physical_contract_changes(
    root: Path, intent: dict[str, Any], ticket: str, implementation: list[str], report: Report,
) -> None:
    path, contracts, error = load_physical_contracts(root)
    if path is None:
        return
    if error:
        report.add(
            "GOV-PHYS-002", f"Physical contract declaration is invalid: {error}",
            "Repair the adopter's physical-contracts.json; the gate fails closed while it is unreadable.",
            [rel(root, path)],
        )
        return
    assert contracts is not None
    changes = intent.get("physicalChanges", [])
    change_error = physical_changes_error(changes) if "physicalChanges" in intent else None
    by_id = {contract["id"]: contract for contract in contracts["contracts"]}
    if change_error is None:
        for change in changes:
            contract = by_id.get(change["contract"])
            if contract is None:
                change_error = f"Unknown physical contract '{change['contract']}'"
                break
            if change["property"] != "none" and change["property"] not in contract["properties"]:
                change_error = f"Property '{change['property']}' is not declared by physical contract '{contract['id']}'"
                break
    if change_error:
        report.add(
            "GOV-PHYS-001", f"Intent physicalChanges are invalid: {change_error}",
            "Name an existing physical contract and one of its declared properties, or property none with a rationale.",
            [f"project/{ticket}/intent.json"], {"ticket": ticket},
        )
        return
    declared = {change["contract"] for change in changes}
    for contract in contracts["contracts"]:
        touched = [item for item in implementation if matches(item, contract["paths"])]
        if not touched or contract["id"] in declared:
            continue
        report.add(
            "GOV-PHYS-001",
            f"Changed paths carry physical contract '{contract['id']}' but the intent declares no physicalChanges for it.",
            "Declare each changed property (pin, active level, pull, capability set, scale, range, timing) with before, "
            f"after and hardware acceptance checks, or property none with a rationale. Acceptance: {contract['acceptance']}",
            touched, {"ticket": ticket, "contract": contract["id"], "hazard": contract["hazard"],
                      "properties": contract["properties"]},
        )


PLACEMENT_HOMES = {"wellmanifest", "subactor", "semcod"}
PLACEMENT_SHAPES = {"domain_pack", "runtime_service", "both"}
PLACEMENT_ADOPT = re.compile(r"^wellmanifest/[a-z0-9][a-z0-9-]*$")


def placement_error(value: Any) -> str | None:
    required = {"home", "shape"}
    allowed = required | {"runtimeOwner", "adopt"}
    if not isinstance(value, dict) or not required <= set(value) <= allowed:
        return "placement must contain home and shape"
    if value["home"] not in PLACEMENT_HOMES:
        return "placement home is invalid"
    if value["shape"] not in PLACEMENT_SHAPES:
        return "placement shape is invalid"
    runtime_owner = value.get("runtimeOwner")
    if runtime_owner is not None and runtime_owner not in PLACEMENT_HOMES:
        return "placement runtimeOwner is invalid"
    if value["home"] == "wellmanifest" and value["shape"] == "runtime_service":
        return "runtime_service must not HOME wellmanifest; ADOPT packs from subactor or semcod"
    adopt = value.get("adopt")
    if adopt is not None and (
        not string_list(adopt) or not all(PLACEMENT_ADOPT.fullmatch(item) for item in adopt)
    ):
        return "placement adopt must be wellmanifest/<pack> ids"
    return None


def managed_target_bindings_error(
    value: Any,
    *,
    field: str,
    label: str,
) -> tuple[list[str], str | None]:
    if not isinstance(value, list):
        return [], f"delivery standardAdoption {field} must be a list"
    paths: list[str] = []
    for binding in value:
        if not isinstance(binding, dict) or set(binding) != {"path", "baseDigest"}:
            return [], f"delivery standardAdoption managed target {label} fields are invalid"
        path, digest = binding.get("path"), binding.get("baseDigest")
        if (
            not isinstance(path, str)
            or not path
            or not relative_pattern(path)
            or any(character in path for character in "*?[")
        ):
            return [], f"delivery standardAdoption managed target {label} path is invalid"
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return [], f"delivery standardAdoption managed target {label} digest is invalid"
        paths.append(path)
    if len(paths) != len(set(paths)):
        return [], f"delivery standardAdoption managed target {label} paths must be unique"
    return paths, None


def target_owned_transitions_error(value: Any) -> tuple[list[str], str | None]:
    if not isinstance(value, list):
        return [], "delivery standardAdoption targetOwnedTransitions must be a list"
    paths: list[str] = []
    for transition in value:
        if not isinstance(transition, dict) or set(transition) != {
            "path", "baseDigest", "headDigest",
        }:
            return [], "delivery standardAdoption target-owned transition fields are invalid"
        path = transition.get("path")
        base_digest = transition.get("baseDigest")
        head_digest = transition.get("headDigest")
        if (
            not isinstance(path, str)
            or not path
            or not relative_pattern(path)
            or any(character in path for character in "*?[")
        ):
            return [], "delivery standardAdoption target-owned transition path is invalid"
        if not all(
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            for digest in (base_digest, head_digest)
        ):
            return [], "delivery standardAdoption target-owned transition digest is invalid"
        if base_digest == head_digest:
            return [], "delivery standardAdoption target-owned transition digests must differ"
        paths.append(path)
    if len(paths) != len(set(paths)):
        return [], "delivery standardAdoption target-owned transition paths must be unique"
    return paths, None


def standard_adoption_header_error(value: Any) -> str | None:
    required_fields = {"sourceRepository", "fromRevision", "toRevision"}
    allowed_fields = required_fields | {
        "managedTargetTakeovers",
        "managedTargetRestorations",
        "targetOwnedTransitions",
    }
    if not isinstance(value, dict) or not required_fields <= set(value) <= allowed_fields:
        return "delivery standardAdoption fields are invalid"
    if value.get("sourceRepository") != "wellmanifest/new-project":
        return "delivery standardAdoption sourceRepository is invalid"
    from_revision = value.get("fromRevision")
    to_revision = value.get("toRevision")
    if from_revision is not None and (
        not isinstance(from_revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", from_revision) is None
    ):
        return "delivery standardAdoption revisions must be full lowercase commit SHAs"
    if not isinstance(to_revision, str) or re.fullmatch(r"[0-9a-f]{40}", to_revision) is None:
        return "delivery standardAdoption revisions must be full lowercase commit SHAs"
    if from_revision == to_revision:
        return "delivery standardAdoption revisions must differ"
    return None


def standard_adoption_error(value: Any) -> str | None:
    error = standard_adoption_header_error(value)
    if error:
        return error
    takeover_paths, error = managed_target_bindings_error(
        value.get("managedTargetTakeovers", []),
        field="managedTargetTakeovers",
        label="takeover",
    )
    if error:
        return error
    restoration_paths, error = managed_target_bindings_error(
        value.get("managedTargetRestorations", []),
        field="managedTargetRestorations",
        label="restoration",
    )
    if error:
        return error
    transition_paths, error = target_owned_transitions_error(
        value.get("targetOwnedTransitions", [])
    )
    if error:
        return error
    if set(takeover_paths) & set(restoration_paths):
        return "delivery standardAdoption managed target paths cannot be both takeover and restoration"
    if set(transition_paths) & (set(takeover_paths) | set(restoration_paths)):
        return "delivery standardAdoption target-owned transitions cannot overlap managed target bindings"
    if value["fromRevision"] is None and (takeover_paths or restoration_paths or transition_paths):
        return "initial standard adoption cannot declare target bindings"
    return None


def snapshot_migration_runtime():
    spec = importlib.util.spec_from_file_location(
        "new_project_snapshot_migration", Path(__file__).with_name("snapshot_migration.py"),
    )
    if spec is None or spec.loader is None:
        raise ValueError("Managed snapshot migration runtime is unavailable")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def prepare_snapshot_migrations(args, root, records, base, changed, report):
    candidates = [record for record in records if record.intent is not None
                  and "snapshotMigration" in record.intent.get("delivery", {})
                  and any(path.startswith(rel(root, record.directory) + "/") for path in changed)]
    authorization = getattr(args, "migration_authorization", None)
    if not candidates:
        if authorization:
            report.add("GOV-SNAPSHOT-MIGRATION-003", "Grant supplied without a migration ticket.",
                       "Bind the protected grant to exactly one current migration ticket.")
        return set(), set()
    try:
        if len(candidates) != 1:
            raise ValueError("Exactly one migration ticket is required")
        record = candidates[0]
        branch = getattr(args, "migration_branch", None)
        if not branch:
            raise ValueError("Authenticated migration head branch is required")
        observed_branch = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                                         cwd=root, text=True, capture_output=True)
        if observed_branch.returncode == 0 and observed_branch.stdout.strip() != branch:
            raise ValueError("Current branch differs from the protected migration binding")
        proof = snapshot_migration_runtime().prove(
            root, record.intent, base=base, head=args.head,
            repository=args.expected_repository, branch=branch,
            authorization_path=authorization,
            authorization_sha256=getattr(args, "migration_authorization_sha256", None),
        )
        # An index-only edit is a pending repair even when the worktree still
        # matches HEAD. Never exempt staged content from ordinary path checks.
        staged = git_output(root, ["diff", "--cached", "--no-ext-diff", "--no-textconv",
                                   "--name-only", "-z", args.head])
        staged_paths = {p for p in staged.decode("utf-8").split("\0") if p}
        proof["repairPaths"] = sorted(set(proof["repairPaths"]) | staged_paths)
        proof["importedPaths"] = sorted(set(proof["importedPaths"]) - set(proof["repairPaths"]))
        proof["unchangedImportedFiles"] = len(proof["importedPaths"])
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.CalledProcessError) as error:
        report.add(getattr(error, "code", "GOV-SNAPSHOT-MIGRATION-003"),
                   "Snapshot migration proof was rejected: " + str(error),
                   "Reobserve the protected subject and follow error/GOV-SNAPSHOT-MIGRATION.md.")
        return set(), set()
    report.snapshot_migrations[record.directory.name] = proof
    return set(proof["historicalTickets"]), set(proof["repairPaths"])


def delivery_intent_error(value: Any) -> str | None:
    required_fields = {
        "acceptedBaseSha", "targetBranch", "outcome", "nonGoals",
        "complexity", "estimatedMinutes", "budgets", "architecture",
        "runtimeDependencies", "validation",
    }
    optional_fields = {"standardAdoption", "snapshotMigration"}
    if not isinstance(value, dict) or not required_fields <= set(value) <= required_fields | optional_fields:
        return "delivery must contain exactly the bounded-delivery fields" + field_set_hint(value, required_fields, optional_fields)
    if "snapshotMigration" in value:
        try:
            migration_error = snapshot_migration_runtime().contract_error(value["snapshotMigration"])
        except (OSError, ValueError):
            return "managed snapshot migration contract validator is unavailable"
        if migration_error:
            return migration_error
    error = delivery_header_error(value) or delivery_budgets_error(value.get("budgets"))
    if error:
        return error
    error = delivery_architecture_error(value.get("architecture"))
    if error:
        return error
    if not string_list(value.get("runtimeDependencies")):
        return "delivery runtimeDependencies must be a unique string list"
    if "standardAdoption" in value:
        error = standard_adoption_error(value["standardAdoption"])
        if error:
            return error
    return delivery_validation_error(value.get("validation"))


def matches(path: str, patterns: Iterable[str]) -> bool:
    path_parts = path.replace("\\", "/").strip("/").split("/")

    def match_pattern(pattern: str) -> bool:
        pattern_parts = pattern.replace("\\", "/").strip("/").split("/")
        memo: dict[tuple[int, int], bool] = {}

        def visit(path_index: int, pattern_index: int) -> bool:
            key = (path_index, pattern_index)
            if key in memo:
                return memo[key]
            if pattern_index == len(pattern_parts):
                result = path_index == len(path_parts)
            elif pattern_parts[pattern_index] == "**":
                result = visit(path_index, pattern_index + 1) or (
                    path_index < len(path_parts) and visit(path_index + 1, pattern_index)
                )
            else:
                result = (
                    path_index < len(path_parts)
                    and fnmatch.fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
                    and visit(path_index + 1, pattern_index + 1)
                )
            memo[key] = result
            return result

        return visit(0, 0)

    return any(match_pattern(pattern) for pattern in patterns)


def segment_literal_prefix(pattern: str) -> str:
    index = min((pattern.find(char) for char in "*?[" if char in pattern), default=len(pattern))
    return pattern[:index]


def segment_literal_suffix(pattern: str) -> str:
    indexes = [pattern.rfind(char) for char in "*?]" if char in pattern]
    return pattern[max(indexes, default=-1) + 1:]


def segments_may_overlap(first: str, second: str) -> bool:
    first_magic = any(char in first for char in "*?[")
    second_magic = any(char in second for char in "*?[")
    if not first_magic and not second_magic:
        return first == second
    if not first_magic:
        return fnmatch.fnmatchcase(first, second)
    if not second_magic:
        return fnmatch.fnmatchcase(second, first)
    first_prefix = segment_literal_prefix(first)
    second_prefix = segment_literal_prefix(second)
    if first_prefix and second_prefix and not (
        first_prefix.startswith(second_prefix) or second_prefix.startswith(first_prefix)
    ):
        return False
    first_suffix = segment_literal_suffix(first)
    second_suffix = segment_literal_suffix(second)
    return not (
        first_suffix
        and second_suffix
        and not (
            first_suffix.endswith(second_suffix) or second_suffix.endswith(first_suffix)
        )
    )


def patterns_may_overlap(first: str, second: str) -> bool:
    first_parts = first.replace("\\", "/").strip("/").split("/")
    second_parts = second.replace("\\", "/").strip("/").split("/")
    memo: dict[tuple[int, int], bool] = {}

    def remaining_are_globstars(parts: list[str], index: int) -> bool:
        return all(part == "**" for part in parts[index:])

    def visit(first_index: int, second_index: int) -> bool:
        key = (first_index, second_index)
        if key in memo:
            return memo[key]
        if first_index == len(first_parts) and second_index == len(second_parts):
            result = True
        elif first_index == len(first_parts):
            result = remaining_are_globstars(second_parts, second_index)
        elif second_index == len(second_parts):
            result = remaining_are_globstars(first_parts, first_index)
        elif first_parts[first_index] == "**":
            result = visit(first_index + 1, second_index) or visit(first_index, second_index + 1)
        elif second_parts[second_index] == "**":
            result = visit(first_index, second_index + 1) or visit(first_index + 1, second_index)
        else:
            result = segments_may_overlap(first_parts[first_index], second_parts[second_index]) and visit(
                first_index + 1, second_index + 1
            )
        memo[key] = result
        return result

    return visit(0, 0)


def segment_pattern_covered_by(pattern: str, owner_pattern: str) -> bool:
    if pattern == owner_pattern:
        return True
    if not any(char in pattern for char in "*?["):
        return fnmatch.fnmatchcase(pattern, owner_pattern)
    if owner_pattern == "*":
        return True
    if "?" in owner_pattern or "[" in owner_pattern or owner_pattern.count("*") != 1:
        return False
    owner_prefix, owner_suffix = owner_pattern.split("*", 1)
    first_magic = min(
        (pattern.find(char) for char in "*?[" if char in pattern),
        default=len(pattern),
    )
    last_magic = max(pattern.rfind(char) for char in "*?[")
    pattern_prefix = pattern[:first_magic]
    pattern_suffix = pattern[last_magic + 1:]
    return pattern_prefix.startswith(owner_prefix) and pattern_suffix.endswith(owner_suffix)


def pattern_covered_by(pattern: str, owner_pattern: str) -> bool:
    if pattern == owner_pattern:
        return True
    if not any(char in pattern for char in "*?["):
        return matches(pattern, [owner_pattern])
    pattern_parts = pattern.replace("\\", "/").strip("/").split("/")
    owner_parts = owner_pattern.replace("\\", "/").strip("/").split("/")
    if owner_parts and owner_parts[-1] == "**" and len(pattern_parts) >= len(owner_parts) - 1:
        prefix = owner_parts[:-1]
        return all(
            segment_pattern_covered_by(allowed, owned)
            for allowed, owned in zip(pattern_parts, prefix)
        )
    if len(pattern_parts) == len(owner_parts) and "**" not in owner_parts:
        return all(
            segment_pattern_covered_by(allowed, owned)
            for allowed, owned in zip(pattern_parts, owner_parts)
        )
    return False


def git_output(root: Path, args: list[str]) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
    ).stdout


def changed_paths(root: Path, base: str | None, head: str, explicit: list[str]) -> list[str]:
    if explicit:
        normalized = sorted({path.replace("\\", "/").removeprefix("./") for path in explicit if path})
        for path in normalized:
            safe_repo_path(root, path)
        return normalized
    try:
        if base:
            raw = git_output(root, ["diff", "--name-only", "-z", f"{base}...{head}"])
            paths = raw.decode("utf-8", "surrogateescape").split("\0")
        else:
            tracked = git_output(root, ["diff", "--name-only", "-z", "HEAD"])
            untracked = git_output(root, ["ls-files", "--others", "--exclude-standard", "-z"])
            paths = (tracked + untracked).decode("utf-8", "surrogateescape").split("\0")
        return sorted({path for path in paths if path})
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise RuntimeError("Git could not determine the changed-path set") from error


def check_history_order(
    root: Path,
    base: str | None,
    head: str,
    ticket_name: str,
    ticket_root: str,
    intent_path: str,
    governance_patterns: list[str],
    report: Report,
) -> None:
    if not base:
        return
    try:
        arguments = ["rev-list", "--reverse", f"{base}..{head}"]
        migration = report.snapshot_migrations.get(ticket_name)
        if migration:
            arguments.append("^" + migration["sourceSha"])
        commits = git_output(root, arguments).decode().splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        report.add(
            "GOV-DIFF-001", "Git could not enumerate commits for history-order validation.",
            "Fetch the complete base/head history and rerun the governance gate.",
            evidence={"base": base, "head": head},
        )
        return
    first_implementation: tuple[int, str] | None = None
    for index, commit in enumerate(commits):
        try:
            raw = git_output(root, ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit])
        except subprocess.CalledProcessError:
            report.add(
                "GOV-DIFF-001", f"Git could not inspect commit {commit}.",
                "Fetch complete commit objects and rerun the governance gate.",
                evidence={"commit": commit},
            )
            return
        paths = [path for path in raw.decode("utf-8", "surrogateescape").split("\0") if path]
        if any(not matches(path, governance_patterns) for path in paths):
            first_implementation = (index, commit)
            break
    if first_implementation is None:
        return
    _, commit = first_implementation
    ticket_intent = f"{ticket_root.rstrip('/')}/{ticket_name}/{intent_path}"
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{ticket_intent}"], cwd=root,
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        report.add(
            "GOV-INTENT-003",
            f"{ticket_intent} was absent from the first material implementation commit.",
            "Include the validated intent atomically with the first material commit; do not create a separate plan-only commit.",
            [ticket_intent], {"firstImplementationCommit": commit},
        )


def standard_policy_valid(standard: Any) -> bool:
    return (
        isinstance(standard, dict)
        and set(standard) == {"id", "version"}
        and standard.get("id") == "wellmanifest/new-project"
        and isinstance(standard.get("version"), str)
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", standard["version"]) is not None
    )


def ticket_policy_valid(ticket: Any) -> bool:
    base_fields = {
        "root", "directoryPattern", "requiredFiles", "requiredAgentFiles",
        "activeStatuses", "closedStatuses", "implementationStates", "intentFile",
    }
    if not isinstance(ticket, dict) or set(ticket) not in {
        frozenset(base_fields), frozenset({*base_fields, "nonActiveStatuses"}),
    }:
        return False
    values_valid = ticket_scalar_policy_valid(ticket) and ticket_list_policy_valid(ticket)
    if not values_valid:
        return False
    try:
        re.compile(ticket["directoryPattern"])
    except re.error:
        return False
    return True


def ticket_scalar_policy_valid(ticket: dict[str, Any]) -> bool:
    return all([
        isinstance(ticket.get("root"), str) and bool(ticket["root"]) and relative_pattern(ticket["root"]),
        isinstance(ticket.get("directoryPattern"), str) and bool(ticket["directoryPattern"]),
        isinstance(ticket.get("intentFile"), str) and bool(ticket["intentFile"]) and relative_pattern(ticket["intentFile"]),
    ])


def ticket_list_policy_valid(ticket: dict[str, Any]) -> bool:
    status_groups = [
        set(ticket.get(name, []))
        for name in ("activeStatuses", "nonActiveStatuses", "closedStatuses")
    ]
    return all([
        ticket.get("requiredFiles") == ["README.md", "intent.json"],
        ticket.get("requiredAgentFiles") == [],
        string_list(ticket.get("activeStatuses"), nonempty=True),
        "nonActiveStatuses" not in ticket or string_list(ticket.get("nonActiveStatuses"), nonempty=True),
        string_list(ticket.get("closedStatuses"), nonempty=True),
        string_list(ticket.get("implementationStates"), nonempty=True),
        all(
            left.isdisjoint(right)
            for index, left in enumerate(status_groups)
            for right in status_groups[index + 1:]
        ),
    ])


def docker_policy_valid(docker: Any) -> bool:
    return (
        isinstance(docker, dict)
        and set(docker) == {"required", "dockerfiles", "composeFiles"}
        and isinstance(docker.get("required"), bool)
        and relative_pattern_list(docker.get("dockerfiles"), nonempty=True)
        and relative_pattern_list(docker.get("composeFiles"), nonempty=True)
    )


def repository_policy_valid(repository: Any) -> bool:
    if repository is None:
        return True
    if (
        not isinstance(repository, dict)
        or set(repository) != {"mode", "componentRoots"}
    ):
        return False
    mode = repository.get("mode")
    roots = repository.get("componentRoots")
    if mode not in {"standalone", "monorepo"} or not relative_pattern_list(roots):
        return False
    if len(set(roots)) != len(roots):
        return False
    return (mode == "standalone" and not roots) or (mode == "monorepo" and bool(roots))


def selected_repository_policy_valid(value: Any) -> bool:
    return value is None or policy_error(value) is None


def domain_contract_policy_valid(domain_contracts: Any) -> bool:
    """Keep the optional target contract closed and backwards compatible."""
    return (
        domain_contracts is None
        or domain_contracts == {"mode": "none"}
        or domain_contracts == DOMAIN_CONTRACTS_CQRS
    )


def workstreams_policy_valid(workstreams: Any) -> bool:
    if not isinstance(workstreams, dict) or not workstreams:
        return False
    valid_name = re.compile(r"[a-z0-9][a-z0-9-]*").fullmatch
    return all(
        isinstance(name, str)
        and valid_name(name) is not None
        and isinstance(item, dict)
        and set(item) == {"ownedPaths"}
        and relative_pattern_list(item.get("ownedPaths"), nonempty=True)
        for name, item in workstreams.items()
    )


def integration_policy_valid(integration: Any, workstreams: dict[str, Any]) -> bool:
    return (
        isinstance(integration, dict)
        and set(integration) == {"workstream", "requiredForPaths"}
        and isinstance(integration.get("workstream"), str)
        and relative_pattern_list(integration.get("requiredForPaths"))
        and integration["workstream"] in workstreams
    )


def coordination_policy_valid(coordination: Any) -> bool:
    fields = {
        "mode", "maxActiveTicketsPerWorkstream", "rejectActiveScopeOverlap",
        "workstreams", "integration",
    }
    if not isinstance(coordination, dict) or set(coordination) != fields:
        return False
    limit = coordination.get("maxActiveTicketsPerWorkstream")
    settings_valid = (
        coordination.get("mode") == "workstreams"
        and isinstance(limit, int)
        and not isinstance(limit, bool)
        and limit >= 1
        and isinstance(coordination.get("rejectActiveScopeOverlap"), bool)
    )
    workstreams = coordination.get("workstreams")
    return (
        settings_valid
        and workstreams_policy_valid(workstreams)
        and integration_policy_valid(coordination.get("integration"), workstreams)
    )


def common_manifest_policy_valid(manifest: dict[str, Any]) -> bool:
    approvals = manifest.get("trustedApprovalSources")
    return (
        standard_policy_valid(manifest.get("standard"))
        and relative_pattern_list(manifest.get("requiredFiles"))
        and relative_pattern_list(manifest.get("governancePaths"))
        and string_list(approvals, nonempty=True)
        and set(approvals) <= {
            "github-review", "github-app-review", "signed-attestation",
        }
        and approval_evidence_config_valid(manifest.get("approvalEvidence"))
        and ticket_policy_valid(manifest.get("ticket"))
        and docker_policy_valid(manifest.get("docker"))
    )


def basic_manifest_valid(manifest: Any) -> bool:
    if not isinstance(manifest, dict) or manifest.get("schema") not in {
        "new-project.governance/v1", "new-project.governance/v2",
    }:
        return False
    common_valid = common_manifest_policy_valid(manifest)
    if not common_valid or manifest["schema"] == "new-project.governance/v1":
        return common_valid
    if "nonActiveStatuses" not in manifest["ticket"]:
        return False
    allowed_root_keys = {
        "$schema", "schema", "standard", "requiredFiles", "governancePaths",
        "trustedApprovalSources", "approvalEvidence", "ticket", "docker",
        "repository", "domainContracts", "coordination", "delivery", "stacks",
        "repositoryPolicy",
    }
    coordination = manifest.get("coordination")
    delivery = manifest.get("delivery")
    return (
        set(manifest) <= allowed_root_keys
        and repository_policy_valid(manifest.get("repository"))
        and selected_repository_policy_valid(manifest.get("repositoryPolicy"))
        and domain_contract_policy_valid(manifest.get("domainContracts"))
        and string_list(manifest.get("stacks", []))
        and set(manifest.get("stacks", [])) <= {"node", "python", "go", "rust", "java", "docker", "frontend", "terraform", "kubernetes"}
        and coordination_policy_valid(coordination)
        and (delivery is None or delivery_policy_valid(delivery))
    )


def lock_standard_valid(standard: Any, expected_version: str) -> bool:
    return isinstance(standard, dict) and (
        set(standard) == {"id", "version", "sourceRepository", "sourceRevision", "publicationStatus"}
        and standard.get("id") == "wellmanifest/new-project"
        and standard.get("version") == expected_version
        and standard.get("sourceRepository") == "wellmanifest/new-project"
        and isinstance(standard.get("sourceRevision"), str)
        and re.fullmatch(r"[0-9a-f]{40}", standard["sourceRevision"]) is not None
        and standard.get("publicationStatus") == "published"
    )


def load_managed_lock(lock_path: Path, manifest: dict[str, Any]) -> dict[str, str]:
    lock = load_json(lock_path)
    managed = lock["managedFiles"]
    if (
        lock.get("schema") != "new-project.lock/v1"
        or set(lock) != {"schema", "standard", "managedFiles"}
        or not isinstance(managed, dict)
    ):
        raise ValueError("unsupported lock schema")
    if not lock_standard_valid(lock["standard"], manifest["standard"]["version"]):
        raise ValueError("lock must identify the published immutable standard revision")
    if not all(
            isinstance(raw_path, str)
            and relative_pattern(raw_path)
            and isinstance(digest, str)
            and re.fullmatch(r"[a-f0-9]{64}", digest)
            for raw_path, digest in managed.items()
    ):
        raise ValueError("managedFiles must map repository-relative paths to lowercase SHA-256 digests")
    return managed


def check_managed_file(root: Path, raw_path: str, expected: str, report: Report) -> None:
    try:
        path = safe_repo_path(root, raw_path)
    except ValueError as error:
        report.add("GOV-SYNC-001", str(error), "Use repository-relative managed paths.", [raw_path])
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if actual != expected:
        report.add(
            "GOV-SYNC-001", f"Managed governance file digest differs: {raw_path}",
            "Restore the pinned file or perform an explicit standard upgrade and regenerate the lock.",
            [raw_path], {"expectedSha256": expected, "actualSha256": actual},
        )


def extension_error(required: Any, candidate: Any, path: str = "$") -> str | None:
    if isinstance(required, dict):
        if not isinstance(candidate, dict):
            return f"{path} must remain an object"
        for key, value in required.items():
            if key not in candidate:
                return f"{path}/{key} is required by the managed base"
            error = extension_error(value, candidate[key], f"{path}/{key}")
            if error:
                return error
        return None
    if isinstance(required, list):
        if not isinstance(candidate, list):
            return f"{path} must remain an array"
        for value in required:
            if value not in candidate:
                return f"{path} removed a value required by the managed base"
        return None
    if candidate != required:
        return f"{path} differs from the managed base"
    return None


def check_lock(
    root: Path,
    lock_path: Path | None,
    manifest: dict[str, Any],
    report: Report,
) -> None:
    if lock_path is None:
        return
    if not lock_path.is_file():
        report.add(
            "GOV-SYNC-001", "Governance lock file is missing.",
            "Copy the versioned manifest lock from the approved standard adoption.",
            [rel(root, lock_path)] if lock_path.is_relative_to(root) else [],
        )
        return
    try:
        managed = load_managed_lock(lock_path, manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        report.add("GOV-SYNC-001", f"Governance lock is invalid: {error}", "Regenerate the lock from a trusted standard release.", [rel(root, lock_path)])
        return
    for raw_path, expected in sorted(managed.items()):
        check_managed_file(root, raw_path, expected, report)
    package_path = root / ".governance/package-manifest.json"
    if not package_path.is_file():
        return
    try:
        strategies = package_strategies(package_path.read_bytes())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        report.add(
            "GOV-SYNC-001", f"Governance package manifest is invalid: {error}",
            "Restore the pinned package manifest through an explicit standard upgrade.",
            [rel(root, package_path)],
        )
        return
    manifest_target = ".governance/manifest.json"
    base_target = ".governance/manifest.base.json"
    if strategies.get(manifest_target) != "extendable":
        return
    if strategies.get(base_target) != "managed" or base_target not in managed:
        report.add(
            "GOV-SYNC-001", "Extendable governance manifest has no hash-bound managed base.",
            "Adopt the complete published package including manifest.base.json.",
            [base_target, manifest_target],
        )
        return
    try:
        base = load_json(safe_repo_path(root, base_target))
        error = extension_error(base, manifest)
    except (OSError, ValueError, json.JSONDecodeError) as load_error:
        error = f"managed manifest base is invalid: {load_error}"
    if error:
        report.add(
            "GOV-SYNC-001", f"Target governance manifest violates its managed base: {error}",
            "Restore standard-owned values; keep target changes inside the declared extension fields.",
            [base_target, manifest_target],
        )


def parse_ticket_state(readme: Path) -> tuple[str | None, str | None]:
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return None, None
    return parse_ticket_state_text(text)


def parse_ticket_state_text(text: str) -> tuple[str | None, str | None]:
    status_match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", text)
    state_match = re.search(r"(?mi)^-[ \t]+\*\*Workflow state\*\*:[ \t]*([A-Z_]+)[ \t]*$", text)
    return (
        status_match.group(1).upper() if status_match else None,
        state_match.group(1).upper() if state_match else None,
    )


def ticket_directories(root: Path, config: dict[str, Any]) -> list[Path]:
    ticket_root = safe_repo_path(root, config["root"])
    pattern = re.compile(config["directoryPattern"])
    if not ticket_root.is_dir():
        return []
    return sorted(
        path for path in ticket_root.iterdir()
        if path.is_dir() and not path.is_symlink() and pattern.fullmatch(path.name)
    )


def intent_common_error(intent: dict[str, Any], ticket_name: str) -> str | None:
    if intent.get("ticket") != ticket_name:
        return "intent schema or ticket identity differs"
    if not isinstance(intent.get("summary"), str) or not intent["summary"].strip():
        return "intent summary is blank"
    for field_name in ("allowedPaths", "forbiddenPaths", "stacks"):
        if not string_list(intent.get(field_name)):
            return f"intent {field_name} must be a list of non-blank strings"
    if not intent["allowedPaths"]:
        return "intent allowedPaths is empty"
    for field_name in ("allowedPaths", "forbiddenPaths"):
        if not all(relative_pattern(value) for value in intent[field_name]):
            return f"intent {field_name} must contain repository-relative patterns"
    return None


def ticket_id_list_error(intent: dict[str, Any], field_name: str) -> str | None:
    values = intent.get(field_name)
    if not isinstance(values, list) or not all(
        isinstance(value, str) and re.fullmatch(r"ticket-[0-9]{3,}", value)
        for value in values
    ):
        return f"intent {field_name} must contain ticket IDs"
    return f"intent {field_name} contains duplicates" if len(values) != len(set(values)) else None


def intent_v2_error(intent: dict[str, Any], ticket_name: str) -> str | None:
    workstream = intent.get("workstream")
    if not isinstance(workstream, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", workstream):
        return "intent workstream is invalid"
    for field_name in ("dependsOn", "conflictsWith"):
        error = ticket_id_list_error(intent, field_name)
        if error:
            return error
    integration = intent.get("integrationTicket")
    if integration is not None and (not isinstance(integration, str) or not re.fullmatch(r"ticket-[0-9]{3,}", integration)):
        return "intent integrationTicket must be null or a ticket ID"
    if integration == ticket_name:
        return "intent integrationTicket cannot reference its own ticket"
    if "delivery" in intent:
        error = delivery_intent_error(intent["delivery"])
        if error:
            return error
    if "physicalChanges" in intent:
        error = physical_changes_error(intent["physicalChanges"])
        if error:
            return error
    if "placement" in intent:
        return placement_error(intent["placement"])
    return None


def intent_classification_error(value: Any) -> str | None:
    if not isinstance(value, dict) or set(value) != {"kind", "priority", "origin"}:
        return "intent classification must contain kind, priority and origin"
    if value.get("kind") not in {"BUG", "FEATURE", "SERVICE"}:
        return "intent classification kind is invalid"
    if value.get("priority") not in {"P0", "P1", "P2", "P3"}:
        return "intent classification priority is invalid"
    if value.get("origin") not in {"regression", "requested", "health"}:
        return "intent classification origin is invalid"
    return None


def intent_fields_error(intent: Any) -> str | None:
    v1_fields = {"schema", "ticket", "summary", "allowedPaths", "forbiddenPaths", "stacks"}
    v2_fields = v1_fields | {"workstream", "dependsOn", "conflictsWith", "integrationTicket"}
    if not isinstance(intent, dict) or intent.get("schema") not in {
        "new-project.intent/v1", "new-project.intent/v2", "new-project.intent/v3",
    }:
        return "unsupported intent schema"
    expected = v1_fields if intent["schema"] == "new-project.intent/v1" else v2_fields
    if intent["schema"] == "new-project.intent/v3":
        expected |= {"classification"}
    optional = set() if intent["schema"] == "new-project.intent/v1" else {"delivery", "placement", "physicalChanges"}
    if not expected <= set(intent) <= expected | optional:
        return f"intent must contain exactly the {intent['schema'].rsplit('/', 1)[-1]} fields"
    return None


def validate_intent(path: Path, ticket_name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        intent = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return None, str(error)
    return validate_intent_value(intent, ticket_name)


def validate_intent_value(intent: Any, ticket_name: str) -> tuple[dict[str, Any] | None, str | None]:
    error = intent_fields_error(intent)
    if error:
        return None, error
    assert isinstance(intent, dict)
    error = intent_common_error(intent, ticket_name)
    if error:
        return None, error
    if intent["schema"] in {"new-project.intent/v2", "new-project.intent/v3"}:
        error = intent_v2_error(intent, ticket_name)
        if error:
            return None, error
    if intent["schema"] == "new-project.intent/v3":
        error = intent_classification_error(intent.get("classification"))
        if error:
            return None, error
    return intent, None


def load_ticket_records(directories: list[Path], config: dict[str, Any]) -> list[TicketRecord]:
    records = []
    for directory in directories:
        status, workflow = parse_ticket_state(directory / "README.md")
        intent, error = validate_intent(directory / config["intentFile"], directory.name)
        records.append(TicketRecord(directory, status, workflow, intent, error))
    return records


def load_repository_policy_ticket(
    root: Path,
    manifest: dict[str, Any],
    report: Report,
) -> TicketRecord | None:
    """Project a declared external ticket into the normal scope checker.

    The projection carries only bounded intent and current state.  It never
    treats a local adapter as trusted approval or as a replacement for the
    external ticket system's protected publication receipt.
    """
    policy = selected_policy(manifest)
    if policy.get("tickets", {}).get("backend") != "planfile":
        return None
    adapter, error = load_adapter(root, manifest)
    raw_path = policy.get("tickets", {}).get("adapterPath", ".governance/ticket-adapter.json")
    if error or adapter is None:
        report.add(
            "GOV-TICKET-EXTERNAL-001",
            f"External ticket adapter is invalid: {error or 'missing adapter'}",
            "Create or refresh the repository-local adapter from the active Planfile ticket before changing implementation files.",
            [str(raw_path)],
        )
        return None
    intent = {
        "schema": "new-project.intent/v3",
        "ticket": adapter["ticket"],
        "summary": adapter["summary"],
        "allowedPaths": adapter["allowedPaths"],
        "forbiddenPaths": adapter["forbiddenPaths"],
        "stacks": [],
        "workstream": adapter["workstream"],
        "dependsOn": [],
        "conflictsWith": [],
        "integrationTicket": None,
        "classification": {"kind": "SERVICE", "priority": "P2", "origin": "requested"},
    }
    return TicketRecord(
        root / str(raw_path),
        adapter["status"],
        adapter["workflow"],
        intent,
        None,
        external=True,
    )


def load_external_ticket_records(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> list[TicketRecord] | None:
    database = getattr(args, "ticket_database", None)
    snapshot = getattr(args, "ticket_snapshot", None)
    pin = getattr(args, "ticket_snapshot_sha256", None)
    if not any((database, snapshot, pin)):
        try:
            mode = git_output(root, ["config", "--local", "--get", "new-project.ticketStorage"]).decode().strip()
        except subprocess.CalledProcessError as error:
            # Explicit-path validation also supports an uninitialized scaffold.
            # Such a directory has no clone-local opt-in; preserve file mode.
            no_repository = error.returncode == 128 and b"--local can only be used inside a git repository" in error.stderr
            if error.returncode != 1 and not no_repository:
                raise
            mode = "files"
        if mode == "files":
            return None
        if mode != "sqlite":
            raise ValueError("unknown ticket storage mode")
    spec = importlib.util.spec_from_file_location("new_project_ticket_input", Path(__file__).with_name("ticket_input.py"))
    if spec is None or spec.loader is None:
        raise ValueError("managed ticket input reader missing")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    if not any((database, snapshot, pin)):
        database = module.primary_database(root)
    source = module.load_input(root, database=database, snapshot=snapshot, snapshot_sha256=pin,
        repository=args.expected_repository, base=args.base, head=args.head,
        protected=args.actor == "ci" or args.enforce_approval)
    records = []
    for item in source:
        files = item["files"]
        readme = files.get("README.md", (b"", "100644"))[0].decode("utf-8")
        status, workflow = parse_ticket_state_text(readme)
        raw_intent = files.get(config["intentFile"], (b"null", "100644"))[0]
        try:
            intent, error = validate_intent_value(module.parse_json(raw_intent), item["ticket"])
        except (ValueError, UnicodeError):
            intent, error = None, "invalid database intent JSON"
        records.append(TicketRecord(root / config["root"] / item["ticket"], status, workflow, intent, error, files))
    return records


def active_ticket_records(
    root: Path,
    config: dict[str, Any],
    records: list[TicketRecord],
    report: Report | None = None,
) -> list[TicketRecord]:
    """Return live reservations from the shared status/receipt resolver."""
    active_statuses = set(config.get("activeStatuses", ACTIVE_DEFAULT))
    active: list[TicketRecord] = []
    for record in records:
        if record.status not in active_statuses:
            continue
        try:
            resolution = resolve_ticket_activity(root, record.directory, active_statuses,
                **({"status_override": record.status} if record.files is not None else {}))
        except ActivityError as error:
            # A broken optional cache must never fabricate terminal authority.
            # Keep the projection active and expose one stable, recoverable error.
            active.append(record)
            if report is not None and not any(
                finding.code == TICKET_ACTIVITY_ERROR for finding in report.findings
            ):
                report.add(
                    TICKET_ACTIVITY_ERROR,
                    f"Ticket activity could not be resolved safely: {error}",
                    "Reconcile or quarantine the clone-external registry from protected evidence; follow error/GOV-TICKET-ACTIVITY.md.",
                    [rel(root, record.directory / "README.md")],
                    {"ticket": record.directory.name, "fallback": "remain-active"},
                )
            continue
        if resolution.active:
            active.append(record)
    return active


def repository_files(root: Path, changed: list[str]) -> list[str]:
    try:
        raw = git_output(root, ["ls-files", "-co", "--exclude-standard", "-z"])
        files = raw.decode("utf-8", "surrogateescape").split("\0")
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [rel(root, path) for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]
    return sorted({*files, *changed} - {""})


def valid_active_tickets(
    root: Path,
    config: dict[str, Any],
    active: list[TicketRecord],
    workstreams: dict[str, Any],
    report: Report,
) -> list[TicketRecord]:
    valid: list[TicketRecord] = []
    for record in active:
        intent_path = rel(root, record.directory / config["intentFile"])
        if record.intent_error:
            report.add(
                "GOV-INTENT-002", f"Ticket intent is invalid: {record.intent_error}",
                "Create a valid new-project.intent/v3 file before implementation.", [intent_path],
            )
            continue
        assert record.intent is not None
        if record.intent["schema"] != "new-project.intent/v3":
            report.add(
                "GOV-INTENT-002", f"Active ticket {record.directory.name} lacks deterministic intent/v3 classification.",
                "Migrate the active ticket to intent/v3 and declare kind, priority and origin; archived v1/v2 tickets remain readable.", [intent_path],
            )
            continue
        workstream = record.intent["workstream"]
        if workstream not in workstreams:
            report.add(
                "GOV-WORKSTREAM-001", f"Active ticket {record.directory.name} declares unknown workstream '{workstream}'.",
                "Choose a workstream declared in the pinned governance manifest and obtain fresh plan approval.", [intent_path],
                {"workstream": workstream, "knownWorkstreams": sorted(workstreams)},
            )
            continue
        valid.append(record)
    return valid


def check_workstream_limits(
    root: Path,
    valid_active: list[TicketRecord],
    limit: int,
    report: Report,
) -> None:
    grouped: dict[str, list[TicketRecord]] = {}
    for record in valid_active:
        grouped.setdefault(record.intent["workstream"], []).append(record)  # type: ignore[index]
    for workstream, members in sorted(grouped.items()):
        if len(members) > limit:
            report.add(
                "GOV-WORKSTREAM-002", f"Workstream '{workstream}' has {len(members)} active tickets; limit is {limit}.",
                "Keep active tickets within the configured limit, narrow scopes, or close/block-route competing work.",
                [rel(root, member.directory) for member in members],
                {"workstream": workstream, "tickets": [member.directory.name for member in members], "limit": limit},
            )


def dependency_graph(
    root: Path,
    records: list[TicketRecord],
    config: dict[str, Any],
    report: Report,
) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for record in records:
        if record.intent and record.intent.get("schema") in {"new-project.intent/v2", "new-project.intent/v3"}:
            graph[record.directory.name] = list(record.intent["dependsOn"])
            if record.directory.name in record.intent["dependsOn"] or record.directory.name in record.intent["conflictsWith"]:
                report.add(
                    "GOV-DEPENDENCY-001", f"Ticket {record.directory.name} references itself as a dependency or conflict.",
                    "Remove the self-reference and keep only directed edges to other tickets.", [rel(root, record.directory / config["intentFile"])],
                )
    return graph


def find_dependency_cycle(graph: dict[str, list[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: list[str] = []

    def visit(name: str, trail: list[str]) -> bool:
        if name in visiting:
            cycle.extend(trail[trail.index(name):] + [name])
            return True
        if name in visited:
            return False
        visiting.add(name)
        for dependency in graph.get(name, []):
            if dependency in graph and visit(dependency, [*trail, dependency]):
                return True
        visiting.remove(name)
        visited.add(name)
        return False

    for name in sorted(graph):
        if visit(name, [name]):
            return cycle
    return []


def check_dependency_cycle(graph: dict[str, list[str]], report: Report) -> None:
    cycle = find_dependency_cycle(graph)
    if cycle:
        report.add(
            "GOV-DEPENDENCY-001", "Ticket dependency graph contains a cycle.",
            "Break the cycle by choosing a directed implementation order or an explicit integration ticket.",
            [f"project/{item}/intent.json" for item in sorted(set(cycle))], {"cycle": cycle},
        )


def integration_reference_valid(record: TicketRecord | None, required_workstream: str) -> bool:
    return bool(
        record is not None
        and record.intent is not None
        and record.intent.get("schema") in {"new-project.intent/v2", "new-project.intent/v3"}
        and record.intent.get("workstream") == required_workstream
        and record.status != "CANCELLED"
    )


def adoption_path_list_valid(paths: Any, pattern: str) -> bool:
    return (
        isinstance(paths, list)
        and bool(paths)
        and len(paths) == len(set(paths))
        and all(
            isinstance(path, str)
            and re.fullmatch(pattern, path) is not None
            and relative_pattern(path)
            for path in paths
        )
    )


def adoption_binding_registry(root: Path) -> tuple[list[str], list[str]] | None:
    registry_path = next(
        (
            root / candidate
            for candidate in (
                ".governance/adoption-bindings.json",
                "governance/adoption-bindings.json",
            )
            if (root / candidate).is_file()
        ),
        None,
    )
    if registry_path is None:
        return None
    try:
        registry = load_json(registry_path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    workflow_paths = registry.get("revisionBoundWorkflowPaths")
    target_patterns = registry.get("digestBoundTargetPatterns")
    valid = (
        set(registry) == {
            "schema", "revisionBoundWorkflowPaths", "digestBoundTargetPatterns",
        }
        and registry.get("schema") == "new-project.adoption-bindings/v2"
        and adoption_path_list_valid(workflow_paths, r"[A-Za-z0-9._/-]+\.ya?ml")
        and adoption_path_list_valid(target_patterns, r"\.github/workflows/[A-Za-z0-9._/*?-]+\.ya?ml")
    )
    if not valid:
        return None
    return workflow_paths, target_patterns


def add_adoption_workflow_bindings(root: Path, revision: Any, registry: Any, bindings: set[str]) -> None:
    if registry is not None and isinstance(revision, str):
        try:
            workflow_paths, _target_patterns = registry
            if re.fullmatch(r"[a-f0-9]{40}", revision) is not None:
                uses_pattern = re.compile(
                    r"(?m)^\s*uses:\s*wellmanifest/new-project/\.github/workflows/"
                    r"governance\.yml@([a-f0-9]{40})\s*(?:#.*)?$"
                )
                ref_pattern = re.compile(
                    r"(?m)^\s*standard-ref:\s*([a-f0-9]{40})\s*(?:#.*)?$"
                )
                for raw_path in workflow_paths:
                    workflow_path = safe_repo_path(root, raw_path)
                    if not workflow_path.is_file():
                        continue
                    content = workflow_path.read_text(encoding="utf-8")
                    if uses_pattern.findall(content) == [revision] and ref_pattern.findall(content) == [revision]:
                        bindings.add(raw_path)
        except (OSError, UnicodeError, TypeError, ValueError):
            pass  # Lock and ownership validation remain fail closed.


def add_adoption_packaging_bindings(root: Path, bindings: set[str]) -> None:
    contract_path = next(
        (
            root / candidate
            for candidate in (".governance/agent-hosts.json", "governance/agent-hosts.json")
            if (root / candidate).is_file()
        ),
        None,
    )
    if contract_path is not None:
        try:
            contract = load_json(contract_path)
            packaging = contract.get("packaging", {})
            if isinstance(packaging, dict):
                for binding in packaging.values():
                    marker = binding.get("marker") if isinstance(binding, dict) else None
                    if isinstance(marker, str) and relative_pattern(marker) and (root / marker).is_file():
                        bindings.add(marker)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass  # The authoritative agent-host validator reports malformed contracts.


def add_adoption_docker_bindings(root: Path, manifest: dict[str, Any], bindings: set[str]) -> None:
    docker = manifest.get("docker", {})
    if isinstance(docker, dict) and docker.get("required") is True:
        for field in ("dockerfiles", "composeFiles"):
            candidates = docker.get(field, [])
            if isinstance(candidates, list):
                bindings.update(
                    path for path in candidates
                    if isinstance(path, str) and relative_pattern(path) and (root / path).is_file()
                )


def atomic_adoption_binding_paths(
    root: Path,
    manifest: dict[str, Any],
    intent: dict[str, Any],
) -> set[str]:
    """Return the closed set of target-owned files required during adoption."""
    delivery = intent.get("delivery")
    if not isinstance(delivery, dict) or "standardAdoption" not in delivery:
        return set()
    adoption = delivery["standardAdoption"]
    if not isinstance(adoption, dict):
        return set()
    bindings: set[str] = set()
    revision = adoption.get("toRevision")
    registry = adoption_binding_registry(root)
    add_adoption_workflow_bindings(root, revision, registry, bindings)
    add_adoption_packaging_bindings(root, bindings)
    add_adoption_docker_bindings(root, manifest, bindings)
    return bindings


def dependency_is_terminal(
    prerequisite: TicketRecord | None, dependency: str,
    closed_statuses: set[str], active_statuses: set[str], active_names: set[str],
) -> bool:
    verified_terminal = bool(
        prerequisite
        and prerequisite.status in active_statuses
        and dependency not in active_names
    )
    return prerequisite is not None and (
        prerequisite.status in closed_statuses or verified_terminal
    )


def check_active_relationships(
    root: Path,
    config: dict[str, Any],
    coordination: dict[str, Any],
    records: list[TicketRecord],
    active: list[TicketRecord],
    valid_active: list[TicketRecord],
    report: Report,
) -> None:
    closed_statuses = set(config.get("closedStatuses", []))
    active_statuses = set(config.get("activeStatuses", ACTIVE_DEFAULT))
    by_name = {record.directory.name: record for record in records}
    active_names = {record.directory.name for record in active}
    conflict_pairs: set[tuple[str, str]] = set()
    integration_config = coordination["integration"]
    for record in valid_active:
        assert record.intent is not None
        for dependency in record.intent["dependsOn"]:
            prerequisite = by_name.get(dependency)
            if not dependency_is_terminal(prerequisite, dependency, closed_statuses, active_statuses, active_names):
                report.add(
                    "GOV-DEPENDENCY-002", f"Active ticket {record.directory.name} has unfinished or missing dependency {dependency}.",
                    "Complete the prerequisite or return the dependent ticket to a non-active planning backlog.",
                    [rel(root, record.directory / config["intentFile"])],
                    {"ticket": record.directory.name, "dependency": dependency, "dependencyStatus": prerequisite.status if prerequisite else None},
                )
        for conflict in record.intent["conflictsWith"]:
            if conflict in active_names:
                conflict_pairs.add(tuple(sorted((record.directory.name, conflict))))
        integration_name = record.intent["integrationTicket"]
        if integration_name is not None:
            integration_record = by_name.get(integration_name)
            valid_integration = integration_reference_valid(integration_record, integration_config["workstream"])
            if not valid_integration:
                report.add(
                    "GOV-INTEGRATION-001",
                    f"Ticket {record.directory.name} references an invalid integration ticket {integration_name}.",
                    "Reference an existing, non-cancelled ticket in the manifest-declared integration workstream.",
                    [rel(root, record.directory / config["intentFile"])],
                    {"ticket": record.directory.name, "integrationTicket": integration_name, "requiredWorkstream": integration_config["workstream"]},
                )
    for first, second in sorted(conflict_pairs):
        report.add(
            "GOV-CONFLICT-001", f"Conflicting tickets {first} and {second} are active together.",
            "Serialize the tickets or resolve the conflict through an approved integration plan.",
            [f"project/{first}/intent.json", f"project/{second}/intent.json"],
        )


def unowned_scope_files(
    record: TicketRecord, files: list[str], governance_patterns: list[str],
    adoption_bindings: set[str], owned_paths: list[str],
) -> list[str]:
    assert record.intent is not None
    return [
        path for path in files
        if not matches(path, governance_patterns)
        and matches(path, record.intent["allowedPaths"])
        and not matches(path, record.intent["forbiddenPaths"])
        and path not in adoption_bindings
        and not matches(path, owned_paths)
    ]


def check_workstream_claims(
    root: Path,
    manifest: dict[str, Any],
    config: dict[str, Any],
    workstreams: dict[str, Any],
    governance_patterns: list[str],
    files: list[str],
    valid_active: list[TicketRecord],
    verified_adoption_paths: set[str],
    report: Report,
) -> None:
    for record in valid_active:
        assert record.intent is not None
        owned_paths = workstreams[record.intent["workstream"]]["ownedPaths"]
        adoption_bindings = (
            atomic_adoption_binding_paths(root, manifest, record.intent)
            | verified_adoption_paths
        )
        implementation_patterns = [
            pattern for pattern in record.intent["allowedPaths"]
            if not matches(pattern, governance_patterns)
        ]
        unowned_patterns = [
            pattern for pattern in implementation_patterns
            if pattern not in adoption_bindings
            and not any(pattern_covered_by(pattern, owned) for owned in owned_paths)
        ]
        unowned_claims = unowned_scope_files(record, files, governance_patterns, adoption_bindings, owned_paths)
        if unowned_patterns or unowned_claims:
            report.add(
                "GOV-WORKSTREAM-003", f"Ticket {record.directory.name} claims paths outside workstream '{record.intent['workstream']}'.",
                "Narrow allowedPaths or route the paths to their owning workstream/integration ticket and obtain fresh approval.",
                sorted({*unowned_patterns, *unowned_claims})[:20],
                {
                    "ticket": record.directory.name,
                    "workstream": record.intent["workstream"],
                    "ownedPaths": owned_paths,
                    "unownedPatterns": unowned_patterns,
                    "concretePathCount": len(unowned_claims),
                },
            )


def ticket_shared_files(
    first: TicketRecord,
    second: TicketRecord,
    files: list[str],
    governance_patterns: list[str],
) -> list[str]:
    assert first.intent is not None and second.intent is not None
    return [
        path for path in files
        if not matches(path, governance_patterns)
        and matches(path, first.intent["allowedPaths"])
        and not matches(path, first.intent["forbiddenPaths"])
        and matches(path, second.intent["allowedPaths"])
        and not matches(path, second.intent["forbiddenPaths"])
    ]


def ticket_overlapping_patterns(
    first: TicketRecord,
    second: TicketRecord,
    governance_patterns: list[str],
) -> list[str]:
    assert first.intent is not None and second.intent is not None
    first_patterns = [pattern for pattern in first.intent["allowedPaths"] if not matches(pattern, governance_patterns)]
    second_patterns = [pattern for pattern in second.intent["allowedPaths"] if not matches(pattern, governance_patterns)]
    return sorted({
        f"{first_pattern} <-> {second_pattern}"
        for first_pattern in first_patterns
        for second_pattern in second_patterns
        if patterns_may_overlap(first_pattern, second_pattern)
    })


def check_scope_overlaps(
    valid_active: list[TicketRecord],
    files: list[str],
    governance_patterns: list[str],
    report: Report,
) -> None:
    for index, first in enumerate(valid_active):
        for second in valid_active[index + 1:]:
            shared_files = ticket_shared_files(first, second, files, governance_patterns)
            overlapping_patterns = ticket_overlapping_patterns(first, second, governance_patterns)
            if shared_files or overlapping_patterns:
                report.add(
                    "GOV-WORKSTREAM-004",
                    f"Active ticket scopes overlap: {first.directory.name} and {second.directory.name}.",
                    "Narrow one allowedPaths declaration, serialize the work, or route the shared contract through integration.",
                    shared_files[:20],
                    {"tickets": [first.directory.name, second.directory.name], "overlappingPatterns": overlapping_patterns, "concretePathCount": len(shared_files)},
                )


def check_ticket_statuses(
    root: Path,
    config: dict[str, Any],
    records: list[TicketRecord],
    report: Report,
) -> None:
    allowed = set(config.get("activeStatuses", ACTIVE_DEFAULT))
    allowed.update(config.get("nonActiveStatuses", []))
    allowed.update(config.get("closedStatuses", []))
    for record in records:
        if record.status not in allowed:
            report.add(
                "GOV-STATUS-001",
                f"Ticket {record.directory.name} has unknown status '{record.status or 'MISSING'}'.",
                "Use a status declared in activeStatuses, nonActiveStatuses or closedStatuses.",
                [rel(root, record.directory / "README.md")],
                {
                    "ticket": record.directory.name,
                    "status": record.status,
                    "allowedStatuses": sorted(allowed),
                },
            )


def check_coordination(
    root: Path,
    manifest: dict[str, Any],
    records: list[TicketRecord],
    changed: list[str],
    verified_adoption_paths: set[str],
    report: Report,
    active_records: list[TicketRecord] | None = None,
) -> None:
    coordination = manifest.get("coordination")
    if not isinstance(coordination, dict):
        return
    config = manifest["ticket"]
    check_ticket_statuses(root, config, records, report)
    active = active_records if active_records is not None else active_ticket_records(root, config, records, report)
    if not changed:
        # Ticket records merged into the clean default-branch snapshot are
        # authorization history, not evidence of concurrent live writers. A
        # current non-empty change selects its lease below; implementation
        # authorization remains independently fail-closed in check_change_gate.
        active = []
    else:
        changed_active = [
            record for record in active
            if any(path.startswith(f"{rel(root, record.directory).rstrip('/')}/") for path in changed)
        ]
        if changed_active:
            active = changed_active
        elif len(active) > 1:
            path_active = [
                record for record in active
                if record.intent is not None and any(
                    matches(path, record.intent["allowedPaths"])
                    and not matches(path, record.intent["forbiddenPaths"])
                    for path in changed
                )
            ]
            active = path_active if len(path_active) == 1 else active
    workstreams = coordination["workstreams"]
    valid_active = valid_active_tickets(root, config, active, workstreams, report)
    check_workstream_limits(root, valid_active, coordination["maxActiveTicketsPerWorkstream"], report)
    check_dependency_cycle(dependency_graph(root, records, config, report), report)
    check_active_relationships(root, config, coordination, records, active, valid_active, report)
    files = repository_files(root, changed)
    governance_patterns = manifest["governancePaths"]
    check_workstream_claims(
        root, manifest, config, workstreams, governance_patterns, files,
        valid_active, verified_adoption_paths, report,
    )
    if coordination["rejectActiveScopeOverlap"]:
        check_scope_overlaps(valid_active, files, governance_patterns, report)


def contract_record_index(
    value: Any,
    identity: str,
    fields: set[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty record list")
    result: dict[str, dict[str, Any]] = {}
    for record in value:
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError(f"{label} records must have closed fields")
        identifier = record.get(identity)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError(f"{label} identifiers must be nonempty and unique")
        result[identifier] = record
    return result


def contract_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a unique string list")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a unique string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must be a unique string list")
    return value


def contract_reference_file(root: Path, base: Path, reference: Any, label: str) -> None:
    if not isinstance(reference, str) or not reference:
        raise ValueError(f"{label} reference must be a nonempty string")
    raw_path = reference.split("#", 1)[0]
    if not raw_path:
        raise ValueError(f"{label} reference needs a transport file")
    target = (base / raw_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} reference escapes the repository") from error
    if not target.is_file():
        raise ValueError(f"{label} transport file is missing")


def contract_document(root: Path, actual: Any, expected: str, label: str) -> None:
    if actual != expected or not safe_repo_path(root, expected).is_file():
        raise ValueError(f"{label} documentation must match its stable identifier")


def validate_domain_source(root: Path, source: Any) -> None:
    if not isinstance(source, dict) or set(source) != {
        "commandsAndQueries", "events", "errors", "models", "transportRule",
    }:
        raise ValueError("operation source-of-truth fields are not closed")
    if source.get("commandsAndQueries") != "operations/index.json":
        raise ValueError("commands and queries have a noncanonical source")
    if source.get("events") != "events/index.json" or source.get("errors") != "error/index.json":
        raise ValueError("event or error registry binding is invalid")
    if not isinstance(source.get("models"), str) or not source["models"]:
        raise ValueError("transport model source must be explicit")
    contract_reference_file(root, root, source["models"], "model source")
    if not isinstance(source.get("transportRule"), str) or not source["transportRule"]:
        raise ValueError("transport authority boundary must be explicit")


def validate_domain_operation_header(root: Path, operations: dict[str, Any]):
    operation_fields = {
        "$schema", "schema", "domain", "sourceOfTruth", "invariants",
        "models", "commands", "queries", "projections",
    }
    if set(operations) != operation_fields:
        raise ValueError("operation registry fields are not closed")
    if operations.get("schema") != "wellmanifest.operations/v1":
        raise ValueError("operation registry schema family is invalid")
    contract_reference_file(
        root, root / "operations", operations.get("$schema"), "operation schema",
    )
    domain = operations.get("domain")
    if not isinstance(domain, str) or not domain:
        raise ValueError("operation domain must be nonempty")
    validate_domain_source(root, operations.get("sourceOfTruth"))
    if operations.get("invariants") != {
        "commandEffectsBecomeFactsOnlyThroughEvents": True,
        "queriesAreEffectFree": True,
        "replayExecutesEffects": False,
        "eventsCarryAuthority": False,
        "modelsCarryAuthority": False,
    }:
        raise ValueError("CQRS safety invariants are invalid")
    return domain


def validate_domain_models(root: Path, operations: dict[str, Any]):
    models = contract_record_index(
        operations.get("models"), "id",
        {"id", "schemaRef", "transport", "authority"}, "models",
    )
    for model in models.values():
        if model["transport"] not in {"json-schema", "protobuf"}:
            raise ValueError("model transport is unsupported")
        if model["authority"] is not False:
            raise ValueError("transport model must not carry authority")
        contract_reference_file(root, root / "operations", model["schemaRef"], "model")
    return models


def validate_domain_commands(operations: dict[str, Any], models: dict[str, Any]):
    commands = contract_record_index(
        operations.get("commands"), "id",
        {
            "id", "uri", "intent", "inputModel", "authority",
            "inputCarriesAuthority", "idempotency", "effect", "emits", "rejects",
        },
        "commands",
    )
    for command in commands.values():
        if command["inputModel"] not in models:
            raise ValueError("command input model is unknown")
        if not isinstance(command["uri"], str) or not command["uri"]:
            raise ValueError("command URI must be nonempty")
        if not isinstance(command["intent"], str) or not command["intent"]:
            raise ValueError("command intent must be nonempty")
        if (
            command["authority"] != "external-policy"
            or command["inputCarriesAuthority"] is not False
            or command["idempotency"] != "required"
        ):
            raise ValueError("command authority or idempotency boundary is unsafe")
        if not isinstance(command["effect"], str) or command["effect"] in {"", "none"}:
            raise ValueError("command must declare a state-changing effect")
        contract_string_list(command["emits"], "command events")
        contract_string_list(command["rejects"], "command errors")
    all_emitted = [item for command in commands.values() for item in command["emits"]]
    if len(all_emitted) != len(set(all_emitted)):
        raise ValueError("each event must have one command emitter")
    return commands, all_emitted


def validate_domain_projections(operations: dict[str, Any], models: dict[str, Any]):
    projections = contract_record_index(
        operations.get("projections"), "id",
        {"id", "intent", "outputModel", "cardinality", "rebuiltFrom", "reducer"},
        "projections",
    )
    for projection in projections.values():
        if projection["outputModel"] not in models:
            raise ValueError("projection output model is unknown")
        contract_string_list(projection["rebuiltFrom"], "projection events")
        reducer = projection["reducer"]
        if (
            not isinstance(reducer, dict)
            or set(reducer) != {"version", "deterministic", "effects"}
            or not isinstance(reducer["version"], int)
            or isinstance(reducer["version"], bool)
            or reducer["version"] < 1
            or reducer["deterministic"] is not True
            or reducer["effects"] is not False
        ):
            raise ValueError("projection reducer is not deterministic and effect-free")
    return projections


def validate_domain_queries(operations: dict[str, Any], models: dict[str, Any], projections: dict[str, Any]):
    queries = contract_record_index(
        operations.get("queries"), "id",
        {
            "id", "uri", "intent", "inputModel", "outputModel", "cardinality",
            "projection", "consistency", "effect", "emits",
        },
        "queries",
    )
    for query in queries.values():
        if not isinstance(query["uri"], str) or not query["uri"]:
            raise ValueError("query URI must be nonempty")
        if not isinstance(query["intent"], str) or not query["intent"]:
            raise ValueError("query intent must be nonempty")
        if query["inputModel"] not in models or query["outputModel"] not in models:
            raise ValueError("query model is unknown")
        if query["projection"] not in projections:
            raise ValueError("query projection is unknown")
        if query["consistency"] not in {"strong", "eventual"}:
            raise ValueError("query consistency is unknown")
        if query["effect"] != "none" or query["emits"] != []:
            raise ValueError("query must be effect-free")
    if {query["projection"] for query in queries.values()} != set(projections):
        raise ValueError("projection must be owned by exactly this operation registry")


def validate_domain_events(root: Path, events: dict[str, Any], domain: str, commands: dict[str, Any], projections: dict[str, Any], all_emitted: list[str]):
    if set(events) != {"schema", "domain", "sourceOfTruth", "immutability", "events"}:
        raise ValueError("event registry fields are not closed")
    if events.get("schema") != "wellmanifest.events/v1" or events.get("domain") != domain:
        raise ValueError("event registry domain binding is invalid")
    if events.get("sourceOfTruth") != "operations/index.json":
        raise ValueError("event registry attempts to redefine operation authority")
    if events.get("immutability") != {
        "appendOnly": True,
        "eventsCarryAuthority": False,
        "replayExecutesEffects": False,
    }:
        raise ValueError("event registry must be append-only and replay-safe")
    event_index = contract_record_index(
        events.get("events"), "id",
        {
            "id", "emittedBy", "payloadFields", "documentation", "authority", "replay",
        },
        "events",
    )
    for event in event_index.values():
        emitter = event["emittedBy"]
        if emitter not in commands or event["id"] not in commands[emitter]["emits"]:
            raise ValueError("event emitter relation is inconsistent")
        contract_string_list(event["payloadFields"], "event payload fields")
        if event["authority"] is not False:
            raise ValueError("event must not carry authority")
        if event["replay"] != {"deterministic": True, "effects": False}:
            raise ValueError("event replay must be deterministic and effect-free")
        contract_document(
            root, event["documentation"], f"events/{event['id']}.md", "event",
        )
    rebuilt = {
        item for projection in projections.values() for item in projection["rebuiltFrom"]
    }
    if set(all_emitted) != set(event_index) or rebuilt != set(event_index):
        raise ValueError("event registry, command emissions and projections differ")
    return event_index


def validate_domain_error_status(status: Any) -> None:
    if (
        not isinstance(status, dict)
        or set(status) != {"http", "grpc"}
        or not isinstance(status["http"], int)
        or isinstance(status["http"], bool)
        or status["http"] < 400
        or status["http"] > 599
        or not isinstance(status["grpc"], str)
        or not status["grpc"]
    ):
        raise ValueError("error transport status is invalid")


def validate_domain_errors(root: Path, errors: dict[str, Any], domain: str, commands: dict[str, Any], event_index: dict[str, Any]):
    if set(errors) != {"schema", "domain", "sourceOfTruth", "errors"}:
        raise ValueError("error registry fields are not closed")
    if errors.get("schema") != "wellmanifest.errors/v1" or errors.get("domain") != domain:
        raise ValueError("error registry domain binding is invalid")
    if errors.get("sourceOfTruth") != "operations/index.json#/commands/*/rejects":
        raise ValueError("error registry attempts to redefine command rejection authority")
    error_index = contract_record_index(
        errors.get("errors"), "code",
        {"code", "documentation", "retryability", "status", "rejectionEvent"},
        "errors",
    )
    for error in error_index.values():
        contract_document(
            root, error["documentation"], f"error/{error['code']}.md", "error",
        )
        if error["rejectionEvent"] not in event_index:
            raise ValueError("error rejection event is unknown")
        if error["retryability"] not in {
            "never", "after-correction", "after-new-evidence",
        }:
            raise ValueError("error retryability is unknown")
        validate_domain_error_status(error["status"])
    rejected = {item for command in commands.values() for item in command["rejects"]}
    if rejected != set(error_index):
        raise ValueError("error registry and command rejections differ")


def validate_domain_contract_graph(
    root: Path,
    operations: dict[str, Any],
    events: dict[str, Any],
    errors: dict[str, Any],
) -> None:
    domain = validate_domain_operation_header(root, operations)
    models = validate_domain_models(root, operations)
    commands, all_emitted = validate_domain_commands(operations, models)
    projections = validate_domain_projections(operations, models)
    validate_domain_queries(operations, models, projections)
    event_index = validate_domain_events(root, events, domain, commands, projections, all_emitted)
    validate_domain_errors(root, errors, domain, commands, event_index)


def check_domain_contracts(root: Path, manifest: dict[str, Any], report: Report) -> None:
    config = manifest.get("domainContracts")
    if config is None or config == {"mode": "none"}:
        return
    assert config == DOMAIN_CONTRACTS_CQRS
    raw_paths = [config["commandsAndQueries"], config["events"], config["errors"]]
    try:
        documents = [load_json(safe_repo_path(root, raw_path)) for raw_path in raw_paths]
        if not all(isinstance(document, dict) for document in documents):
            raise ValueError("domain contract roots must be JSON objects")
        validate_domain_contract_graph(root, *documents)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report.add(
            "GOV-MANIFEST-001",
            f"CQRS domain contract is invalid: {error}",
            "Restore the canonical operations, events and error registries and their references.",
            raw_paths,
        )


def check_required_files(root: Path, manifest: dict[str, Any], report: Report) -> None:
    missing = []
    for raw in manifest["requiredFiles"]:
        try:
            if not safe_repo_path(root, raw).exists():
                missing.append(raw)
        except ValueError:
            missing.append(raw)
    if missing:
        report.add("GOV-BOOT-001", "Required target-repository files are missing.", "Run the approved new-project bootstrap before implementation.", missing)

    docker = manifest["docker"]
    if docker["required"]:
        def first_repo_file(names: list[str]) -> str | None:
            for name in names:
                try:
                    if safe_repo_path(root, name).is_file():
                        return name
                except ValueError:
                    continue
            return None

        dockerfile = first_repo_file(docker["dockerfiles"])
        compose = first_repo_file(docker["composeFiles"])
        if dockerfile is None or compose is None:
            report.add(
                "GOV-DOCKER-001", "Required Dockerfile or Compose declaration is missing.",
                "Add a pinned Docker runtime and validate its Compose configuration.",
                [*([] if dockerfile else docker["dockerfiles"]), *([] if compose else docker["composeFiles"])],
            )


def _extract_pyproject_version(content: str) -> str | None:
    if tomllib is not None:
        try:
            data = tomllib.loads(content)
            project = data.get("project", {})
            if isinstance(project, dict) and "version" in project and isinstance(project["version"], str):
                return project["version"].strip()
            poetry = data.get("tool", {}).get("poetry", {})
            if isinstance(poetry, dict) and "version" in poetry and isinstance(poetry["version"], str):
                return poetry["version"].strip()
            flit = data.get("tool", {}).get("flit", {}).get("metadata", {})
            if isinstance(flit, dict) and "version" in flit and isinstance(flit["version"], str):
                return flit["version"].strip()
        except Exception:
            pass
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1).strip() if m else None


def _extract_setup_py_version(content: str) -> str | None:
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r'\bversion\s*=\s*["\']([^"\']+)["\']', content)
    return m2.group(1).strip() if m2 else None


def _extract_cargo_version(content: str) -> str | None:
    if tomllib is not None:
        try:
            data = tomllib.loads(content)
            pkg = data.get("package", {})
            if isinstance(pkg, dict) and "version" in pkg and isinstance(pkg["version"], str):
                return pkg["version"].strip()
        except Exception:
            pass
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1).strip() if m else None


def check_version_parity(root: Path, manifest: dict[str, Any], report: Report) -> None:
    try:
        version_path = safe_repo_path(root, "VERSION")
    except ValueError:
        return
    if not version_path.is_file():
        return

    try:
        raw_version = version_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        report.add(
            "GOV-VERSION-001",
            "Authoritative VERSION file is unreadable or contains invalid encoding.",
            "Ensure VERSION is an accessible UTF-8 file declaring a valid plain version.",
            ["VERSION"],
        )
        return

    if not raw_version:
        report.add(
            "GOV-VERSION-001",
            "Authoritative VERSION file is empty.",
            "Declare a valid semantic or plain version in VERSION.",
            ["VERSION"],
        )
        return

    # 1. pyproject.toml
    try:
        pyproject_path = safe_repo_path(root, "pyproject.toml")
        if pyproject_path.is_file():
            content = pyproject_path.read_text(encoding="utf-8")
            pyproject_version = _extract_pyproject_version(content)
            if pyproject_version and pyproject_version != raw_version:
                report.add(
                    "GOV-VERSION-001",
                    f"Declared pyproject.toml version '{pyproject_version}' does not match authoritative VERSION '{raw_version}'.",
                    "Synchronize pyproject.toml version with the VERSION file.",
                    ["pyproject.toml", "VERSION"],
                )
    except (OSError, UnicodeDecodeError, ValueError):
        pass

    # 2. setup.py
    try:
        setup_path = safe_repo_path(root, "setup.py")
        if setup_path.is_file():
            content = setup_path.read_text(encoding="utf-8")
            setup_version = _extract_setup_py_version(content)
            if setup_version and setup_version != raw_version:
                report.add(
                    "GOV-VERSION-001",
                    f"Declared setup.py version '{setup_version}' does not match authoritative VERSION '{raw_version}'.",
                    "Synchronize setup.py version with the VERSION file or read VERSION dynamically.",
                    ["setup.py", "VERSION"],
                )
    except (OSError, UnicodeDecodeError, ValueError):
        pass

    # 3. package.json
    try:
        package_json_path = safe_repo_path(root, "package.json")
        if package_json_path.is_file():
            pkg_data = json.loads(package_json_path.read_text(encoding="utf-8"))
            if isinstance(pkg_data, dict) and "version" in pkg_data:
                pkg_version = str(pkg_data["version"]).strip()
                if pkg_version and pkg_version != raw_version:
                    report.add(
                        "GOV-VERSION-001",
                        f"Declared package.json version '{pkg_version}' does not match authoritative VERSION '{raw_version}'.",
                        "Synchronize package.json version with the VERSION file.",
                        ["package.json", "VERSION"],
                    )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        pass

    # 4. Cargo.toml
    try:
        cargo_path = safe_repo_path(root, "Cargo.toml")
        if cargo_path.is_file():
            content = cargo_path.read_text(encoding="utf-8")
            cargo_version = _extract_cargo_version(content)
            if cargo_version and cargo_version != raw_version:
                report.add(
                    "GOV-VERSION-001",
                    f"Declared Cargo.toml version '{cargo_version}' does not match authoritative VERSION '{raw_version}'.",
                    "Synchronize Cargo.toml version with the VERSION file.",
                    ["Cargo.toml", "VERSION"],
                )
    except (OSError, UnicodeDecodeError, ValueError):
        pass

    # 5. Check static __version__ in python packages
    skip_dirs = {
        ".git", ".venv", "venv", "env", ".subactor", ".worktrees",
        "tests", "test", "build", "dist", "node_modules", "fixtures",
        "__pycache__", ".tox", ".nox", ".pytest_cache"
    }
    for init_file in root.glob("**/__init__.py"):
        rel_parts = init_file.relative_to(root).parts
        if any(part in skip_dirs for part in rel_parts):
            continue
        try:
            text = init_file.read_text(encoding="utf-8")
            m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
            if m:
                found_v = m.group(1).strip()
                if found_v != raw_version:
                    rel_p = rel(root, init_file)
                    report.add(
                        "GOV-VERSION-001",
                        f"Static __version__ '{found_v}' in {rel_p} does not match authoritative VERSION '{raw_version}'.",
                        "Use dynamic version discovery (importlib.metadata / VERSION) or synchronize __version__ with VERSION.",
                        [rel_p, "VERSION"],
                    )
        except (OSError, UnicodeDecodeError):
            pass


def immutable_image_reference(reference: str) -> bool:
    return reference == "scratch" or IMMUTABLE_IMAGE_RE.fullmatch(reference) is not None


def dockerfile_image_references(path: Path) -> list[tuple[int, str]]:
    references: list[tuple[int, str]] = []
    stage_aliases: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        tokens = line.strip().split()
        if not tokens or tokens[0].upper() != "FROM":
            continue
        operands = [token for token in tokens[1:] if not token.startswith("--")]
        image = operands[0] if operands else ""
        if image.lower() not in stage_aliases:
            references.append((line_number, image))
        if len(operands) >= 3 and operands[1].upper() == "AS":
            stage_aliases.add(operands[2].lower())
    return references


def compose_image_references(path: Path) -> list[tuple[int, str]]:
    references: list[tuple[int, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = COMPOSE_IMAGE_RE.match(line)
        if match:
            references.append((line_number, next(value for value in match.groups() if value is not None)))
    return references


def check_docker_image_references(root: Path, manifest: dict[str, Any], report: Report) -> None:
    docker = manifest["docker"]
    invalid: list[tuple[str, int, str]] = []
    for raw_path in docker["dockerfiles"]:
        path = safe_repo_path(root, raw_path)
        if path.is_file():
            invalid.extend(
                (raw_path, line_number, reference)
                for line_number, reference in dockerfile_image_references(path)
                if not immutable_image_reference(reference)
            )
    for raw_path in docker["composeFiles"]:
        path = safe_repo_path(root, raw_path)
        if path.is_file():
            invalid.extend(
                (raw_path, line_number, reference)
                for line_number, reference in compose_image_references(path)
                if not immutable_image_reference(reference)
            )
    if invalid:
        report.add(
            "GOV-DOCKER-002",
            "Docker image references are not pinned to immutable SHA-256 digests.",
            "Pin external images as name@sha256:<64 lowercase hex>; for a local-only Compose build, omit image so no mutable tag can be pulled.",
            [f"{path}:{line_number}" for path, line_number, _ in invalid],
            {"references": [reference for _, _, reference in invalid]},
        )


def check_stacks(root: Path, manifest: dict[str, Any], profiles_path: Path | None, report: Report) -> None:
    stacks = manifest.get("stacks", [])
    if not stacks or profiles_path is None:
        return
    try:
        profiles = load_json(profiles_path)["profiles"]
        if not isinstance(profiles, dict):
            raise TypeError("profiles must be an object")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        report.add("GOV-MANIFEST-001", "Stack profile catalog is unreadable.", "Restore the pinned stack profile catalog.", [])
        return
    for stack in stacks:
        profile = profiles.get(stack)
        if not isinstance(profile, dict):
            report.add("GOV-STACK-001", f"Unknown stack profile: {stack}", "Declare a profile published by the pinned governance standard.", [])
            continue
        markers = profile.get("anyFiles", [])
        if not string_list(markers) or not all(relative_pattern(marker) for marker in markers):
            report.add("GOV-MANIFEST-001", f"Stack profile '{stack}' has invalid markers.", "Restore the pinned stack profile catalog.", [])
            continue
        if markers and not any(safe_repo_path(root, marker).exists() for marker in markers):
            report.add("GOV-STACK-001", f"Declared stack '{stack}' has no recognized project marker.", "Add the stack marker or remove the inaccurate stack declaration.", markers)


def check_virtual_ticket_content(root, directory, files, active_names, config, report) -> None:
    if directory.name in active_names:
        missing = [name for name in config["requiredFiles"] if name not in files]
        missing += [pattern for pattern in config["requiredAgentFiles"] if not any(fnmatch.fnmatchcase(name, pattern) for name in files)]
        if missing:
            report.add("GOV-TICKET-003", "Active database ticket is missing required content.",
                "Complete the ticket in its database without materializing Git carriers.",
                [rel(root, directory / name) for name in missing])
    for name, (content, mode) in files.items():
        if Path(name).suffix.lower() in EXECUTABLE_SUFFIXES or mode == "100755":
            report.add("GOV-TICKET-004", "Executable content is forbidden in a database ticket.",
                "Move implementation into source or test paths.", [rel(root, directory / name)])


def check_file_ticket_content(root, directory, active_names, config, report) -> None:
    if directory.name in active_names:
        missing = [rel(root, directory / item) for item in config["requiredFiles"] if not (directory / item).is_file()]
        for pattern in config["requiredAgentFiles"]:
            if not any(directory.glob(pattern)):
                missing.append(rel(root, directory / pattern))
        if missing:
            report.add("GOV-TICKET-003", f"Active ticket {directory.name} is missing required governance files.", "Complete the ticket scaffold before implementation.", missing)
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        mode_executable = bool(path.stat().st_mode & 0o111)
        if path.suffix.lower() in EXECUTABLE_SUFFIXES or mode_executable:
            report.add(
                "GOV-TICKET-004", f"Executable content is forbidden in ticket directory: {rel(root, path)}",
                "Move implementation to the repository's normal source, test or scripts directory.", [rel(root, path)],
            )


def check_ticket_content(
    root: Path,
    directories: list[Path],
    active: list[TicketRecord],
    config: dict[str, Any],
    report: Report,
    records: list[TicketRecord] | None = None,
) -> None:
    active_names = {record.directory.name for record in active}
    virtual = {record.directory.name: record.files for record in records or [] if record.files is not None}
    for directory in directories:
        if directory.name in virtual:
            check_virtual_ticket_content(root, directory, virtual[directory.name], active_names, config, report)
        else:
            check_file_ticket_content(root, directory, active_names, config, report)


def extract_constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = extract_constant_string(node.left)
        right = extract_constant_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def is_secret_literal(node: ast.AST) -> bool:
    val = extract_constant_string(node)
    if val is not None:
        if len(val) >= 12 and not SAFE_SECRET_VALUES.match(val) and not GENERATED_SECRET_PLACEHOLDER_RE.fullmatch(val):
            return True
    return False


def find_python_secrets(tree: ast.AST) -> list[str]:
    fields: list[str] = []

    def add_field(name: str) -> None:
        m = SECRET_FIELD_NAME_RE.search(name)
        if m:
            fields.append(m.group(1))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and SECRET_FIELD_NAME_RE.search(target.id):
                    if is_secret_literal(node.value):
                        add_field(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    if isinstance(node.value, (ast.Tuple, ast.List)) and len(target.elts) == len(node.value.elts):
                        for t, v in zip(target.elts, node.value.elts):
                            if isinstance(t, ast.Name) and SECRET_FIELD_NAME_RE.search(t.id) and is_secret_literal(v):
                                add_field(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and SECRET_FIELD_NAME_RE.search(node.target.id):
                if node.value is not None and is_secret_literal(node.value):
                    add_field(node.target.id)
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg and SECRET_FIELD_NAME_RE.search(kw.arg):
                    if is_secret_literal(kw.value):
                        add_field(kw.arg)
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and SECRET_FIELD_NAME_RE.search(k.value):
                    if is_secret_literal(v):
                        add_field(k.value)
        elif isinstance(node, ast.Compare):
            if isinstance(node.left, ast.Name) and SECRET_FIELD_NAME_RE.search(node.left.id):
                for comp in node.comparators:
                    if is_secret_literal(comp):
                        add_field(node.left.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pos_args = node.args.args
            defaults = node.args.defaults
            for arg, default in zip(pos_args[-len(defaults):], defaults):
                if SECRET_FIELD_NAME_RE.search(arg.arg) and is_secret_literal(default):
                    add_field(arg.arg)
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                if default is not None and SECRET_FIELD_NAME_RE.search(arg.arg) and is_secret_literal(default):
                    add_field(arg.arg)
    return sorted(set(fields))


def probable_secret_fields(text: str, filename: str = "") -> list[str]:
    if filename.endswith((".py", ".pyi", ".pyw")):
        try:
            tree = ast.parse(text)
            return find_python_secrets(tree)
        except SyntaxError:
            pass
    fields = []
    for match in SECRET_RE.finditer(text):
        value = match.group(2)
        shell_assignment = text[match.end(2):].startswith("=")
        environment_reference = re.match(r"^[A-Z][A-Z0-9_]*=", value)
        safe_generated_placeholder = GENERATED_SECRET_PLACEHOLDER_RE.fullmatch(value)
        if (
            not shell_assignment
            and not environment_reference
            and not SAFE_SECRET_VALUES.match(value)
            and not safe_generated_placeholder
        ):
            fields.append(match.group(1))
    return sorted(set(fields))


def check_changed_file(root: Path, raw: str, report: Report) -> None:
    try:
        path = safe_repo_path(root, raw)
    except ValueError:
        return
    if not path.is_file() or path.stat().st_size > 1_000_000:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    secrets = probable_secret_fields(text, raw)
    if secrets:
        report.add(
            "GOV-SECRET-001", f"Probable secret assignment detected in {raw}.",
            "Remove and rotate the secret; keep only placeholders in tracked files.", [raw], {"fieldNames": secrets},
        )
    if raw.startswith(("project/ticket-", ".governance/")) and LOCAL_PATH_RE.search(text):
        report.add(
            "GOV-PATH-001", f"Machine-local absolute path detected in governed artifact: {raw}",
            "Replace it with a repository-relative path before publication.", [raw],
        )
    if fnmatch.fnmatchcase(raw, "project/ticket-*/decisions.md"):
        check_decision_log_file(root, raw, text, report)


def check_agent_hosts(root: Path, actor: str, report: Report) -> None:
    """Prove the host-agnostic contract is installed, not merely documented (ticket-106)."""
    if not any(
        (root / candidate).is_file()
        for candidate in ("governance/agent-hosts.json", ".governance/agent-hosts.json")
    ):
        return
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from agent_host_check import audit as agent_host_audit
    except ImportError:
        # The validator is a managed file, so its absence is a sync defect
        # rather than a host-contract finding.
        report.add(
            "GOV-SYNC-001",
            "Managed agent host validator is missing next to governance_check.py.",
            "Restore agent_host_check.py through an explicit standard upgrade.",
            [".governance/agent_host_check.py"],
        )
        return
    for finding in agent_host_audit(root, actor)["findings"]:
        report.add(
            finding["code"], finding["message"], finding["remediation"], finding["paths"],
        )


def check_decision_log_file(root: Path, raw: str, text: str, report: Report) -> None:
    """Validate recomputable decision records (C-DECISION / ticket-031)."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from decision_record import parse_dsl_record, split_decision_blocks, validate_record
    except ImportError:
        report.add(
            "GOV-DECISION-002",
            f"Cannot import decision_record helper while validating {raw}.",
            "Keep scripts/decision_record.py next to governance_check.py.",
            [raw],
        )
        return
    blocks = split_decision_blocks(text)
    if not blocks:
        report.add(
            "GOV-DECISION-001",
            f"Decision log {raw} has no DECISION records.",
            "Append a fenced ```dsl DECISION record or remove the empty log.",
            [raw],
        )
        return
    for block in blocks:
        try:
            record = parse_dsl_record(block)
        except ValueError as error:
            report.add(
                "GOV-DECISION-002",
                f"Decision record in {raw} is not parseable: {error}",
                "Store deterministic INPUT lines and a complete DECISION shape.",
                [raw],
            )
            continue
        for error in validate_record(record):
            code = "GOV-DECISION-002"
            if "GOV-DECISION-003" in error or "ADVISORY" in error:
                code = "GOV-DECISION-003"
            elif "GOV-DECISION-004" in error or "replayed verdict" in error:
                code = "GOV-DECISION-004"
            elif "GOV-DECISION-001" in error:
                code = "GOV-DECISION-001"
            report.add(
                code,
                f"Decision record in {raw}: {error}",
                "Fix the record so INPUT + APPLIED_RULE recompute VERDICT with DETERMINISTIC authority.",
                [raw],
            )


def check_changed_content(root: Path, changed: list[str], actor: str, trusted_human_change: bool, report: Report) -> None:
    human_paths = [path for path in changed if fnmatch.fnmatchcase(path, "project/ticket-*/user-*.md")]
    if human_paths and (actor != "human" or not trusted_human_change):
        report.add(
            "GOV-OWNER-001", "Human-owned participant content changed without trusted human intake evidence.",
            "Revert the agent edit or have the human owner submit it through the trusted intake boundary.", human_paths,
        )
    for raw in changed:
        check_changed_file(root, raw, report)


def check_declared_delivery_budget(
    policy: dict[str, Any],
    delivery: dict[str, Any],
    record: TicketRecord,
    intent_path: str,
    report: Report,
) -> None:
    profile = policy.get("profiles", {}).get(delivery["complexity"], {})
    limits = effective_delivery_policy(policy, delivery["complexity"])
    complexity_limit = profile.get("maxActiveMinutes", 10 if delivery["complexity"] == "XS" else policy["maxActiveMinutes"])
    declared_limits = delivery["budgets"]
    policy_limits = {
        "maxImplementationFiles": limits["maxImplementationFiles"],
        "maxAffectedComponents": limits["maxAffectedComponents"],
        "maxPublicInterfaceChanges": limits["maxPublicInterfaceChanges"],
        "maxRuntimeDependencies": limits["maxRuntimeDependencies"],
    }
    violations = {
        name: {"declared": declared_limits[name], "policy": limit}
        for name, limit in policy_limits.items()
        if declared_limits[name] > limit
    }
    if (
        delivery["complexity"] not in policy["allowedComplexityClasses"]
        or delivery["estimatedMinutes"] > policy["maxActiveMinutes"]
        or delivery["estimatedMinutes"] > complexity_limit
        or violations
    ):
        report.add(
            "GOV-DELIVERY-001",
            f"Ticket {record.directory.name} exceeds the approved delivery class or policy budget.",
            "Split the outcome into dependent XS/S slices; do not widen the current ticket or PR.",
            [intent_path],
            {
                "complexity": delivery["complexity"],
                "estimatedMinutes": delivery["estimatedMinutes"],
                "maxActiveMinutes": policy["maxActiveMinutes"],
                "budgetViolations": violations,
            },
        )


def check_delivery_timebox(
    policy: dict[str, Any],
    record: TicketRecord,
    intent_path: str,
    elapsed_minutes: int | None,
    report: Report,
) -> None:
    if elapsed_minutes is not None:
        if elapsed_minutes >= policy["maxActiveMinutes"]:
            report.add(
                "GOV-DELIVERY-001",
                f"Ticket {record.directory.name} reached its {policy['maxActiveMinutes']}-minute implementation timebox.",
                "Stop implementation, preserve evidence and plan unfinished work as an explicit dependent slice.",
                [intent_path], {"elapsedMinutes": elapsed_minutes},
            )
        elif elapsed_minutes >= policy["checkpointMinutes"]:
            report.add(
                "GOV-DELIVERY-002",
                f"Ticket {record.directory.name} reached its delivery checkpoint.",
                "Record completed and remaining scope now; stop at the hard timebox instead of expanding the diff.",
                [intent_path], {"elapsedMinutes": elapsed_minutes, "stopAtMinutes": policy["maxActiveMinutes"]},
                severity="warning",
            )


def is_published_integration(root: Path, target: str, supplied_base: str | None) -> bool:
    """Recognize one clean integration already observed on the target branch.

    The supplied first parent is the target before this integration. Comparing
    the accepted base with the published HEAD would include the ticket's own
    changes as intervening drift. Ambiguous ranges and dirty trees retain the
    conservative target comparison; this observation never grants approval.
    """
    if not supplied_base:
        return False
    try:
        return (
            git_output(root, ["rev-parse", "HEAD"]).decode().strip() == target
            and git_output(root, ["rev-parse", f"{target}^1"]).decode().strip() == supplied_base
            and not git_output(root, ["status", "--porcelain"])
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def observe_delivery_bases(root, delivery, accepted_sha, intent_path, base, report):
    observed: list[tuple[str, str]] = []
    if base:
        try:
            observed.append((
                "suppliedBase",
                git_output(root, ["rev-parse", f"{base}^{{commit}}"])
                .decode()
                .strip(),
            ))
        except (subprocess.CalledProcessError, FileNotFoundError):
            report.add(
                "GOV-BASE-001", "The supplied base revision cannot be resolved.",
                "Fetch the complete target history and rerun against the accepted base SHA.",
                [intent_path], {"suppliedBase": base, "acceptedBaseSha": accepted_sha},
            )

    target_refs = [
        f"refs/remotes/origin/{delivery['targetBranch']}",
        f"refs/heads/{delivery['targetBranch']}",
    ]
    for target_ref in target_refs:
        try:
            current_target = git_output(root, ["rev-parse", "--verify", f"{target_ref}^{{commit}}"]).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        supplied_base = next((sha for source, sha in observed if source == "suppliedBase"), None)
        if is_published_integration(root, current_target, supplied_base):
            # The accepted-to-supplied-base check below still detects changes
            # that landed on the target before this ticket was integrated.
            break
        observed.append((target_ref, current_target))
        break

    return observed


def check_observed_delivery_bases(root, accepted_commit, observed, component_patterns, record, intent_path, report) -> None:
    checked: set[str] = set()
    for source, observed_sha in observed:
        if observed_sha in checked or observed_sha == accepted_commit:
            continue
        checked.add(observed_sha)
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", accepted_commit, observed_sha],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if ancestor.returncode != 0:
            report.add(
                "GOV-BASE-001",
                f"Ticket {record.directory.name} accepted base is not an ancestor of the observed target.",
                "Rebuild from the current target and obtain fresh scope and architecture approval.",
                [intent_path],
                {
                    "acceptedBaseSha": accepted_commit,
                    "observedBaseSha": observed_sha,
                    "source": source,
                },
            )
            continue
        try:
            raw_paths = git_output(
                root,
                ["diff", "--name-only", "-z", f"{accepted_commit}..{observed_sha}"],
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            report.add(
                "GOV-BASE-001", "Intervening target changes cannot be inspected.",
                "Fetch the complete target history and rerun the overlap check.",
                [intent_path],
                {"acceptedBaseSha": accepted_commit, "observedBaseSha": observed_sha},
            )
            continue
        intervening = sorted(
            path
            for path in raw_paths.decode("utf-8", "surrogateescape").split("\0")
            if path
        )
        overlap = [path for path in intervening if matches(path, component_patterns)]
        if overlap:
            report.add(
                "GOV-BASE-002",
                f"Target branch changes overlap components approved for {record.directory.name}.",
                "Refresh the branch, re-run validation and obtain fresh approval for the overlapping scope.",
                [intent_path, *overlap],
                {
                    "acceptedBaseSha": accepted_commit,
                    "observedBaseSha": observed_sha,
                    "source": source,
                    "componentPatterns": component_patterns,
                    "overlappingPaths": overlap,
                },
            )


def check_delivery_base(
    root: Path,
    policy: dict[str, Any],
    delivery: dict[str, Any],
    record: TicketRecord,
    intent_path: str,
    base: str | None,
    report: Report,
) -> None:
    if delivery["targetBranch"] not in policy["targetBranches"]:
        report.add(
            "GOV-BASE-001",
            f"Ticket {record.directory.name} targets unapproved branch '{delivery['targetBranch']}'.",
            "Choose a manifest-approved target branch and obtain fresh approval for its exact base SHA.",
            [intent_path], {"allowedTargets": policy["targetBranches"]},
        )

    accepted_sha = delivery["acceptedBaseSha"]
    component_patterns = [
        pattern
        for component in delivery["architecture"]["components"]
        for pattern in component["paths"]
    ]
    observed = observe_delivery_bases(root, delivery, accepted_sha, intent_path, base, report)

    if not observed:
        return
    try:
        accepted_commit = git_output(
            root, ["rev-parse", "--verify", f"{accepted_sha}^{{commit}}"]
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        report.add(
            "GOV-BASE-001", "The accepted base revision cannot be resolved.",
            "Fetch the complete target history and rerun against the accepted base SHA.",
            [intent_path], {"acceptedBaseSha": accepted_sha},
        )
        return

    check_observed_delivery_bases(root, accepted_commit, observed, component_patterns, record, intent_path, report)


def map_implementation_components(
    implementation: list[str],
    components: list[dict[str, Any]],
) -> tuple[list[str], list[str], set[str]]:
    unmapped: list[str] = []
    multiply_mapped: list[str] = []
    touched_components: set[str] = set()
    for path in implementation:
        owners = [component["name"] for component in components if matches(path, component["paths"])]
        if not owners:
            unmapped.append(path)
        elif len(owners) > 1:
            multiply_mapped.append(path)
        else:
            touched_components.add(owners[0])
    return unmapped, multiply_mapped, touched_components


def check_delivery_architecture(
    policy: dict[str, Any],
    delivery: dict[str, Any],
    record: TicketRecord,
    implementation: list[str],
    intent_path: str,
    report: Report,
) -> set[str]:
    limits = effective_delivery_policy(policy, delivery["complexity"])
    declared_limits = delivery["budgets"]
    architecture = delivery["architecture"]
    components = architecture["components"]
    component_overflow = len(components) > min(
        declared_limits["maxAffectedComponents"], limits["maxAffectedComponents"],
    )
    interface_overflow = len(architecture["interfaceChanges"]) > min(
        declared_limits["maxPublicInterfaceChanges"], limits["maxPublicInterfaceChanges"],
    )
    dependency_overflow = len(delivery["runtimeDependencies"]) > min(
        declared_limits["maxRuntimeDependencies"], limits["maxRuntimeDependencies"],
    )
    unmapped, multiply_mapped, touched_components = map_implementation_components(implementation, components)
    if component_overflow or unmapped or multiply_mapped:
        report.add(
            "GOV-ARCHITECTURE-001",
            f"Ticket {record.directory.name} has unresolved or ambiguous component ownership.",
            "Decide component ownership before EDIT; map every changed implementation path to exactly one approved component.",
            [intent_path, *unmapped, *multiply_mapped],
            {
                "declaredComponents": [component["name"] for component in components],
                "touchedComponents": sorted(touched_components),
                "unmappedPaths": unmapped,
                "multiplyMappedPaths": multiply_mapped,
            },
        )
    check_actual_delivery_budget(
        limits, delivery, record, implementation, touched_components,
        interface_overflow, dependency_overflow, report,
    )
    return touched_components


def check_actual_delivery_budget(
    policy: dict[str, Any],
    delivery: dict[str, Any],
    record: TicketRecord,
    implementation: list[str],
    touched_components: set[str],
    interface_overflow: bool,
    dependency_overflow: bool,
    report: Report,
) -> None:
    declared_limits = delivery["budgets"]
    implementation_limit = min(declared_limits["maxImplementationFiles"], policy["maxImplementationFiles"])
    migration = report.snapshot_migrations.get(record.directory.name)
    if migration:
        imported = set(migration["importedPaths"])
        implementation = [path for path in implementation if path not in imported]
    public_paths = [path for path in implementation if matches(path, policy["publicInterfacePaths"])]
    dependency_paths = [path for path in implementation if path in policy["dependencyManifestPaths"]]
    if (
        len(implementation) > implementation_limit
        or len(touched_components) > declared_limits["maxAffectedComponents"]
        or interface_overflow
        or dependency_overflow
        or len(public_paths) > declared_limits["maxPublicInterfaceChanges"]
    ):
        report.add(
            "GOV-BUDGET-001",
            f"Actual diff for {record.directory.name} exceeds its approved complexity budget.",
            "Stop and split the remaining outcome into an explicitly dependent ticket; do not enlarge the current PR.",
            implementation,
            {
                "implementationFiles": len(implementation),
                "implementationFileLimit": implementation_limit,
                "touchedComponents": sorted(touched_components),
                "publicInterfacePaths": public_paths,
                "dependencyManifestPaths": dependency_paths,
                "declaredRuntimeDependencies": delivery["runtimeDependencies"],
            },
        )


def check_integration_ownership(
    manifest: dict[str, Any],
    delivery: dict[str, Any],
    record: TicketRecord,
    intent_path: str,
    report: Report,
) -> None:
    integration_workstream = manifest["coordination"]["integration"]["workstream"]
    architecture = delivery["architecture"]
    data_changes = integration_data_changes(architecture["dataChanges"])
    if (architecture["responsibilityChanges"] or data_changes) and record.intent["workstream"] != integration_workstream:
        report.add(
            "GOV-ARCHITECTURE-001",
            "Responsibility or persistent-data movement is not owned by an integration slice.",
            "Use integration for responsibility transfers or data migrations. Explicit component-local-state records stay with the component owner; legacy prose remains integration-owned. Reconcile the declared impact and actual diff before requesting new authority.",
            [intent_path],
            {"workstream": record.intent["workstream"], "requiredWorkstream": integration_workstream,
             "responsibilityChanges": architecture["responsibilityChanges"],
             "integrationDataChanges": data_changes},
        )


def check_delivery_gate(
    root: Path,
    manifest: dict[str, Any],
    record: TicketRecord,
    implementation: list[str],
    base: str | None,
    elapsed_minutes: int | None,
    report: Report,
) -> None:
    policy = manifest.get("delivery")
    if not isinstance(policy, dict):
        return
    assert record.intent is not None
    delivery = record.intent.get("delivery")
    intent_path = rel(root, record.directory / manifest["ticket"]["intentFile"])
    if not isinstance(delivery, dict):
        explicit_paths = [
            path for path in implementation
            if path in policy["dependencyManifestPaths"]
            or matches(path, manifest["coordination"]["integration"]["requiredForPaths"])
        ]
        if policy.get("requiredForImplementation") or explicit_paths:
            report.add(
                "GOV-DELIVERY-001",
                f"Implementation ticket {record.directory.name} needs an explicit delivery contract.",
                "Add delivery architecture and validation evidence for the high-risk paths; routine disjoint source/test changes use the compact intent.",
                [intent_path, *explicit_paths],
                {"explicitContractPaths": explicit_paths},
            )
            return
        public_paths = [
            path for path in implementation
            if matches(path, policy["publicInterfacePaths"])
        ]
        if (
            len(implementation) > policy["maxImplementationFiles"]
            or len(public_paths) > policy["maxPublicInterfaceChanges"]
        ):
            report.add(
                "GOV-BUDGET-001",
                f"Routine diff for {record.directory.name} exceeds the policy hard limit.",
                "Narrow the change or add an explicit delivery contract; do not create tracking-only split tickets.",
                implementation,
                {
                    "implementationFiles": len(implementation),
                    "implementationFileLimit": policy["maxImplementationFiles"],
                    "publicInterfacePaths": public_paths,
                    "publicInterfaceLimit": policy["maxPublicInterfaceChanges"],
                },
            )
        return
    check_declared_delivery_budget(policy, delivery, record, intent_path, report)
    check_delivery_timebox(policy, record, intent_path, elapsed_minutes, report)
    check_delivery_base(root, policy, delivery, record, intent_path, base, report)
    check_delivery_architecture(policy, delivery, record, implementation, intent_path, report)
    check_integration_ownership(manifest, delivery, record, intent_path, report)


def ticket_owns_implementation(record: TicketRecord, implementation: list[str]) -> bool:
    return bool(
        record.intent is not None
        and record.intent.get("schema") in {"new-project.intent/v2", "new-project.intent/v3"}
        and all(
            matches(path, record.intent["allowedPaths"])
            and not matches(path, record.intent["forbiddenPaths"])
            for path in implementation
        )
    )


def ticket_path_owners(active: list[TicketRecord], implementation: list[str]) -> dict[str, list[str]]:
    return {
        path: [
            record.directory.name for record in active
            if record.intent is not None
            and matches(path, record.intent["allowedPaths"])
            and not matches(path, record.intent["forbiddenPaths"])
        ]
        for path in implementation
    }


def select_change_ticket(
    root: Path,
    active: list[TicketRecord],
    coordination: Any,
    implementation: list[str],
    report: Report,
) -> TicketRecord | None:
    if not active:
        report.add(
            "GOV-TICKET-001", "Implementation paths changed without an active ticket.",
            "Create the next target-repository ticket, publish its plan and obtain approval before editing implementation.", implementation,
        )
        return None
    if not isinstance(coordination, dict):
        if len(active) > 1:
            report.add(
                "GOV-TICKET-002", "More than one active ticket exists.",
                "Continue the existing ticket or close/cancel it before creating another.",
                [rel(root, item.directory) for item in active], {"tickets": [item.directory.name for item in active]},
            )
            return None
        return active[0]
    candidates = [record for record in active if ticket_owns_implementation(record, implementation)]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates and len(active) == 1:
        return active[0]
    path_owners = ticket_path_owners(active, implementation)
    report.add(
        "GOV-TICKET-005", "Implementation diff does not resolve to exactly one active ticket.",
        "Use one ticket per branch/PR, narrow allowedPaths, or create an approved integration ticket for the combined diff.",
        implementation, {"candidateTickets": [record.directory.name for record in candidates], "pathOwners": path_owners},
    )
    return None


def check_selected_ticket_state(
    root: Path,
    config: dict[str, Any],
    selected: TicketRecord,
    implementation: list[str],
    base: str | None,
    head: str,
    governance_patterns: list[str],
    report: Report,
) -> None:
    directory = selected.directory
    workflow = selected.workflow
    if selected.files is None and not selected.external:
        check_history_order(
            root, base=base, head=head, ticket_name=directory.name,
            ticket_root=config["root"],
            intent_path=config["intentFile"], governance_patterns=governance_patterns,
            report=report,
        )
    # External ticket chronology belongs to its protected receipt store. The
    # pinned input binds repository/base/head; a local DB is never accepted for
    # protected validation. Scope, state, base and approval checks still run.
    if workflow not in set(config["implementationStates"]):
        report.add(
            "GOV-INTENT-001", f"Ticket {directory.name} is in workflow state {workflow or 'UNKNOWN'}, not an implementation state.",
            "Do not commit the pending change; obtain approval that moves the ticket to EDIT, then deliver it with material output.", implementation,
        )


def check_workstream_change_scope(
    root: Path,
    manifest: dict[str, Any],
    records: list[TicketRecord],
    coordination: dict[str, Any],
    selected: TicketRecord,
    implementation: list[str],
    report: Report,
) -> None:
    intent = selected.intent
    assert intent is not None
    adoption_bindings = atomic_adoption_binding_paths(root, manifest, intent)
    workstream = coordination["workstreams"].get(intent["workstream"])
    if isinstance(workstream, dict):
        unowned = [
            path for path in implementation
            if path not in adoption_bindings and not matches(path, workstream["ownedPaths"])
        ]
        if unowned:
            report.add(
                "GOV-WORKSTREAM-003", f"Changed paths are not owned by workstream '{intent['workstream']}'.",
                "Move the change to its owning workstream or create and approve an integration ticket; do not widen ownership retroactively.",
                unowned, {"ticket": selected.directory.name, "workstream": intent["workstream"], "ownedPaths": workstream["ownedPaths"]},
            )
    integration = coordination["integration"]
    shared = [
        path for path in implementation
        if path not in adoption_bindings and matches(path, integration["requiredForPaths"])
    ]
    if shared and intent["workstream"] != integration["workstream"]:
        integration_name = intent["integrationTicket"]
        integration_record = next((record for record in records if record.directory.name == integration_name), None)
        report.add(
            "GOV-INTEGRATION-001", "Shared contract paths must be changed by the integration-workstream ticket.",
            "Move the shared-path diff to the referenced integration ticket's branch; integrationTicket coordinates work but does not transfer path ownership.",
            shared,
            {
                "ticket": selected.directory.name,
                "integrationTicket": integration_name,
                "validIntegrationReference": integration_reference_valid(integration_record, integration["workstream"]),
                "requiredWorkstream": integration["workstream"],
            },
        )


def check_selected_ticket_intent(
    root: Path,
    manifest: dict[str, Any],
    records: list[TicketRecord],
    selected: TicketRecord,
    implementation: list[str],
    base: str | None,
    elapsed_minutes: int | None,
    report: Report,
) -> None:
    directory = selected.directory
    config = manifest["ticket"]
    intent_path = directory / config["intentFile"]
    intent, error = selected.intent, selected.intent_error
    if error:
        report.add("GOV-INTENT-002", f"Ticket intent is invalid: {error}", "Create a valid intent file before implementation.", [rel(root, intent_path)])
    else:
        outside = [path for path in implementation if not matches(path, intent["allowedPaths"]) or matches(path, intent["forbiddenPaths"])]
        if outside:
            report.add(
                "GOV-SCOPE-001", "Changed implementation paths are outside the ticket intent.",
                "Revert the paths or return to PLAN, expand allowedPaths and obtain fresh approval.", outside,
                {"ticket": directory.name, "allowedPaths": intent["allowedPaths"]},
            )
        coordination = manifest.get("coordination")
        if isinstance(coordination, dict) and intent.get("schema") in {"new-project.intent/v2", "new-project.intent/v3"}:
            check_workstream_change_scope(root, manifest, records, coordination, selected, implementation, report)
        check_physical_contract_changes(root, intent, directory.name, implementation, report)
        if intent is not None and not selected.external:
            check_delivery_gate(root, manifest, selected, implementation, base, elapsed_minutes, report)


def approval_subject_valid(evidence: Any) -> bool:
    required = {
        "schema", "source", "repository", "pullRequest", "headSha", "ticket",
        "actor", "verification",
    }
    return (
        isinstance(evidence, dict)
        and set(evidence) == required
        and evidence.get("schema") == "new-project.approval-evidence/v1"
        and evidence.get("source") in {
            "github-review", "github-app-review", "signed-attestation",
        }
        and isinstance(evidence.get("repository"), str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", evidence["repository"]) is not None
        and isinstance(evidence.get("pullRequest"), int)
        and not isinstance(evidence.get("pullRequest"), bool)
        and evidence["pullRequest"] >= 1
        and isinstance(evidence.get("headSha"), str)
        and re.fullmatch(r"[0-9a-f]{40}", evidence["headSha"]) is not None
        and isinstance(evidence.get("ticket"), str)
        and re.fullmatch(r"ticket-[0-9]{3,}", evidence["ticket"]) is not None
    )


def approval_actor_valid(actor: Any) -> bool:
    return (
        isinstance(actor, dict)
        and set(actor) == {"login", "type"}
        and isinstance(actor.get("login"), str)
        and bool(actor["login"])
        and actor.get("type") in {"User", "Bot", "Workflow"}
    )


def approval_verification_valid(verification: Any) -> bool:
    return (
        isinstance(verification, dict)
        and {"method", "verified"} <= set(verification)
        and set(verification) <= {"method", "verified", "issuer", "predicateType"}
        and verification.get("method") in {
            "github-api-allowlist", "github-attestation", "sigstore",
        }
        and verification.get("verified") is True
    )


def approval_authority_valid(
    evidence: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    source = evidence["source"]
    actor = evidence["actor"]
    verification = evidence["verification"]
    method = verification["method"]
    if source == "github-review":
        return actor["type"] == "User" and method == "github-api-allowlist"
    if source == "github-app-review":
        return (
            actor["type"] == "Bot"
            and actor["login"].endswith("[bot]")
            and method == "github-api-allowlist"
        )
    approval_config = manifest.get("approvalEvidence") or {}
    expected_predicate = approval_config.get(
        "signedAttestationPredicateType",
        "https://wellmanifest.com/attestations/validator/v1",
    )
    return (
        actor["type"] in {"Bot", "Workflow"}
        and method in {"github-attestation", "sigstore"}
        and isinstance(verification.get("issuer"), str)
        and bool(verification["issuer"])
        and verification.get("predicateType") == expected_predicate
    )


def approval_binding_mismatches(
    evidence: dict[str, Any],
    expected_repository: str | None,
    expected_pull_request: int | None,
    expected_head: str | None,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    missing = (
        expected_repository is None
        or expected_pull_request is None
        or expected_head is None
        or re.fullmatch(r"[0-9a-f]{40}", expected_head or "") is None
    )
    expected = {
        "repository": expected_repository,
        "pullRequest": expected_pull_request,
        "headSha": expected_head,
    }
    mismatches = {
        name: {"evidence": evidence[name], "expected": value}
        for name, value in expected.items()
        if evidence[name] != value
    }
    return missing, mismatches


def load_external_approval_evidence(
    root: Path,
    raw_path: str | None,
    report: Report,
) -> Any | None:
    if not raw_path:
        return None
    expanded = Path(raw_path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    try:
        path = expanded.parent.resolve(strict=True) / expanded.name
    except OSError as error:
        report.add(
            "GOV-APPROVAL-003", f"Approval evidence path is unreadable: {error}",
            "Have the protected approval resolver create a valid v1 evidence document outside the checkout.",
        )
        return None
    if path.is_relative_to(root):
        report.add(
            "GOV-APPROVAL-003",
            "Approval evidence is controlled by the pull-request checkout.",
            "Create evidence outside the checkout from a protected workflow after API or signature verification.",
            [rel(root, path)],
        )
        return None
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        report.add(
            "GOV-APPROVAL-003",
            "Approval evidence cannot be opened safely on this platform.",
            "Use a validator platform that supports no-follow file opens for external approval evidence.",
        )
        return None
    descriptor = -1
    try:
        flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("approval evidence is not a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        report.add(
            "GOV-APPROVAL-003", f"Approval evidence is unreadable: {error}",
            "Have the protected approval resolver create a valid v1 evidence document outside the checkout.",
        )
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return evidence


def approval_evidence(
    root: Path,
    raw_path: str | None,
    manifest: dict[str, Any],
    expected_repository: str | None,
    expected_pull_request: int | None,
    expected_head: str | None,
    report: Report,
) -> dict[str, Any] | None:
    evidence = load_external_approval_evidence(root, raw_path, report)
    if evidence is None:
        return None
    actor = evidence.get("actor") if isinstance(evidence, dict) else None
    verification = evidence.get("verification") if isinstance(evidence, dict) else None
    if not (
        approval_subject_valid(evidence)
        and approval_actor_valid(actor)
        and approval_verification_valid(verification)
    ):
        report.add(
            "GOV-APPROVAL-003", "Approval evidence does not conform to new-project.approval-evidence/v1.",
            "Regenerate evidence with the protected resolver and the pinned approval-evidence schema.",
        )
        return None
    missing, mismatches = approval_binding_mismatches(
        evidence, expected_repository, expected_pull_request, expected_head,
    )
    if missing or mismatches:
        report.add(
            "GOV-APPROVAL-004",
            "Approval evidence is not bound to the current repository, pull request and HEAD.",
            "Pass the current protected event bindings and request a fresh approval for the exact HEAD.",
            evidence={"missingExpectedBinding": missing, "mismatches": mismatches},
        )
        return None
    if not approval_authority_valid(evidence, manifest):
        report.add(
            "GOV-APPROVAL-005",
            "Approval actor or verification method is not valid for the claimed source.",
            "Use an allowlisted User, an allowlisted GitHub App bot login, or a signature-verified trusted attestation issuer.",
            evidence={
                "source": evidence["source"],
                "actor": evidence["actor"],
                "verification": evidence["verification"],
            },
        )
        return None
    return evidence


def check_change_approval(
    root: Path,
    manifest: dict[str, Any],
    selected: TicketRecord,
    approval_source: str | None,
    approved_ticket: str | None,
    report: Report,
) -> None:
    directory = selected.directory
    trusted = set(manifest["trustedApprovalSources"])
    if approval_source not in trusted:
        report.add(
            "GOV-APPROVAL-001", "No trusted external approval was supplied for implementation.",
            "Require an approving CODEOWNER GitHub review or signed attestation; Markdown status alone is not trusted.",
            [rel(root, directory / "README.md")], {"suppliedSource": approval_source, "trustedSources": sorted(trusted)},
        )
    approved_tickets = set((approved_ticket or "").split(",")) - {""}
    if directory.name not in approved_tickets:
        report.add(
            "GOV-APPROVAL-002", "Trusted approval does not identify the active ticket.",
            "Approve the current ticket after reviewing its latest intent and implementation diff.",
            [rel(root, directory)], {"activeTicket": directory.name, "approvedTickets": sorted(approved_tickets)},
        )


def resolve_change_approval(
    root: Path,
    manifest: dict[str, Any],
    selected: TicketRecord,
    approval_source: str | None,
    approved_ticket: str | None,
    approval_evidence_path: str | None,
    expected_repository: str | None,
    expected_pull_request: int | None,
    expected_head: str | None,
    report: Report,
) -> None:
    supplied = approval_evidence(
        root, approval_evidence_path, manifest, expected_repository,
        expected_pull_request, expected_head, report,
    )
    if supplied is not None:
        approval_source = supplied["source"]
        approved_ticket = supplied["ticket"]
    elif approval_source in {"github-app-review", "signed-attestation"}:
        report.add(
            "GOV-APPROVAL-003",
            f"Approval source {approval_source} requires external v1 evidence.",
            "Create bound evidence outside the checkout after allowlist or signature verification.",
        )
    check_change_approval(
        root, manifest, selected, approval_source, approved_ticket, report,
    )


def git_revision_file(root: Path, revision: str, raw_path: str) -> bytes | None:
    try:
        return git_output(root, ["show", f"{revision}:{raw_path}"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def package_entry(item: Any) -> tuple[str, str, str]:
    if not isinstance(item, dict) or set(item) != {"source", "target", "strategy", "executable"}:
        raise ValueError("package manifest entry fields are invalid")
    source, target = item.get("source"), item.get("target")
    if not isinstance(source, str) or not isinstance(target, str):
        raise TypeError("package manifest entry is invalid")
    if not relative_pattern(source) or not relative_pattern(target):
        raise ValueError("package manifest entry is invalid")
    if item.get("strategy") not in {"managed", "seed", "extendable"}:
        raise ValueError("package manifest entry is invalid")
    if not isinstance(item.get("executable"), bool):
        raise TypeError("package manifest entry is invalid")
    allowed_extendable = {
        ("governance/manifest.default.json", ".governance/manifest.json"),
        # ticket-206 moved the adopter seed off the hub's own live instance,
        # which shipped the hub's identity and job names into every adopter.
        # Both sources stay accepted so a repository pinned before that change
        # still validates its own manifest while it upgrades.
        ("template/files/required-checks.template.json", ".governance/required-checks.json"),
        ("governance/required-checks.json", ".governance/required-checks.json"),
        ("governance/ticket-allocation.json", ".governance/ticket-allocation.json"),
    }
    if item.get("strategy") == "extendable" and (
        (source, target) not in allowed_extendable or item.get("executable")
    ):
        raise ValueError("package manifest extendable target is invalid")
    return source, target, item["strategy"]


def package_strategies(content: bytes) -> dict[str, str]:
    document = json.loads(content)
    if not isinstance(document, dict) or set(document) != {"schema", "files"}:
        raise ValueError("package manifest fields are invalid")
    if document.get("schema") != "new-project.package-manifest/v1" or not isinstance(document.get("files"), list):
        raise ValueError("package manifest schema is invalid")
    strategies: dict[str, str] = {}
    for item in document["files"]:
        _source, target, strategy = package_entry(item)
        if target in strategies:
            raise ValueError("package manifest targets must be unique")
        strategies[target] = strategy
    if not strategies:
        raise ValueError("package manifest is empty")
    return strategies


def adoption_standard_binding_is_valid(document: dict[str, Any], expected_revision: str) -> bool:
    standard = document.get("standard")
    if document.get("schema") != "new-project.lock/v1" or not isinstance(standard, dict):
        return False
    fields = {"id", "version", "sourceRepository", "sourceRevision", "publicationStatus"}
    if set(standard) != fields:
        return False
    expected = {
        "id": "wellmanifest/new-project",
        "sourceRepository": "wellmanifest/new-project",
        "sourceRevision": expected_revision,
        "publicationStatus": "published",
    }
    if any(standard.get(key) != value for key, value in expected.items()):
        return False
    version = standard.get("version")
    return isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None


def adoption_lock(content: bytes, expected_revision: str) -> dict[str, str]:
    document = json.loads(content)
    if not isinstance(document, dict) or set(document) != {"schema", "standard", "managedFiles"}:
        raise ValueError("adoption lock fields are invalid")
    managed = document.get("managedFiles")
    if not adoption_standard_binding_is_valid(document, expected_revision) or not isinstance(managed, dict):
        raise ValueError("adoption lock standard binding is invalid")
    if not all(
        isinstance(path, str)
        and relative_pattern(path)
        and isinstance(digest, str)
        and re.fullmatch(r"[a-f0-9]{64}", digest) is not None
        for path, digest in managed.items()
    ):
        raise ValueError("adoption lock managed hashes are invalid")
    return managed


def content_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def standard_adoption_records(active: list[TicketRecord]) -> list[TicketRecord]:
    return [
        record for record in active
        if record.intent is not None
        and isinstance(record.intent.get("delivery"), dict)
        and "standardAdoption" in record.intent["delivery"]
    ]


def load_standard_adoption_evidence(
    root: Path,
    base: str,
    adoption: dict[str, Any],
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    bool,
    dict[str, str],
    dict[str, str],
    dict[str, tuple[str, str]],
]:
    base_package_content = git_revision_file(root, base, ".governance/package-manifest.json")
    base_lock_content = git_revision_file(root, base, ".governance/manifest.lock.json")
    head_package_path = safe_repo_path(root, ".governance/package-manifest.json")
    head_lock_path = safe_repo_path(root, ".governance/manifest.lock.json")
    if not head_package_path.is_file() or not head_lock_path.is_file():
        raise ValueError("head package manifest or lock is missing")
    initial = adoption["fromRevision"] is None
    if initial:
        if base_package_content is not None:
            raise ValueError("initial adoption base already contains a package manifest")
        base_strategies: dict[str, str] = {}
        base_hashes: dict[str, str] = {}
    else:
        if base_lock_content is None:
            raise ValueError("upgrade base lock is missing")
        if base_package_content is None:
            base_strategies = {}
        else:
            base_strategies = package_strategies(base_package_content)
        base_hashes = adoption_lock(base_lock_content, adoption["fromRevision"])
    head_strategies = package_strategies(head_package_path.read_bytes())
    head_hashes = adoption_lock(head_lock_path.read_bytes(), adoption["toRevision"])
    base_managed = {path for path, strategy in base_strategies.items() if strategy == "managed"}
    head_managed = {path for path, strategy in head_strategies.items() if strategy == "managed"}
    legacy_base = not base_strategies or (set(base_hashes) <= set(base_strategies))
    if (
        frozenset(base_hashes) not in {frozenset(base_strategies), frozenset(base_managed)}
        and not legacy_base
    ):
        raise ValueError("base package targets and lock targets differ")
    if set(head_hashes) != head_managed:
        raise ValueError("package targets and lock targets differ")
    takeovers = {
        item["path"]: item["baseDigest"]
        for item in adoption.get("managedTargetTakeovers", [])
    }
    restorations = {
        item["path"]: item["baseDigest"]
        for item in adoption.get("managedTargetRestorations", [])
    }
    transitions = {
        item["path"]: (item["baseDigest"], item["headDigest"])
        for item in adoption.get("targetOwnedTransitions", [])
    }
    return (
        base_strategies,
        head_strategies,
        base_hashes,
        head_hashes,
        initial,
        takeovers,
        restorations,
        transitions,
    )


def verify_managed_base(raw_path, base_content, base_strategies, base_hashes, initial,
                        takeovers, restorations, consumed_takeovers, consumed_restorations) -> bool:
    if raw_path in base_hashes:
        if base_strategies.get(raw_path) != "managed" and raw_path != ".governance/manifest.json":
            raise ValueError(f"managed strategy continuity differs: {raw_path}")
        if base_content is None:
            if restorations.get(raw_path) != base_hashes[raw_path]:
                raise ValueError(
                    f"base managed target is absent without matching restoration digest: {raw_path}"
                )
            consumed_restorations.add(raw_path)
        elif content_digest(base_content) != base_hashes[raw_path]:
            observed_digest = content_digest(base_content)
            if takeovers.get(raw_path) != observed_digest:
                raise ValueError(
                    f"base managed hash differs without matching takeover digest: {raw_path}"
                )
            consumed_takeovers.add(raw_path)
    elif base_content is not None:
        if initial:
            # Installing the standard does not erase target ownership.
            # A replaced path remains an ordinary implementation change.
            return False
        observed_digest = content_digest(base_content)
        if takeovers.get(raw_path) != observed_digest:
            raise ValueError(
                f"new managed target already existed at base without matching takeover digest: {raw_path}"
            )
        consumed_takeovers.add(raw_path)
    return True


def verify_adoption_transitions(root, base, changed, base_strategies, head_strategies, transitions, exempt) -> None:
    registry = adoption_binding_registry(root)
    if transitions and registry is None:
        raise ValueError("target-owned transitions require a valid managed adoption-binding registry")
    target_patterns = registry[1] if registry is not None else []
    for raw_path, (base_digest, head_digest) in transitions.items():
        if raw_path not in changed:
            raise ValueError(f"target-owned transition declaration was not consumed: {raw_path}")
        if raw_path in base_strategies or raw_path in head_strategies:
            raise ValueError(f"target-owned transition overlaps a package target: {raw_path}")
        if not matches(raw_path, target_patterns):
            raise ValueError(f"target-owned transition path is not allowlisted: {raw_path}")
        base_content = git_revision_file(root, base, raw_path)
        head_path = safe_repo_path(root, raw_path)
        if base_content is None or not head_path.is_file():
            raise ValueError(f"target-owned transition must preserve an existing file: {raw_path}")
        if content_digest(base_content) != base_digest:
            raise ValueError(f"target-owned transition base hash differs: {raw_path}")
        if content_digest(head_path.read_bytes()) != head_digest:
            raise ValueError(f"target-owned transition head hash differs: {raw_path}")
        exempt.add(raw_path)


def verify_changed_managed_paths(
    root: Path,
    base: str,
    changed: list[str],
    base_strategies: dict[str, str],
    head_strategies: dict[str, str],
    base_hashes: dict[str, str],
    head_hashes: dict[str, str],
    initial: bool,
    takeovers: dict[str, str],
    restorations: dict[str, str],
    transitions: dict[str, tuple[str, str]],
) -> set[str]:
    exempt: set[str] = set()
    consumed_takeovers: set[str] = set()
    consumed_restorations: set[str] = set()
    for raw_path in changed:
        if head_strategies.get(raw_path) != "managed":
            continue
        head_path = safe_repo_path(root, raw_path)
        if not head_path.is_file() or content_digest(head_path.read_bytes()) != head_hashes[raw_path]:
            raise ValueError(f"head managed hash differs: {raw_path}")
        base_content = git_revision_file(root, base, raw_path)
        if not verify_managed_base(
            raw_path, base_content, base_strategies, base_hashes, initial,
            takeovers, restorations, consumed_takeovers, consumed_restorations,
        ):
            continue
        exempt.add(raw_path)
    unused_takeovers = sorted(set(takeovers) - consumed_takeovers)
    if unused_takeovers:
        raise ValueError(f"managed target takeover declarations were not consumed: {', '.join(unused_takeovers)}")
    unused_restorations = sorted(set(restorations) - consumed_restorations)
    if unused_restorations:
        raise ValueError(
            "managed target restoration declarations were not consumed: "
            + ", ".join(unused_restorations)
        )
    verify_adoption_transitions(root, base, changed, base_strategies, head_strategies, transitions, exempt)
    if not exempt:
        raise ValueError("no changed managed payload was verified")
    return exempt


def atomic_standard_adoption_paths(
    root: Path,
    base: str | None,
    changed: list[str],
    active: list[TicketRecord],
    report: Report,
) -> set[str]:
    records = standard_adoption_records(active)
    if not records:
        return set()
    evidence_paths = [".governance/manifest.lock.json", ".governance/package-manifest.json"]
    if len(records) != 1:
        report.add(
            "GOV-SYNC-001",
            "Atomic standard adoption must resolve to exactly one active ticket.",
            "Keep one approved adoption ticket active and serialize every other adoption.",
            [rel(root, record.directory / "intent.json") for record in records],
        )
        return set()
    record = records[0]
    assert record.intent is not None
    adoption = record.intent["delivery"]["standardAdoption"]
    error = standard_adoption_error(adoption)
    if error or base is None or ".governance/manifest.lock.json" not in changed:
        report.add(
            "GOV-SYNC-001",
            f"Atomic standard adoption preconditions are invalid: {error or 'base and changed lock are required'}.",
            "Declare null-to-SHA bootstrap or distinct immutable upgrade revisions, compare against the approved Git base and regenerate the complete lock through Goal.",
            evidence_paths,
        )
        return set()
    try:
        evidence = load_standard_adoption_evidence(root, base, adoption)
        verified_paths = verify_changed_managed_paths(root, base, changed, *evidence)
        # The lock is verified input to the atomic adoption proof, but is not
        # itself a package-managed payload. Keep it in the same one-ticket
        # ownership slice instead of forcing a carrier-only companion ticket.
        return verified_paths | {".governance/manifest.lock.json"}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        report.add(
            "GOV-SYNC-001",
            f"Atomic standard adoption is inconsistent: {error}.",
            "Restore the base, install the complete published managed set through Goal and regenerate its lock before review.",
            evidence_paths,
            {"ticket": record.directory.name, "base": base},
        )
        return set()


def change_scoped_records(root, active, changed, governance_patterns, adoption_paths):
    changed_active = [
        record for record in active
        if any(path.startswith(f"{rel(root, record.directory).rstrip('/')}/") for path in changed)
    ]
    if changed_active:
        active = changed_active
    implementation = [
        path for path in changed
        if not matches(path, governance_patterns) and path not in adoption_paths
    ]
    if not changed_active and len(active) > 1 and implementation:
        path_active = [record for record in active if ticket_owns_implementation(record, implementation)]
        if len(path_active) == 1:
            active = path_active
    return active, implementation


def verified_import_paths(report: Report) -> set[str]:
    """Only immutable paths proven against a pinned grant are history context."""
    return {path for proof in report.snapshot_migrations.values()
            for path in proof["importedPaths"]}


def check_change_gate(
    root: Path,
    manifest: dict[str, Any],
    records: list[TicketRecord],
    changed: list[str],
    base: str | None,
    head: str,
    approval_source: str | None,
    approved_ticket: str | None,
    approval_evidence_path: str | None,
    expected_repository: str | None,
    expected_pull_request: int | None,
    expected_head: str | None,
    enforce_approval: bool,
    elapsed_minutes: int | None,
    adoption_paths: set[str],
    report: Report,
    active_records: list[TicketRecord] | None = None,
) -> str | None:
    governance_patterns = manifest["governancePaths"]
    config = manifest["ticket"]
    active = active_records if active_records is not None else active_ticket_records(root, config, records, report)
    repair_changed = [path for path in changed if path not in verified_import_paths(report)]
    active, implementation = change_scoped_records(root, active, repair_changed, governance_patterns, adoption_paths)
    migrations = [record for record in active if record.directory.name in report.snapshot_migrations]
    if not implementation and not migrations:
        if changed and not adoption_paths:
            report.add(
                "GOV-MATERIAL-001",
                "Changed paths contain only ticket tracking carriers.",
                "Add a material source, test, configuration, standard or requested documentation change; if no material delta exists, emit an external no-change receipt without a commit or pull request.",
                changed,
                {"trackingCarriers": governance_patterns},
            )
        return None
    repository = manifest.get("repository")
    if repository and repository["mode"] == "monorepo":
        outside_roots = [
            path for path in implementation
            if not matches(path, repository["componentRoots"])
        ]
        if outside_roots:
            report.add(
                "GOV-SCOPE-001",
                "Monorepo implementation paths fall outside declared component roots.",
                "Move the change under repository.componentRoots or update the manifest in a separately governed adoption.",
                outside_roots,
                {"componentRoots": repository["componentRoots"]},
            )
    # Import-only delivery is still material and requires the ordinary current
    # ticket, chronology, bounded intent and independent exact-head approval.
    selected = (migrations[0] if not implementation and len(migrations) == 1 else
                select_change_ticket(root, active, manifest.get("coordination"), implementation, report))
    if selected is None:
        return None
    check_selected_ticket_state(root, config, selected, implementation, base, head, governance_patterns, report)
    check_selected_ticket_intent(root, manifest, records, selected, implementation, base, elapsed_minutes, report)
    if enforce_approval:
        resolve_change_approval(
            root, manifest, selected, approval_source, approved_ticket,
            approval_evidence_path, expected_repository, expected_pull_request,
            expected_head, report,
        )
    return selected.directory.name


def sarif(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload["findings"]
    rules = {}
    results = []
    for item in findings:
        rules[item["code"]] = {
            "id": item["code"],
            "shortDescription": {"text": item["message"]},
            "help": {"text": item["remediation"]},
        }
        result: dict[str, Any] = {
            "ruleId": item["code"],
            "level": "error" if item["severity"] == "error" else "warning",
            "message": {"text": item["message"]},
        }
        if item["paths"]:
            result["locations"] = [{
                "physicalLocation": {"artifactLocation": {"uri": item["paths"][0]}},
            }]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "new-project-governance", "version": RUNTIME_VERSION, "rules": [rules[key] for key in sorted(rules)]}},
            "results": results,
        }],
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = []
    for item in payload["findings"]:
        paths = f" [{', '.join(item['paths'])}]" if item["paths"] else ""
        lines.append(f"{item['code']} {item['severity'].upper()}: {item['message']}{paths}")
        lines.append(f"  remediation: {item['remediation']}")
    summary = payload["summary"]
    code = "GOV-PASS" if payload["status"] == "passed" else "GOV-FAIL"
    lines.append(f"{code}: {payload['status']} ({summary['errors']} errors, {summary['warnings']} warnings)")
    if payload.get("cached"):
        lines.append("Preflight cache: HIT (deterministic result reused)")
    if "timings" in payload and payload["timings"]:
        lines.append("Phase timings:")
        for phase, duration in sorted(payload["timings"].items()):
            lines.append(f"  - {phase}: {duration:.4f}s" if isinstance(duration, (int, float)) else f"  - {phase}: {duration}")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", default=".governance/manifest.json")
    parser.add_argument("--lock", default=None)
    parser.add_argument("--stack-profiles", default=None)
    parser.add_argument(
        "--work-classification",
        default=".governance/work-classification.dsl.json",
    )
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--actor", choices=["agent", "human", "ci"], default="agent")
    parser.add_argument("--trusted-human-change", action="store_true")
    parser.add_argument("--enforce-approval", action="store_true")
    parser.add_argument("--approval-source")
    parser.add_argument("--approved-ticket")
    parser.add_argument("--approval-evidence")
    parser.add_argument("--expected-repository")
    parser.add_argument("--expected-pull-request", type=int)
    parser.add_argument("--expected-head")
    parser.add_argument("--ticket-database", help="Local primary-checkout project.sqlite; forbidden for CI/approval enforcement")
    parser.add_argument("--ticket-snapshot", help="Externally acquired ticket snapshot outside Git checkouts")
    parser.add_argument("--ticket-snapshot-sha256", help="Independent protected snapshot digest")
    parser.add_argument("--migration-authorization", help="External migration grant selected by protected policy")
    parser.add_argument("--migration-authorization-sha256", help="Independently protected grant digest")
    parser.add_argument("--migration-branch", help="Authenticated PR head branch, including detached jobs")
    parser.add_argument("--resolved-ticket-output")
    parser.add_argument("--elapsed-minutes", type=int)
    parser.add_argument("--timing", action="store_true", help="Report phase execution timings")
    parser.add_argument("--no-cache", action="store_true", help="Bypass reading and writing governance preflight cache")
    parser.add_argument("--cache-file", help="Custom path to governance preflight cache JSON")
    parser.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def load_manifest(root: Path, raw_path: str, report: Report) -> dict[str, Any] | None:
    try:
        manifest_path = safe_repo_path(root, raw_path)
    except ValueError as error:
        report.add("GOV-MANIFEST-001", str(error), "Use a repository-relative manifest path.")
        return None
    try:
        manifest = load_json(manifest_path)
        if not basic_manifest_valid(manifest):
            raise ValueError("required manifest fields are missing or invalid")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report.add("GOV-MANIFEST-001", f"Governance manifest is invalid: {error}", "Restore a manifest conforming to the pinned governance schema.", [raw_path])
        return None
    return manifest


def optional_repo_path(
    root: Path,
    raw_path: str | None,
    code: str,
    label: str,
    report: Report,
) -> Path | None:
    if not raw_path:
        return None
    try:
        return safe_repo_path(root, raw_path)
    except ValueError as error:
        report.add(code, str(error), f"Use a repository-relative {label} path.", [raw_path])
        return None


def resolve_changed_paths(
    args: argparse.Namespace,
    root: Path,
    base: str | None,
    report: Report,
) -> list[str]:
    try:
        return changed_paths(root, base, args.head, args.changed_file)
    except (RuntimeError, ValueError) as error:
        report.add(
            "GOV-DIFF-001", str(error),
            "Use repository-relative changed paths and fetch the complete base/head history before retrying.",
            evidence={"base": base, "head": args.head},
        )
        return []


def published_adoption_validation_base(root: Path, delivery: dict[str, Any], head: str) -> str | None:
    """Bound implicit adoption validation without changing ticket authority.

    A historical IN_PROGRESS adoption may remain in a fresh published checkout
    without its external terminal receipt. Validate the latest integration's
    diff there, not every delivery since that adoption. Require origin evidence;
    a local target branch alone does not establish published state.
    """
    try:
        target_ref = f"refs/remotes/origin/{delivery['targetBranch']}"
        target = git_output(root, ["rev-parse", "--verify", f"{target_ref}^{{commit}}"]).decode().strip()
        if git_output(root, ["rev-parse", "--verify", f"{head}^{{commit}}"]).decode().strip() != target:
            return None
        parent = git_output(root, ["rev-parse", "--verify", f"{target}^1"]).decode().strip()
        if is_published_integration(root, target, parent):
            return parent
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def resolve_validation_base(
    supplied_base: str | None,
    root: Path,
    records: list[TicketRecord],
    config: dict[str, Any],
    head: str = "HEAD",
    active_records: list[TicketRecord] | None = None,
) -> str | None:
    if supplied_base is not None:
        return supplied_base
    active = active_records if active_records is not None else active_ticket_records(root, config, records)
    adoption_records = standard_adoption_records(active)
    # If an adoption ticket's delivery is already landed on its target branch,
    # its prose status remains active only because terminal receipts were not recorded.
    # Exclude landed adoptions so subsequent tickets do not have their validation base poisoned.
    unlanded_adoptions = []
    for record in adoption_records:
        if record.intent is None:
            continue
        delivery = record.intent.get("delivery")
        if not isinstance(delivery, dict):
            continue
        ticket_dir = getattr(record, "directory", None)
        target_branch = delivery.get("targetBranch")
        if ticket_dir is not None and target_branch:
            target_ref = f"refs/remotes/origin/{target_branch}"
            try:
                if delivery_landed(root, ticket_dir, target_ref):
                    continue
            except Exception:
                pass
        unlanded_adoptions.append(record)
    deliveries = [record.intent["delivery"] for record in unlanded_adoptions if record.intent is not None]
    if not deliveries:
        return None
    # Fresh published clones retain historical adoption prose but not external
    # terminal receipts. Establish the latest integration's range before its
    # changed-ticket filter decides ownership; do not declare tickets terminal.
    if len({delivery["targetBranch"] for delivery in deliveries}) == 1:
        published_base = published_adoption_validation_base(root, deliveries[0], head)
        if published_base is not None:
            return published_base
    if len(deliveries) != 1:
        return None
    return deliveries[0]["acceptedBaseSha"]


def check_change_lease(root: Path, report: Report) -> None:
    candidates = [
        root / "scripts" / "change_lease_check.py",
        root / ".governance" / "change_lease_check.py",
    ]
    checker = next((path for path in candidates if path.is_file()), None)
    if checker is None:
        return
    spec = importlib.util.spec_from_file_location("new_project_change_lease_check", checker)
    if spec is None or spec.loader is None:
        report.add(
            "GOV-CHANGE-LEASE-001", "Could not load the managed change-lease checker.",
            "Restore the managed checker from the pinned new-project package.", [rel(root, checker)],
        )
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        findings = module.validate_repository(root)
    except Exception as error:
        report.add(
            "GOV-CHANGE-LEASE-001", f"Change-lease validation failed closed: {error}",
            "Repair the managed checker or lease evidence before continuing.", [rel(root, checker)],
        )
        return
    for item in findings:
        report.add(
            item["code"], item["message"],
            "Read the authoritative lease and follow error/GOV-CHANGE-LEASE.md.",
            evidence=item.get("evidence", {}),
        )


def timed_step(report: Report, name: str, func, *args, **kwargs):
    if not report.timing:
        return func(*args, **kwargs)
    start = time.perf_counter()
    try:
        return func(*args, **kwargs)
    finally:
        report.record_timing(name, time.perf_counter() - start)


def compute_git_dirty_digest(root: Path) -> str:
    """Computes a deterministic digest of uncommitted worktree changes."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return "git-status-failed"

    raw = proc.stdout
    if not raw:
        return "clean"

    fields = iter(raw.split(b"\0"))
    dirty_files: list[str] = []
    for field in fields:
        if not field:
            continue
        path_bytes = field[3:]
        try:
            rel_path = path_bytes.decode("utf-8")
        except UnicodeDecodeError:
            rel_path = path_bytes.decode("utf-8", errors="replace")
        dirty_files.append(rel_path)
        if field[:2] in (b"R ", b"C "):
            try:
                dest = next(fields).decode("utf-8", errors="replace")
                dirty_files.append(dest)
            except StopIteration:
                pass

    file_hashes: dict[str, str] = {}
    for rel_path in sorted(set(dirty_files)):
        if rel_path.startswith(".subactor/cache/"):
            continue
        p = root / rel_path
        if p.is_symlink():
            try:
                target = os.readlink(p)
                file_hashes[rel_path] = f"symlink:{target}"
            except OSError:
                file_hashes[rel_path] = "symlink:error"
        elif p.is_file():
            try:
                hasher = hashlib.sha256()
                with p.open("rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                file_hashes[rel_path] = hasher.hexdigest()
            except OSError:
                file_hashes[rel_path] = "read-error"
        else:
            file_hashes[rel_path] = "absent"

    hasher = hashlib.sha256()
    hasher.update(raw)
    for k in sorted(file_hashes.keys()):
        hasher.update(f"\n{k}:{file_hashes[k]}".encode("utf-8"))
    return hasher.hexdigest()


def file_sha256_or_none(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return "read-error"


def git_rev_parse(root: Path, ref: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return f"unresolved:{ref}"


def compute_preflight_cache_key(
    root: Path,
    args: argparse.Namespace,
    manifest_path: Path,
    lock_path: Path | None,
    profiles_path: Path | None,
    work_classification_path: Path | None,
) -> str | None:
    head_sha = git_rev_parse(root, args.head or "HEAD")
    base_sha = git_rev_parse(root, args.base) if args.base else "inferred"
    dirty_digest = compute_git_dirty_digest(root)
    if dirty_digest == "git-status-failed":
        return None

    manifest_sha = file_sha256_or_none(manifest_path)
    if manifest_sha is None:
        return None

    key_payload = {
        "runtime_version": RUNTIME_VERSION,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "dirty_digest": dirty_digest,
        "manifest_sha": manifest_sha,
        "lock_sha": file_sha256_or_none(lock_path),
        "profiles_sha": file_sha256_or_none(profiles_path),
        "work_classification_sha": file_sha256_or_none(work_classification_path),
        "actor": args.actor,
        "trusted_human_change": bool(args.trusted_human_change),
        "changed_files": sorted(args.changed_file),
        "approval_source": args.approval_source,
        "approved_ticket": args.approved_ticket,
        "approval_evidence": args.approval_evidence,
        "expected_repository": args.expected_repository,
        "expected_pull_request": args.expected_pull_request,
        "expected_head": args.expected_head,
        "ticket_database": args.ticket_database,
        "ticket_snapshot": args.ticket_snapshot,
        "ticket_snapshot_sha256": args.ticket_snapshot_sha256,
        "migration_authorization": args.migration_authorization,
        "migration_authorization_sha256": args.migration_authorization_sha256,
        "migration_branch": args.migration_branch,
        "elapsed_minutes": args.elapsed_minutes,
    }
    return hashlib.sha256(json.dumps(key_payload, sort_keys=True).encode("utf-8")).hexdigest()


def resolve_cache_path(root: Path, custom_path: str | None) -> Path:
    if custom_path:
        p = Path(custom_path)
        return p if p.is_absolute() else (root / p)
    return root / ".subactor" / "cache" / "governance-preflight.json"


def is_preflight_cache_allowed(args: argparse.Namespace) -> bool:
    if args.no_cache:
        return False
    if args.actor == "ci" or args.enforce_approval:
        return False
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        return False
    return True


def load_preflight_cache(cache_path: Path, cache_key: str) -> dict[str, Any] | None:
    if not cache_path.is_file():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("schema") != "new-project.governance-preflight-cache/v1":
            return None
        entries = data.get("entries")
        if isinstance(entries, dict) and cache_key in entries:
            entry = entries[cache_key]
            if isinstance(entry, dict) and "payload" in entry:
                return entry
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def save_preflight_cache(
    cache_path: Path,
    cache_key: str,
    payload: dict[str, Any],
    selected_ticket: str | None,
) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {"schema": "new-project.governance-preflight-cache/v1", "entries": {}}
        if cache_path.is_file():
            try:
                with cache_path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict) and existing.get("schema") == "new-project.governance-preflight-cache/v1":
                    if isinstance(existing.get("entries"), dict):
                        data["entries"] = existing["entries"]
            except Exception:
                pass
        if len(data["entries"]) >= 50:
            keys_to_remove = list(data["entries"].keys())[: len(data["entries"]) - 49]
            for k in keys_to_remove:
                data["entries"].pop(k, None)
        entry_payload = dict(payload)
        entry_payload.pop("cached", None)
        data["entries"][cache_key] = {
            "payload": entry_payload,
            "selected_ticket": selected_ticket,
        }
        tmp_path = cache_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp_path.replace(cache_path)
    except OSError:
        pass


def run_governance_checks(
    args: argparse.Namespace,
    root: Path,
    manifest: dict[str, Any],
    report: Report,
) -> str | None:
    lock_path = optional_repo_path(root, args.lock, "GOV-SYNC-001", "governance lock", report)
    profiles_path = optional_repo_path(root, args.stack_profiles, "GOV-MANIFEST-001", "stack-profile", report)
    repository_policy = selected_policy(manifest)
    if repository_policy.get("tickets", {}).get("backend") == "planfile":
        projected = load_repository_policy_ticket(root, manifest, report)
        records = [projected] if projected is not None else []
        directories = []
        active = records[:]
    else:
        try:
            records = load_external_ticket_records(args, root, manifest["ticket"])
        except Exception:
            report.add("GOV-INTENT-002", "Ticket input is missing, invalid or untrusted for this validation mode.",
                "Use initialized local SQLite for local checks, or an independently acquired exact-subject snapshot and digest for CI.")
            return None
        if records is None:
            directories = ticket_directories(root, manifest["ticket"])
            records = load_ticket_records(directories, manifest["ticket"])
        else:
            directories = [record.directory for record in records]
        active = timed_step(report, "active_ticket_records", active_ticket_records, root, manifest["ticket"], records, report)
    base = timed_step(report, "resolve_validation_base", resolve_validation_base, args.base, root, records, manifest["ticket"], args.head, active)
    changed = timed_step(report, "resolve_changed_paths", resolve_changed_paths, args, root, base, report)
    historical_tickets, migration_repairs = prepare_snapshot_migrations(args, root, records, base, changed, report)
    if historical_tickets:
        # This candidate's imported metadata is historical evidence, not a live
        # reservation. The external controller still owns leases and closure.
        records = [record for record in records if record.directory.name not in historical_tickets]
        directories = [record.directory for record in records]
        active = [record for record in active if record.directory.name not in historical_tickets]
    changed = sorted(set(changed) | migration_repairs)
    changed_active = [
        record for record in active
        if any(path.startswith(f"{rel(root, record.directory).rstrip('/')}/") for path in changed)
    ]
    adoption_paths = atomic_standard_adoption_paths(
        root, base, changed, changed_active or active, report,
    )
    timed_step(report, "load_work_classification", load_work_classification, root, report, args.work_classification)
    timed_step(report, "check_lock", check_lock, root, lock_path, manifest, report)
    timed_step(report, "check_policy_dsl", check_policy_dsl, root, report)
    timed_step(report, "check_required_checks_declaration", check_required_checks_declaration, root, report)
    timed_step(report, "check_agent_hosts", check_agent_hosts, root, args.actor, report)
    timed_step(report, "check_required_files", check_required_files, root, manifest, report)
    timed_step(report, "check_version_parity", check_version_parity, root, manifest, report)
    timed_step(report, "check_domain_contracts", check_domain_contracts, root, manifest, report)
    timed_step(report, "check_docker_image_references", check_docker_image_references, root, manifest, report)
    timed_step(report, "check_stacks", check_stacks, root, manifest, profiles_path, report)
    timed_step(report, "check_ticket_content", check_ticket_content, root, directories, active, manifest["ticket"], report, records)
    repair_changed = [path for path in changed if path not in verified_import_paths(report)]
    timed_step(report, "check_coordination", check_coordination, root, manifest, records, repair_changed, adoption_paths, report, active)
    timed_step(report, "check_change_lease", check_change_lease, root, report)
    timed_step(report, "check_changed_content", check_changed_content, root, changed, args.actor, args.trusted_human_change, report)
    return timed_step(
        report, "check_change_gate", check_change_gate,
        root, manifest, records, changed, base, args.head, args.approval_source,
        args.approved_ticket, args.approval_evidence, args.expected_repository,
        args.expected_pull_request, args.expected_head, args.enforce_approval,
        args.elapsed_minutes, adoption_paths, report, active,
    )


def formatted_report(payload: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output_format == "sarif":
        return json.dumps(sarif(payload), indent=2, sort_keys=True) + "\n"
    return render_text(payload)


def write_report(output_path: Path | None, output: str) -> None:
    if output_path is None:
        sys.stdout.write(output)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")


def write_resolved_ticket(
    root: Path,
    raw_path: str | None,
    selected_ticket: str | None,
    report: Report,
) -> None:
    if not raw_path or not selected_ticket or report.errors:
        return
    path = Path(raw_path).expanduser().resolve()
    if path.is_relative_to(root):
        report.add(
            "GOV-PATH-001", "Resolved ticket output must be outside the repository checkout.",
            "Write ephemeral approval context to runner.temp or another protected directory.",
            [rel(root, path)],
        )
        return
    try:
        path.write_text(f"{selected_ticket}\n", encoding="utf-8")
    except OSError as error:
        report.add(
            "GOV-PATH-001", f"Could not write resolved ticket output: {error}",
            "Use a writable protected directory outside the checkout.",
        )


def main(argv: list[str] | None = None) -> int:
    t_start = time.perf_counter()
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    report = Report(root, timing=args.timing)

    cache_allowed = is_preflight_cache_allowed(args)
    cache_path = resolve_cache_path(root, args.cache_file)
    cache_key: str | None = None

    manifest_path: Path | None = None
    lock_path: Path | None = None
    profiles_path: Path | None = None
    work_class_path: Path | None = None

    try:
        manifest_path = safe_repo_path(root, args.manifest)
    except ValueError:
        pass
    try:
        lock_path = safe_repo_path(root, args.lock) if args.lock else None
    except ValueError:
        pass
    try:
        profiles_path = safe_repo_path(root, args.stack_profiles) if args.stack_profiles else None
    except ValueError:
        pass
    try:
        work_class_path = safe_repo_path(root, args.work_classification) if args.work_classification else None
    except ValueError:
        pass

    if cache_allowed and manifest_path and manifest_path.is_file():
        cache_key = compute_preflight_cache_key(
            root, args, manifest_path, lock_path, profiles_path, work_class_path
        )
        if cache_key:
            cached_entry = load_preflight_cache(cache_path, cache_key)
            if cached_entry is not None:
                payload = cached_entry["payload"]
                selected_ticket = cached_entry.get("selected_ticket")
                payload["cached"] = True
                if args.timing:
                    timings = dict(payload.get("timings", {}))
                    timings["preflight_cache"] = round(time.perf_counter() - t_start, 4)
                    payload["timings"] = timings
                write_resolved_ticket(root, args.resolved_ticket_output, selected_ticket, report)
                output_path = optional_repo_path(root, args.output, "GOV-PATH-001", "report output", report)
                current = report.payload()
                if current["findings"]:
                    payload["findings"].extend(current["findings"])
                    for field in ("errors", "warnings", "findings"):
                        payload["summary"][field] += current["summary"][field]
                    payload["status"] = "failed" if payload["summary"]["errors"] else "passed"
                write_report(output_path, formatted_report(payload, args.format))
                return 0 if payload["summary"]["errors"] == 0 else 1

    manifest = load_manifest(root, args.manifest, report)
    selected_ticket: str | None = None

    if manifest is not None:
        selected_ticket = run_governance_checks(args, root, manifest, report)
    write_resolved_ticket(root, args.resolved_ticket_output, selected_ticket, report)
    output_path = optional_repo_path(root, args.output, "GOV-PATH-001", "report output", report)
    payload = report.payload()
    if args.timing:
        report.record_timing("total", time.perf_counter() - t_start)
        payload["timings"] = report.timings

    if cache_allowed and cache_key and report.errors == 0:
        save_preflight_cache(cache_path, cache_key, payload, selected_ticket)

    write_report(output_path, formatted_report(payload, args.format))
    return 0 if report.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
