#!/usr/bin/env python3
"""Validate Wellmanifest pack ownership, evidence and managed projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any

LEVELS = {f"S{index}": index for index in range(6)}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
DIAGNOSTIC_CODE = "GOV-STANDARD-PACK-001"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def finding(code: str, message: str, path: str = "") -> dict[str, str]:
    return {
        "code": code,
        "diagnostic": DIAGNOSTIC_CODE,
        "message": message,
        "path": path,
    }


def catalog_ownership_findings(packs, pack_ids, concerns, findings) -> None:
    for pack in packs:
        owns = pack.get("owns") if isinstance(pack, dict) else None
        if (not isinstance(pack, dict) or not isinstance(pack.get("id"), str)
                or not pack["id"] or not isinstance(owns, list)):
            findings.append(finding("STD-PACK-CATALOG", "each pack needs an id and ownership list"))
            continue
        pack_id = pack["id"]
        if pack_id in pack_ids:
            findings.append(finding("STD-PACK-DUPLICATE-ID", f"duplicate pack id: {pack_id}"))
        pack_ids.add(pack_id)
        for concern in owns:
            if not isinstance(concern, str) or not concern:
                findings.append(finding("STD-PACK-CATALOG", f"invalid ownership claim in {pack_id}"))
                continue
            elif concern in concerns:
                findings.append(finding("STD-PACK-DUPLICATE-OWNER", f"duplicate normative owner: {concern}"))
            concerns.add(concern)


def catalog_profile_findings(profiles, pack_ids, findings) -> None:
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            findings.append(finding("STD-PACK-PROFILE", f"profile {name} is not an object"))
            continue
        parents = profile.get("extends", [])
        if not isinstance(parents, list):
            findings.append(finding("STD-PACK-PROFILE", f"profile {name} extends must be an array"))
            parents = []
        for parent in parents:
            if not isinstance(parent, str) or parent not in profiles or parent == name:
                findings.append(finding("STD-PACK-PROFILE", f"profile {name} has invalid parent {parent}"))
        requirements = profile.get("requirements", [])
        if not isinstance(requirements, list):
            findings.append(finding("STD-PACK-PROFILE", f"profile {name} requirements must be an array"))
            requirements = []
        for requirement in requirements:
            if (not isinstance(requirement, dict)
                    or not isinstance(requirement.get("id"), str)
                    or requirement["id"] not in pack_ids
                    or not isinstance(requirement.get("minimumLevel"), str)
                    or requirement["minimumLevel"] not in LEVELS):
                findings.append(finding("STD-PACK-PROFILE", f"profile {name} has invalid requirement"))


def catalog_findings(catalog: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not isinstance(catalog, dict) or catalog.get("schema") != "wellmanifest.standard-pack-routing/v1":
        return [finding("STD-PACK-CATALOG", "unsupported standard pack catalog schema")]
    packs = catalog.get("packs")
    profiles = catalog.get("profiles")
    models = catalog.get("executionModels")
    if not isinstance(packs, list) or not isinstance(profiles, dict) or not isinstance(models, dict):
        return [finding("STD-PACK-CATALOG", "catalog must define packs, profiles and executionModels")]
    pack_ids: set[str] = set()
    concerns: set[str] = set()
    catalog_ownership_findings(packs, pack_ids, concerns, findings)
    aliases = catalog.get("aliases", {})
    if not isinstance(aliases, dict):
        findings.append(finding("STD-PACK-ALIAS", "aliases must be an object"))
        aliases = {}
    for alias, target in aliases.items():
        if (not isinstance(alias, str) or not alias or alias in pack_ids
                or not isinstance(target, str) or target not in pack_ids):
            findings.append(finding("STD-PACK-ALIAS", f"invalid compatibility alias: {alias} -> {target}"))
    catalog_profile_findings(profiles, pack_ids, findings)
    for name, model in models.items():
        if not isinstance(name, str) or not name.strip():
            findings.append(finding("STD-PACK-CATALOG", "execution model name must be nonempty"))
        if not isinstance(model, dict):
            findings.append(finding("STD-PACK-CATALOG", f"execution model {name} must be an object"))
            continue
        level = model.get("maximumLevel")
        if not isinstance(level, str) or level not in LEVELS:
            findings.append(finding("STD-PACK-CATALOG", f"execution model {name} has invalid maximumLevel"))
        if not isinstance(model.get("authorizesEffects"), bool):
            findings.append(finding("STD-PACK-CATALOG", f"execution model {name} authorizesEffects must be boolean"))
    return findings


def profile_requirements(catalog: dict[str, Any], name: str) -> dict[str, str]:
    profiles = catalog["profiles"]
    result: dict[str, str] = {}
    visiting: set[str] = set()

    def visit(profile_name: str) -> None:
        if profile_name in visiting:
            raise ValueError(f"profile inheritance cycle at {profile_name}")
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            raise ValueError(f"unknown profile {profile_name}")
        visiting.add(profile_name)
        for parent in profile.get("extends", []):
            visit(parent)
        for requirement in profile.get("requirements", []):
            pack_id = requirement["id"]
            level = requirement["minimumLevel"]
            if pack_id not in result or LEVELS[level] > LEVELS[result[pack_id]]:
                result[pack_id] = level
        visiting.remove(profile_name)

    visit(name)
    return result


def adoption_artifact_findings(root, pack_id, record, level, findings) -> None:
    artifacts = record.get("artifacts")
    if LEVELS[level] >= LEVELS["S2"] and not isinstance(artifacts, list):
        findings.append(finding("STD-ADOPTION-ARTIFACT", f"{pack_id} needs managed artifact digests"))
        return
    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            findings.append(finding("STD-ADOPTION-ARTIFACT", f"invalid artifact for {pack_id}"))
            continue
        target = artifact.get("target")
        expected_digest = artifact.get("sha256")
        if (not isinstance(target, str) or not target
                or PureWindowsPath(target).drive or PureWindowsPath(target).root
                or ".." in PureWindowsPath(target).parts or ".." in Path(target).parts):
            findings.append(finding("STD-ADOPTION-ARTIFACT", f"unsafe target for {pack_id}"))
            continue
        try:
            target_path = (root / target).resolve()
            target_path.relative_to(root.resolve())
        except (OSError, ValueError, RuntimeError):
            findings.append(finding("STD-ADOPTION-ARTIFACT", f"unsafe target for {pack_id}", target))
            continue
        try:
            if not target_path.is_file():
                findings.append(finding("STD-ADOPTION-MISSING", f"managed projection is missing for {pack_id}", target))
            elif SHA64.fullmatch(str(expected_digest or "")) is None or sha256(target_path) != expected_digest:
                findings.append(finding("STD-ADOPTION-DRIFT", f"managed projection drift for {pack_id}", target))
        except OSError:
            findings.append(finding("STD-ADOPTION-ARTIFACT", f"cannot read managed projection for {pack_id}", target))

def adoption_record_findings(root, pack_id, record, models, findings) -> None:
    level = record.get("level")
    model = record.get("model")
    if level not in LEVELS or model not in models:
        findings.append(finding("STD-ADOPTION-RECORD", f"invalid model or level for {pack_id}"))
        return
    if LEVELS[level] > LEVELS.get(models[model].get("maximumLevel"), -1):
        findings.append(finding("STD-ADOPTION-MODEL", f"{model} cannot claim {level} for {pack_id}"))
    revision = record.get("revision")
    if not isinstance(revision, str) or SHA40.fullmatch(revision) is None:
        findings.append(finding("STD-ADOPTION-REVISION", f"{pack_id} needs an immutable 40-character revision"))
    evidence = record.get("evidence")
    evidence_levels = {
        item.get("level") for item in evidence or []
        if isinstance(item, dict) and isinstance(item.get("uri"), str)
        and SHA64.fullmatch(str(item.get("sha256", "")))
    }
    for index in range(LEVELS[level] + 1):
        expected = f"S{index}"
        if expected not in evidence_levels:
            findings.append(finding("STD-ADOPTION-EVIDENCE", f"{pack_id} lacks valid {expected} evidence"))
    adoption_artifact_findings(root, pack_id, record, level, findings)


def adoption_record_index(records, findings):
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            findings.append(finding("STD-ADOPTION-RECORD", "adoption entry must have an id"))
            continue
        pack_id = record["id"]
        if pack_id in by_id:
            findings.append(finding("STD-ADOPTION-DUPLICATE", f"duplicate adoption: {pack_id}"))
        by_id[pack_id] = record
    return by_id


def adoption_findings(root: Path, catalog: dict[str, Any], adoption: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not isinstance(adoption, dict) or adoption.get("schema") != "wellmanifest.standard-adoption/v1":
        return [finding("STD-ADOPTION-SCHEMA", "unsupported standard adoption schema")]
    if adoption.get("mode") not in {"audit", "enforce"}:
        findings.append(finding("STD-ADOPTION-MODE", "mode must be audit or enforce"))
    try:
        required = profile_requirements(catalog, adoption.get("profile", ""))
    except ValueError as exc:
        return [finding("STD-ADOPTION-PROFILE", str(exc))]
    records = adoption.get("adoptions")
    if not isinstance(records, list):
        return [finding("STD-ADOPTION-SCHEMA", "adoptions must be an array")]
    by_id = adoption_record_index(records, findings)
    models = catalog["executionModels"]
    known_packs = {item["id"] for item in catalog["packs"]}
    for pack_id, record in by_id.items():
        if pack_id not in known_packs:
            findings.append(finding("STD-ADOPTION-UNKNOWN", f"unknown pack: {pack_id}"))
            continue
        adoption_record_findings(root, pack_id, record, models, findings)
    for pack_id, minimum in required.items():
        record = by_id.get(pack_id)
        if record is None:
            findings.append(finding("STD-PACK-MISSING", f"profile requires {pack_id} at {minimum}"))
        elif record.get("level") not in LEVELS or LEVELS[record["level"]] < LEVELS[minimum]:
            findings.append(finding("STD-PACK-LEVEL", f"profile requires {pack_id} at {minimum}"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--catalog", default=".governance/standard-packs.json")
    parser.add_argument("--adoption", default=".governance/standard-adoption.json")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero for findings even when the adoption record is in audit mode",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    catalog_path = root / args.catalog
    adoption_path = root / args.adoption
    structural: list[dict[str, str]] = []
    if not catalog_path.is_file():
        structural.append(finding("STD-PACK-CATALOG", "standard pack catalog is missing", args.catalog))
        catalog: dict[str, Any] = {}
    else:
        catalog = load_json(catalog_path)
        structural.extend(catalog_findings(catalog))
    if not adoption_path.is_file():
        structural.append(finding("STD-ADOPTION-MISSING", "standard adoption record is missing", args.adoption))
        adoption: dict[str, Any] = {"mode": "enforce"}
    else:
        adoption = load_json(adoption_path)
    findings = structural or adoption_findings(root, catalog, adoption)
    result = {
        "schema": "wellmanifest.standard-adoption-report/v1",
        "mode": adoption.get("mode", "enforce"),
        "profile": adoption.get("profile"),
        "strict": args.strict,
        "ok": not findings,
        "findings": findings,
    }
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"standard-pack-check: mode={result['mode']} profile={result['profile']} findings={len(findings)}")
        for item in findings:
            suffix = f" ({item['path']})" if item.get("path") else ""
            print(f"{item['code']}: {item['message']}{suffix}")
    if structural:
        return 2
    return 1 if findings and (args.strict or adoption.get("mode") == "enforce") else 0


if __name__ == "__main__":
    raise SystemExit(main())
