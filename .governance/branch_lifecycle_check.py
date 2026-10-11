#!/usr/bin/env python3
"""Validate a versioned GitHub branch lifecycle snapshot without network access."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SNAPSHOT_SCHEMA = "new-project.branch-lifecycle-snapshot/v1"
REPORT_SCHEMA = "new-project.branch-lifecycle-report/v1"
MAX_ITEMS = 10_000
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(order=True)
class Finding:
    code: str
    severity: str
    message: str
    remediation: str
    evidence: dict[str, Any]


class SnapshotError(ValueError):
    """A closed snapshot contract or its internal consistency is invalid."""


def require_exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        extra = sorted(observed - fields)
        raise SnapshotError(f"{label} fields are invalid (missing={missing}, extra={extra})")


def require_repository(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
        raise SnapshotError(f"{label} must be an owner/repository identifier")
    return value


def require_ref(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise SnapshotError(f"{label} must be a non-empty bounded Git ref name")
    return value


def parse_snapshot_pulls(pulls_value: Any) -> list[dict[str, Any]]:
    if not isinstance(pulls_value, list) or len(pulls_value) > MAX_ITEMS:
        raise SnapshotError(f"openPullRequests must be an array with at most {MAX_ITEMS} items")
    pulls: list[dict[str, Any]] = []
    numbers: set[int] = set()
    for index, item in enumerate(pulls_value):
        if not isinstance(item, dict):
            raise SnapshotError(f"openPullRequests[{index}] must be an object")
        require_exact_fields(item, {"number", "headRepository", "headRef"}, f"openPullRequests[{index}]")
        number = item["number"]
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise SnapshotError(f"openPullRequests[{index}].number must be a positive integer")
        if number in numbers:
            raise SnapshotError("openPullRequests must not contain duplicate numbers")
        numbers.add(number)
        pulls.append(
            {
                "number": number,
                "headRepository": require_repository(
                    item["headRepository"],
                    f"openPullRequests[{index}].headRepository",
                    nullable=True,
                ),
                "headRef": require_ref(item["headRef"], f"openPullRequests[{index}].headRef"),
            }
        )
    return pulls


def parse_snapshot(value: Any, expected_repository: str | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotError("snapshot root must be an object")
    require_exact_fields(
        value,
        {
            "schema",
            "repository",
            "defaultBranch",
            "deleteBranchOnMerge",
            "branches",
            "openPullRequests",
        },
        "snapshot",
    )
    if value["schema"] != SNAPSHOT_SCHEMA:
        raise SnapshotError(f"unsupported snapshot schema: {value['schema']!r}")
    repository = require_repository(value["repository"], "repository")
    if expected_repository is not None and repository.lower() != expected_repository.lower():
        raise SnapshotError(
            f"snapshot repository {repository!r} differs from expected {expected_repository!r}"
        )
    default_branch = require_ref(value["defaultBranch"], "defaultBranch")
    if not isinstance(value["deleteBranchOnMerge"], bool):
        raise SnapshotError("deleteBranchOnMerge must be a boolean")

    branches_value = value["branches"]
    if not isinstance(branches_value, list) or len(branches_value) > MAX_ITEMS:
        raise SnapshotError(f"branches must be an array with at most {MAX_ITEMS} items")
    branches = [require_ref(item, f"branches[{index}]") for index, item in enumerate(branches_value)]
    if len(branches) != len(set(branches)):
        raise SnapshotError("branches must not contain duplicate names")
    if default_branch not in branches:
        raise SnapshotError("defaultBranch is missing from branches")

    pulls = parse_snapshot_pulls(value["openPullRequests"])
    return {
        "repository": repository,
        "defaultBranch": default_branch,
        "deleteBranchOnMerge": value["deleteBranchOnMerge"],
        "branches": branches,
        "openPullRequests": pulls,
    }


def evaluate(snapshot: dict[str, Any], focus_branch: str | None = None) -> list[Finding]:
    repository = snapshot["repository"]
    branch_set = set(snapshot["branches"])
    findings: list[Finding] = []
    if not snapshot["deleteBranchOnMerge"]:
        findings.append(Finding(
            code="GOV-BRANCH-LIFECYCLE-001",
            severity="error",
            message="GitHub automatic head-branch deletion after merge is disabled.",
            remediation="Set repository delete_branch_on_merge to true.",
            evidence={"repository": repository, "deleteBranchOnMerge": False},
        ))

    internal_heads = {
        item["headRef"]
        for item in snapshot["openPullRequests"]
        if item["headRepository"] is not None
        and item["headRepository"].lower() == repository.lower()
    }
    missing_heads = sorted(internal_heads - branch_set)
    if missing_heads:
        findings.append(Finding(
            code="GOV-BRANCH-LIFECYCLE-003",
            severity="error",
            message="The branch lifecycle snapshot is missing, malformed or inconsistent.",
            remediation="Re-acquire the snapshot and reobserve the open PR head branches; preserve refs while the observation is unresolved.",
            evidence={"repository": repository, "missingInternalHeads": missing_heads},
        ))

    allowed = {snapshot["defaultBranch"], *internal_heads}
    orphaned = sorted(branch_set - allowed)
    if focus_branch is not None:
        orphaned = [b for b in orphaned if b == focus_branch]
    if orphaned:
        findings.append(Finding(
            code="GOV-BRANCH-LIFECYCLE-002",
            severity="error",
            message="Remote branches exist without ownership by an open pull request.",
            remediation=(
                "Observe the exact branch head and open/closed PR history; preserve unmerged work "
                "and reconcile its intent with branch_intent_reconciliation.py before choosing "
                "continued delivery or an explicitly authorized discard. Do not create an empty PR "
                "or delete a branch merely to satisfy this check. Unknown evidence is not permission to discard."
            ),
            evidence={"repository": repository, "orphanedBranches": orphaned},
        ))
    return sorted(findings)


def report_payload(findings: list[Finding]) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "passed" if not findings else "failed",
        "summary": {"errors": len(findings), "warnings": 0, "findings": len(findings)},
        "findings": [asdict(item) for item in findings],
    }


def render_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for finding in payload["findings"]:
        evidence = json.dumps(finding["evidence"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        lines.append(f"{finding['code']} ERROR: {finding['message']} [{evidence}]")
        lines.append(f"  remediation: {finding['remediation']}")
    summary = payload["summary"]
    label = "GOV-BRANCH-PASS" if payload["status"] == "passed" else "GOV-BRANCH-FAIL"
    lines.append(
        f"{label}: {payload['status']} ({summary['errors']} errors, {summary['warnings']} warnings)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--expected-repository")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--focus-branch",
        help="When validating in the context of a pull request, evaluate orphan status specifically for this branch.",
    )
    args = parser.parse_args(argv)

    expected_repository: str | None = None
    if args.expected_repository is not None:
        try:
            expected_repository = require_repository(args.expected_repository, "expected repository")
        except SnapshotError as error:
            parser.error(str(error))

    findings: list[Finding]
    try:
        with args.snapshot.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        snapshot = parse_snapshot(raw, expected_repository)
        findings = evaluate(snapshot, focus_branch=args.focus_branch)
    except (OSError, json.JSONDecodeError, SnapshotError) as error:
        findings = [Finding(
            code="GOV-BRANCH-LIFECYCLE-003",
            severity="error",
            message="The branch lifecycle snapshot is missing, malformed or inconsistent.",
            remediation="Re-acquire the snapshot from the protected GitHub workflow; preserve refs while the observation is unresolved.",
            evidence={"reason": str(error)},
        )]

    payload = report_payload(findings)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(render_text(payload))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
