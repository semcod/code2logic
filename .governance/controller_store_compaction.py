#!/usr/bin/env python3
"""Bounded retention and archive-preserving compaction for external controller lease stores.

Plan mode is strictly read-only and grants no writer, takeover, or publication
authority. Apply mode requires an explicit operator actor and exact SHA-256 CAS
on state.json, acquires the store's exclusive flock (.lock), writes pruned
historical records to an append-only private archive before replacing state.json,
and preserves nextFencingToken monotonicity, active ownership, non-terminal/expired
leases, expiry previousReceiptRef receipts, and recent idempotency keys.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

sys.dont_write_bytecode = True

STORE_SCHEMA = "subactor.repository-change-lease-store/v1"
REPORT_SCHEMA = "new-project.controller-store-compaction-report/v1"
ARCHIVE_SCHEMA = "new-project.controller-store-compaction-archive/v1"
CODE = "GOV-CHANGE-LEASE-002"
ALLOWED_TOP_KEYS = {
    "schema", "nextFencingToken", "leases", "active",
    "acquisitions", "requests", "evidence", "identities",
}
REQUIRED_TOP_KEYS = {"schema", "leases", "active"}
ALL_PHASES = {
    "claimed", "editing", "validating", "publication_frozen", "dispatching",
    "approved", "merged", "closed", "cancelled", "expired", "released",
}
PRUNABLE_TERMINAL_PHASES = {"closed", "cancelled", "released"}
MIN_RETENTION_SECONDS = 3600
DEFAULT_RETENTION_SECONDS = 7 * 86400
MAX_STORE_BYTES = 128 * 1024 * 1024
CHUNK_BYTES = 65536
ACTOR_RE = re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CompactionError(ValueError):
    """Fixed safe diagnostic code without leaking secret session tokens."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompactionError(message)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _parse_iso(value) -> datetime:
    require(isinstance(value, str) and bool(value), "invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError as error:
        raise CompactionError("invalid_timestamp") from error
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "invalid_timestamp")
    return parsed.astimezone(timezone.utc)


def _encode(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _verify_external_store(root: Path, store: Path) -> None:
    root = Path(os.path.abspath(root))
    require(all(not p.is_symlink() for p in (root, *root.parents)), "symlinked_repository_root")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    common = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    wt = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain", "-z"],
        env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    require(top.returncode == 0 and common.returncode == 0 and wt.returncode == 0,
            "repository_observation_unavailable")
    common_path = Path(os.path.abspath(common.stdout.strip()))
    require(not store.is_relative_to(common_path), "store_inside_git_metadata")
    for token in wt.stdout.split("\0"):
        if token.startswith("worktree "):
            checkout = Path(os.path.abspath(token.split(" ", 1)[1]))
            require(not store.is_relative_to(checkout), "store_inside_candidate_checkout")


@contextmanager
def _anchored_directory(path: Path):
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "posix_controller_required")
    resolved = Path(os.path.abspath(path))
    require(".." not in resolved.parts, "unsafe_store_path")
    require(all(not p.is_symlink() for p in (resolved, *resolved.parents)), "symlinked_store_path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors = [os.open(resolved.anchor, flags)]
    try:
        for part in resolved.parts[1:]:
            descriptors.append(os.open(part, flags, dir_fd=descriptors[-1]))
        store_info = os.fstat(descriptors[-1])
        require(store_info.st_uid == os.geteuid(), "store_owner_mismatch")

        def verify() -> None:
            for parent_fd, child_fd, part in zip(descriptors, descriptors[1:], resolved.parts[1:]):
                named = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                held = os.fstat(child_fd)
                require(
                    stat.S_ISDIR(named.st_mode)
                    and (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino),
                    "store_directory_identity_changed",
                )

        verify()
        yield resolved, descriptors[-1], verify
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _read_state_at(store_fd: int) -> tuple[dict, str, int]:
    try:
        fd = os.open("state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=store_fd)
    except FileNotFoundError as error:
        raise CompactionError("controller_state_missing") from error
    chunks = []
    total = 0
    hasher = hashlib.sha256()
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "controller_state_not_regular")
        require(info.st_uid == os.geteuid(), "controller_state_owner_mismatch")
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            require(total <= MAX_STORE_BYTES, "controller_state_exceeds_bound")
            hasher.update(chunk)
            chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompactionError("controller_state_invalid_json") from error
    require(isinstance(decoded, dict), "controller_state_invalid_root")
    return decoded, hasher.hexdigest(), total


@contextmanager
def _exclusive_store_lock(store_fd: int, verify):
    import fcntl

    fd = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=store_fd)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid(),
                "unsafe_controller_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CompactionError("controller_lock_busy") from error
        verify()
        named = os.stat(".lock", dir_fd=store_fd, follow_symlinks=False)
        require(
            stat.S_ISREG(named.st_mode)
            and named.st_nlink == 1
            and (named.st_dev, named.st_ino) == (info.st_dev, info.st_ino),
            "controller_lock_identity_changed",
        )
        yield
    finally:
        os.close(fd)


def _lease_timestamp(lease: dict) -> datetime:
    stamps = []
    for key in ("heartbeatAt", "expiresAt", "issuedAt"):
        if lease.get(key) is not None:
            stamps.append(_parse_iso(lease[key]))
    require(bool(stamps), "lease_timestamp_missing")
    return max(stamps)


def _compute_compaction(
    state: dict,
    *,
    cutoff: datetime,
    min_recent_leases: int,
    min_recent_acquisitions: int,
    min_recent_requests: int,
) -> tuple[dict, dict]:
    require(state.get("schema") == STORE_SCHEMA, "unsupported_controller_schema")
    require(REQUIRED_TOP_KEYS.issubset(state) and set(state).issubset(ALLOWED_TOP_KEYS),
            "invalid_controller_top_level_keys")
    leases = state["leases"]
    active = state["active"]
    require(isinstance(leases, dict) and isinstance(active, dict), "invalid_controller_maps")

    active_lease_ids = set()
    for res_key, holder_id in active.items():
        require(isinstance(res_key, str) and bool(res_key), "invalid_active_resource")
        if holder_id is not None:
            require(isinstance(holder_id, str) and holder_id in leases, "dangling_active_lease")
            active_lease_ids.add(holder_id)

    max_token = 0
    lease_times: dict[str, datetime] = {}
    terminal_candidates: list[tuple[datetime, str]] = []
    retained_lease_ids: set[str] = set()

    for lid, lease in leases.items():
        require(isinstance(lid, str) and isinstance(lease, dict), "invalid_lease_entry")
        require(lease.get("leaseId") in (None, lid), "lease_id_key_mismatch")
        phase = lease.get("phase")
        require(isinstance(phase, str) and phase in ALL_PHASES, "invalid_lease_phase")
        token = lease.get("fencingToken")
        if token is not None:
            require(type(token) is int and token >= 1, "invalid_fencing_token")
            if token > max_token:
                max_token = token
        stamp = _lease_timestamp(lease)
        lease_times[lid] = stamp
        if lid in active_lease_ids or phase not in PRUNABLE_TERMINAL_PHASES:
            retained_lease_ids.add(lid)
        else:
            terminal_candidates.append((stamp, lid))

    if "nextFencingToken" in state:
        next_token = state["nextFencingToken"]
        require(type(next_token) is int and next_token >= max(1, max_token),
                "non_monotonic_next_fencing_token")

    terminal_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for index, (stamp, lid) in enumerate(terminal_candidates):
        if index < min_recent_leases or stamp >= cutoff:
            retained_lease_ids.add(lid)

    retained_leases = {lid: leases[lid] for lid in leases if lid in retained_lease_ids}
    pruned_leases = {lid: leases[lid] for lid in leases if lid not in retained_lease_ids}

    compacted: dict = {"schema": STORE_SCHEMA}
    if "nextFencingToken" in state:
        compacted["nextFencingToken"] = state["nextFencingToken"]
    compacted["leases"] = retained_leases
    compacted["active"] = dict(active)

    pruned: dict = {
        "leases": pruned_leases,
        "identities": {},
        "acquisitions": {},
        "requests": {},
        "evidence": {},
    }

    if "identities" in state:
        identities = state["identities"]
        require(isinstance(identities, dict), "invalid_identities_map")
        compacted["identities"] = {
            lid: val for lid, val in identities.items() if lid in retained_lease_ids
        }
        pruned["identities"] = {
            lid: val for lid, val in identities.items() if lid not in retained_lease_ids
        }

    if "acquisitions" in state:
        acquisitions = state["acquisitions"]
        require(isinstance(acquisitions, dict), "invalid_acquisitions_map")
        acq_candidates: list[tuple[datetime, str]] = []
        retained_acq_keys: set[str] = set()
        epoch = datetime.fromtimestamp(0, tz=timezone.utc)
        for req_key, entry in acquisitions.items():
            require(isinstance(req_key, str) and isinstance(entry, dict), "invalid_acquisition_entry")
            lid = entry.get("leaseId")
            require(isinstance(lid, str) and bool(lid), "invalid_acquisition_lease_ref")
            if lid in retained_lease_ids:
                retained_acq_keys.add(req_key)
            else:
                acq_candidates.append((lease_times.get(lid, epoch), req_key))
        acq_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for index, (stamp, req_key) in enumerate(acq_candidates):
            if index < min_recent_acquisitions or stamp >= cutoff:
                retained_acq_keys.add(req_key)
        compacted["acquisitions"] = {
            k: v for k, v in acquisitions.items() if k in retained_acq_keys
        }
        pruned["acquisitions"] = {
            k: v for k, v in acquisitions.items() if k not in retained_acq_keys
        }

    referenced_prev_receipts = {
        lease["previousReceiptRef"]
        for lease in retained_leases.values()
        if isinstance(lease.get("previousReceiptRef"), str) and lease["previousReceiptRef"]
    }

    if "requests" in state:
        requests = state["requests"]
        require(isinstance(requests, dict), "invalid_requests_map")
        req_candidates: list[tuple[datetime, str]] = []
        retained_req_keys: set[str] = set()
        for idem_key, receipt in requests.items():
            require(isinstance(idem_key, str) and isinstance(receipt, dict), "invalid_request_receipt")
            occurred = _parse_iso(receipt["occurredAt"]) if "occurredAt" in receipt else cutoff
            if (receipt.get("leaseId") in retained_lease_ids
                    or receipt.get("receiptRef") in referenced_prev_receipts
                    or occurred >= cutoff):
                retained_req_keys.add(idem_key)
            else:
                req_candidates.append((occurred, idem_key))
        req_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for index, (_stamp, idem_key) in enumerate(req_candidates):
            if index < min_recent_requests:
                retained_req_keys.add(idem_key)
        compacted["requests"] = {
            k: v for k, v in requests.items() if k in retained_req_keys
        }
        pruned["requests"] = {
            k: v for k, v in requests.items() if k not in retained_req_keys
        }

    if "evidence" in state:
        evidence = state["evidence"]
        require(isinstance(evidence, dict), "invalid_evidence_map")
        retained_ev_keys: set[str] = set()
        for ev_key, item in evidence.items():
            require(isinstance(ev_key, str) and isinstance(item, dict), "invalid_evidence_entry")
            recorded = _parse_iso(item["recordedAt"]) if "recordedAt" in item else cutoff
            if item.get("leaseId") in retained_lease_ids or recorded >= cutoff:
                retained_ev_keys.add(ev_key)
        compacted["evidence"] = {
            k: v for k, v in evidence.items() if k in retained_ev_keys
        }
        pruned["evidence"] = {
            k: v for k, v in evidence.items() if k not in retained_ev_keys
        }

    return compacted, pruned


def _write_archive(store_fd: int, archive_name: str, archive_bytes: bytes) -> str:
    try:
        os.mkdir("archive", 0o700, dir_fd=store_fd)
    except FileExistsError:
        pass
    archive_dir_fd = os.open("archive", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=store_fd)
    try:
        dir_info = os.fstat(archive_dir_fd)
        require(dir_info.st_uid == os.geteuid(), "archive_owner_mismatch")
        temp_name = f".archive-{secrets.token_hex(12)}.tmp"
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=archive_dir_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(archive_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_name, archive_name, src_dir_fd=archive_dir_fd, dst_dir_fd=archive_dir_fd,
                        follow_symlinks=False)
            except FileExistsError:
                existing_fd = os.open(archive_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                      dir_fd=archive_dir_fd)
                existing_hasher = hashlib.sha256()
                existing_total = 0
                with os.fdopen(existing_fd, "rb") as existing_stream:
                    require(stat.S_ISREG(os.fstat(existing_stream.fileno()).st_mode),
                            "archive_not_regular")
                    while True:
                        chunk = existing_stream.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        existing_total += len(chunk)
                        require(existing_total <= MAX_STORE_BYTES, "archive_exceeds_bound")
                        existing_hasher.update(chunk)
                require(existing_hasher.hexdigest() == hashlib.sha256(archive_bytes).hexdigest(),
                        "archive_collision_mismatch")
            finally:
                try:
                    os.unlink(temp_name, dir_fd=archive_dir_fd)
                except FileNotFoundError:
                    pass
            os.fsync(archive_dir_fd)
        except Exception:
            try:
                os.unlink(temp_name, dir_fd=archive_dir_fd)
            except FileNotFoundError:
                pass
            raise
    finally:
        os.close(archive_dir_fd)
    os.fsync(store_fd)
    return f"archive/{archive_name}"


def _atomic_replace_state(store_fd: int, raw: bytes) -> None:
    temp_name = f".state-compact-{secrets.token_hex(12)}.tmp"
    fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=store_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, "state.json", src_dir_fd=store_fd, dst_dir_fd=store_fd)
        os.fsync(store_fd)
    except Exception:
        try:
            os.unlink(temp_name, dir_fd=store_fd)
        except FileNotFoundError:
            pass
        raise


def compact_store(
    store: Path,
    *,
    apply: bool = False,
    operator_actor: str | None = None,
    expected_state_sha256: str | None = None,
    retention_seconds: int = DEFAULT_RETENTION_SECONDS,
    min_recent_leases: int = 64,
    min_recent_acquisitions: int = 256,
    min_recent_requests: int = 512,
    now: datetime | None = None,
    root: Path | None = None,
) -> dict:
    require(type(retention_seconds) is int and retention_seconds >= MIN_RETENTION_SECONDS,
            "retention_below_minimum")
    for count in (min_recent_leases, min_recent_acquisitions, min_recent_requests):
        require(type(count) is int and count >= 0, "invalid_minimum_retention_count")
    if expected_state_sha256 is not None:
        require(isinstance(expected_state_sha256, str) and bool(SHA256_RE.fullmatch(expected_state_sha256)),
                "invalid_expected_state_sha256")
    if apply:
        require(expected_state_sha256 is not None, "apply_requires_expected_state_sha256")
        require(isinstance(operator_actor, str) and bool(ACTOR_RE.fullmatch(operator_actor)),
                "apply_requires_operator_actor")
    elif operator_actor is not None:
        require(isinstance(operator_actor, str) and bool(ACTOR_RE.fullmatch(operator_actor)),
                "invalid_operator_actor")

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current_time - timedelta(seconds=retention_seconds)

    with _anchored_directory(Path(store)) as (resolved_store, store_fd, verify):
        if root is not None:
            _verify_external_store(Path(root), resolved_store)
        if not apply:
            state, pre_sha, pre_bytes = _read_state_at(store_fd)
            verify()
            if expected_state_sha256 is not None:
                require(pre_sha == expected_state_sha256, "controller_state_cas_mismatch")
            compacted, pruned = _compute_compaction(
                state,
                cutoff=cutoff,
                min_recent_leases=min_recent_leases,
                min_recent_acquisitions=min_recent_acquisitions,
                min_recent_requests=min_recent_requests,
            )
            pruned_total = sum(len(items) for items in pruned.values())
            post_raw = _encode(compacted) if pruned_total else None
            post_sha = hashlib.sha256(post_raw).hexdigest() if post_raw is not None else pre_sha
            post_bytes = len(post_raw) if post_raw is not None else pre_bytes
            return {
                "schema": REPORT_SCHEMA,
                "mode": "plan",
                "applied": False,
                "grantsAuthority": False,
                "store": str(resolved_store),
                "preStateSha256": pre_sha,
                "postStateSha256": post_sha,
                "preBytes": pre_bytes,
                "postBytes": post_bytes,
                "nextFencingToken": compacted.get("nextFencingToken"),
                "activeResourceCount": len(compacted["active"]),
                "retainedCounts": {
                    "leases": len(compacted["leases"]),
                    "identities": len(compacted.get("identities", {})),
                    "acquisitions": len(compacted.get("acquisitions", {})),
                    "requests": len(compacted.get("requests", {})),
                    "evidence": len(compacted.get("evidence", {})),
                },
                "prunedCounts": {key: len(val) for key, val in pruned.items()},
                "archiveRelPath": None,
                "archiveSha256": None,
            }

        with _exclusive_store_lock(store_fd, verify):
            state, pre_sha, pre_bytes = _read_state_at(store_fd)
            verify()
            require(pre_sha == expected_state_sha256, "controller_state_cas_mismatch")
            compacted, pruned = _compute_compaction(
                state,
                cutoff=cutoff,
                min_recent_leases=min_recent_leases,
                min_recent_acquisitions=min_recent_acquisitions,
                min_recent_requests=min_recent_requests,
            )
            pruned_total = sum(len(items) for items in pruned.values())
            archive_rel = None
            archive_sha = None
            if pruned_total > 0:
                post_raw = _encode(compacted)
                post_sha = hashlib.sha256(post_raw).hexdigest()
                post_bytes = len(post_raw)
                archive_payload = {
                    "schema": ARCHIVE_SCHEMA,
                    "compactedAt": current_time.isoformat(),
                    "operatorActor": operator_actor,
                    "retentionSeconds": retention_seconds,
                    "preStateSha256": pre_sha,
                    "postStateSha256": post_sha,
                    "nextFencingToken": compacted.get("nextFencingToken"),
                    "pruned": pruned,
                }
                archive_bytes = _encode(archive_payload)
                archive_sha = hashlib.sha256(archive_bytes).hexdigest()
                archive_name = f"compaction-{archive_sha}.json"
                archive_rel = _write_archive(store_fd, archive_name, archive_bytes)
                verify()
                _atomic_replace_state(store_fd, post_raw)
            else:
                post_sha = pre_sha
                post_bytes = pre_bytes

            return {
                "schema": REPORT_SCHEMA,
                "mode": "apply",
                "applied": pruned_total > 0,
                "grantsAuthority": False,
                "operatorActor": operator_actor,
                "store": str(resolved_store),
                "preStateSha256": pre_sha,
                "postStateSha256": post_sha,
                "preBytes": pre_bytes,
                "postBytes": post_bytes,
                "nextFencingToken": compacted.get("nextFencingToken"),
                "activeResourceCount": len(compacted["active"]),
                "retainedCounts": {
                    "leases": len(compacted["leases"]),
                    "identities": len(compacted.get("identities", {})),
                    "acquisitions": len(compacted.get("acquisitions", {})),
                    "requests": len(compacted.get("requests", {})),
                    "evidence": len(compacted.get("evidence", {})),
                },
                "prunedCounts": {key: len(val) for key, val in pruned.items()},
                "archiveRelPath": archive_rel,
                "archiveSha256": archive_sha,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True,
                        help="External controller lease store directory containing state.json")
    parser.add_argument("--root", type=Path,
                        help="Optional repository root to verify store resides outside candidate checkouts")
    parser.add_argument("--retention-seconds", type=int, default=DEFAULT_RETENTION_SECONDS,
                        help="Minimum age in seconds before terminal closed/cancelled/released entries can be archived")
    parser.add_argument("--min-recent-leases", type=int, default=64)
    parser.add_argument("--min-recent-acquisitions", type=int, default=256)
    parser.add_argument("--min-recent-requests", type=int, default=512)
    parser.add_argument("--expected-state-sha256", metavar="SHA256",
                        help="Exact SHA-256 of state.json (required with --apply)")
    parser.add_argument("--operator-actor", metavar="ACTOR",
                        help="Explicit operator/controller actor identity (required with --apply)")
    parser.add_argument("--apply", action="store_true",
                        help="Acquire .lock, write content-addressed archive, and atomically replace state.json")
    args = parser.parse_args(argv)
    try:
        report = compact_store(
            args.store,
            apply=args.apply,
            operator_actor=args.operator_actor,
            expected_state_sha256=args.expected_state_sha256,
            retention_seconds=args.retention_seconds,
            min_recent_leases=args.min_recent_leases,
            min_recent_acquisitions=args.min_recent_acquisitions,
            min_recent_requests=args.min_recent_requests,
            root=args.root,
        )
    except (CompactionError, OSError, subprocess.SubprocessError) as error:
        reason = error.args[0] if isinstance(error, CompactionError) and error.args else "controller_compaction_failed"
        print(json.dumps({
            "schema": REPORT_SCHEMA,
            "mode": "apply" if args.apply else "plan",
            "applied": False,
            "grantsAuthority": False,
            "diagnostic": CODE,
            "reason": reason,
        }, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
