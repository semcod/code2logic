"""Explicit isolated advisory stores; never repository aliases or authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile

SCHEMA = "new-project.continuity-namespace/v1"
MAX_BYTES = 16384
FIELDS = {"schema", "authority", "repositoryRef", "legacyRepositoryRef",
          "legacyEventSha256", "legacyEventCount", "recordedAt"}


def locations(root, repository):
    key = hashlib.sha256(repository.encode("utf-8")).hexdigest()
    return (root / ".subactor/recovery/continuity-namespaces" / (key + ".json"),
            root / ".subactor/sessions/continuity-namespaces" / key / "events.jsonl",
            root / ".subactor/recovery/continuity-namespaces" / key / "checkpoint-index.json")


def read_selector(path, repository, api):
    try:
        with api._stream_descriptor(path, False) as descriptor:
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_BYTES:
        api.fail("GOV-CONTINUITY-001", "continuity namespace selector is too large")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate namespace field")
            value[key] = item
        return value

    try:
        value = api.exact_object(json.loads(raw.decode("utf-8"), object_pairs_hook=unique),
                                 FIELDS, "continuity namespace selector")
    except (ValueError, UnicodeError) as error:
        raise api.ContinuityError("GOV-CONTINUITY-001", "invalid continuity namespace selector") from error
    if (value["schema"] != SCHEMA or value["authority"] != "advisory-projection"
            or value["repositoryRef"] != repository
            or value["legacyRepositoryRef"] == repository
            or type(value["legacyEventCount"]) is not int or value["legacyEventCount"] < 1):
        api.fail("GOV-CONTINUITY-002", "continuity namespace selector binding differs")
    api.validate_repository(value["legacyRepositoryRef"], "legacy repository")
    api.sha(value["legacyEventSha256"], "legacy stream digest", api.SHA256_RE)
    api.timestamp(value["recordedAt"], "namespace timestamp")
    return value


def select(root, repository, legacy, api):
    marker, events, index = locations(root, repository)
    if read_selector(marker, repository, api) is None:
        return legacy
    return events, index, legacy[2], legacy[3]


def stream_digest(path, api):
    digest = hashlib.sha256()
    with api._stream_descriptor(path, False) as descriptor:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
    return digest.hexdigest()


def legacy_observation(path, repository, expected_digest, api):
    try:
        before = stream_digest(path, api)
        if before != expected_digest:
            api.fail("GOV-CONTINUITY-002", "legacy stream digest changed")
        events, _ = api.event_state(api.iter_events(path), repository)
        if not events or stream_digest(path, api) != before:
            api.fail("GOV-CONTINUITY-002", "legacy stream is empty or changed during observation")
    except FileNotFoundError as error:
        raise api.ContinuityError("GOV-CONTINUITY-002", "expected legacy journal is unavailable") from error
    return len(events)


def require_unoccupied(paths, api):
    for path in paths:
        try:
            with api._stream_descriptor(path, False):
                api.fail("GOV-CONTINUITY-002", "new namespace already contains unselected storage")
        except FileNotFoundError:
            pass


def publish_selector(path, value, api):
    """Reuse anchored storage and serialization, with no-clobber publication.

    The index writer replaces an owned cache. This immutable selector instead
    links an exclusively created private file, preserving any concurrent file.
    """
    payload = api.index_payload(value, MAX_BYTES)
    with api._parent_directory(path, True) as (directory, verify):
        temporary = "namespace." + secrets.token_hex(16) + ".pending"
        if os.name == "posix":
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            remove = lambda: os.unlink(temporary, dir_fd=directory)
        else:
            descriptor, temporary = tempfile.mkstemp(prefix="namespace.", dir=path.parent)
            remove = lambda: os.unlink(temporary)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            verify()
            if os.name == "posix":
                os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
            else:
                os.link(temporary, path)
            verify()
        finally:
            remove()
        if os.name == "posix":
            try:
                os.fsync(directory)
            except OSError:
                pass  # Same directory-fsync portability boundary as index writes.


def initialize(args, api):
    root = args.root.resolve()
    repository = api.repository_ref(root)
    old_repository = api.validate_repository(args.expected_legacy_repository, "legacy repository")
    api.sha(args.expected_legacy_sha256, "legacy stream digest", api.SHA256_RE)
    if old_repository == repository:
        api.fail("GOV-CONTINUITY-002", "legacy repository already matches; preserve its existing chain")
    settings = api.load_local_manifest(root)["continuity"]
    legacy = root / settings["eventStreamPath"]
    legacy_index = root / settings["checkpointIndexPath"]
    marker, events, index = locations(root, repository)

    def result(status):
        return {"status": status, "repositoryRef": repository, "grantsAuthority": False,
                "legacyModified": False, "legacyRepositoryRef": old_repository,
                "legacyEventSha256": args.expected_legacy_sha256,
                "selectorPath": marker.relative_to(root).as_posix(),
                "eventStreamPath": events.relative_to(root).as_posix(),
                "checkpointIndexPath": index.relative_to(root).as_posix()}

    def inspect():
        if api.repository_ref(root) != repository:
            api.fail("GOV-CONTINUITY-002", "repository changed during namespace initialization")
        existing = read_selector(marker, repository, api)
        if existing is not None:
            if (existing["legacyRepositoryRef"] != old_repository
                    or existing["legacyEventSha256"] != args.expected_legacy_sha256):
                api.fail("GOV-CONTINUITY-002", "namespace initialization request differs")
            return None
        count = legacy_observation(legacy, old_repository, args.expected_legacy_sha256, api)
        require_unoccupied((events, index), api)
        return {"schema": SCHEMA, "authority": "advisory-projection", "repositoryRef": repository,
                "legacyRepositoryRef": old_repository, "legacyEventSha256": args.expected_legacy_sha256,
                "legacyEventCount": count, "recordedAt": api.utc_now()}

    if not args.apply:
        return result("already-enabled" if inspect() is None else "planned")
    with api.storage_transaction(legacy, legacy_index, marker, events, index):
        value = inspect()
        if value is None:
            return result("already-enabled")
        publish_selector(marker, value, api)
    return result("enabled")
