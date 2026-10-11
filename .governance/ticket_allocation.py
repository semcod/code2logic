#!/usr/bin/env python3
"""Build and verify registered ticket allocation requests and receipts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


CONFIG_SCHEMA = "new-project.ticket-allocation/v1"
REQUEST_SCHEMA = "new-project.ticket-allocation-request/v1"
RECEIPT_SCHEMA = "new-project.ticket-allocation-receipt/v1"
INVALID_RECEIPT_CODE = "GOV-TICKET-ALLOCATION-003"
VISIBLE_CLAIM_CODE = "GOV-TICKET-ALLOCATION-004"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
AGENT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
WORKSTREAM = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class AllocationError(ValueError):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AllocationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AllocationError(f"expected a JSON object: {path}")
    return value


def require_exact(value: dict, fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise AllocationError(f"{label} fields do not match the closed contract")


def require_uri(value: object, label: str) -> str:
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        raise AllocationError(f"{label} must be an absolute URI")
    parsed = urlparse(value)
    if not parsed.scheme or not (parsed.netloc or parsed.path):
        raise AllocationError(f"{label} must be an absolute URI")
    return value


def parse_config(path: Path) -> dict:
    value = load_json(path)
    mode = value.get("mode")
    if mode == "local-single-clone":
        require_exact(value, {"$schema", "schema", "mode"}, "allocation config")
    elif mode == "registered":
        require_exact(value, {"$schema", "schema", "mode", "allocator"}, "allocation config")
        allocator = value.get("allocator")
        if not isinstance(allocator, dict):
            raise AllocationError("registered allocator config must be an object")
        require_exact(allocator, {"processUri", "issuer", "maxReceiptAgeSeconds"}, "allocator")
        require_uri(allocator.get("processUri"), "allocator.processUri")
        require_uri(allocator.get("issuer"), "allocator.issuer")
        age = allocator.get("maxReceiptAgeSeconds")
        if not isinstance(age, int) or isinstance(age, bool) or not 30 <= age <= 3600:
            raise AllocationError("allocator.maxReceiptAgeSeconds must be between 30 and 3600")
    else:
        raise AllocationError("allocation config mode must be local-single-clone or registered")
    if value.get("schema") != CONFIG_SCHEMA:
        raise AllocationError("unsupported allocation config schema")
    return value


def canonical_repository_ref(url: str) -> str:
    match = re.fullmatch(r"git@([^:]+):(.+?)(?:\.git)?", url)
    if match:
        host, path = match.groups()
        return f"git+ssh://{host.lower()}/{path.removesuffix('.git')}"
    parsed = urlparse(url)
    if parsed.scheme and parsed.hostname:
        path = parsed.path.lstrip("/").removesuffix(".git")
        scheme = "git+ssh" if parsed.scheme == "ssh" else parsed.scheme.lower()
        return f"{scheme}://{parsed.hostname.lower()}/{path}"
    raise AllocationError("origin URL cannot be normalized to a repository URI")


def request_value(args: argparse.Namespace, config: dict) -> dict:
    if config["mode"] != "registered":
        raise AllocationError("allocation requests are valid only in registered mode")
    if not KEY.fullmatch(args.allocation_key):
        raise AllocationError("allocation key has an invalid format")
    if not AGENT.fullmatch(args.agent):
        raise AllocationError("agent has an invalid format")
    if not WORKSTREAM.fullmatch(args.workstream):
        raise AllocationError("workstream has an invalid format")
    if args.kind not in {"BUG", "FEATURE", "SERVICE"}:
        raise AllocationError("kind is outside the closed vocabulary")
    if args.priority not in {"P0", "P1", "P2", "P3"}:
        raise AllocationError("priority is outside the closed vocabulary")
    if args.origin not in {"regression", "requested", "health"}:
        raise AllocationError("origin is outside the closed vocabulary")
    require_uri(args.repository_ref, "repositoryRef")
    return {
        "schema": REQUEST_SCHEMA,
        "repositoryRef": args.repository_ref,
        "allocationKey": args.allocation_key,
        "titleDigest": "sha256:" + hashlib.sha256(args.title.encode("utf-8")).hexdigest(),
        "agent": args.agent,
        "workstream": args.workstream,
        "classification": {
            "kind": args.kind,
            "priority": args.priority,
            "origin": args.origin,
        },
        "processUri": config["allocator"]["processUri"],
    }


def canonical_digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_time(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise AllocationError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AllocationError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise AllocationError(f"{label} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def validate_receipt_lifetime(receipt: dict, allocator: dict, now: dt.datetime) -> None:
    issued = parse_time(receipt.get("issuedAt"), "issuedAt")
    expires = parse_time(receipt.get("expiresAt"), "expiresAt")
    if issued > now + dt.timedelta(seconds=60):
        raise AllocationError("receipt issuedAt is in the future")
    if expires <= now:
        raise AllocationError("allocation receipt has expired")
    if expires <= issued or (expires - issued).total_seconds() > allocator["maxReceiptAgeSeconds"]:
        raise AllocationError("allocation receipt lifetime exceeds policy")


def validate_receipt(receipt: dict, request: dict, config: dict, now: dt.datetime) -> str:
    fields = {
        "schema", "allocationId", "repositoryRef", "ticket", "number",
        "requestDigest", "processUri", "issuer", "fencingToken", "issuedAt",
        "expiresAt", "receiptRef", "proofDigest",
    }
    require_exact(receipt, fields, "allocation receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise AllocationError("unsupported allocation receipt schema")
    for field in ("allocationId", "repositoryRef", "processUri", "issuer", "receiptRef"):
        require_uri(receipt.get(field), field)
    if receipt["repositoryRef"] != request["repositoryRef"]:
        raise AllocationError("receipt repository does not match the request")
    allocator = config["allocator"]
    if receipt["processUri"] != allocator["processUri"] or receipt["issuer"] != allocator["issuer"]:
        raise AllocationError("receipt is not issued by the registered allocator")
    if receipt.get("requestDigest") != canonical_digest(request):
        raise AllocationError("receipt request digest does not match this invocation")
    number = receipt.get("number")
    token = receipt.get("fencingToken")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise AllocationError("receipt number must be a positive integer")
    if receipt.get("ticket") != f"ticket-{number:03d}":
        raise AllocationError("receipt ticket does not match its number")
    if not isinstance(token, int) or isinstance(token, bool) or token < 1:
        raise AllocationError("receipt fencing token must be a positive integer")
    if not SHA256.fullmatch(str(receipt.get("proofDigest", ""))):
        raise AllocationError("receipt proof digest is invalid")
    validate_receipt_lifetime(receipt, allocator, now)
    return f"{number:03d}"


def add_request_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--allocation-key", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--workstream", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--priority", required=True)
    parser.add_argument("--origin", required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    mode = sub.add_parser("mode")
    mode.add_argument("--config", type=Path, required=True)
    repository = sub.add_parser("repository-ref")
    repository.add_argument("--url", required=True)
    request = sub.add_parser("request")
    add_request_args(request)
    validate = sub.add_parser("validate")
    add_request_args(validate)
    validate.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "repository-ref":
            print(canonical_repository_ref(args.url))
            return 0
        config = parse_config(args.config)
        if args.command == "mode":
            print(config["mode"])
            return 0
        request_doc = request_value(args, config)
        if args.command == "request":
            json.dump(request_doc, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        receipt = load_json(args.receipt)
        now = dt.datetime.now(dt.timezone.utc)
        print(validate_receipt(receipt, request_doc, config, now))
        return 0
    except AllocationError as exc:
        print(f"{INVALID_RECEIPT_CODE}: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
