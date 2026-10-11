#!/usr/bin/env python3
"""Read-only conformance of branch intent reports, never deletion authority.

The controller supplies independently acquired expectations and a verified
receipt allowlist. Content-addressed receipts are read locally; no commands,
network requests, repository writes or automatic approvals are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


BINDINGS = {"repository", "sourceRef", "sourceHeadSha", "targetRef", "targetHeadSha", "intentSha256"}
OUTCOMES = {"implemented", "partial", "superseded", "missing", "unknown"}
KINDS = {"preservation", "content-equivalence", "test-result", "decision", "follow-up", "advisory"}


class Invalid(ValueError):
    """A closed contract or a required evidence binding is invalid."""


def require(condition, message):
    if not condition:
        raise Invalid(message)


def fields(value, names, label):
    require(isinstance(value, dict) and set(value) == set(names), f"{label}: missing or unknown fields")


def string(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: nonempty string required")


def digest(value, length=64):
    require(isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value), "invalid digest")


def unique_strings(values, label, nonempty=True):
    require(isinstance(values, list) and (bool(values) or not nonempty), f"{label}: list required")
    for value in values:
        string(value, label)
    require(len(set(values)) == len(values), f"{label}: duplicates")


def bindings(value):
    fields(value, BINDINGS, "bindings")
    for key in BINDINGS:
        string(value[key], key)
    for key in ("sourceHeadSha", "targetHeadSha"):
        digest(value[key], 40)
    digest(value["intentSha256"])
    for key in ("sourceRef", "targetRef"):
        require(value[key].startswith("refs/heads/") and len(value[key]) > len("refs/heads/"),
                "exact branch refs required")
    require(value["sourceRef"] != value["targetRef"], "source and target refs must differ")


def parse_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Invalid("nonfinite JSON value")))


def read_json(path):
    return parse_json(Path(path).read_bytes())


def expectations(value):
    fields(value, {"schema", "bindings", "criteria", "receipts"}, "observation")
    require(value["schema"] == "new-project.branch-intent-observation/v1", "wrong observation schema")
    bindings(value["bindings"])
    require(isinstance(value["criteria"], list) and value["criteria"], "empty criterion inventory")
    criteria = {}
    for item in value["criteria"]:
        fields(item, {"id", "requiredProof"}, "expected criterion")
        string(item["id"], "criterion id")
        require(item["id"] not in criteria, "duplicate expected criterion")
        require(item["requiredProof"] in ("content", "behavior", "either"), "unknown required proof")
        criteria[item["id"]] = item["requiredProof"]
    require(isinstance(value["receipts"], dict), "receipt allowlist required")
    for ref, sha in value["receipts"].items():
        string(ref, "receipt ref")
        digest(sha)
    return criteria


def evidence(reference, observation, directory):
    fields(reference, {"receiptRef", "sha256"}, "evidence reference")
    string(reference["receiptRef"], "receipt ref")
    digest(reference["sha256"])
    require(observation["receipts"].get(reference["receiptRef"]) == reference["sha256"],
            "receipt absent from independently verified allowlist")
    path = directory / (reference["sha256"] + ".json")
    require(not path.is_symlink() and path.is_file(), "receipt must be a regular local artifact")
    content = path.read_bytes()
    require(hashlib.sha256(content).hexdigest() == reference["sha256"], "receipt digest mismatch")
    item = parse_json(content)
    fields(item, {"schema", "receiptRef", "kind", "bindings", "criterionIds", "facts"}, "receipt")
    require(item["schema"] == "new-project.branch-intent-evidence/v1", "wrong evidence schema")
    require(item["receiptRef"] == reference["receiptRef"], "receipt identity mismatch")
    require(item["bindings"] == observation["bindings"], "stale or mismatched evidence bindings")
    require(item["kind"] in KINDS, "unknown evidence kind")
    unique_strings(item["criterionIds"], "evidence criteria", nonempty=False)
    known = {row["id"] for row in observation["criteria"]}
    require(set(item["criterionIds"]) <= known, "evidence cites unknown criteria")
    facts = item["facts"]
    if item["kind"] == "content-equivalence":
        fields(facts, {"sourcePath", "targetPath", "sourceSha256", "targetSha256"}, "content facts")
        for key in ("sourcePath", "targetPath"):
            string(facts[key], key)
        for key in ("sourceSha256", "targetSha256"):
            digest(facts[key])
        require(facts["sourceSha256"] == facts["targetSha256"], "content is not byte-equivalent")
    elif item["kind"] == "test-result":
        fields(facts, {"suiteSha256", "resultSha256", "passed"}, "test facts")
        digest(facts["suiteSha256"])
        digest(facts["resultSha256"])
        require(facts["passed"] is True, "behavioral evidence did not pass")
    elif item["kind"] == "preservation":
        fields(facts, {"archiveRef", "archiveSha256", "restoreVerified"}, "preservation facts")
        string(facts["archiveRef"], "archive ref")
        digest(facts["archiveSha256"])
        require(facts["restoreVerified"] is True, "restoration not verified")
    elif item["kind"] == "decision":
        fields(facts, {"decisionRef", "actor", "disposition"}, "decision facts")
        string(facts["decisionRef"], "decision ref")
        string(facts["actor"], "decision actor")
        require(facts["disposition"] in ("superseded", "discard"), "invalid decision disposition")
    elif item["kind"] == "follow-up":
        fields(facts, {"ticketRef", "intentSha256"}, "follow-up facts")
        string(facts["ticketRef"], "follow-up ticket")
        digest(facts["intentSha256"])
    else:
        fields(facts, {"analysisRef"}, "advisory facts")
        string(facts["analysisRef"], "analysis ref")
    return item


def reconcile_criterion_disposition(row, criteria, proof, decision, follow, unresolved):
    if row["outcome"] in ("implemented", "partial"):
        required = {"content": {"content-equivalence"}, "behavior": {"test-result"},
                    "either": {"content-equivalence", "test-result"}}[criteria[row["id"]]]
        require(any(item["kind"] in required for item in proof), "implementation proof required; advisory is insufficient")
    if row["outcome"] == "superseded":
        require(decision is not None and decision["facts"]["disposition"] == "superseded", "superseding decision required")
        require(follow is None, "superseded criterion cannot also defer work")
    elif row["outcome"] in ("partial", "missing"):
        require(decision is None or decision["facts"]["disposition"] == "discard",
                "remaining work has contradictory decision")
        require(follow is not None or (decision is not None and decision["facts"]["disposition"] == "discard"),
                "remaining work needs a follow-up or explicit discard decision")
    elif row["outcome"] == "unknown":
        unresolved.append(row["id"])
    elif row["outcome"] == "implemented":
        require(decision is None and follow is None, "implemented criterion has contradictory disposition")


def reconcile(report, observation, evidence_root):
    """Return review readiness only; the caller owns observation authenticity."""
    criteria = expectations(observation)
    fields(report, {"schema", "bindings", "preservation", "criteria"}, "report")
    require(report["schema"] == "new-project.branch-intent-reconciliation/v1", "wrong report schema")
    require(report["bindings"] == observation["bindings"], "stale or mismatched report bindings")
    directory = Path(evidence_root).resolve(strict=True)
    saved = evidence(report["preservation"], observation, directory)
    require(saved["kind"] == "preservation", "preservation evidence required")
    require(isinstance(report["criteria"], list), "report criteria must be a list")
    seen, unresolved = set(), []
    for row in report["criteria"]:
        fields(row, {"id", "outcome", "evidence", "followUp", "decision"}, "criterion")
        string(row["id"], "criterion id")
        require(row["id"] in criteria and row["id"] not in seen, "unknown or duplicate criterion")
        seen.add(row["id"])
        require(row["outcome"] in OUTCOMES, "unknown criterion outcome")
        require(isinstance(row["evidence"], list), "criterion evidence must be a list")
        proof = [evidence(ref, observation, directory) for ref in row["evidence"]]
        require(len({item["receiptRef"] for item in proof}) == len(proof), "duplicate criterion evidence")
        for item in proof:
            require(row["id"] in item["criterionIds"], "evidence does not cite this criterion")
        decision = evidence(row["decision"], observation, directory) if row["decision"] is not None else None
        follow = evidence(row["followUp"], observation, directory) if row["followUp"] is not None else None
        for item, kind in ((decision, "decision"), (follow, "follow-up")):
            if item is not None:
                require(item["kind"] == kind and row["id"] in item["criterionIds"], "wrong disposition evidence")
        reconcile_criterion_disposition(row, criteria, proof, decision, follow, unresolved)
    require(seen == set(criteria), "report omits expected criteria")
    return {"schema": "new-project.branch-intent-result/v1", "status": "needs-review" if unresolved else "ready-for-owner-review",
            "unresolvedCriteria": sorted(unresolved), "authority": "none", "deletionAuthorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--observation", required=True)
    parser.add_argument("--evidence-root", required=True)
    args = parser.parse_args()
    try:
        result = reconcile(read_json(args.report), read_json(args.observation), args.evidence_root)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "invalid", "code": "GOV-BRANCH-INTENT-001", "message": str(exc),
                          "authority": "none", "deletionAuthorized": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ready-for-owner-review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
