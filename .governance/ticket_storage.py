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


def scoped_paths(root, workstream, paths, bootstrap_adoption_digest=None):
    """Share the gate's ownership predicate; narrowing is never write authority."""
    if not paths:
        return []
    from governance_check import pattern_covered_by
    from work_start_check import manifest_at, material, patterns
    if any(
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or raw.startswith(("/", "!"))
        or ":" in raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
        for raw in paths
    ):
        raise ValueError("canonical repository-relative scope required")
    scope = patterns(paths)
    if any(any(part in {"", ".", ".."} for part in path.split("/")) for path in scope):
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
    bootstrap = set()
    if bootstrap_adoption_digest is not None:
        if (not isinstance(bootstrap_adoption_digest, str)
                or re.fullmatch(r'[0-9a-f]{64}', bootstrap_adoption_digest) is None
                or workstream not in {'governance', manifest['coordination']['integration']['workstream']}):
            raise ScopeOwnershipError('first bootstrap requires an exact digest and its declared owner')
        from work_start_check import ObservationError, bootstrap_owned_paths
        try:
            bootstrap = bootstrap_owned_paths(Path(root), manifest, bootstrap_adoption_digest)
        except (ObservationError, OSError, ValueError) as error:
            raise ScopeOwnershipError('bootstrap adoption ownership evidence unavailable') from error
    unowned = [path for path in scope if not any(pattern_covered_by(path, owner) for owner in owned)]
    if (unowned and bootstrap_adoption_digest is not None
            and workstream == manifest['coordination']['integration']['workstream']):
        # Integration retains dependency-manifest ownership. Its first native
        # adoption may also carry the exact installer-owned governance assets;
        # this is the gate's verified-adoption exception, not arbitrary scope.
        governance = patterns(workstreams['governance']['ownedPaths'])
        verified = {path for path in bootstrap
                    if any(pattern_covered_by(path, owner) for owner in governance)}
        unowned = [path for path in unowned if path not in verified]
    if (unowned and workstream == 'governance'
            and (Path(root) / '.subactor/receipts/bootstrap-adoption.json').exists()):
        from work_start_check import ObservationError, bootstrap_seed_paths
        try:
            seeds = bootstrap_seed_paths(Path(root), manifest)
        except (ObservationError, OSError, ValueError) as error:
            raise ScopeOwnershipError('bootstrap required seed evidence unavailable') from error
        unowned = [path for path in unowned if path not in seeds]
    if unowned:
        raise ScopeOwnershipError(ownership_hint(manifest, workstream, unowned))
    return scope


def persist_scope(args):
    if getattr(args, 'bootstrap_adoption_digest', None) is not None and args.ticket is not None:
        raise ScopeOwnershipError('bootstrap digest is admission-only; it cannot rewrite a ticket')
    scope = scoped_paths(args.root, args.workstream, args.path,
                         getattr(args, 'bootstrap_adoption_digest', None))
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


def radar_readme(readme, intent, root):
    """Assess initial intent through the external product; never grant authority.

    Radar is advisory and separately installed. A missing/failed runtime is
    visible in the README rather than blocking identity allocation or inventing
    a score. No network installation, shell command or repository edit occurs.
    """
    readme = re.sub(r"\n<!-- ticket-radar:start -->\n.*?<!-- ticket-radar:end -->\n?",
                    "\n", readme, flags=re.S)
    heading = "\n<!-- ticket-radar:start -->\n## Ticket Radar\n\n"
    notice = "Initial planned-scope estimate; advisory only, not execution or merge approval.\n"
    ticket = {"id": intent["ticket"], "name": intent["summary"],
              "description": "", "files": intent["allowedPaths"],
              "acceptance_criteria": [], "delivery": intent.get("delivery", {})}
    budget = intent.get("delivery", {}).get("estimatedMinutes", 30)
    reason = "runtime not installed"
    try:
        result = subprocess.run(
            ["ticket-radar", "--repository-root", str(root)],
            input=json.dumps({"ticket": ticket, "budget_minutes": budget}),
            capture_output=True, text=True, timeout=10, check=False,
        )
        reason = "runtime failed or returned an invalid assessment"
        if result.returncode or len(result.stdout) > 1024 * 1024:
            raise ValueError("radar invocation failed")
        bundle = json.loads(result.stdout)
        if not isinstance(bundle, dict) or bundle.get("schema") != "subactor.ticket-radar-bundle/v1":
            raise ValueError("unknown radar bundle")
        record = json.loads(bundle["jsonl"])
        if (record["schema"] != "subactor.ticket-radar/v1"
                or record["ticket_ref"] != intent["ticket"]
                or record.get("authority", "ADVISORY") != "ADVISORY"
                or record["assessment_mode"] != "predicted"
                or record["complexity"] not in {"XS", "S", "M", "L", "XL"}
                or type(record["score"]) is not int or not 0 <= record["score"] <= 100
                or type(record["estimate"]["minutes"]) is not int
                or not 0 <= record["estimate"]["minutes"] <= 100000
                or type(record["estimate"]["budget_minutes"]) is not int
                or not 5 <= record["estimate"]["budget_minutes"] <= 240
                or type(record["split"]["recommended"]) is not bool):
            raise ValueError("invalid planned assessment")
        diagnostics = record.get("diagnostics", [])
        if (not isinstance(diagnostics, list) or len(diagnostics) > 40
                or any(not isinstance(v, str) or not re.fullmatch(r"[A-Z0-9_-]{1,100}", v)
                       for v in diagnostics)):
            raise ValueError("invalid diagnostics")
        body = ("| Measure | Initial assessment |\n| --- | --- |\n"
                f"| Impact score | {record['score']}/100 |\n"
                f"| Complexity | {record['complexity']} |\n"
                f"| Estimated effort | {record['estimate']['minutes']} min |\n"
                f"| Planning budget | {record['estimate']['budget_minutes']} min |\n"
                f"| Split recommended | {'yes' if record['split']['recommended'] else 'no'} |\n")
        if diagnostics:
            body += "\nDiagnostics: " + ", ".join(diagnostics) + ".\n"
    except subprocess.TimeoutExpired:
        body = "Assessment unavailable: runtime timed out.\n"
    except (OSError, ValueError, KeyError, TypeError):
        body = "Assessment unavailable: " + reason + ".\n"
    return readme.rstrip() + "\n" + heading + notice + "\n" + body + "<!-- ticket-radar:end -->\n"


def assess_file_ticket(args):
    if re.fullmatch(r"ticket-[0-9]{3,}", args.ticket or "") is None:
        raise ValueError("reserved ticket identity required")
    directory = args.root / "project" / args.ticket
    for name in ("README.md", "intent.json"):
        no_links((directory / name).absolute())
    intent = json.loads((directory / "intent.json").read_text(encoding="utf-8"))
    if intent["ticket"] != args.ticket:
        raise ValueError("allocated intent identity mismatch")
    path = directory / "README.md"
    path.write_text(radar_readme(path.read_text(encoding="utf-8"), intent, args.root), encoding="utf-8")


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
    readme = radar_readme(readme, intent, args.root)
    content = json.dumps({"README.md": readme, "intent.json": json.dumps(intent, indent=2) + "\n"})
    invoke(args.runtime_root, args.runtime_sha256, "init", "--repository", str(args.root))
    receipt = invoke(args.runtime_root, args.runtime_sha256, "create", "--repository", str(args.root),
        "--ticket", ticket, "--allocation-key", args.allocation_key, content=content)
    return {**receipt, "runtime_sha256": args.runtime_sha256, "storage": "sqlite"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["digest", "verify", "highest", "create", "active", "scope", "radar"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root")
    parser.add_argument("--runtime-sha256")
    parser.add_argument("--active-status", action="append", default=[])
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--bootstrap-adoption-digest")
    for name in ("ticket", "title", "workstream", "kind", "priority", "origin", "allocation-key"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    try:
        if args.bootstrap_adoption_digest is not None and args.command != 'scope':
            raise ValueError('bootstrap digest is scope-admission-only')
        if args.command == "radar":
            assess_file_ticket(args)
        elif args.command == "scope":
            print(json.dumps(persist_scope(args)))
        elif args.command == "active":
            import ticket_activity
            text = read_file(args.root, args.ticket, "README.md").decode("utf-8")
            status, _ = ticket_activity.parse_ticket_state_text(text)
            if status is None:
                raise ValueError("ticket status required")
            result = ticket_activity.resolve(args.root, args.root / "project" / args.ticket, set(args.active_status), status_override=status)
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
