#!/usr/bin/env python3
"""Capture and verify host-agnostic local continuity events.

The JSONL stream is append-only and has no policy size cap. The checkpoint
index is a bounded, atomically replaced acceleration structure; it is never an
authority source and can always be rebuilt from the stream. Cross-machine
durability still requires a protected external receipt store.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit


CHECKPOINT_SCHEMA = "new-project.work-continuity/v2"
EVENT_SCHEMA = "new-project.work-continuity-event/v2"
INDEX_SCHEMA = "new-project.work-continuity-index/v2"
MANIFEST_SCHEMA = "new-project.subactor-local/v1"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TICKET_RE = re.compile(r"^ticket-[0-9]{3,}$")
WORKSTREAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
REPOSITORY_RE = re.compile(r"^repository:[A-Za-z0-9][A-Za-z0-9._/-]{0,500}$")
ACCOUNT_RE = re.compile(r"^account:[a-z0-9][a-z0-9._:/-]{0,255}$")
CRITERION_RE = re.compile(r"^AC-[0-9]{2,}$")
REFERENCE_RE = re.compile(
    r"^(artifact|authorization|decision|knowledge|receipt):"
    r"[a-z0-9][a-z0-9._:/-]{0,510}$"
)
IDEMPOTENCY_RE = re.compile(r"^idempotency:[a-z0-9][a-z0-9._-]{0,127}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
PHASES = {"analysis", "plan", "tools", "edit", "validation", "publication", "blocked"}
NEXT_ACTIONS = {"observe", "edit", "validate", "publish", "reconcile", "wait"}
EFFECT_KINDS = {
    "push", "pull-request", "validation", "merge", "release", "external-coordination"
}
EFFECT_STATES = {"planned", "in-flight", "failed"}
IGNORED_DIRECTORIES = [
    ".subactor/leases/",
    ".subactor/sessions/",
    ".subactor/recovery/",
    ".subactor/receipts/",
    ".subactor/cache/",
    ".subactor/snapshots/",
]


class ContinuityError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise ContinuityError(code, message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, *, maximum: int = 1024 * 1024) -> Any:
    try:
        if path.stat().st_size > maximum:
            fail("GOV-CONTINUITY-001", f"bounded continuity document is too large: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
    except ContinuityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail("GOV-CONTINUITY-001", f"cannot read continuity document {path}: {exc}")


def exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        fail("GOV-CONTINUITY-001", f"{label} fields are invalid")
    return value


def string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        fail("GOV-CONTINUITY-001", f"{label} must be a bounded non-empty string")
    if any(ord(character) < 32 for character in value):
        fail("GOV-CONTINUITY-001", f"{label} contains control characters")
    return value


def safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID_RE.fullmatch(value) is None:
        fail("GOV-CONTINUITY-001", f"{label} is invalid")
    return value


def reference(value: Any, label: str, *, kind: str | None = None) -> str:
    result = string(value, label)
    match = REFERENCE_RE.fullmatch(result)
    if match is None or (kind is not None and match.group(1) != kind):
        fail("GOV-CONTINUITY-001", f"{label} is not an allowed opaque {kind or 'evidence'} reference")
    return result


def sha(value: Any, label: str, expression: re.Pattern[str]) -> str:
    if not isinstance(value, str) or expression.fullmatch(value) is None:
        fail("GOV-CONTINUITY-001", f"{label} has an invalid digest")
    return value


def timestamp(value: Any, label: str = "recordedAt") -> str:
    result = string(value, label, maximum=64)
    if not result.endswith("Z"):
        fail("GOV-CONTINUITY-001", f"{label} must be UTC and end with Z")
    try:
        parsed = datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError:
        fail("GOV-CONTINUITY-001", f"{label} is not an RFC 3339 timestamp")
    if parsed.tzinfo != timezone.utc:
        fail("GOV-CONTINUITY-001", f"{label} must use UTC")
    return result


def unique_strings(
    value: Any, label: str, expression: re.Pattern[str], maximum: int = 128
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        fail("GOV-CONTINUITY-001", f"{label} must be a bounded array")
    if any(not isinstance(item, str) or expression.fullmatch(item) is None for item in value):
        fail("GOV-CONTINUITY-001", f"{label} contains an invalid item")
    if len(value) != len(set(value)):
        fail("GOV-CONTINUITY-001", f"{label} contains duplicates")
    return value


def git_ref(value: Any, label: str) -> str:
    result = string(value, label, maximum=255)
    invalid = (
        result.startswith(("/", "."))
        or result.endswith(("/", ".", ".lock"))
        or any(token in result for token in ("..", "//", "@{", "\\", " "))
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", result) is None
    )
    if invalid:
        fail("GOV-CONTINUITY-001", f"{label} is not a safe Git ref")
    return result


def validate_repository(value: Any, label: str) -> str:
    repository = string(value, label)
    if REPOSITORY_RE.fullmatch(repository) is None or ".." in repository or "//" in repository:
        fail("GOV-CONTINUITY-001", f"{label} is not a credential-free repository identity")
    return repository


def validate_binding(value: Any, label: str) -> dict[str, Any]:
    binding = exact_object(value, {"ref", "sha256"}, label)
    reference(binding["ref"], f"{label}.ref", kind="artifact")
    sha(binding["sha256"], f"{label}.sha256", SHA256_RE)
    return binding


def validate_slice(value: Any) -> dict[str, Any]:
    binding = exact_object(value, {"ref", "sha256", "ordinal", "total"}, "slice")
    reference(binding["ref"], "slice.ref", kind="artifact")
    sha(binding["sha256"], "slice.sha256", SHA256_RE)
    for field in ("ordinal", "total"):
        if not isinstance(binding[field], int) or isinstance(binding[field], bool) or binding[field] < 1:
            fail("GOV-CONTINUITY-001", f"slice.{field} must be a positive integer")
    if binding["ordinal"] > binding["total"]:
        fail("GOV-CONTINUITY-001", "slice ordinal cannot exceed total")
    return binding


def validate_lease(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    lease = exact_object(value, {"leaseRef", "leaseRevision", "fencingToken"}, "lease")
    reference(lease["leaseRef"], "lease.leaseRef", kind="receipt")
    for field in ("leaseRevision", "fencingToken"):
        if not isinstance(lease[field], int) or isinstance(lease[field], bool) or lease[field] < 1:
            fail("GOV-CONTINUITY-001", f"lease.{field} must be a positive integer")
    return lease


def validate_remote(value: Any, repository: str) -> dict[str, Any]:
    observation = exact_object(
        value,
        {"remoteName", "repositoryRef", "accountRef", "observedAt", "receiptRef"},
        "remoteObservation",
    )
    safe_id(observation["remoteName"], "remoteObservation.remoteName")
    if validate_repository(observation["repositoryRef"], "remoteObservation.repositoryRef") != repository:
        fail("GOV-CONTINUITY-002", "remote observation belongs to another repository")
    if not isinstance(observation["accountRef"], str) or ACCOUNT_RE.fullmatch(observation["accountRef"]) is None:
        fail("GOV-CONTINUITY-001", "remoteObservation.accountRef is invalid")
    timestamp(observation["observedAt"], "remoteObservation.observedAt")
    reference(observation["receiptRef"], "remoteObservation.receiptRef", kind="receipt")
    return observation


def validate_workspace(value: Any) -> dict[str, Any]:
    workspace = exact_object(
        value,
        {
            "state", "resumeSource", "statusSha256", "snapshotRef", "snapshotSha256",
            "snapshotReceipt", "secretScanReceipt",
        },
        "workspace",
    )
    sha(workspace["statusSha256"], "workspace.statusSha256", SHA256_RE)
    snapshot_fields = ("snapshotRef", "snapshotSha256", "snapshotReceipt", "secretScanReceipt")
    if workspace["state"] == "clean" and workspace["resumeSource"] == "commit":
        if workspace["statusSha256"] != EMPTY_SHA256 or any(workspace[field] is not None for field in snapshot_fields):
            fail("GOV-CONTINUITY-001", "clean workspace must bind only the exact committed HEAD")
    elif workspace["state"] == "snapshotted" and workspace["resumeSource"] == "snapshot":
        reference(workspace["snapshotRef"], "workspace.snapshotRef", kind="artifact")
        sha(workspace["snapshotSha256"], "workspace.snapshotSha256", SHA256_RE)
        reference(workspace["snapshotReceipt"], "workspace.snapshotReceipt", kind="receipt")
        reference(workspace["secretScanReceipt"], "workspace.secretScanReceipt", kind="receipt")
        if workspace["statusSha256"] == EMPTY_SHA256:
            fail("GOV-CONTINUITY-001", "snapshotted workspace must bind a non-empty status digest")
    else:
        fail("GOV-CONTINUITY-001", "workspace is resumable only from commit or snapshot")
    return workspace


def validate_pending_effect(value: Any, index: int) -> dict[str, Any]:
    effect = exact_object(
        value, {"kind", "state", "idempotencyKey", "effectRef"}, f"pendingEffects[{index}]"
    )
    if effect["kind"] not in EFFECT_KINDS or effect["state"] not in EFFECT_STATES:
        fail("GOV-CONTINUITY-001", f"pendingEffects[{index}] uses an unsupported enum")
    if not isinstance(effect["idempotencyKey"], str) or IDEMPOTENCY_RE.fullmatch(effect["idempotencyKey"]) is None:
        fail("GOV-CONTINUITY-001", f"pendingEffects[{index}].idempotencyKey is invalid")
    if effect["effectRef"] is not None:
        reference(effect["effectRef"], f"pendingEffects[{index}].effectRef")
    return effect


def validate_checkpoint_effects(checkpoint):
    effects = checkpoint["pendingEffects"]
    if not isinstance(effects, list) or len(effects) > 32:
        fail("GOV-CONTINUITY-001", "pendingEffects must be a bounded array")
    validated_effects = [validate_pending_effect(item, index) for index, item in enumerate(effects)]
    keys = [item["idempotencyKey"] for item in validated_effects]
    if len(keys) != len(set(keys)):
        fail("GOV-CONTINUITY-001", "pending effect idempotency keys must be unique")


def validate_checkpoint_progress(checkpoint):
    completed = unique_strings(checkpoint["completedCriteria"], "completedCriteria", CRITERION_RE)
    remaining = unique_strings(checkpoint["remainingCriteria"], "remainingCriteria", CRITERION_RE)
    if set(completed) & set(remaining):
        fail("GOV-CONTINUITY-001", "completed and remaining criteria overlap")
    evidence = checkpoint["evidenceRefs"]
    if not isinstance(evidence, list) or len(evidence) > 128:
        fail("GOV-CONTINUITY-001", "evidenceRefs must be a bounded array")
    for index, item in enumerate(evidence):
        reference(item, f"evidenceRefs[{index}]")
    if len(evidence) != len(set(evidence)):
        fail("GOV-CONTINUITY-001", "evidenceRefs contains duplicates")
    validate_checkpoint_effects(checkpoint)
    next_action = exact_object(checkpoint["nextAction"], {"kind", "criterion"}, "nextAction")
    if next_action["kind"] not in NEXT_ACTIONS:
        fail("GOV-CONTINUITY-001", "nextAction.kind is invalid")
    if next_action["criterion"] is not None and (
        not isinstance(next_action["criterion"], str)
        or CRITERION_RE.fullmatch(next_action["criterion"]) is None
        or next_action["criterion"] not in remaining
    ):
        fail("GOV-CONTINUITY-001", "next action criterion must remain unfinished")


def validate_checkpoint(value: Any) -> dict[str, Any]:
    fields = {
        "schema", "authority", "checkpointRef", "previousCheckpointRef", "sequence",
        "repositoryRef", "ticket", "workstream", "intentRef", "intentSha256",
        "scopeSha256", "plan", "slice", "targetBranch", "branchRef", "headSha",
        "worktreeId", "phase", "authorizationRef", "lease", "remoteObservation",
        "workspace", "completedCriteria", "remainingCriteria", "evidenceRefs",
        "pendingEffects", "nextAction", "recordedAt",
    }
    checkpoint = exact_object(value, fields, "checkpoint")
    if checkpoint["schema"] != CHECKPOINT_SCHEMA or checkpoint["authority"] != "advisory-projection":
        fail("GOV-CONTINUITY-001", "checkpoint schema or authority is invalid")
    reference(checkpoint["checkpointRef"], "checkpointRef", kind="receipt")
    if checkpoint["previousCheckpointRef"] is not None:
        reference(checkpoint["previousCheckpointRef"], "previousCheckpointRef", kind="receipt")
    sequence = checkpoint["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        fail("GOV-CONTINUITY-001", "sequence must be a positive integer")
    if (sequence == 1) != (checkpoint["previousCheckpointRef"] is None):
        fail("GOV-CONTINUITY-002", "checkpoint sequence and previous reference do not agree")
    repository = validate_repository(checkpoint["repositoryRef"], "repositoryRef")
    if not isinstance(checkpoint["ticket"], str) or TICKET_RE.fullmatch(checkpoint["ticket"]) is None:
        fail("GOV-CONTINUITY-001", "ticket is invalid")
    if not isinstance(checkpoint["workstream"], str) or WORKSTREAM_RE.fullmatch(checkpoint["workstream"]) is None:
        fail("GOV-CONTINUITY-001", "workstream is invalid")
    reference(checkpoint["intentRef"], "intentRef", kind="artifact")
    sha(checkpoint["intentSha256"], "intentSha256", SHA256_RE)
    sha(checkpoint["scopeSha256"], "scopeSha256", SHA256_RE)
    validate_binding(checkpoint["plan"], "plan")
    validate_slice(checkpoint["slice"])
    git_ref(checkpoint["targetBranch"], "targetBranch")
    git_ref(checkpoint["branchRef"], "branchRef")
    sha(checkpoint["headSha"], "headSha", SHA1_RE)
    safe_id(checkpoint["worktreeId"], "worktreeId")
    if checkpoint["phase"] not in PHASES:
        fail("GOV-CONTINUITY-001", "phase is invalid")
    reference(checkpoint["authorizationRef"], "authorizationRef", kind="authorization")
    validate_lease(checkpoint["lease"])
    validate_remote(checkpoint["remoteObservation"], repository)
    validate_workspace(checkpoint["workspace"])
    validate_checkpoint_progress(checkpoint)
    timestamp(checkpoint["recordedAt"])
    digest_payload = dict(checkpoint)
    digest_payload.pop("checkpointRef")
    expected_ref = f"receipt:continuity.{checkpoint['ticket']}.{sequence}.{canonical_digest(digest_payload)}"
    if checkpoint["checkpointRef"] != expected_ref:
        fail("GOV-CONTINUITY-002", "checkpoint reference does not bind its canonical content")
    return checkpoint


def validate_event(value: Any) -> dict[str, Any]:
    event = exact_object(
        value,
        {"schema", "eventRef", "previousEventRef", "eventSequence", "sessionId", "checkpoint"},
        "event",
    )
    if event["schema"] != EVENT_SCHEMA:
        fail("GOV-CONTINUITY-001", "event schema is invalid")
    reference(event["eventRef"], "eventRef", kind="receipt")
    if event["previousEventRef"] is not None:
        reference(event["previousEventRef"], "previousEventRef", kind="receipt")
    sequence = event["eventSequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        fail("GOV-CONTINUITY-001", "eventSequence must be a positive integer")
    if (sequence == 1) != (event["previousEventRef"] is None):
        fail("GOV-CONTINUITY-002", "event sequence and previous reference do not agree")
    safe_id(event["sessionId"], "sessionId")
    validate_checkpoint(event["checkpoint"])
    digest_payload = dict(event)
    digest_payload.pop("eventRef")
    expected = f"receipt:continuity-event.{event['sessionId']}.{sequence}.{canonical_digest(digest_payload)}"
    if event["eventRef"] != expected:
        fail("GOV-CONTINUITY-002", "event reference does not bind its canonical content")
    return event


def validate_index(value: Any) -> dict[str, Any]:
    index = exact_object(value, {"schema", "repositoryRef", "maxEntries", "entries", "updatedAt"}, "index")
    if index["schema"] != INDEX_SCHEMA:
        fail("GOV-CONTINUITY-001", "index schema is invalid")
    validate_repository(index["repositoryRef"], "index.repositoryRef")
    maximum = index["maxEntries"]
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 128:
        fail("GOV-CONTINUITY-001", "index maxEntries is invalid")
    entries = index["entries"]
    if not isinstance(entries, list) or len(entries) > maximum:
        fail("GOV-CONTINUITY-001", "index exceeds its bounded entry limit")
    tickets: set[str] = set()
    for number, item in enumerate(entries):
        entry = exact_object(
            item,
            {"ticket", "sessionId", "eventRef", "checkpointRef", "checkpointSequence", "recordedAt"},
            f"index.entries[{number}]",
        )
        if not isinstance(entry["ticket"], str) or TICKET_RE.fullmatch(entry["ticket"]) is None:
            fail("GOV-CONTINUITY-001", "index ticket is invalid")
        if entry["ticket"] in tickets:
            fail("GOV-CONTINUITY-002", "index contains duplicate tickets")
        tickets.add(entry["ticket"])
        safe_id(entry["sessionId"], "index sessionId")
        reference(entry["eventRef"], "index eventRef", kind="receipt")
        reference(entry["checkpointRef"], "index checkpointRef", kind="receipt")
        if (not isinstance(entry["checkpointSequence"], int)
                or isinstance(entry["checkpointSequence"], bool)
                or entry["checkpointSequence"] < 1):
            fail("GOV-CONTINUITY-001", "index checkpointSequence is invalid")
        timestamp(entry["recordedAt"], "index recordedAt")
    timestamp(index["updatedAt"], "index updatedAt")
    return index


def validate_document(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("schema") == CHECKPOINT_SCHEMA:
        return validate_checkpoint(value)
    if isinstance(value, dict) and value.get("schema") == EVENT_SCHEMA:
        return validate_event(value)
    if isinstance(value, dict) and value.get("schema") == INDEX_SCHEMA:
        return validate_index(value)
    fail("GOV-CONTINUITY-001", "unsupported continuity schema")


def git(root: Path, *arguments: str, binary: bool = False, check: bool = True) -> str | bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        fail("GOV-CONTINUITY-003", f"cannot observe Git state for {arguments[0]}: {exc}")
    if result.returncode != 0:
        if not check:
            return None
        fail("GOV-CONTINUITY-003", f"cannot observe Git state for {arguments[0]}")
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def repository_ref(root: Path) -> str:
    value = git(root, "config", "--get", "remote.origin.url")
    assert isinstance(value, str)
    origin = string(value, "repository origin")
    if "://" in origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"git", "http", "https", "ssh"} or not parsed.hostname:
            fail("GOV-CONTINUITY-001", "repository origin uses an unsupported transport")
        try:
            port = parsed.port
        except ValueError:
            fail("GOV-CONTINUITY-001", "repository origin has an invalid port")
        host = parsed.hostname if port is None else f"{parsed.hostname}.port-{port}"
        repository_path = parsed.path
    else:
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", origin)
        if match is None:
            fail("GOV-CONTINUITY-001", "repository origin must name a remote host and path")
        host, repository_path = match.groups()
    repository_path = repository_path.lstrip("/")
    if repository_path.endswith(".git"):
        repository_path = repository_path[:-4]
    return validate_repository(f"repository:{host.lower()}/{repository_path}", "repository origin")


def validate_manifest_value(value: Any) -> dict[str, Any]:
    fields = {"schema", "standardPin", "ignoredRuntimeDirectories", "continuity"}
    manifest = exact_object(value, fields, "subactor manifest")
    if manifest["schema"] != MANIFEST_SCHEMA:
        fail("GOV-CONTINUITY-001", "subactor manifest schema is invalid")
    pin = exact_object(manifest["standardPin"], {"lockPath", "requiredStandardId"}, "standardPin")
    if pin != {
        "lockPath": ".governance/manifest.lock.json",
        "requiredStandardId": "wellmanifest/new-project",
    }:
        fail("GOV-CONTINUITY-001", "standard pin contract is invalid")
    if manifest["ignoredRuntimeDirectories"] != IGNORED_DIRECTORIES:
        fail("GOV-CONTINUITY-001", "managed local-runtime directory list is invalid")
    continuity = exact_object(
        manifest["continuity"],
        {
            "checkpointSchema", "eventSchema", "indexSchema", "eventStreamPath",
            "eventStreamPolicyMaxBytes", "checkpointIndexPath", "checkpointIndexMaxEntries",
            "checkpointIndexMaxBytes", "checkpointIndexWrite",
        },
        "continuity manifest",
    )
    expected = {
        "checkpointSchema": CHECKPOINT_SCHEMA,
        "eventSchema": EVENT_SCHEMA,
        "indexSchema": INDEX_SCHEMA,
        "eventStreamPath": ".subactor/sessions/work-continuity.jsonl",
        "eventStreamPolicyMaxBytes": None,
        "checkpointIndexPath": ".subactor/recovery/checkpoint-index.json",
        "checkpointIndexMaxEntries": 128,
        "checkpointIndexMaxBytes": 262144,
        "checkpointIndexWrite": "atomic-replace",
    }
    if continuity != expected:
        fail("GOV-CONTINUITY-001", "continuity storage contract is invalid")
    return manifest


def load_local_manifest(root: Path) -> dict[str, Any]:
    return validate_manifest_value(load_json(root / ".subactor" / "manifest.json"))


def storage_paths(root: Path) -> tuple[Path, Path, int, int]:
    continuity = load_local_manifest(root)["continuity"]
    return (
        root / continuity["eventStreamPath"],
        root / continuity["checkpointIndexPath"],
        continuity["checkpointIndexMaxEntries"],
        continuity["checkpointIndexMaxBytes"],
    )



@contextmanager
def _posix_stream_descriptor(path: Path, append: bool):
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        fail("GOV-CONTINUITY-001", "safe continuity directory opens are unavailable")
    directory_flags = os.O_RDONLY | directory_flag | no_follow | getattr(os, "O_CLOEXEC", 0)
    directory = os.open(path.anchor, directory_flags)
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directory)
            except FileNotFoundError:
                if not append:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass  # Reopen with no-follow; a concurrent link is never traversed.
                child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        flags = (os.O_WRONLY | os.O_CREAT | os.O_APPEND) if append else os.O_RDONLY
        flags |= no_follow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path.name, flags, 0o600, dir_fd=directory)
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


@contextmanager
def _windows_stream_descriptor(path: Path, append: bool, *, readwrite: bool = False):
    # Open reparse points themselves. Held directory handles omit DELETE
    # sharing, so parent names cannot be replaced during the file operation.
    # https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
    import ctypes
    from ctypes import wintypes
    import msvcrt
    if len(path.anchor) != 3 or path.anchor[1:] != ":\\":
        fail("GOV-CONTINUITY-001", "continuity requires an absolute local drive path")
    class FileInformation(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("creation", wintypes.FILETIME),
                    ("access", wintypes.FILETIME), ("write", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("sizeHigh", wintypes.DWORD),
                    ("sizeLow", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("indexHigh", wintypes.DWORD), ("indexLow", wintypes.DWORD)]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    api.GetFileInformationByHandle.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    handles = []
    descriptor = None
    def open_handle(candidate, directory=False):
        access = 0x80 if directory else (
            0xC0000080 if readwrite else (0x40000080 if append else 0x80000000))
        flags = 0x00200000 | (0x02000000 if directory else 0)
        creation = 4 if append and not directory else 3  # OPEN_ALWAYS / OPEN_EXISTING
        handle = api.CreateFileW(str(candidate), access, 3, None, creation, flags, None)
        if handle == invalid:
            error = ctypes.get_last_error()
            if error in (2, 3):
                raise FileNotFoundError(errno.ENOENT, "continuity path is absent", str(candidate))
            raise ctypes.WinError(error)
        handles.append(handle)
        metadata = FileInformation()
        if not api.GetFileInformationByHandle(handle, ctypes.byref(metadata)):
            raise ctypes.WinError(ctypes.get_last_error())
        if metadata.attributes & 0x400 or bool(metadata.attributes & 0x10) != directory:
            fail("GOV-CONTINUITY-001", "continuity paths must not be reparse points or unexpected types")
        if not directory and metadata.links != 1:
            fail("GOV-CONTINUITY-001", "continuity stream must be a single-linked regular file")
        return handle
    try:
        open_handle(Path(path.anchor), directory=True)
        current = Path(path.anchor)
        for part in path.parts[1:-1]:
            current /= part
            try:
                open_handle(current, directory=True)
            except FileNotFoundError:
                if not append:
                    raise
                try:
                    current.mkdir(mode=0o700)
                except FileExistsError:
                    pass
                open_handle(current, directory=True)
        handle = open_handle(path)
        descriptor = msvcrt.open_osfhandle(
            handle, os.O_BINARY | os.O_NOINHERIT | (
                os.O_RDWR if readwrite else (os.O_APPEND if append else os.O_RDONLY))
        )
        handles.pop()  # The CRT descriptor now owns the file handle.
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for handle in reversed(handles):
            api.CloseHandle(handle)


@contextmanager
def _stream_descriptor(path: Path, append: bool):
    candidate = path.absolute()
    if not candidate.name or ".." in candidate.parts:
        fail("GOV-CONTINUITY-001", "continuity stream needs a confined file path")
    adapter = _windows_stream_descriptor if os.name == "nt" else _posix_stream_descriptor
    try:
        with adapter(candidate, append) as descriptor:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                fail("GOV-CONTINUITY-001", "continuity stream must be a single-linked regular file")
            yield descriptor
    except FileNotFoundError:
        if not append:
            raise
        fail("GOV-CONTINUITY-001", "continuity stream parent disappeared before creation")
    except OSError as error:
        fail("GOV-CONTINUITY-001", f"cannot safely access continuity stream: {error}")


def iter_events(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with _stream_descriptor(path, append=False) as descriptor, os.fdopen(descriptor, "rb", closefd=False) as stream:
            for number, raw in enumerate(stream, start=1):
                if len(raw) > 1024 * 1024:
                    fail("GOV-CONTINUITY-001", f"event line {number} exceeds the bounded event size")
                if not raw.endswith(b"\n"):
                    fail("GOV-CONTINUITY-002", f"event stream has an incomplete line at {number}")
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    fail("GOV-CONTINUITY-002", f"event stream line {number} is invalid: {exc}")
                yield validate_event(value)
    except FileNotFoundError:
        return
    except ContinuityError:
        raise
    except OSError as exc:
        fail("GOV-CONTINUITY-001", f"cannot read event stream {path}: {exc}")


def event_state(events: Iterable[dict[str, Any]], repository: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_events: list[dict[str, Any]] = []
    latest_checkpoint: dict[str, dict[str, Any]] = {}
    latest_session: dict[str, dict[str, Any]] = {}
    refs: set[str] = set()
    for event in events:
        checkpoint = event["checkpoint"]
        if checkpoint["repositoryRef"] != repository:
            fail("GOV-CONTINUITY-002", "event belongs to another repository")
        if event["eventRef"] in refs:
            fail("GOV-CONTINUITY-002", "event reference is not append-only unique")
        refs.add(event["eventRef"])
        prior_session = latest_session.get(event["sessionId"])
        expected_event_sequence = 1 if prior_session is None else prior_session["eventSequence"] + 1
        expected_event_previous = None if prior_session is None else prior_session["eventRef"]
        if event["eventSequence"] != expected_event_sequence or event["previousEventRef"] != expected_event_previous:
            fail("GOV-CONTINUITY-002", f"session chain for {event['sessionId']} is not monotonic")
        prior_checkpoint = latest_checkpoint.get(checkpoint["ticket"])
        expected_sequence = 1 if prior_checkpoint is None else prior_checkpoint["sequence"] + 1
        expected_previous = None if prior_checkpoint is None else prior_checkpoint["checkpointRef"]
        if checkpoint["sequence"] != expected_sequence or checkpoint["previousCheckpointRef"] != expected_previous:
            fail("GOV-CONTINUITY-002", f"checkpoint chain for {checkpoint['ticket']} is not monotonic")
        latest_session[event["sessionId"]] = event
        latest_checkpoint[checkpoint["ticket"]] = checkpoint
        all_events.append(event)
    return all_events, {"sessions": latest_session, "checkpoints": latest_checkpoint}


def append_event(path: Path, event: dict[str, Any]) -> None:
    payload = canonical_bytes(event) + b"\n"
    with _stream_descriptor(path, append=True) as descriptor:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)


def index_from_events(repository: str, events: list[dict[str, Any]], maximum: int) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        checkpoint = event["checkpoint"]
        ticket = checkpoint["ticket"]
        if ticket in order:
            order.remove(ticket)
        order.append(ticket)
        latest[ticket] = {
            "ticket": ticket,
            "sessionId": event["sessionId"],
            "eventRef": event["eventRef"],
            "checkpointRef": checkpoint["checkpointRef"],
            "checkpointSequence": checkpoint["sequence"],
            "recordedAt": checkpoint["recordedAt"],
        }
    value = {
        "schema": INDEX_SCHEMA,
        "repositoryRef": repository,
        "maxEntries": maximum,
        "entries": [latest[ticket] for ticket in order[-maximum:]],
        "updatedAt": utc_now(),
    }
    return validate_index(value)


def index_payload(value: dict[str, Any], maximum_bytes: int) -> bytes:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(payload) > maximum_bytes:
        fail("GOV-CONTINUITY-001", "checkpoint index exceeds its bounded byte limit")
    return payload


def write_index(path: Path, value: dict[str, Any], maximum_bytes: int) -> None:
    payload = index_payload(value, maximum_bytes)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="checkpoint-index.", suffix=".json", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _posix_lock_descriptor(path: Path):
    """Anchor every parent and recheck public names after a potentially long wait."""
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        fail("GOV-CONTINUITY-001", "safe continuity lock directory opens are unavailable")
    directory_flags = os.O_RDONLY | directory_flag | no_follow | getattr(os, "O_CLOEXEC", 0)
    directories = [os.open(path.anchor, directory_flags)]
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directories[-1])
                except FileExistsError:
                    pass
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            directories.append(child)
        descriptor = os.open(path.name, os.O_RDWR | os.O_CREAT | no_follow
                             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
                             0o600, dir_fd=directories[-1])
        def verify_identity():
            # Held descriptors prevent traversal through a swapped link. They
            # alone do not prove the public path still names the locked inode.
            for parent, child, part in zip(directories, directories[1:], path.parts[1:-1]):
                named = os.stat(part, dir_fd=parent, follow_symlinks=False)
                held = os.fstat(child)
                if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
                    fail("GOV-CONTINUITY-001", "continuity lock parent identity changed")
            named = os.stat(path.name, dir_fd=directories[-1], follow_symlinks=False)
            held = os.fstat(descriptor)
            if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
                    or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)):
                fail("GOV-CONTINUITY-001", "continuity lock file identity changed")
        yield descriptor, verify_identity
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)


@contextmanager
def _lock_descriptor(path: Path):
    with ExitStack() as handles:
        try:
            if os.name == "nt":
                # No DELETE sharing on any held handle: Windows cannot rename
                # the parent or lock while this transaction owns those handles.
                descriptor = handles.enter_context(_windows_stream_descriptor(path, True, readwrite=True))
                verify = lambda: None
            elif os.name == "posix":
                descriptor, verify = handles.enter_context(_posix_lock_descriptor(path))
            else:
                fail("GOV-CONTINUITY-001", "safe continuity transaction locking is unavailable")
        except (OSError, NotImplementedError) as error:
            raise ContinuityError("GOV-CONTINUITY-001", "continuity transaction lock path is unsafe or unavailable") from error
        def verify_identity():
            try:
                verify()
            except (OSError, NotImplementedError) as error:
                raise ContinuityError("GOV-CONTINUITY-001", "continuity transaction lock identity is unavailable") from error
        # Exceptions from the transaction body keep their original meaning,
        # notably interrupted journal/index writes which exact replay repairs.
        yield descriptor, verify_identity


@contextmanager
def storage_transaction(event_path: Path):
    """Stable OS-owned lock; never unlink it while another writer can use it."""
    if not event_path.name or ".." in event_path.absolute().parts:
        fail("GOV-CONTINUITY-001", "continuity transaction needs a confined file path")
    lock_path = event_path.with_name(event_path.name + ".lock").absolute()
    with _lock_descriptor(lock_path) as (descriptor, verify_identity):
        with _locked_transaction(descriptor, verify_identity):
            yield


@contextmanager
def _locked_transaction(descriptor, verify_identity):
    acquired = False
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            fail("GOV-CONTINUITY-001", "continuity transaction lock must be a regular private file")
        if os.name == "nt":
            import msvcrt
            def acquire():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            def unlock():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlock():
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        deadline = time.monotonic() + 30
        while True:
            verify_identity()
            try:
                acquire()
                acquired = True
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    fail("GOV-CONTINUITY-001", "continuity transaction lock acquisition timed out")
                time.sleep(0.05)
        verify_identity()
        yield
    finally:
        if acquired:
            unlock()


def commit_event(root: Path, event: dict[str, Any]) -> dict[str, Any]:
    repository = repository_ref(root)
    event_path, index_path, maximum, maximum_bytes = storage_paths(root)
    validate_event(event)
    with storage_transaction(event_path):
        events, _ = event_state(iter_events(event_path), repository)
        matching = next((existing for existing in events if existing["eventRef"] == event["eventRef"]), None)
        if matching is not None:
            if matching != event:
                fail("GOV-CONTINUITY-002", "event reference already binds different content")
            # An append can survive a failed index replace. The journal is
            # authoritative for this advisory projection; exact replay heals it.
            write_index(index_path, index_from_events(repository, events, maximum), maximum_bytes)
            return {"status": "already-recorded", "event": event}
        candidate = events + [event]
        event_state(candidate, repository)
        index = index_from_events(repository, candidate, maximum)
        index_payload(index, maximum_bytes)  # Reject bounded-size failure before append.
        append_event(event_path, event)
        write_index(index_path, index, maximum_bytes)
        return {"status": "recorded", "event": event}


def resolve_compact_target_branch(root: Path) -> str:
    candidates = (
        root / ".governance" / "manifest.json",
        root / ".governance" / "manifest.base.json",
        root / "governance" / "manifest.hub.json",
    )
    targets: list[str] = []
    for cand in candidates:
        if cand.is_file():
            try:
                manifest_data = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                continue
            delivery_cfg = manifest_data.get("delivery")
            if isinstance(delivery_cfg, dict):
                tb = delivery_cfg.get("targetBranches")
                if isinstance(tb, list):
                    for b in tb:
                        if isinstance(b, str) and b and b not in targets:
                            targets.append(b)
            rep_cfg = manifest_data.get("repositoryPolicy", {}).get("delivery", {})
            if isinstance(rep_cfg, dict):
                tb = rep_cfg.get("targetBranches")
                if isinstance(tb, list):
                    for b in tb:
                        if isinstance(b, str) and b and b not in targets:
                            targets.append(b)
            if targets:
                break
    if len(targets) == 1:
        return targets[0]
    fail("GOV-CONTINUITY-001", "intent target branch must be a bounded non-empty string")


def intent_state(root: Path, ticket: str) -> tuple[dict[str, Any], str, str, str]:
    path = root / "project" / ticket / "intent.json"
    try:
        storage = git(root, "config", "--local", "--default", "files", "--get", "new-project.ticketStorage")
        if storage == "sqlite":
            spec = importlib.util.spec_from_file_location("continuity_ticket_input", Path(__file__).with_name("ticket_input.py"))
            module = importlib.util.module_from_spec(spec)
            previous = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                spec.loader.exec_module(module)
            finally:
                sys.dont_write_bytecode = previous
            raw = module.read_file(root, ticket, "intent.json")
        elif storage == "files":
            raw = path.read_bytes()
        else:
            raise ValueError("unknown ticket storage mode")
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        fail("GOV-CONTINUITY-003", "cannot resolve active ticket intent from configured storage")
    if not isinstance(value, dict) or value.get("ticket") != ticket:
        fail("GOV-CONTINUITY-003", "ticket intent identity does not match")
    workstream = value.get("workstream")
    if not isinstance(workstream, str) or WORKSTREAM_RE.fullmatch(workstream) is None:
        fail("GOV-CONTINUITY-003", "ticket intent workstream is invalid")
    delivery = value.get("delivery")
    target_branch = delivery.get("targetBranch") if isinstance(delivery, dict) else None
    if target_branch is None:
        target_branch = resolve_compact_target_branch(root)
    git_ref(target_branch, "intent target branch")
    scope = {
        "ticket": value.get("ticket"),
        "workstream": workstream,
        "allowedPaths": value.get("allowedPaths"),
        "forbiddenPaths": value.get("forbiddenPaths"),
        "dependsOn": value.get("dependsOn"),
        "conflictsWith": value.get("conflictsWith"),
        "integrationTicket": value.get("integrationTicket"),
        "targetBranch": target_branch,
    }
    return value, hashlib.sha256(raw).hexdigest(), canonical_digest(scope), target_branch


def parse_pending(value: str) -> dict[str, Any]:
    fields = value.split(",", 3)
    if len(fields) not in {3, 4}:
        fail("GOV-CONTINUITY-001", "--pending expects kind,state,idempotencyKey[,effectRef]")
    return {
        "kind": fields[0],
        "state": fields[1],
        "idempotencyKey": fields[2],
        "effectRef": fields[3] if len(fields) == 4 and fields[3] else None,
    }


def capture_workspace(args, status_bytes):
    snapshot_values = (
        args.snapshot_ref, args.snapshot_sha256, args.snapshot_receipt,
        args.snapshot_secret_scan_receipt,
    )
    status_digest = hashlib.sha256(status_bytes).hexdigest()
    if status_bytes:
        if not all(value is not None for value in snapshot_values):
            fail(
                "GOV-CONTINUITY-001",
                "dirty workspace needs a content-addressed snapshot, snapshot receipt and secret-scan receipt",
            )
        workspace = {
            "state": "snapshotted",
            "resumeSource": "snapshot",
            "statusSha256": status_digest,
            "snapshotRef": args.snapshot_ref,
            "snapshotSha256": args.snapshot_sha256,
            "snapshotReceipt": args.snapshot_receipt,
            "secretScanReceipt": args.snapshot_secret_scan_receipt,
        }
    else:
        if any(value is not None for value in snapshot_values):
            fail("GOV-CONTINUITY-001", "clean workspace cannot claim a snapshot")
        workspace = {
            "state": "clean", "resumeSource": "commit", "statusSha256": EMPTY_SHA256,
            "snapshotRef": None, "snapshotSha256": None, "snapshotReceipt": None,
            "secretScanReceipt": None,
        }
    return workspace


def capture(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    repository = repository_ref(root)
    event_path, _, _, _ = storage_paths(root)
    _, state = event_state(iter_events(event_path), repository)
    intent, intent_digest, scope_digest, target_branch = intent_state(root, args.ticket)
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    status_bytes = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    assert isinstance(branch, str) and isinstance(head, str) and isinstance(status_bytes, bytes)
    workspace = capture_workspace(args, status_bytes)
    prior = state["checkpoints"].get(args.ticket)
    sequence = 1 if prior is None else prior["sequence"] + 1
    lease = None
    lease_values = (args.lease_ref, args.lease_revision, args.fencing_token)
    if any(value is not None for value in lease_values):
        if not all(value is not None for value in lease_values):
            fail("GOV-CONTINUITY-001", "lease reference, revision and fencing token must be supplied together")
        lease = {
            "leaseRef": args.lease_ref,
            "leaseRevision": args.lease_revision,
            "fencingToken": args.fencing_token,
        }
    recorded_at = utc_now()
    checkpoint: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "authority": "advisory-projection",
        "checkpointRef": "receipt:pending",
        "previousCheckpointRef": None if prior is None else prior["checkpointRef"],
        "sequence": sequence,
        "repositoryRef": repository,
        "ticket": args.ticket,
        "workstream": intent["workstream"],
        "intentRef": f"artifact:intent/{args.ticket}/{intent_digest}",
        "intentSha256": intent_digest,
        "scopeSha256": scope_digest,
        "plan": {"ref": args.plan_ref, "sha256": args.plan_sha256},
        "slice": {
            "ref": args.slice_ref, "sha256": args.slice_sha256,
            "ordinal": args.slice_ordinal, "total": args.slice_total,
        },
        "targetBranch": target_branch,
        "branchRef": branch,
        "headSha": head,
        "worktreeId": args.worktree_id,
        "phase": args.phase,
        "authorizationRef": args.authorization_ref,
        "lease": lease,
        "remoteObservation": {
            "remoteName": args.remote_name,
            "repositoryRef": repository,
            "accountRef": args.remote_account_ref,
            "observedAt": recorded_at,
            "receiptRef": args.remote_observation_receipt,
        },
        "workspace": workspace,
        "completedCriteria": args.completed,
        "remainingCriteria": args.remaining,
        "evidenceRefs": args.evidence,
        "pendingEffects": [parse_pending(value) for value in args.pending],
        "nextAction": {"kind": args.next_action, "criterion": args.next_criterion},
        "recordedAt": recorded_at,
    }
    digest_payload = dict(checkpoint)
    digest_payload.pop("checkpointRef")
    checkpoint["checkpointRef"] = f"receipt:continuity.{args.ticket}.{sequence}.{canonical_digest(digest_payload)}"
    validate_checkpoint(checkpoint)
    prior_event = state["sessions"].get(args.session_id)
    event_sequence = 1 if prior_event is None else prior_event["eventSequence"] + 1
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "eventRef": "receipt:pending",
        "previousEventRef": None if prior_event is None else prior_event["eventRef"],
        "eventSequence": event_sequence,
        "sessionId": args.session_id,
        "checkpoint": checkpoint,
    }
    event_payload = dict(event)
    event_payload.pop("eventRef")
    event["eventRef"] = f"receipt:continuity-event.{args.session_id}.{event_sequence}.{canonical_digest(event_payload)}"
    validate_event(event)
    commit_event(root, event)
    return event


def record(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    checkpoint = validate_checkpoint(load_json(args.checkpoint))
    repository = repository_ref(root)
    if checkpoint["repositoryRef"] != repository:
        fail("GOV-CONTINUITY-002", "checkpoint belongs to another repository")
    event_path, _, _, _ = storage_paths(root)
    _, state = event_state(iter_events(event_path), repository)
    prior = state["sessions"].get(args.session_id)
    event_sequence = 1 if prior is None else prior["eventSequence"] + 1
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "eventRef": "receipt:pending",
        "previousEventRef": None if prior is None else prior["eventRef"],
        "eventSequence": event_sequence,
        "sessionId": args.session_id,
        "checkpoint": checkpoint,
    }
    digest_payload = dict(event)
    digest_payload.pop("eventRef")
    event["eventRef"] = f"receipt:continuity-event.{args.session_id}.{event_sequence}.{canonical_digest(digest_payload)}"
    validate_event(event)
    return commit_event(root, event)


def resolve(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    repository = repository_ref(root)
    event_path, _, _, _ = storage_paths(root)
    _, state = event_state(iter_events(event_path), repository)
    checkpoint = state["checkpoints"].get(args.ticket)
    if checkpoint is None:
        fail("GOV-CONTINUITY-002", f"no continuity checkpoint exists for {args.ticket}")
    return checkpoint


def rebuild_index(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    repository = repository_ref(root)
    event_path, index_path, maximum, maximum_bytes = storage_paths(root)
    with storage_transaction(event_path):
        events, _ = event_state(iter_events(event_path), repository)
        index = index_from_events(repository, events, maximum)
        write_index(index_path, index, maximum_bytes)
    return {"status": "rebuilt", "entries": len(index["entries"]), "index": str(index_path.relative_to(root))}


def verify_checkpoint(root: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    observations: dict[str, Any] = {
        "repositoryRef": repository_ref(root),
        "branchRef": git(root, "symbolic-ref", "--quiet", "--short", "HEAD"),
        "headSha": git(root, "rev-parse", "HEAD"),
    }
    _, intent_digest, scope_digest, target_branch = intent_state(root, checkpoint["ticket"])
    observations.update({
        "intentSha256": intent_digest,
        "scopeSha256": scope_digest,
        "targetBranch": target_branch,
    })
    status_bytes = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    assert isinstance(status_bytes, bytes)
    observations["statusSha256"] = hashlib.sha256(status_bytes).hexdigest()
    expected = {
        "repositoryRef": checkpoint["repositoryRef"],
        "branchRef": checkpoint["branchRef"],
        "headSha": checkpoint["headSha"],
        "intentSha256": checkpoint["intentSha256"],
        "scopeSha256": checkpoint["scopeSha256"],
        "targetBranch": checkpoint["targetBranch"],
        "statusSha256": checkpoint["workspace"]["statusSha256"],
    }
    mismatches = {
        field: {"expected": expected[field], "observed": observations[field]}
        for field in expected if expected[field] != observations[field]
    }
    if mismatches:
        fail("GOV-CONTINUITY-003", "checkpoint diverges from current repository observation: " + ", ".join(mismatches))
    return {
        "status": "matches-observed-state",
        "checkpointRef": checkpoint["checkpointRef"],
        "authority": "advisory-projection",
        "authorityVerified": False,
        "leaseMustBeRevalidated": checkpoint["lease"] is not None,
        "remoteAccountMustBeReobserved": True,
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    checkpoint = validate_checkpoint(load_json(args.checkpoint)) if args.checkpoint else resolve(args)
    return verify_checkpoint(root, checkpoint)


def candidate_bytes(root: Path, relative: str, staged: bool) -> bytes | None:
    if not staged:
        try:
            return (root / relative).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            fail("GOV-CONTINUITY-001", f"cannot read local pin file {relative}: {exc}")
    value = git(root, "show", f":{relative}", binary=True, check=False)
    return value if isinstance(value, bytes) else None


def validate_adoption_pin(manifest, lock):
    pin = manifest["standardPin"]
    standard = lock.get("standard") if isinstance(lock, dict) else None
    if not isinstance(standard, dict):
        fail("GOV-CONTINUITY-001", "adoption lock has no standard pin")
    expected_fields = {"id", "version", "sourceRepository", "sourceRevision", "publicationStatus"}
    if set(standard) != expected_fields:
        fail("GOV-CONTINUITY-001", "adoption lock standard pin fields are invalid")
    if (
        standard["id"] != pin["requiredStandardId"]
        or standard["sourceRepository"] != "wellmanifest/new-project"
        or not isinstance(standard["version"], str)
        or VERSION_RE.fullmatch(standard["version"]) is None
        or not isinstance(standard["sourceRevision"], str)
        or SHA1_RE.fullmatch(standard["sourceRevision"]) is None
        or standard["publicationStatus"] not in {"published", "unpublished-test"}
    ):
        fail("GOV-CONTINUITY-001", "adoption lock standard pin is invalid")
    return standard


def verify_pin(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    manifest_relative = ".subactor/manifest.json"
    lock_relative = ".governance/manifest.lock.json"
    manifest_raw = candidate_bytes(root, manifest_relative, args.staged)
    lock_raw = candidate_bytes(root, lock_relative, args.staged)
    if manifest_raw is None and lock_raw is None:
        return {"status": "not-applicable", "networkAccess": False, "mutated": False}
    if manifest_raw is None or lock_raw is None:
        fail("GOV-CONTINUITY-001", "local standard pin requires both manifest and adoption lock")
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
        lock = json.loads(lock_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail("GOV-CONTINUITY-001", f"local standard pin is unreadable: {exc}")
    try:
        validate_manifest_value(manifest)
    except ContinuityError as exc:
        fail("GOV-CONTINUITY-001", f"local Subactor manifest drifted: {exc}")
    standard = validate_adoption_pin(manifest, lock)
    managed = lock.get("managedFiles")
    if not isinstance(managed, dict):
        fail("GOV-CONTINUITY-001", "adoption lock has no managed file map")
    if managed.get(manifest_relative) != hashlib.sha256(manifest_raw).hexdigest():
        fail("GOV-CONTINUITY-001", "tracked Subactor manifest does not match the local immutable pin")
    ignore_relative = ".subactor/.gitignore"
    ignore_raw = candidate_bytes(root, ignore_relative, args.staged)
    if ignore_raw is None or managed.get(ignore_relative) != hashlib.sha256(ignore_raw).hexdigest():
        fail("GOV-CONTINUITY-001", "managed Subactor ignore rules do not match the local immutable pin")
    return {
        "status": "locally-pinned",
        "standard": standard["id"],
        "version": standard["version"],
        "sourceRevision": standard["sourceRevision"],
        "networkAccess": False,
        "mutated": False,
    }


def add_capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--worktree-id", required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--plan-ref", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--slice-ref", required=True)
    parser.add_argument("--slice-sha256", required=True)
    parser.add_argument("--slice-ordinal", type=int, required=True)
    parser.add_argument("--slice-total", type=int, required=True)
    parser.add_argument("--remote-name", default="origin")
    parser.add_argument("--remote-account-ref", required=True)
    parser.add_argument("--remote-observation-receipt", required=True)
    parser.add_argument("--lease-ref")
    parser.add_argument("--lease-revision", type=int)
    parser.add_argument("--fencing-token", type=int)
    parser.add_argument("--snapshot-ref")
    parser.add_argument("--snapshot-sha256")
    parser.add_argument("--snapshot-receipt")
    parser.add_argument("--snapshot-secret-scan-receipt")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--remaining", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--pending", action="append", default=[])
    parser.add_argument("--next-action", choices=sorted(NEXT_ACTIONS), required=True)
    parser.add_argument("--next-criterion")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a v2 checkpoint, event or index")
    validate_parser.add_argument("document", type=Path)
    capture_parser = subparsers.add_parser("capture", help="append the current repository checkpoint event")
    add_capture_arguments(capture_parser)
    record_parser = subparsers.add_parser("record", help="append an externally restored checkpoint event")
    record_parser.add_argument("--root", type=Path, default=Path.cwd())
    record_parser.add_argument("--checkpoint", type=Path, required=True)
    record_parser.add_argument("--session-id", required=True)
    resolve_parser = subparsers.add_parser("resolve", help="resolve the latest checkpoint for a ticket")
    resolve_parser.add_argument("--root", type=Path, default=Path.cwd())
    resolve_parser.add_argument("--ticket", required=True)
    verify_parser = subparsers.add_parser("verify", help="compare a checkpoint with current observable state")
    verify_parser.add_argument("--root", type=Path, default=Path.cwd())
    source = verify_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--checkpoint", type=Path)
    source.add_argument("--ticket")
    rebuild_parser = subparsers.add_parser("rebuild-index", help="atomically rebuild the bounded index")
    rebuild_parser.add_argument("--root", type=Path, default=Path.cwd())
    pin_parser = subparsers.add_parser("verify-pin", help="validate only the local immutable standard pin")
    pin_parser.add_argument("--root", type=Path, default=Path.cwd())
    pin_parser.add_argument("--staged", action="store_true", help="read managed candidates from the Git index")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            document = validate_document(load_json(args.document))
            output: Any = {"status": "valid", "schema": document["schema"]}
        elif args.command == "capture":
            output = capture(args)
        elif args.command == "record":
            output = record(args)
        elif args.command == "resolve":
            output = resolve(args)
        elif args.command == "verify":
            output = verify(args)
        elif args.command == "rebuild-index":
            output = rebuild_index(args)
        else:
            output = verify_pin(args)
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except ContinuityError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 3 if exc.code == "GOV-CONTINUITY-003" else 2


if __name__ == "__main__":
    raise SystemExit(main())
