#!/usr/bin/env python3
"""Bridge managed ID reservation to a digest-pinned local Registry writer."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

from ticket_input import database_rows, no_links, primary_database, read_file

# Versioned Registry ticket CLI integration: these are its complete relative
# module dependencies. A source update needs a newly acquired independent pin.
RUNTIME_FILES = ("storage-common.mjs", "ticket-store-cli.mjs", "ticket-store.mjs")
MAX_MODULE_BYTES = 1024 * 1024

# Sources travel through a bounded stdin frame, never an executable path or an
# argv-sized source string. Read exactly the frame so the writer retains its
# original stdin. The loader uses original URLs for ESM/argv identity while
# serving only bytes from the verified closure. Node builtins remain available
# to the independently trusted writer; this is integrity binding, not a sandbox.
CAPTURED_LOADER = r"""
import {isBuiltin} from 'node:module';
let sources;
export function initialize(data) { sources = data.sources; }
export async function resolve(specifier, context, nextResolve) {
  if (isBuiltin(specifier)) return nextResolve(specifier, context);
  const url = new URL(specifier, context.parentURL).href;
  if (!Object.hasOwn(sources, url)) throw Error('Unpinned Registry module');
  return {url, shortCircuit: true};
}
export async function load(url, context, nextLoad) {
  if (url.startsWith('node:')) return nextLoad(url, context);
  if (!Object.hasOwn(sources, url)) throw Error('Unpinned Registry module');
  return {format: 'module', source: sources[url], shortCircuit: true};
}
"""
CAPTURED_BOOTSTRAP = r"""
import {readSync} from 'node:fs';
import {register} from 'node:module';
import {pathToFileURL} from 'node:url';
function exact(size) {
  const bytes = Buffer.alloc(size);
  for (let offset = 0; offset < size;) {
    const count = readSync(0, bytes, offset, size - offset, null);
    if (!count) throw Error('Incomplete Registry frame');
    offset += count;
  }
  return bytes;
}
const size = exact(4).readUInt32BE(0);
if (!size || size > 24 * 1024 * 1024) throw Error('Unbounded Registry frame');
const payload = JSON.parse(exact(size).toString('utf8'));
// The consumer owns URL canonicalization. Python as_uri and Node differ on
// characters such as '~', including Windows temporary-directory aliases.
const sources = Object.fromEntries(Object.entries(payload.sources).map(
  ([filename, source]) => [pathToFileURL(filename).href, source]
));
register('data:text/javascript,' + encodeURIComponent(payload.loader), {
  data: {sources}
});
process.argv = [process.execPath, payload.entryPath, ...payload.args];
await import(pathToFileURL(payload.entryPath).href);
"""


def captured_runtime(root):
    """Read each bounded regular source through the same inspected descriptor."""
    root = Path(root).absolute()
    no_links(root)
    sources = {}
    for name in RUNTIME_FILES:
        file = root / name
        no_links(file)
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(os.open(file, flags), "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_MODULE_BYTES:
                raise ValueError("bounded complete Registry runtime required")
            source = stream.read(MAX_MODULE_BYTES + 1)
            if len(source) > MAX_MODULE_BYTES:
                raise ValueError("bounded complete Registry runtime required")
            sources[name] = source
    return sources


def sources_digest(sources):
    hashes = {name: hashlib.sha256(source).hexdigest() for name, source in sources.items()}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def runtime_digest(root):
    return sources_digest(captured_runtime(root))


def verified_sources(root, expected):
    if not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None:
        raise ValueError("independent Registry runtime pin required")
    sources = captured_runtime(root)
    if sources_digest(sources) != expected:
        raise ValueError("Registry runtime digest mismatch")
    return sources


def verify_runtime(root, expected):
    verified_sources(root, expected)


def invoke(root, pin, *args, content=None):
    sources = verified_sources(root, pin)
    node = shutil.which("node")
    if node is None:
        raise ValueError("Node runtime required")
    root = Path(root).absolute()
    entry = root / "ticket-store-cli.mjs"
    payload = json.dumps({"sources": {str(root / name): source.decode("utf-8")
                                     for name, source in sources.items()},
                          "loader": CAPTURED_LOADER, "entryPath": str(entry),
                          "args": list(args)}).encode()
    if len(payload) > 24 * MAX_MODULE_BYTES:
        raise ValueError("bounded Registry frame required")
    frame = len(payload).to_bytes(4, "big") + payload + (content or "").encode("utf-8")
    result = subprocess.run([node, "--input-type=module", "--eval", CAPTURED_BOOTSTRAP],
        input=frame, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("Registry ticket operation failed")
    return json.loads(result.stdout)


SAFE_SCOPE_TEXT = re.compile(r"[A-Za-z0-9._*/-]{1,160}")


class ScopeOwnershipError(ValueError):
    """Rejected scope whose message is safe to print: caller patterns and workstream names only."""


def _safe(value):
    return value if SAFE_SCOPE_TEXT.fullmatch(value) else "<redacted>"


def ownership_hint(manifest, workstream, unowned):
    """Name each unowned pattern and the workstreams that do own it."""
    workstreams = manifest['coordination']['workstreams']
    from governance_check import pattern_covered_by
    from work_start_check import patterns
    parts = []
    for path in unowned[:5]:
        owners = sorted(name for name, entry in workstreams.items()
                        if any(pattern_covered_by(path, owner) for owner in patterns(entry.get('ownedPaths', []))))
        where = f"owned by {', '.join(_safe(o) for o in owners)}" if owners else "owned by no workstream"
        parts.append(f"{_safe(path)} ({where})")
    more = f" and {len(unowned) - 5} more" if len(unowned) > 5 else ""
    return (f"path(s) not owned by workstream '{_safe(workstream)}': {'; '.join(parts)}{more}. "
            "Drop them from --path, or allocate the work in the owning workstream.")


def scoped_paths(root, workstream, paths):
    """Share the gate's ownership predicate; narrowing is never write authority."""
    if not paths:
        return []
    from governance_check import pattern_covered_by
    from work_start_check import manifest_at, material, patterns
    scope = patterns(paths)
    if any(any(part in {"", "."} for part in path.split("/")) for path in scope):
        raise ValueError("canonical repository-relative scope required")
    manifest = manifest_at(Path(root))
    workstreams = manifest['coordination']['workstreams']
    if workstream not in workstreams:
        raise ScopeOwnershipError(
            f"unknown workstream '{_safe(workstream)}'; declared: {', '.join(_safe(w) for w in sorted(workstreams))}")
    owned = patterns(workstreams[workstream]['ownedPaths'])
    if not material(scope):
        raise ScopeOwnershipError(
            "scope has no implementation path; ticket tracking files alone are not material work")
    unowned = [path for path in scope if not any(pattern_covered_by(path, owner) for owner in owned)]
    if unowned:
        raise ScopeOwnershipError(ownership_hint(manifest, workstream, unowned))
    return scope


def persist_scope(args):
    scope = scoped_paths(args.root, args.workstream, args.path)
    if args.ticket is not None:
        if not scope or re.fullmatch(r"ticket-[0-9]{3,}", args.ticket) is None:
            raise ValueError("reserved identity and explicit scope required")
        path = args.root / 'project' / args.ticket / 'intent.json'
        no_links(path.absolute())
        intent = json.loads(path.read_text(encoding='utf-8'))
        if intent['ticket'] != args.ticket or intent['workstream'] != args.workstream:
            raise ValueError("allocated intent identity mismatch")
        # Replace template implementation placeholders, never broaden admission.
        intent['allowedPaths'] = [f'project/{args.ticket}/**', 'TODO.md', 'project/TICKETS.md', *scope]
        path.write_text(json.dumps(intent, indent=2) + '\n', encoding='utf-8')
    return scope


def create(args):
    ticket = args.ticket
    if re.fullmatch(r"ticket-[0-9]{3,}", ticket or "") is None:
        raise ValueError("reserved ticket identity required")
    if not args.title or "\n" in args.title or "\r" in args.title:
        raise ValueError("single-line title required")
    scope = scoped_paths(args.root, args.workstream, args.path)
    intent = {"schema": "new-project.intent/v3", "ticket": ticket, "summary": args.title,
        "workstream": args.workstream,
        "classification": {"kind": args.kind, "priority": args.priority, "origin": args.origin},
        # Retain the admitted scope; complete delivery intent and fencing before
        # editing. With no explicit scope, retain the conservative old seed.
        "allowedPaths": [f"project/{ticket}/**", *scope], "forbiddenPaths": ["project/ticket-*/user-*.md"],
        "stacks": [], "dependsOn": [], "conflictsWith": [], "integrationTicket": None}
    readme = (f"# {args.title}\n\n- **Status**: IN_PROGRESS\n- **Workflow state**: EDIT\n\n"
        "## Goal and scope\n\nComplete the bounded intent in SQLite before implementation.\n")
    content = json.dumps({"README.md": readme, "intent.json": json.dumps(intent, indent=2) + "\n"})
    invoke(args.runtime_root, args.runtime_sha256, "init", "--repository", str(args.root))
    receipt = invoke(args.runtime_root, args.runtime_sha256, "create", "--repository", str(args.root),
        "--ticket", ticket, "--allocation-key", args.allocation_key, content=content)
    return {**receipt, "runtime_sha256": args.runtime_sha256, "storage": "sqlite"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["digest", "verify", "highest", "create", "active", "scope"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root")
    parser.add_argument("--runtime-sha256")
    parser.add_argument("--active-status", action="append", default=[])
    parser.add_argument("--path", action="append", default=[])
    for name in ("ticket", "title", "workstream", "kind", "priority", "origin", "allocation-key"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    try:
        if args.command == "scope":
            print(json.dumps(persist_scope(args)))
        elif args.command == "active":
            from ticket_activity import resolve
            text = read_file(args.root, args.ticket, "README.md").decode("utf-8")
            match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", text)
            if match is None:
                raise ValueError("ticket status required")
            result = resolve(args.root, args.root / "project" / args.ticket, set(args.active_status), status_override=match.group(1))
            raise SystemExit(0 if result.active else 1)
        elif args.command == "highest":
            database = primary_database(args.root)
            rows = database_rows(args.root, database) if database.exists() else []
            print(max((int(row[0].removeprefix("ticket-")) for row in rows), default=0))
        elif args.command == "digest":
            print(runtime_digest(args.runtime_root))
        elif args.command == "verify":
            verify_runtime(args.runtime_root, args.runtime_sha256)
        else:
            print(json.dumps(create(args)))
    except Exception as error:
        # Do not echo command input, ticket contents or child stderr. A scope
        # ownership rejection holds only validated caller patterns and manifest
        # workstream names, so it is named instead of the generic diagnostic.
        if args.command == "scope" and isinstance(error, ScopeOwnershipError):
            parser.exit(3, f"GOV-WORK-START-001: {error}\n")
        if args.command == "scope":
            parser.exit(3, "GOV-WORK-START-001: invalid scope, unowned paths or missing managed scope runtime.\n")
        parser.exit(2 if args.command == "active" else 1, "GOV-TICKET-ALLOCATION-003: SQLite storage or pinned runtime validation failed.\n")


if __name__ == "__main__":
    main()
