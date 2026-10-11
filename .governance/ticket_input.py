#!/usr/bin/env python3
"""Read Registry ticket content without creating repository carrier files.

Local SQLite is advisory input. Protected callers must provide an independently
acquired snapshot and digest, bound to the exact repository/base/head.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

MAX_BYTES = 32 * 1024 * 1024
APPLICATION_ID = 1398030897
SCHEMA = "new-project.ticket-input/v1"


class TicketInputError(ValueError):
    pass


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    return subprocess.check_output(["git", "-C", str(root), *args], env=env, stderr=subprocess.PIPE)


def no_links(path):
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise TicketInputError("ticket input symlink rejected")
        if candidate.is_file() and candidate.stat().st_nlink != 1:
            raise TicketInputError("ticket input hardlink rejected")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TicketInputError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_object)


def validate_document_contract(doc, ticket):
    if (not isinstance(doc, dict) or set(doc) != {"schema", "ticket", "files", "execution_authorized", "merge_authorized"}
            or doc["schema"] != "registry.ticket-content/v1" or doc["ticket"] != ticket
            or doc["execution_authorized"] is not False or doc["merge_authorized"] is not False
            or not isinstance(doc["files"], dict)):
        raise TicketInputError("invalid ticket content contract")


def validate_ticket_path(name):
    if (not isinstance(name, str) or not name or len(name) > 1024 or "\\" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or re.search(r"[\x00-\x1f\x7f]", name)):
        raise TicketInputError("invalid ticket file path")


def decode_ticket_file(name, entry):
    validate_ticket_path(name)
    if (not isinstance(entry, dict) or set(entry) != {"encoding", "mode", "sha256", "content"}
            or entry["encoding"] != "base64" or entry["mode"] not in {"100644", "100755"}
            or not isinstance(entry["content"], str)):
        raise TicketInputError("invalid ticket file record")
    content = base64.b64decode(entry["content"], validate=True)
    if (base64.b64encode(content).decode("ascii") != entry["content"]
            or hashlib.sha256(content).hexdigest() != entry["sha256"]):
        raise TicketInputError("ticket file digest mismatch")
    return content, entry["mode"]


def decode_document(ticket, revision, sha, raw):
    if not isinstance(ticket, str) or re.fullmatch(r"ticket-[0-9]{3,}", ticket) is None:
        raise TicketInputError("unsupported ticket identity")
    if type(revision) is not int or revision < 1 or not isinstance(raw, str):
        raise TicketInputError("invalid ticket revision")
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != sha:
        raise TicketInputError("ticket document digest mismatch")
    doc = parse_json(raw)
    validate_document_contract(doc, ticket)
    files = {name: decode_ticket_file(name, entry) for name, entry in doc["files"].items()}
    return {"ticket": ticket, "revision": revision, "files": files}


def primary_database(root):
    records = git(root, "worktree", "list", "--porcelain", "-z").decode().split("\0")
    if not records[0].startswith("worktree ") or "bare" in records:
        raise TicketInputError("registered primary checkout required")
    database = Path(records[0][9:]) / "project.sqlite"
    no_links(database)
    return database


def configured_mode(root):
    try:
        mode = git(root, "config", "--local", "--get", "new-project.ticketStorage").decode().strip()
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
        mode = "files"
    if mode not in {"files", "sqlite"}:
        raise TicketInputError("unknown configured ticket storage")
    return mode


def configured_records(root):
    if configured_mode(root) == "files":
        return None
    return [decode_document(*row) for row in database_rows(root, primary_database(root))]


def read_file(root, ticket, filename):
    for item in database_rows(root, primary_database(root)):
        if item[0] == ticket:
            files = decode_document(*item)["files"]
            if filename in files:
                return files[filename][0]
    raise TicketInputError("ticket content not found")


def database_rows(root, database):
    database = Path(database).absolute()
    no_links(database)
    primary = primary_database(root).parent
    if database != primary / "project.sqlite":
        raise TicketInputError("database must be primary checkout project.sqlite")
    names = ["project.sqlite" + suffix for suffix in ("", "-wal", "-shm", "-journal")]
    for name in names:
        no_links(primary / name)
    for checkout in {Path(root).absolute(), primary}:
        if git(checkout, "ls-files", "-z", "--", *names):
            raise TicketInputError("ticket database is tracked")
        ignored = git(checkout, "check-ignore", "--", *names).decode().splitlines()
        if set(ignored) != set(names):
            raise TicketInputError("ticket database and sidecars must be ignored")
    if not database.is_file() or database.stat().st_mode & 0o077:
        raise TicketInputError("private initialized database required")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if (connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1):
            raise TicketInputError("unsupported Registry database schema")
        rows, total = [], 0
        for row in connection.execute("""SELECT ticket, revision, document_sha256, document_json
            FROM ticket_versions AS t WHERE revision=(SELECT MAX(revision)
            FROM ticket_versions WHERE ticket=t.ticket) ORDER BY ticket"""):
            total += len(row[3].encode("utf-8"))
            if total > MAX_BYTES or len(rows) >= 10000:
                raise TicketInputError("ticket input exceeds bound")
            decode_document(*row)
            rows.append(row)
        return rows
    finally:
        connection.close()


def subject(root, repository, base, head):
    if not isinstance(repository, str) or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise TicketInputError("explicit repository identity required")
    if not base:
        raise TicketInputError("explicit validation base required")
    resolved = [git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
                for ref in (base, head)]
    return {"repository": repository, "base_sha": resolved[0], "head_sha": resolved[1]}


def export_snapshot(root, database, repository, base, head):
    binding = subject(root, repository, base, head)
    return {"schema": SCHEMA, **binding, "tickets": [
        {"ticket": row[0], "revision": row[1], "document_sha256": row[2], "document_json": row[3]}
        for row in database_rows(root, database)], "execution_authorized": False, "merge_authorized": False}


def read_pinned_snapshot(snapshot, snapshot_sha256):
    if not isinstance(snapshot_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", snapshot_sha256) is None:
        raise TicketInputError("independent snapshot SHA-256 required")
    path = Path(snapshot).absolute()
    no_links(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise TicketInputError("bounded snapshot file required")
    try:
        git(path.parent, "rev-parse", "--absolute-git-dir")
    except subprocess.CalledProcessError as error:
        if error.returncode != 128 or b"not a git repository" not in error.stderr:
            raise
    else:
        raise TicketInputError("snapshot must be outside Git checkouts")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != snapshot_sha256:
        raise TicketInputError("snapshot digest mismatch")
    return raw


def decode_snapshot(doc, binding):
    if (not isinstance(doc, dict) or set(doc) != {"schema", *binding, "tickets", "execution_authorized", "merge_authorized"}
            or doc["schema"] != SCHEMA or any(doc[key] != value for key, value in binding.items())
            or doc["execution_authorized"] is not False or doc["merge_authorized"] is not False
            or not isinstance(doc["tickets"], list) or len(doc["tickets"]) > 10000):
        raise TicketInputError("snapshot subject or contract mismatch")
    result, identities = [], set()
    for item in doc["tickets"]:
        if not isinstance(item, dict) or set(item) != {"ticket", "revision", "document_sha256", "document_json"}:
            raise TicketInputError("invalid snapshot ticket entry")
        decoded = decode_document(item["ticket"], item["revision"], item["document_sha256"], item["document_json"])
        if decoded["ticket"] in identities:
            raise TicketInputError("duplicate snapshot ticket")
        identities.add(decoded["ticket"])
        result.append(decoded)
    return result


def load_input(root, *, database=None, snapshot=None, snapshot_sha256=None,
               repository=None, base=None, head="HEAD", protected=False):
    if database and (snapshot or snapshot_sha256):
        raise TicketInputError("select exactly one ticket input")
    if database:
        if protected:
            raise TicketInputError("protected validation requires an independently pinned snapshot")
        return [decode_document(*row) for row in database_rows(root, database)]
    if not snapshot:
        if snapshot_sha256:
            raise TicketInputError("snapshot path required")
        return None
    raw = read_pinned_snapshot(snapshot, snapshot_sha256)
    doc = parse_json(raw)
    binding = subject(root, repository, base, head)
    return decode_snapshot(doc, binding)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export", "read"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database")
    parser.add_argument("--repository")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--ticket")
    parser.add_argument("--file", choices=["README.md", "intent.json"])
    args = parser.parse_args()
    try:
        if args.command == "read":
            sys.stdout.buffer.write(read_file(args.root, args.ticket, args.file))
        else:
            print(json.dumps(export_snapshot(args.root, args.database or primary_database(args.root), args.repository, args.base, args.head), sort_keys=True))
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError):
        parser.exit(1, "ticket input operation failed; no content emitted\n")
