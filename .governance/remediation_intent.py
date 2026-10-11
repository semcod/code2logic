#!/usr/bin/env python3
"""Validate and project target-owned diagnostic remediation intent DSL files."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Any


INTENT_SCHEMA = "new-project.remediation-intent/v1"
VALIDATION_SCHEMA = "new-project.remediation-validation/v1"
T2C_DIAGNOSTICS_SCHEMA = "t2c.diagnostics/v1"
T2C_PLAN_SET_SCHEMA = "t2c.code-change-plan-set/v1"
T2C_PLAN_SCHEMA = "t2c.code-change-plan/v1"
T2C_GRAPH_SCHEMA = "t2c.graph/v1"
MALFORMED_CODE = "GOV-REMEDIATION-001"
T2C_CODE = "GOV-REMEDIATION-002"
STALE_CODE = "GOV-REMEDIATION-003"
PROJECTION_CODE = "GOV-REMEDIATION-004"

INTENT_ID = re.compile(r"RI-[A-Z0-9][A-Z0-9-]*")
TICKET_ID = re.compile(r"ticket-[0-9]{3,}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
FINDING_ID = re.compile(r"F-[A-Z0-9][A-Z0-9-]*")
ACTION_ID = re.compile(r"A-[A-Z0-9][A-Z0-9-]*")
VERIFICATION_ID = re.compile(r"V-[A-Z0-9][A-Z0-9-]*")
CRITERION_ID = re.compile(r"AC-[0-9]+")
DIAGNOSTIC_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:[_-][A-Z0-9]+)*")
DIGEST = re.compile(r"[0-9a-f]{64}")
SOURCE_DATE_TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})"
)

FINDING_CATEGORIES = {
    "FALSE_POSITIVE",
    "SILENT_OMISSION",
    "AMBIGUOUS_HEURISTIC",
    "CONTRACT_DRIFT",
    "MISSING_INVENTORY",
    "STATE_RISK",
    "OTHER",
}
FINDING_STATUSES = {"CONFIRMED", "PROPOSED", "DEFERRED"}
PRIORITIES = {"P0", "P1", "P2", "P3"}
DIAGNOSTIC_STATES = {"EMITTED", "MISSING", "FALSE_POSITIVE", "DRIFT"}
DIAGNOSTIC_OUTCOMES = {"EMIT", "SUPPRESS", "REFINE", "PRESERVE"}
OPERATIONS = {
    "CLASSIFY",
    "IMPLEMENT",
    "TEST",
    "DOCUMENT",
    "RELEASE",
    "TRIAGE",
    "PRESERVE",
}
RISK_LEVELS = {"READ_ONLY", "REVERSIBLE_WRITE", "DESTRUCTIVE"}
AUTHORIZATIONS = {
    "NOT_APPLICABLE",
    "SESSION_EXECUTION_AUTHORIZATION",
    "EXPLICIT_HUMAN",
}
AUTOMATION_VALUES = {"ALLOWED", "PROHIBITED"}
VERIFICATION_TYPES = {"COMMAND", "ASSERTION", "EXTERNAL_EVIDENCE"}
ANALYSIS_CODES = {
    "T2C_AMBIGUOUS_INTENT",
    "T2C_CONFLICT",
    "T2C_CRITERION_GAP",
    "T2C_PLAN_GAP",
    "T2C_PRIORITY_DRIFT",
    "T2C_SCOPE_EXPANSION",
    "T2C_UNAUTHORIZED_DELETION",
}
REQUIRED_T2C_DIAGNOSTIC_CODES = {
    "AMBIGUOUS_REQUIREMENT",
    "HUMAN_AGENT_CONFLICT",
    "HUMAN_COMMUNICATION_CONFLICT",
    "PLANNED_NOT_IMPLEMENTED",
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def intent_projection(document: dict[str, Any]) -> dict[str, Any]:
    """Return the authority-bearing projection used by advisory bindings."""
    projection = deepcopy(document)
    projection.pop("advisoryAnalysis", None)
    if projection.get("status") == "ANALYZED":
        projection["status"] = "READY"
    return projection


def intent_digest(document: dict[str, Any]) -> str:
    return _digest(intent_projection(document))


def _expect_object(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(_issue(MALFORMED_CODE, path, "must be an object"))
        return {}
    return value



def _cross_check_record(
    value: dict[str, Any],
    string_fields: tuple[str, ...],
    object_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Copy already diagnosed collections for safe cross-field checks.

    Preserve exact string bytes and the original input/digest. Invalid entries
    remain rejected by the preceding field validators, never repaired or
    promoted into a valid plan by this private view.
    """
    result = dict(value)
    for field in string_fields:
        raw = value.get(field)
        result[field] = ([item for item in raw if isinstance(item, str)]
                         if isinstance(raw, list) else [])
    for field in object_fields:
        raw = value.get(field)
        result[field] = ([item for item in raw if isinstance(item, dict)]
                         if isinstance(raw, list) else [])
    return result


def _exact_fields(
    value: dict[str, Any],
    path: str,
    required: set[str],
    optional: set[str],
    errors: list[dict[str, str]],
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        errors.append(
            _issue(MALFORMED_CODE, path, f"missing fields: {', '.join(missing)}")
        )
    if unknown:
        errors.append(
            _issue(MALFORMED_CODE, path, f"unknown fields: {', '.join(unknown)}")
        )


def _nonempty_text(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(_issue(MALFORMED_CODE, path, "must be a non-empty string"))
        return ""
    return value.strip()


def _enum(
    value: Any,
    allowed: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> str:
    result = _nonempty_text(value, path, errors)
    if result and result not in allowed:
        errors.append(
            _issue(
                MALFORMED_CODE,
                path,
                f"must be one of: {', '.join(sorted(allowed))}",
            )
        )
    return result


def _string_list(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
    *,
    minimum: int = 0,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(_issue(MALFORMED_CODE, path, "must be an array"))
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty_text(item, f"{path}[{index}]", errors)
        if text:
            result.append(text)
    if len(result) < minimum:
        errors.append(
            _issue(MALFORMED_CODE, path, f"must contain at least {minimum} item(s)")
        )
    if len(result) != len(set(result)):
        errors.append(_issue(MALFORMED_CODE, path, "must contain unique items"))
    return result


def _pattern(
    value: Any,
    pattern: re.Pattern[str],
    path: str,
    errors: list[dict[str, str]],
) -> str:
    result = _nonempty_text(value, path, errors)
    if result and pattern.fullmatch(result) is None:
        errors.append(_issue(MALFORMED_CODE, path, "has an invalid identifier"))
    return result


def _safe_path(value: str) -> bool:
    if value == "unresolved:agent":
        return True
    if not value or "\\" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return ".." not in path.parts and not value.startswith("unresolved:")


def _path_list(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
    *,
    minimum: int = 0,
) -> list[str]:
    result = _string_list(value, path, errors, minimum=minimum)
    for index, item in enumerate(result):
        if not _safe_path(item):
            errors.append(
                _issue(MALFORMED_CODE, f"{path}[{index}]", "must be a safe relative path")
            )
    return result


def _duplicate_ids(
    items: list[Any],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        item_id = item["id"]
        if item_id in seen:
            errors.append(
                _issue(MALFORMED_CODE, f"{path}[{index}].id", f"duplicate id: {item_id}")
            )
        seen.add(item_id)


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(node: str) -> None:
        if node in active_set:
            start = active.index(node)
            cycles.append(active[start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        active.append(node)
        active_set.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                visit(dependency)
        active.pop()
        active_set.remove(node)

    for node in graph:
        visit(node)
    return cycles


def _matches(path: str, patterns: list[str]) -> bool:
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
                    and fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
                    and visit(path_index + 1, pattern_index + 1)
                )
            memo[key] = result
            return result

        return visit(0, 0)

    return any(match_pattern(pattern) for pattern in patterns)


def _ancestors(action_id: str, graph: dict[str, list[str]]) -> set[str]:
    result: set[str] = set()
    pending = list(graph.get(action_id, []))
    while pending:
        candidate = pending.pop()
        if candidate in result:
            continue
        result.add(candidate)
        pending.extend(graph.get(candidate, []))
    return result


def _validate_source(
    document: dict[str, Any],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    source = _expect_object(document.get("source"), "source", errors)
    _exact_fields(source, "source", {"producer", "observedAt", "reportDigest"}, set(), errors)
    producer = _expect_object(source.get("producer"), "source.producer", errors)
    _exact_fields(producer, "source.producer", {"name", "version"}, set(), errors)
    _nonempty_text(producer.get("name"), "source.producer.name", errors)
    _nonempty_text(producer.get("version"), "source.producer.version", errors)
    observed = _nonempty_text(source.get("observedAt"), "source.observedAt", errors)
    if observed:
        try:
            if SOURCE_DATE_TIME.fullmatch(source["observedAt"]) is None:
                raise ValueError("date-time requires full time and an explicit zone")
            datetime.fromisoformat(observed.upper().replace("Z", "+00:00"))
        except ValueError:
            errors.append(
                _issue(MALFORMED_CODE, "source.observedAt", "must be a full ISO-8601 date-time with an explicit timezone")
            )
    report_digest = _nonempty_text(
        source.get("reportDigest"), "source.reportDigest", errors
    )
    if report_digest and report_digest != "unresolved:agent" and DIGEST.fullmatch(report_digest) is None:
        errors.append(
            _issue(MALFORMED_CODE, "source.reportDigest", "must be a SHA-256 digest")
        )
    if report_digest == "unresolved:agent":
        warnings.append(
            _issue(MALFORMED_CODE, "source.reportDigest", "report digest is unresolved")
        )


def _validate_objective_scope(
    document: dict[str, Any],
    errors: list[dict[str, str]],
) -> tuple[list[str], list[str], list[str]]:
    objective = _expect_object(document.get("objective"), "objective", errors)
    _exact_fields(objective, "objective", {"outcome", "nonGoals", "constraints"}, set(), errors)
    _nonempty_text(objective.get("outcome"), "objective.outcome", errors)
    _string_list(objective.get("nonGoals"), "objective.nonGoals", errors, minimum=1)
    _string_list(objective.get("constraints"), "objective.constraints", errors, minimum=1)

    scope = _expect_object(document.get("scope"), "scope", errors)
    _exact_fields(scope, "scope", {"allowedPaths", "forbiddenPaths", "preservePaths"}, set(), errors)
    allowed = _path_list(scope.get("allowedPaths"), "scope.allowedPaths", errors, minimum=1)
    forbidden = _path_list(scope.get("forbiddenPaths"), "scope.forbiddenPaths", errors)
    preserve = _path_list(scope.get("preservePaths"), "scope.preservePaths", errors)
    return allowed, forbidden, preserve


def _validate_finding_evidence(finding, path, errors):
    evidence = finding.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(_issue(MALFORMED_CODE, f"{path}.evidence", "must be a non-empty array"))
    else:
        for evidence_index, evidence_candidate in enumerate(evidence):
            evidence_path = f"{path}.evidence[{evidence_index}]"
            item = _expect_object(evidence_candidate, evidence_path, errors)
            _exact_fields(item, evidence_path, {"ref", "observation"}, set(), errors)
            _nonempty_text(item.get("ref"), f"{evidence_path}.ref", errors)
            _nonempty_text(item.get("observation"), f"{evidence_path}.observation", errors)



def _validate_finding_applicability(finding, path, errors):
    applicability = _expect_object(finding.get("applicability"), f"{path}.applicability", errors)
    _exact_fields(
        applicability,
        f"{path}.applicability",
        {"requiredSignals", "excludedSignals", "unknownOutcome"},
        set(),
        errors,
    )
    required_signals = _string_list(
        applicability.get("requiredSignals"),
        f"{path}.applicability.requiredSignals",
        errors,
        minimum=1,
    )
    excluded_signals = _string_list(
        applicability.get("excludedSignals"),
        f"{path}.applicability.excludedSignals",
        errors,
    )
    _enum(
        applicability.get("unknownOutcome"),
        {"BLOCK", "REPORT"},
        f"{path}.applicability.unknownOutcome",
        errors,
    )
    return required_signals, excluded_signals


def _validate_finding_transition(category, current, required, required_signals, excluded_signals, path, errors):
    if category == "FALSE_POSITIVE":
        if current != "FALSE_POSITIVE" or required not in {"REFINE", "SUPPRESS"}:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.diagnostic",
                    "FALSE_POSITIVE requires current=FALSE_POSITIVE and required=REFINE|SUPPRESS",
                )
            )
        if not required_signals or not excluded_signals:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.applicability",
                    "FALSE_POSITIVE requires both positive and excluded signals",
                )
            )
    if category in {"SILENT_OMISSION", "MISSING_INVENTORY"} and (
        current != "MISSING" or required != "EMIT"
    ):
        errors.append(
            _issue(
                MALFORMED_CODE,
                f"{path}.diagnostic",
                f"{category} requires current=MISSING and required=EMIT",
            )
        )


def _validate_findings(
    document: dict[str, Any],
    errors: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = document.get("findings")
    if not isinstance(raw, list) or not raw:
        errors.append(_issue(MALFORMED_CODE, "findings", "must be a non-empty array"))
        return [], {}
    _duplicate_ids(raw, "findings", errors)
    findings: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw):
        path = f"findings[{index}]"
        finding = _expect_object(candidate, path, errors)
        _exact_fields(
            finding,
            path,
            {
                "id",
                "category",
                "status",
                "priority",
                "summary",
                "diagnostic",
                "evidence",
                "applicability",
                "desiredOutcome",
                "affectedPaths",
                "dependsOn",
                "acceptanceCriteria",
            },
            set(),
            errors,
        )
        finding_id = _pattern(finding.get("id"), FINDING_ID, f"{path}.id", errors)
        category = _enum(finding.get("category"), FINDING_CATEGORIES, f"{path}.category", errors)
        _enum(finding.get("status"), FINDING_STATUSES, f"{path}.status", errors)
        _enum(finding.get("priority"), PRIORITIES, f"{path}.priority", errors)
        _nonempty_text(finding.get("summary"), f"{path}.summary", errors)
        diagnostic = _expect_object(finding.get("diagnostic"), f"{path}.diagnostic", errors)
        _exact_fields(diagnostic, f"{path}.diagnostic", {"code", "current", "required"}, set(), errors)
        code = _pattern(diagnostic.get("code"), DIAGNOSTIC_CODE, f"{path}.diagnostic.code", errors)
        current = _enum(diagnostic.get("current"), DIAGNOSTIC_STATES, f"{path}.diagnostic.current", errors)
        required = _enum(diagnostic.get("required"), DIAGNOSTIC_OUTCOMES, f"{path}.diagnostic.required", errors)

        _validate_finding_evidence(finding, path, errors)

        required_signals, excluded_signals = _validate_finding_applicability(finding, path, errors)
        _nonempty_text(finding.get("desiredOutcome"), f"{path}.desiredOutcome", errors)
        _path_list(finding.get("affectedPaths"), f"{path}.affectedPaths", errors, minimum=1)
        _string_list(finding.get("dependsOn"), f"{path}.dependsOn", errors)
        _string_list(
            finding.get("acceptanceCriteria"),
            f"{path}.acceptanceCriteria",
            errors,
            minimum=1,
        )

        _validate_finding_transition(category, current, required, required_signals, excluded_signals, path, errors)
        if finding_id and code:
            findings.append(_cross_check_record(
                finding, ("affectedPaths", "dependsOn", "acceptanceCriteria"), ("evidence",)
            ))
    finding_by_id = {item["id"]: item for item in findings}
    graph: dict[str, list[str]] = {}
    for index, finding in enumerate(findings):
        dependencies = finding.get("dependsOn", [])
        graph[finding["id"]] = dependencies if isinstance(dependencies, list) else []
        for dependency in graph[finding["id"]]:
            if dependency not in finding_by_id:
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"findings[{index}].dependsOn",
                        f"unknown finding dependency: {dependency}",
                    )
                )
    for cycle in _cycles(graph):
        errors.append(
            _issue(MALFORMED_CODE, "findings", f"dependency cycle: {' -> '.join(cycle)}")
        )
    return findings, finding_by_id


def _validate_verifications(
    document: dict[str, Any],
    errors: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = document.get("verifications")
    if not isinstance(raw, list) or not raw:
        errors.append(
            _issue(MALFORMED_CODE, "verifications", "must be a non-empty array")
        )
        return [], {}
    _duplicate_ids(raw, "verifications", errors)
    result: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw):
        path = f"verifications[{index}]"
        item = _expect_object(candidate, path, errors)
        _exact_fields(
            item,
            path,
            {"id", "type", "command", "expected", "deterministic", "covers"},
            set(),
            errors,
        )
        verification_id = _pattern(item.get("id"), VERIFICATION_ID, f"{path}.id", errors)
        verification_type = _enum(item.get("type"), VERIFICATION_TYPES, f"{path}.type", errors)
        command = item.get("command")
        if verification_type == "COMMAND":
            _nonempty_text(command, f"{path}.command", errors)
        elif command is not None:
            _nonempty_text(command, f"{path}.command", errors)
        _nonempty_text(item.get("expected"), f"{path}.expected", errors)
        if not isinstance(item.get("deterministic"), bool):
            errors.append(_issue(MALFORMED_CODE, f"{path}.deterministic", "must be boolean"))
        _string_list(item.get("covers"), f"{path}.covers", errors, minimum=1)
        if verification_id:
            result.append(_cross_check_record(item, ("covers",)))
    return result, {item["id"]: item for item in result}


def _validate_action_verifications(verification_ids, verification_by_id, action_id, finding_ids, path, errors):
    verification_coverage: set[str] = set()
    for verification_id in verification_ids:
        verification = verification_by_id.get(verification_id)
        if verification is None:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.verificationIds",
                    f"unknown verification: {verification_id}",
                )
            )
        elif verification.get("deterministic") is not True:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.verificationIds",
                    f"action requires deterministic verification: {verification_id}",
                )
            )
        else:
            verification_coverage.update(verification.get("covers", []))
    missing_coverage = sorted(
        {action_id, *finding_ids} - verification_coverage
    )
    if missing_coverage:
        errors.append(
            _issue(
                MALFORMED_CODE,
                f"{path}.verificationIds",
                "selected verifications do not cover: "
                + ", ".join(missing_coverage),
            )
        )


def _validate_action_paths(paths, allowed, forbidden, path, errors):
    for action_path in paths:
        if action_path == "unresolved:agent":
            continue
        if not _matches(action_path, allowed):
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.paths",
                    f"path is outside scope.allowedPaths: {action_path}",
                )
            )
        if _matches(action_path, forbidden):
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.paths",
                    f"path matches scope.forbiddenPaths: {action_path}",
                )
            )


def _validate_action_risk(level, authorization, automation, finding_ids, finding_by_id, operation, preserves_user_data, path, errors):
    if level == "DESTRUCTIVE" and (
        authorization != "EXPLICIT_HUMAN" or automation != "PROHIBITED"
    ):
        errors.append(
            _issue(
                MALFORMED_CODE,
                f"{path}.risk",
                "DESTRUCTIVE action requires EXPLICIT_HUMAN and PROHIBITED automation",
            )
        )
    state_risk = any(
        finding_by_id.get(finding_id, {}).get("category") == "STATE_RISK"
        for finding_id in finding_ids
    )
    if state_risk and (
        operation != "PRESERVE"
        or automation != "PROHIBITED"
        or preserves_user_data is not True
    ):
        errors.append(
            _issue(
                MALFORMED_CODE,
                f"{path}.risk",
                "STATE_RISK requires a PRESERVE action with prohibited automation and preserved user data",
            )
        )


def _validate_action_dependencies(actions, finding_by_id, errors):
    action_ids = {item["id"] for item in actions}
    graph: dict[str, list[str]] = {}
    for index, action in enumerate(actions):
        dependencies = action.get("dependsOn", [])
        graph[action["id"]] = dependencies if isinstance(dependencies, list) else []
        for dependency in graph[action["id"]]:
            if dependency not in action_ids:
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"actions[{index}].dependsOn",
                        f"unknown action dependency: {dependency}",
                    )
                )
    for cycle in _cycles(graph):
        errors.append(
            _issue(MALFORMED_CODE, "actions", f"dependency cycle: {' -> '.join(cycle)}")
        )

    blocking_actions = {
        action["id"]
        for action in actions
        if action.get("operation") != "RELEASE"
        and any(
            finding_by_id.get(finding_id, {}).get("priority") in {"P0", "P1"}
            and finding_by_id.get(finding_id, {}).get("status") != "DEFERRED"
            for finding_id in action.get("findingIds", [])
        )
    }
    for index, action in enumerate(actions):
        if action.get("operation") != "RELEASE":
            continue
        missing = sorted(blocking_actions - _ancestors(action["id"], graph))
        if missing:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"actions[{index}].dependsOn",
                    "RELEASE must depend transitively on P0/P1 repair actions: "
                    + ", ".join(missing),
                )
            )
    return graph


def _validate_actions(
    document: dict[str, Any],
    finding_by_id: dict[str, dict[str, Any]],
    verification_by_id: dict[str, dict[str, Any]],
    allowed: list[str],
    forbidden: list[str],
    preserve: list[str],
    errors: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    raw = document.get("actions")
    if not isinstance(raw, list) or not raw:
        errors.append(_issue(MALFORMED_CODE, "actions", "must be a non-empty array"))
        return [], {}
    _duplicate_ids(raw, "actions", errors)
    actions: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw):
        path = f"actions[{index}]"
        item = _expect_object(candidate, path, errors)
        _exact_fields(
            item,
            path,
            {
                "id",
                "findingIds",
                "operation",
                "description",
                "paths",
                "dependsOn",
                "verificationIds",
                "risk",
            },
            set(),
            errors,
        )
        action_id = _pattern(item.get("id"), ACTION_ID, f"{path}.id", errors)
        finding_ids = _string_list(item.get("findingIds"), f"{path}.findingIds", errors, minimum=1)
        operation = _enum(item.get("operation"), OPERATIONS, f"{path}.operation", errors)
        _nonempty_text(item.get("description"), f"{path}.description", errors)
        paths = _path_list(item.get("paths"), f"{path}.paths", errors, minimum=1)
        dependencies = _string_list(item.get("dependsOn"), f"{path}.dependsOn", errors)
        verification_ids = _string_list(
            item.get("verificationIds"), f"{path}.verificationIds", errors, minimum=1
        )
        risk = _expect_object(item.get("risk"), f"{path}.risk", errors)
        _exact_fields(
            risk,
            f"{path}.risk",
            {"level", "authorization", "automation", "preservesUserData"},
            set(),
            errors,
        )
        level = _enum(risk.get("level"), RISK_LEVELS, f"{path}.risk.level", errors)
        authorization = _enum(
            risk.get("authorization"),
            AUTHORIZATIONS,
            f"{path}.risk.authorization",
            errors,
        )
        automation = _enum(
            risk.get("automation"), AUTOMATION_VALUES, f"{path}.risk.automation", errors
        )
        preserves_user_data = risk.get("preservesUserData")
        if not isinstance(preserves_user_data, bool):
            errors.append(
                _issue(MALFORMED_CODE, f"{path}.risk.preservesUserData", "must be boolean")
            )
        for finding_id in finding_ids:
            if finding_id not in finding_by_id:
                errors.append(
                    _issue(MALFORMED_CODE, f"{path}.findingIds", f"unknown finding: {finding_id}")
                )
        _validate_action_verifications(verification_ids, verification_by_id, action_id, finding_ids, path, errors)
        _validate_action_paths(paths, allowed, forbidden, path, errors)
        _validate_action_risk(level, authorization, automation, finding_ids, finding_by_id, operation, preserves_user_data, path, errors)
        if operation == "PRESERVE" and preserve and not any(
            _matches(action_path, preserve)
            for action_path in paths
            if action_path != "unresolved:agent"
        ):
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"{path}.paths",
                    "PRESERVE action must reference scope.preservePaths",
                )
            )
        if action_id:
            actions.append(_cross_check_record(
                item, ("paths", "dependsOn", "findingIds", "verificationIds")
            ))

    graph = _validate_action_dependencies(actions, finding_by_id, errors)
    return actions, graph


def _validate_planning_guidance(document, action_graph, errors):
    guidance = _expect_object(document.get("llmGuidance"), "llmGuidance", errors)
    _exact_fields(
        guidance,
        "llmGuidance",
        {"role", "mustPreserve", "forbiddenAssumptions", "planningOrder", "openQuestions"},
        set(),
        errors,
    )
    _nonempty_text(guidance.get("role"), "llmGuidance.role", errors)
    _string_list(guidance.get("mustPreserve"), "llmGuidance.mustPreserve", errors, minimum=1)
    _string_list(
        guidance.get("forbiddenAssumptions"),
        "llmGuidance.forbiddenAssumptions",
        errors,
        minimum=1,
    )
    planning_order = _string_list(
        guidance.get("planningOrder"), "llmGuidance.planningOrder", errors, minimum=1
    )
    _string_list(guidance.get("openQuestions"), "llmGuidance.openQuestions", errors)
    if set(planning_order) != set(action_graph):
        errors.append(
            _issue(
                MALFORMED_CODE,
                "llmGuidance.planningOrder",
                "must contain every action id exactly once",
            )
        )
    position = {action_id: index for index, action_id in enumerate(planning_order)}
    for action_id, dependencies in action_graph.items():
        for dependency in dependencies:
            if position.get(dependency, -1) >= position.get(action_id, -1):
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        "llmGuidance.planningOrder",
                        f"dependency order violated: {dependency} before {action_id}",
                    )
                )



def _validate_todo2code_contract(document, errors):
    todo2code = _expect_object(document.get("todo2code"), "todo2code", errors)
    _exact_fields(
        todo2code,
        "todo2code",
        {"enabled", "taskPath", "todoPath", "planSchema", "requiredDiagnosticCodes"},
        set(),
        errors,
    )
    if not isinstance(todo2code.get("enabled"), bool):
        errors.append(_issue(MALFORMED_CODE, "todo2code.enabled", "must be boolean"))
    _path_list([todo2code.get("taskPath")], "todo2code.taskPath", errors, minimum=1)
    _path_list([todo2code.get("todoPath")], "todo2code.todoPath", errors, minimum=1)
    if todo2code.get("planSchema") != T2C_PLAN_SCHEMA:
        errors.append(
            _issue(MALFORMED_CODE, "todo2code.planSchema", f"must be {T2C_PLAN_SCHEMA}")
        )
    diagnostic_codes = _string_list(
        todo2code.get("requiredDiagnosticCodes"),
        "todo2code.requiredDiagnosticCodes",
        errors,
        minimum=1,
    )
    missing_diagnostic_codes = sorted(
        REQUIRED_T2C_DIAGNOSTIC_CODES - set(diagnostic_codes)
    )
    unknown_diagnostic_codes = sorted(
        set(diagnostic_codes) - REQUIRED_T2C_DIAGNOSTIC_CODES
    )
    if missing_diagnostic_codes:
        errors.append(
            _issue(
                MALFORMED_CODE,
                "todo2code.requiredDiagnosticCodes",
                "missing required consistency diagnostics: "
                + ", ".join(missing_diagnostic_codes),
            )
        )
    if unknown_diagnostic_codes:
        errors.append(
            _issue(
                MALFORMED_CODE,
                "todo2code.requiredDiagnosticCodes",
                "unsupported consistency diagnostics: "
                + ", ".join(unknown_diagnostic_codes),
            )
        )


def _validate_finding_criteria(criteria, finding_by_id, errors):
    criterion_ids = {item["id"] for item in criteria}
    for finding_id, finding in finding_by_id.items():
        for criterion_id in finding.get("acceptanceCriteria", []):
            if criterion_id not in criterion_ids:
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"finding:{finding_id}.acceptanceCriteria",
                        f"unknown acceptance criterion: {criterion_id}",
                    )
                )
            elif finding_id not in next(
                item["findingIds"] for item in criteria if item["id"] == criterion_id
            ):
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"finding:{finding_id}.acceptanceCriteria",
                        f"criterion does not bind this finding: {criterion_id}",
                    )
                )



def _validate_criteria_guidance_t2c(
    document: dict[str, Any],
    finding_by_id: dict[str, dict[str, Any]],
    action_graph: dict[str, list[str]],
    verification_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, str]],
) -> None:
    raw_criteria = document.get("acceptanceCriteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        errors.append(
            _issue(MALFORMED_CODE, "acceptanceCriteria", "must be a non-empty array")
        )
        criteria: list[dict[str, Any]] = []
    else:
        _duplicate_ids(raw_criteria, "acceptanceCriteria", errors)
        criteria = []
        for index, candidate in enumerate(raw_criteria):
            path = f"acceptanceCriteria[{index}]"
            item = _expect_object(candidate, path, errors)
            _exact_fields(
                item,
                path,
                {"id", "statement", "findingIds", "verificationIds"},
                set(),
                errors,
            )
            criterion_id = _pattern(item.get("id"), CRITERION_ID, f"{path}.id", errors)
            _nonempty_text(item.get("statement"), f"{path}.statement", errors)
            finding_ids = _string_list(item.get("findingIds"), f"{path}.findingIds", errors, minimum=1)
            verification_ids = _string_list(
                item.get("verificationIds"), f"{path}.verificationIds", errors, minimum=1
            )
            for finding_id in finding_ids:
                if finding_id not in finding_by_id:
                    errors.append(
                        _issue(MALFORMED_CODE, f"{path}.findingIds", f"unknown finding: {finding_id}")
                    )
            for verification_id in verification_ids:
                if verification_id not in verification_by_id:
                    errors.append(
                        _issue(
                            MALFORMED_CODE,
                            f"{path}.verificationIds",
                            f"unknown verification: {verification_id}",
                        )
                    )
            verification_coverage = {
                covered
                for verification_id in verification_ids
                for covered in verification_by_id.get(verification_id, {}).get(
                    "covers", []
                )
            }
            uncovered_findings = sorted(
                set(finding_ids) - verification_coverage
            )
            if uncovered_findings:
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"{path}.verificationIds",
                        "criterion verifications do not cover findings: "
                        + ", ".join(uncovered_findings),
                    )
                )
            if criterion_id:
                criteria.append(_cross_check_record(item, ("findingIds", "verificationIds")))

    _validate_finding_criteria(criteria, finding_by_id, errors)
    _validate_planning_guidance(document, action_graph, errors)
    _validate_todo2code_contract(document, errors)


def _validate_analysis(
    document: dict[str, Any],
    errors: list[dict[str, str]],
) -> None:
    status = document.get("status")
    analysis = document.get("advisoryAnalysis")
    if status == "ANALYZED" and not isinstance(analysis, dict):
        errors.append(
            _issue(MALFORMED_CODE, "advisoryAnalysis", "ANALYZED status requires advisoryAnalysis")
        )
        return
    if analysis is None:
        return
    analysis = _expect_object(analysis, "advisoryAnalysis", errors)
    _exact_fields(
        analysis,
        "advisoryAnalysis",
        {
            "authority",
            "producer",
            "analyzedAt",
            "intentDigest",
            "graphDigest",
            "diagnosticsDigest",
            "plansDigest",
            "projectionRecordIds",
            "planIds",
            "findings",
            "llmHints",
        },
        set(),
        errors,
    )
    if analysis.get("authority") != "ADVISORY":
        errors.append(
            _issue(MALFORMED_CODE, "advisoryAnalysis.authority", "must be ADVISORY")
        )
    producer = _expect_object(analysis.get("producer"), "advisoryAnalysis.producer", errors)
    _exact_fields(producer, "advisoryAnalysis.producer", {"name", "version", "mode"}, set(), errors)
    if producer.get("name") != "todo2code" or producer.get("mode") != "deterministic":
        errors.append(
            _issue(
                MALFORMED_CODE,
                "advisoryAnalysis.producer",
                "must identify deterministic todo2code",
            )
        )
    _nonempty_text(producer.get("version"), "advisoryAnalysis.producer.version", errors)
    _nonempty_text(analysis.get("analyzedAt"), "advisoryAnalysis.analyzedAt", errors)
    for field in ("intentDigest", "graphDigest", "diagnosticsDigest", "plansDigest"):
        value = _nonempty_text(analysis.get(field), f"advisoryAnalysis.{field}", errors)
        if value and DIGEST.fullmatch(value) is None:
            errors.append(
                _issue(MALFORMED_CODE, f"advisoryAnalysis.{field}", "must be SHA-256")
            )
    if analysis.get("intentDigest") != intent_digest(document):
        errors.append(
            _issue(
                STALE_CODE,
                "advisoryAnalysis.intentDigest",
                "analysis is stale for the authority-bearing intent projection",
            )
        )
    _string_list(
        analysis.get("projectionRecordIds"),
        "advisoryAnalysis.projectionRecordIds",
        errors,
        minimum=1,
    )
    _string_list(analysis.get("planIds"), "advisoryAnalysis.planIds", errors)
    _string_list(analysis.get("llmHints"), "advisoryAnalysis.llmHints", errors)
    findings = analysis.get("findings")
    if not isinstance(findings, list):
        errors.append(_issue(MALFORMED_CODE, "advisoryAnalysis.findings", "must be an array"))
    else:
        for index, candidate in enumerate(findings):
            path = f"advisoryAnalysis.findings[{index}]"
            item = _expect_object(candidate, path, errors)
            _exact_fields(item, path, {"code", "severity", "message", "references", "llmHint"}, set(), errors)
            _enum(item.get("code"), ANALYSIS_CODES, f"{path}.code", errors)
            _enum(item.get("severity"), {"BLOCKING", "REVIEW", "INFO"}, f"{path}.severity", errors)
            _nonempty_text(item.get("message"), f"{path}.message", errors)
            _string_list(item.get("references"), f"{path}.references", errors, minimum=1)
            _nonempty_text(item.get("llmHint"), f"{path}.llmHint", errors)


def _validate_finding_paths(findings, allowed, forbidden, errors):
    for finding in findings:
        for affected_path in finding.get("affectedPaths", []):
            if affected_path == "unresolved:agent":
                continue
            if not _matches(affected_path, allowed):
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"finding:{finding['id']}.affectedPaths",
                        f"path is outside scope.allowedPaths: {affected_path}",
                    )
                )
            if _matches(affected_path, forbidden):
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"finding:{finding['id']}.affectedPaths",
                        f"path matches scope.forbiddenPaths: {affected_path}",
                    )
                )


def _validate_unresolved_paths(document, status, owner_route, allowed, findings, actions, errors, warnings):
    unresolved_paths: list[str] = []
    source = document.get("source")
    if (
        status in {"READY", "ANALYZED"}
        and isinstance(source, dict)
        and source.get("reportDigest") == "unresolved:agent"
    ):
        unresolved_paths.append("source.reportDigest")
    if owner_route in {"unresolved:human", "unresolved:agent"}:
        unresolved_paths.append("ownerRoute")
    for path in allowed:
        if path == "unresolved:agent":
            unresolved_paths.append("scope.allowedPaths")
    for finding in findings:
        if "unresolved:agent" in finding.get("affectedPaths", []):
            unresolved_paths.append(f"finding:{finding['id']}.affectedPaths")
        if any(item.get("ref") == "unresolved:agent" for item in finding.get("evidence", [])):
            unresolved_paths.append(f"finding:{finding['id']}.evidence")
    for action in actions:
        if "unresolved:agent" in action.get("paths", []):
            unresolved_paths.append(f"action:{action['id']}.paths")
    if unresolved_paths:
        target = errors if status in {"READY", "ANALYZED"} else warnings
        for path in unresolved_paths:
            target.append(
                _issue(
                    MALFORMED_CODE,
                    path,
                    "unresolved path is allowed only while status=DRAFT",
                )
            )



def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    _exact_fields(
        document,
        "$",
        {
            "schema",
            "intentId",
            "ticket",
            "repository",
            "ownerRoute",
            "status",
            "source",
            "objective",
            "scope",
            "findings",
            "actions",
            "verifications",
            "acceptanceCriteria",
            "llmGuidance",
            "todo2code",
        },
        {"advisoryAnalysis"},
        errors,
    )
    if document.get("schema") != INTENT_SCHEMA:
        errors.append(_issue(MALFORMED_CODE, "schema", f"must be {INTENT_SCHEMA}"))
    _pattern(document.get("intentId"), INTENT_ID, "intentId", errors)
    _pattern(document.get("ticket"), TICKET_ID, "ticket", errors)
    _pattern(document.get("repository"), REPOSITORY, "repository", errors)
    owner_route = _nonempty_text(document.get("ownerRoute"), "ownerRoute", errors)
    status = _enum(document.get("status"), {"DRAFT", "READY", "ANALYZED"}, "status", errors)
    _validate_source(document, errors, warnings)
    allowed, forbidden, preserve = _validate_objective_scope(document, errors)
    findings, finding_by_id = _validate_findings(document, errors)
    _validate_finding_paths(findings, allowed, forbidden, errors)
    verifications, verification_by_id = _validate_verifications(document, errors)
    actions, action_graph = _validate_actions(
        document,
        finding_by_id,
        verification_by_id,
        allowed,
        forbidden,
        preserve,
        errors,
    )
    action_finding_ids = {
        finding_id
        for action in actions
        for finding_id in action.get("findingIds", [])
    }
    for finding in findings:
        if finding.get("status") != "DEFERRED" and finding["id"] not in action_finding_ids:
            errors.append(
                _issue(
                    MALFORMED_CODE,
                    f"finding:{finding['id']}",
                    "active finding must be resolved by at least one action",
                )
            )
    _validate_criteria_guidance_t2c(
        document, finding_by_id, action_graph, verification_by_id, errors
    )
    _validate_analysis(document, errors)

    _validate_unresolved_paths(document, status, owner_route, allowed, findings, actions, errors, warnings)
    finding_ids = {item["id"] for item in findings}
    action_ids = {item["id"] for item in actions}
    for verification in verifications:
        for covered in verification.get("covers", []):
            if covered not in finding_ids | action_ids:
                errors.append(
                    _issue(
                        MALFORMED_CODE,
                        f"verification:{verification['id']}.covers",
                        f"unknown covered id: {covered}",
                    )
                )

    return {
        "schema": VALIDATION_SCHEMA,
        "intentId": document.get("intentId"),
        "intentDigest": intent_digest(document),
        "findings": len(findings),
        "actions": len(actions),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def _require_valid(document: dict[str, Any], *, ready: bool = False) -> dict[str, Any]:
    report = validate_document(document)
    if ready and document.get("status") == "DRAFT":
        report["errors"].append(
            _issue(MALFORMED_CODE, "status", "todo2code projection requires READY or ANALYZED")
        )
        report["ok"] = False
    if not report["ok"]:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def _criterion_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        criterion["id"]: criterion
        for criterion in document.get("acceptanceCriteria", [])
        if isinstance(criterion, dict) and isinstance(criterion.get("id"), str)
    }


def _atomic_fragment(value: Any) -> str:
    """Keep prose readable without creating a second todo2code statement."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"[.!?;]+(?=\s|$)", ",", text)
    return text.strip(" ,")


def _atomic_json_string(value: Any) -> str:
    """Encode an exact scalar while preventing sentence-boundary splitting."""
    encoded = json.dumps(str(value), ensure_ascii=True)
    return re.sub(r"(?<=[.!?;]) (?=[A-Z0-9])", r"\\u0020", encoded)


def _action_prefix(operation: str) -> str:
    return {
        "TEST": "test(remediation)",
        "DOCUMENT": "docs(remediation)",
        "RELEASE": "build(remediation)",
        "TRIAGE": "chore(remediation)",
        "PRESERVE": "chore(remediation)",
    }.get(operation, "fix(remediation)")


def _todo2code_action_line(
    document: dict[str, Any],
    action: dict[str, Any],
    findings: dict[str, dict[str, Any]],
    criteria: dict[str, dict[str, Any]],
    verifications: dict[str, dict[str, Any]],
    digest: str,
) -> str:
    finding_items = [findings[finding_id] for finding_id in action["findingIds"]]
    finding_labels = ", ".join(
        f"{item['id']}/{item['diagnostic']['code']}/{item['priority']}"
        for item in finding_items
    )
    criterion_ids = list(
        dict.fromkeys(
            criterion_id
            for finding in finding_items
            for criterion_id in finding["acceptanceCriteria"]
        )
    )
    criterion_text = ", ".join(
        f"{criterion_id} {_atomic_fragment(criteria[criterion_id]['statement'])}"
        for criterion_id in criterion_ids
        if criterion_id in criteria
    )
    verification_text = ", ".join(
        " ".join(
            [
                verification_id,
                verification["type"].lower(),
                (
                    f"command-json={_atomic_json_string(verification['command'])}"
                    if verification.get("command")
                    else "command-json=null"
                ),
                f"expected={_atomic_fragment(verification['expected'])}",
                f"deterministic={str(verification['deterministic']).lower()}",
            ]
        )
        for verification_id in action["verificationIds"]
        for verification in [verifications[verification_id]]
    )
    paths = ", ".join(f"`{path}`" for path in action["paths"])
    dependencies = ", ".join(action["dependsOn"]) or "none"
    risk = action["risk"]
    return (
        f"{_action_prefix(action['operation'])}: action {action['id']} must "
        f"{_atomic_fragment(action['description'])} | intent {document['intentId']} "
        f"ticket {document['ticket']} digest {digest} | findings {finding_labels} | "
        f"paths {paths} | dependencies {dependencies} | acceptance {criterion_text} | "
        f"verification {verification_text} when executed and failure must block the action | "
        f"risk {risk['level'].lower()} authorization {risk['authorization'].lower()} "
        f"automation {risk['automation'].lower()} preserves-user-data "
        f"{str(risk['preservesUserData']).lower()} | evidence result must pass."
    )


def _projection_headings(document: dict[str, Any], digest: str) -> list[str]:
    lines = [
        f"## ticket: {document['ticket']}",
        f"## repository: {document['repository']}",
        f"## intent digest: {digest}",
        "## authority: accepted remediation intent; todo2code and LLM output are advisory",
        f"## outcome: {_atomic_fragment(document['objective']['outcome'])}",
    ]
    lines.extend(
        f"### non-goal {index}: {_atomic_fragment(item)}"
        for index, item in enumerate(document["objective"]["nonGoals"], start=1)
    )
    lines.extend(
        f"### constraint {index}: {_atomic_fragment(item)}"
        for index, item in enumerate(document["objective"]["constraints"], start=1)
    )
    lines.extend(
        f"### must preserve {index}: {_atomic_fragment(item)}"
        for index, item in enumerate(document["llmGuidance"]["mustPreserve"], start=1)
    )
    lines.extend(
        f"### forbidden assumption {index}: {_atomic_fragment(item)}"
        for index, item in enumerate(
            document["llmGuidance"]["forbiddenAssumptions"], start=1
        )
    )
    return lines


def _render_findings(document, criteria, lines):
    for finding in document["findings"]:
        diagnostic = finding["diagnostic"]
        lines.extend(
            [
                f"### {finding['id']} — {diagnostic['code']} ({finding['priority']})",
                "",
                f"- Category/state: `{finding['category']}` / `{finding['status']}`",
                f"- Diagnostic transition: `{diagnostic['current']} -> {diagnostic['required']}`",
                f"- Observation: {finding['summary']}",
                f"- Desired outcome: {finding['desiredOutcome']}",
                "- Required signals:",
            ]
        )
        lines.extend(f"  - {item}" for item in finding["applicability"]["requiredSignals"])
        lines.append("- Excluded signals:")
        excluded = finding["applicability"]["excludedSignals"]
        lines.extend(f"  - {item}" for item in excluded or ["(none declared)"])
        lines.append("- Evidence:")
        lines.extend(
            f"  - `{item['ref']}` — {item['observation']}" for item in finding["evidence"]
        )
        lines.append("- Acceptance:")
        lines.extend(
            f"  - [{criterion_id}] {criteria[criterion_id]['statement']}"
            for criterion_id in finding["acceptanceCriteria"]
            if criterion_id in criteria
        )
        lines.append("")


def render_llm(document: dict[str, Any]) -> str:
    report = _require_valid(document, ready=True)
    criteria = _criterion_map(document)
    lines = [
        f"# Remediation planning brief: {document['intentId']}",
        "",
        f"- Ticket: `{document['ticket']}`",
        f"- Repository: `{document['repository']}`",
        f"- Owner route: `{document['ownerRoute']}`",
        f"- Status: `{document['status']}`",
        f"- Intent digest: `{report['intentDigest']}`",
        "- Authority: accepted intent and deterministic governance; LLM/todo2code are advisory.",
        "",
        "## Objective",
        "",
        document["objective"]["outcome"],
        "",
        "### Non-goals",
        "",
    ]
    lines.extend(f"- {item}" for item in document["objective"]["nonGoals"])
    lines.extend(["", "### Constraints", ""])
    lines.extend(f"- {item}" for item in document["objective"]["constraints"])
    lines.extend(["", "## Findings", ""])
    _render_findings(document, criteria, lines)
    lines.extend(["## Required planning order", ""])
    actions = {item["id"]: item for item in document["actions"]}
    for index, action_id in enumerate(document["llmGuidance"]["planningOrder"], start=1):
        action = actions[action_id]
        paths = ", ".join(f"`{path}`" for path in action["paths"])
        lines.append(
            f"{index}. [{action_id}/{action['operation']}] {action['description']} Paths: {paths}."
        )
    lines.extend(["", "## LLM guardrails", "", f"Role: {document['llmGuidance']['role']}", ""])
    lines.append("Must preserve:")
    lines.extend(f"- {item}" for item in document["llmGuidance"]["mustPreserve"])
    lines.append("")
    lines.append("Forbidden assumptions:")
    lines.extend(
        f"- {item}" for item in document["llmGuidance"]["forbiddenAssumptions"]
    )
    analysis = document.get("advisoryAnalysis")
    if isinstance(analysis, dict):
        lines.extend(["", "## Digest-bound todo2code hints (ADVISORY)", ""])
        lines.extend(f"- {hint}" for hint in analysis.get("llmHints", []))
    return "\n".join(lines).rstrip() + "\n"


def render_todo2code(document: dict[str, Any]) -> tuple[str, str]:
    report = _require_valid(document, ready=True)
    if document["todo2code"]["enabled"] is not True:
        raise ValueError("todo2code projection is disabled by the accepted intent")
    criteria = _criterion_map(document)
    findings = {item["id"]: item for item in document["findings"]}
    actions = {item["id"]: item for item in document["actions"]}
    verifications = {item["id"]: item for item in document["verifications"]}
    task_lines = [
        f"# Refactoring task {document['intentId']}",
        "",
        *_projection_headings(document, report["intentDigest"]),
        "## required changes",
    ]
    todo_lines = [
        f"# TODO for {document['intentId']}",
        "",
        *_projection_headings(document, report["intentDigest"]),
        "## required changes",
    ]
    for action_id in document["llmGuidance"]["planningOrder"]:
        line = _todo2code_action_line(
            document,
            actions[action_id],
            findings,
            criteria,
            verifications,
            report["intentDigest"],
        )
        task_lines.extend([f"### action: {action_id}", line])
        todo_lines.append(f"- [ ] {line}")
    return "\n".join(task_lines).rstrip() + "\n", "\n".join(todo_lines).rstrip() + "\n"


class ProjectionError(ValueError):
    """A declared todo2code projection is unsafe, missing or stale."""


def _declared_projection_paths(
    document: dict[str, Any], root: Path
) -> tuple[Path, Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ProjectionError(f"repository root is not a directory: {root}")
    paths: list[Path] = []
    for field in ("taskPath", "todoPath"):
        relative = document["todo2code"][field]
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ProjectionError(
                f"todo2code.{field} escapes repository root: {relative}"
            ) from error
        paths.append(candidate)
    return paths[0], paths[1]


def verify_todo2code(document: dict[str, Any], root: Path) -> dict[str, Any]:
    task, todo = render_todo2code(document)
    task_path, todo_path = _declared_projection_paths(document, root)
    issues: list[dict[str, str]] = []
    for field, path, expected in (
        ("todo2code.taskPath", task_path, task),
        ("todo2code.todoPath", todo_path, todo),
    ):
        if not path.is_file():
            issues.append(_issue(PROJECTION_CODE, field, f"projection is missing: {path}"))
            continue
        try:
            actual = path.read_bytes()
        except OSError as error:
            issues.append(_issue(PROJECTION_CODE, field, f"cannot read projection: {error}"))
            continue
        expected_bytes = expected.encode("utf-8")
        if actual != expected_bytes:
            issues.append(
                _issue(
                    PROJECTION_CODE,
                    field,
                    "projection bytes differ from accepted intent "
                    f"(expected sha256={hashlib.sha256(expected_bytes).hexdigest()}, "
                    f"actual sha256={hashlib.sha256(actual).hexdigest()})",
                )
            )
    return {
        "schema": "new-project.remediation-projection-verification/v1",
        "intentId": document["intentId"],
        "intentDigest": intent_digest(document),
        "ok": not issues,
        "issues": issues,
    }


def _analysis_finding(
    code: str,
    severity: str,
    message: str,
    references: list[str],
    hint: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "references": list(dict.fromkeys(references)),
        "llmHint": hint,
    }


def _plan_corpus(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True).lower()


def _plan_paths(plan: dict[str, Any]) -> list[str]:
    target = plan.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("paths"), list):
        return []
    return [path for path in target["paths"] if isinstance(path, str)]


def _record_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _projection_record_ids(
    document: dict[str, Any], graph: dict[str, Any]
) -> set[str]:
    if graph.get("schemaVersion") != T2C_GRAPH_SCHEMA or not isinstance(
        graph.get("records"), list
    ):
        raise ValueError(f"graph must use {T2C_GRAPH_SCHEMA}")
    expected_paths = {
        str(PurePosixPath(document["todo2code"]["taskPath"])),
        str(PurePosixPath(document["todo2code"]["todoPath"])),
    }
    ids_by_path: dict[str, set[str]] = {path: set() for path in expected_paths}
    for record in graph["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            continue
        source = record.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            continue
        source_path = str(PurePosixPath(source["path"]))
        if source_path in ids_by_path:
            ids_by_path[source_path].add(record["id"])
    missing = sorted(path for path, record_ids in ids_by_path.items() if not record_ids)
    if missing:
        raise ValueError(
            "todo2code graph has no records for declared projection(s): "
            + ", ".join(missing)
        )
    return set().union(*ids_by_path.values())


def _analyze_plan_scope(plan_items, allowed, forbidden, findings):
    for plan in plan_items:
        plan_id = str(plan.get("id", "unknown-plan"))
        for path in _plan_paths(plan):
            if not _safe_path(path) or not _matches(path, allowed) or _matches(path, forbidden):
                findings.append(
                    _analysis_finding(
                        "T2C_SCOPE_EXPANSION",
                        "BLOCKING",
                        f"todo2code plan {plan_id} targets path outside accepted scope: {path}",
                        [plan_id, path],
                        f"Remove `{path}` from the refactoring plan or obtain a fresh bounded intent before implementation.",
                    )
                )
        changes = plan.get("changes", [])
        if isinstance(changes, list):
            for change in changes:
                if not isinstance(change, dict) or change.get("action") != "delete":
                    continue
                path = str(change.get("path", ""))
                # The closed remediation DSL has no typed file-delete operation.
                # Risk/authorization labels do not define additional effects.
                findings.append(
                    _analysis_finding(
                        "T2C_UNAUTHORIZED_DELETION",
                        "BLOCKING",
                        f"todo2code proposes file deletion unsupported by the remediation DSL: {path}",
                        [plan_id, path],
                        "Preserve the file or use read-only triage. File deletion requires a separately supported typed operation and bounded authority; risk metadata alone cannot grant it.",
                    )
                )



def _analyze_finding_coverage(finding_by_id, plan_corpora, plan_items, findings):
    for finding_id, finding in finding_by_id.items():
        if finding.get("status") == "DEFERRED":
            continue
        code = finding["diagnostic"]["code"].lower()
        affected = [path.lower() for path in finding.get("affectedPaths", [])]
        matched = [
            plan_id
            for plan_id, corpus in plan_corpora.items()
            if finding_id.lower() in corpus
            or code in corpus
            or any(path != "unresolved:agent" and path in corpus for path in affected)
        ]
        if not matched:
            findings.append(
                _analysis_finding(
                    "T2C_PLAN_GAP",
                    "REVIEW",
                    f"no todo2code plan is grounded in active finding {finding_id}",
                    [finding_id, finding["diagnostic"]["code"]],
                    f"Add an explicit action/path link for {finding_id}; do not guess a path from the diagnostic name.",
                )
            )
            continue
        expected_priority = finding["priority"]
        for plan in plan_items:
            plan_id = str(plan.get("id", "unknown-plan"))
            if plan_id not in matched:
                continue
            plan_priority = plan.get("priority")
            if plan_priority in PRIORITIES and int(plan_priority[1]) > int(expected_priority[1]):
                findings.append(
                    _analysis_finding(
                        "T2C_PRIORITY_DRIFT",
                        "REVIEW",
                        f"plan {plan_id} lowers {finding_id} from {expected_priority} to {plan_priority}",
                        [finding_id, plan_id],
                        f"Preserve the accepted {expected_priority} priority or record why a fresh intent changes it.",
                    )
                )



def _analyze_diagnostics(diagnostics, projection_record_ids, findings):
    for diagnostic in diagnostics["diagnostics"]:
        if not isinstance(diagnostic, dict):
            continue
        if not (_record_ids(diagnostic.get("recordIds")) & projection_record_ids):
            continue
        code = diagnostic.get("code")
        diagnostic_id = str(diagnostic.get("id", "unknown-diagnostic"))
        action = str(diagnostic.get("suggestedAction", "Review the todo2code diagnostic."))
        detail = str(diagnostic.get("detail", diagnostic.get("title", code or "diagnostic")))
        if code == "AMBIGUOUS_REQUIREMENT":
            findings.append(
                _analysis_finding(
                    "T2C_AMBIGUOUS_INTENT",
                    "REVIEW",
                    detail,
                    [diagnostic_id],
                    action,
                )
            )
        elif code in {"HUMAN_AGENT_CONFLICT", "HUMAN_COMMUNICATION_CONFLICT"}:
            findings.append(
                _analysis_finding(
                    "T2C_CONFLICT",
                    "BLOCKING",
                    detail,
                    [diagnostic_id],
                    action,
                )
            )



def _projected_plan_items(diagnostics, plans, projection_record_ids):
    if diagnostics.get("schemaVersion") != T2C_DIAGNOSTICS_SCHEMA or not isinstance(
        diagnostics.get("diagnostics"), list
    ):
        raise ValueError(f"diagnostics must use {T2C_DIAGNOSTICS_SCHEMA}")
    if plans.get("schemaVersion") != T2C_PLAN_SET_SCHEMA or not isinstance(
        plans.get("plans"), list
    ):
        raise ValueError(f"plans must use {T2C_PLAN_SET_SCHEMA}")
    all_plan_items = [item for item in plans["plans"] if isinstance(item, dict)]
    for index, plan in enumerate(all_plan_items):
        if plan.get("schemaVersion") != T2C_PLAN_SCHEMA:
            raise ValueError(f"plans[{index}] must use {T2C_PLAN_SCHEMA}")
    plan_items = [
        plan
        for plan in all_plan_items
        if _record_ids(
            plan.get("evidence", {}).get("recordIds")
            if isinstance(plan.get("evidence"), dict)
            else None
        )
        & projection_record_ids
    ]

    return plan_items


def _analyze_criterion_coverage(document, plan_corpora, findings):
    all_plan_text = "\n".join(plan_corpora.values())
    for criterion in document["acceptanceCriteria"]:
        if criterion["id"].lower() not in all_plan_text and criterion["statement"].lower() not in all_plan_text:
            findings.append(
                _analysis_finding(
                    "T2C_CRITERION_GAP",
                    "REVIEW",
                    f"todo2code plans do not preserve acceptance criterion {criterion['id']}",
                    [criterion["id"]],
                    f"Add `{criterion['id']}` and its deterministic verification to the implementation plan.",
                )
            )



def analyze_todo2code(
    document: dict[str, Any],
    graph: dict[str, Any],
    diagnostics: dict[str, Any],
    plans: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    _require_valid(document, ready=True)
    projection_record_ids = _projection_record_ids(document, graph)
    plan_items = _projected_plan_items(diagnostics, plans, projection_record_ids)
    scope = document["scope"]
    allowed = scope["allowedPaths"]
    forbidden = scope["forbiddenPaths"]
    finding_by_id = {item["id"]: item for item in document["findings"]}
    plan_corpora = {str(plan.get("id", f"plan-{index}")): _plan_corpus(plan) for index, plan in enumerate(plan_items)}
    findings: list[dict[str, Any]] = []

    _analyze_plan_scope(plan_items, allowed, forbidden, findings)
    _analyze_finding_coverage(finding_by_id, plan_corpora, plan_items, findings)
    _analyze_criterion_coverage(document, plan_corpora, findings)
    _analyze_diagnostics(diagnostics, projection_record_ids, findings)
    unique_findings: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for finding in findings:
        key = _canonical(finding)
        if key not in seen:
            unique_findings.append(finding)
            seen.add(key)
    llm_hints = list(dict.fromkeys(item["llmHint"] for item in unique_findings))
    runtime_version = plans.get("generation", {}).get("runtimeVersion")
    if not isinstance(runtime_version, str) or not runtime_version:
        runtime_version = "unresolved-version"

    result = deepcopy(document)
    result["status"] = "ANALYZED"
    result["advisoryAnalysis"] = {
        "authority": "ADVISORY",
        "producer": {
            "name": "todo2code",
            "version": runtime_version,
            "mode": "deterministic",
        },
        "analyzedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "intentDigest": intent_digest(document),
        "graphDigest": _digest(graph),
        "diagnosticsDigest": _digest(diagnostics),
        "plansDigest": _digest(plans),
        "projectionRecordIds": sorted(projection_record_ids),
        "planIds": [str(plan.get("id")) for plan in plan_items if plan.get("id")],
        "findings": unique_findings,
        "llmHints": llm_hints,
    }
    validation = validate_document(result)
    if not validation["ok"]:
        raise ValueError(json.dumps(validation, ensure_ascii=False, indent=2))
    blocking = any(item["severity"] == "BLOCKING" for item in unique_findings)
    return result, blocking


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _print_validation(report: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(
        f"remediation-intent: {report['findings']} findings, "
        f"{report['actions']} actions, {len(report['errors'])} errors, "
        f"{len(report['warnings'])} warnings"
    )
    for issue in [*report["errors"], *report["warnings"]]:
        print(f"{issue['code']}: {issue['path']}: {issue['message']}")


def _write_todo2code_projection(document, args):
    task, todo = render_todo2code(document)
    if (args.task_out is None) != (args.todo_out is None):
        raise ProjectionError(
            "--task-out and --todo-out must be supplied together or omitted together"
        )
    task_path, todo_path = (
        (args.task_out, args.todo_out)
        if args.task_out is not None
        else _declared_projection_paths(document, args.root)
    )
    _write(task_path, task)
    _write(todo_path, todo)
    return 0


def _verify_todo2code_command(document, args):
    report = verify_todo2code(document, args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        state = "PASS" if report["ok"] else "FAIL"
        print(
            f"remediation-todo2code-projection: {state}; "
            f"{len(report['issues'])} issue(s)"
        )
        for issue in report["issues"]:
            print(f"{issue['code']}: {issue['path']}: {issue['message']}")
    return 0 if report["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate one remediation intent")
    validate_parser.add_argument("intent", type=Path)
    validate_parser.add_argument("--format", choices=("text", "json"), default="text")

    digest_parser = subparsers.add_parser("digest", help="print the authority-bearing intent digest")
    digest_parser.add_argument("intent", type=Path)

    llm_parser = subparsers.add_parser("render-llm", help="render a canonical LLM planning brief")
    llm_parser.add_argument("intent", type=Path)
    llm_parser.add_argument("--out", type=Path)

    todo_parser = subparsers.add_parser(
        "render-todo2code", help="render deterministic todo2code task and TODO inputs"
    )
    todo_parser.add_argument("intent", type=Path)
    todo_parser.add_argument("--root", type=Path, default=Path("."))
    todo_parser.add_argument("--task-out", type=Path)
    todo_parser.add_argument("--todo-out", type=Path)

    verify_parser = subparsers.add_parser(
        "verify-todo2code", help="verify declared todo2code projections byte-for-byte"
    )
    verify_parser.add_argument("intent", type=Path)
    verify_parser.add_argument("--root", type=Path, default=Path("."))
    verify_parser.add_argument("--format", choices=("text", "json"), default="text")

    analyze_parser = subparsers.add_parser(
        "analyze-todo2code", help="bind todo2code diagnostics/plans as an advisory overlay"
    )
    analyze_parser.add_argument("intent", type=Path)
    analyze_parser.add_argument("--graph", type=Path, required=True)
    analyze_parser.add_argument("--diagnostics", type=Path, required=True)
    analyze_parser.add_argument("--plans", type=Path, required=True)
    analyze_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    try:
        document = _load_json(args.intent)
        if args.command == "validate":
            report = validate_document(document)
            _print_validation(report, args.format)
            return 0 if report["ok"] else 1
        if args.command == "digest":
            _require_valid(document)
            print(intent_digest(document))
            return 0
        if args.command == "render-llm":
            content = render_llm(document)
            if args.out:
                _write(args.out, content)
            else:
                print(content, end="")
            return 0
        if args.command == "render-todo2code":
            return _write_todo2code_projection(document, args)
        if args.command == "verify-todo2code":
            return _verify_todo2code_command(document, args)
        if args.command == "analyze-todo2code":
            result, blocking = analyze_todo2code(
                document,
                _load_json(args.graph),
                _load_json(args.diagnostics),
                _load_json(args.plans),
            )
            _write(args.out, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            if blocking:
                print(
                    f"{T2C_CODE}: todo2code analysis contains blocking inconsistencies",
                    file=sys.stderr,
                )
            return 1 if blocking else 0
    except ProjectionError as error:
        print(f"{PROJECTION_CODE}: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"{MALFORMED_CODE}: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
