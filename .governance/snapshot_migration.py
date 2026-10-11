#!/usr/bin/env python3
"""Read-only snapshot migration proofs. Protected input, never author self-approval."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

CONTRACT_SCHEMA = 'new-project.snapshot-migration/v1'
AUTHORIZATION_SCHEMA = 'new-project.snapshot-migration-authorization/v1'
CONTRACT_FIELDS = {'schema', 'repository', 'baseSha', 'sourceSha', 'sourceTree', 'inventorySha256', 'authorizationRef'}
AUTHORIZATION_FIELDS = {'schema', 'grantId', 'repository', 'ticket', 'branch', 'targetBranch', 'baseSha', 'contractSha256', 'intentSha256', 'implementationPaths', 'historicalTickets', 'maxUses', 'status'}
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
REPOSITORY = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
MAX_AUTHORIZATION_BYTES = 2 * 1024 * 1024


class MigrationError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def safe_path(value):
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and all(p not in {'', '.', '..', '.git'} for p in value.split('/'))
            and ':' not in value)


def contract_error(value):
    if not isinstance(value, dict) or set(value) != CONTRACT_FIELDS:
        return 'snapshotMigration must be a closed migration contract'
    if value['schema'] != CONTRACT_SCHEMA or not matches(REPOSITORY, value['repository']):
        return 'snapshotMigration identity is invalid'
    if any(not matches(SHA, value[k]) for k in ('baseSha', 'sourceSha', 'sourceTree')):
        return 'snapshotMigration revisions must be full lowercase Git SHAs'
    if value['baseSha'] == value['sourceSha'] or not matches(DIGEST, value['inventorySha256']):
        return 'snapshotMigration source or inventory is invalid'
    if not isinstance(value['authorizationRef'], str) or not re.fullmatch(r'authorization:[A-Za-z0-9._/-]{1,200}', value['authorizationRef']):
        return 'snapshotMigration requires an explicit authorization reference'
    return None


def git(root, *args):
    try:
        return subprocess.check_output(['git', '--no-replace-objects', '-C', str(root), *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as error:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-002', 'Required Git subject or complete history is unavailable') from error


def commit(root, value):
    if not matches(SHA, value):
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-002', 'Expected an immutable commit SHA')
    return git(root, 'rev-parse', '--verify', value + '^{commit}').decode().strip()


def tree(root, revision):
    result = {}
    for raw in git(root, 'ls-tree', '-r', '-z', '--full-tree', revision).split(b'\0'):
        if not raw:
            continue
        metadata, name = raw.split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split()
        path = name.decode('utf-8')
        if not safe_path(path) or kind != 'blob' or mode not in {'100644', '100755', '120000'}:
            raise MigrationError('GOV-SNAPSHOT-MIGRATION-005', 'Unsupported inventory path or object type')
        result[path] = {'mode': mode, 'oid': oid}
    return result


def inventory(root, base, source):
    commit(root, base)
    commit(root, source)
    before, after = tree(root, base), tree(root, source)
    entries = [{'path': p, 'base': before.get(p), 'source': after.get(p)}
               for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
    return {'baseSha': base, 'sourceSha': source,
            'sourceTree': git(root, 'rev-parse', source + '^{tree}').decode().strip(),
            'entries': entries, 'inventorySha256': digest(entries)}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


def load_authorization(root, path, expected_digest):
    if path is None or not matches(DIGEST, expected_digest):
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-003', 'Independently pinned external authorization is required')
    path = Path(path)
    if not path.is_absolute() or path.resolve().is_relative_to(Path(root).resolve()):
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-003', 'Authorization must be outside the candidate checkout')
    try:
        if path.resolve() != path or not hasattr(os, 'O_NOFOLLOW'):
            raise ValueError('unsafe authorization path')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('not a regular file')
            raw = stream.read(MAX_AUTHORIZATION_BYTES + 1)
        if len(raw) > MAX_AUTHORIZATION_BYTES or hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError('authorization digest mismatch')
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) != AUTHORIZATION_FIELDS or value['schema'] != AUTHORIZATION_SCHEMA:
            raise ValueError('invalid authorization shape')
        paths = value['implementationPaths']
        if (not isinstance(paths, list) or not paths or any(not safe_path(p) for p in paths)
                or paths != sorted(set(paths)) or type(value['maxUses']) is not int or value['maxUses'] != 1):
            raise ValueError('invalid authorization scope')
        historical = value['historicalTickets']
        if (not isinstance(historical, list) or any(not isinstance(t, str) or not re.fullmatch(r'ticket-[0-9]{3,}', t) for t in historical)
                or historical != sorted(set(historical))):
            raise ValueError('invalid historical ticket inventory')
        if value['status'] not in {'reserved', 'consumed'}:
            raise ValueError('invalid authorization state')
        if value['status'] == 'consumed':
            raise MigrationError('GOV-SNAPSHOT-MIGRATION-006', 'Migration authorization has already been consumed')
        return value
    except MigrationError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-003', 'External authorization is invalid or its protected pin differs') from error


def _entry_stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def workspace_entry(root, path):
    """Bind content and Git mode to one descriptor; reject observed mutation."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        try:
            opened = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=descriptor)
        except FileNotFoundError:
            return None
        except OSError:
            before = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISLNK(before.st_mode):
                return {'unsupported': True}
            raw = os.fsencode(os.readlink(parts[-1], dir_fd=descriptor))
            after = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if _entry_stamp(before) != _entry_stamp(after):
                return {'unsupported': True}
            mode = '120000'
        else:
            with os.fdopen(opened, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    return {'unsupported': True}
                raw = stream.read()
                after = os.fstat(stream.fileno())
                current = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
                if (_entry_stamp(before) != _entry_stamp(after)
                        or _entry_stamp(after) != _entry_stamp(current)):
                    return {'unsupported': True}
                mode = '100755' if after.st_mode & stat.S_IXUSR else '100644'
        return {'mode': mode, 'oid': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
    except FileNotFoundError:
        return None
    except OSError:
        return {'unsupported': True}
    finally:
        os.close(descriptor)


def prove(root, intent, *, base, head, repository, branch, authorization_path, authorization_sha256):
    contract = intent.get('delivery', {}).get('snapshotMigration')
    error = contract_error(contract)
    if error:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-001', error)
    grant = load_authorization(root, authorization_path, authorization_sha256)
    expected = {'grantId': contract['authorizationRef'], 'repository': repository,
                'ticket': intent['ticket'], 'branch': branch,
                'targetBranch': intent['delivery']['targetBranch'], 'baseSha': base,
                'contractSha256': digest(contract), 'intentSha256': digest(intent)}
    if (not matches(REPOSITORY, repository) or not isinstance(branch, str) or not branch
            or repository != contract['repository'] or any(grant[k] != v for k, v in expected.items())):
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-003', 'Authorization is not bound to this repository, ticket, branch and intent')
    if base != contract['baseSha'] or base != intent['delivery']['acceptedBaseSha']:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-006', 'Fresh protected base differs from the one-use migration base')
    commit(root, base)
    source = commit(root, contract['sourceSha'])
    head_sha = git(root, 'rev-parse', '--verify', head + '^{commit}').decode().strip()
    if git(root, 'rev-parse', 'HEAD').decode().strip() != head_sha or git(root, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-002', 'Validation requires the checked-out head and complete source history')
    for ancestor, descendant in ((base, source), (source, head_sha)):
        git(root, 'merge-base', '--is-ancestor', ancestor, descendant)
    observed = inventory(root, base, source)
    if observed['sourceTree'] != contract['sourceTree'] or observed['inventorySha256'] != contract['inventorySha256']:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-005', 'Snapshot tree or inventory differs from the authorized subject')
    imported = set(grant['implementationPaths'])
    if not imported <= {entry['path'] for entry in observed['entries']}:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-005', 'Authorized implementation inventory includes an unrelated path')
    source_tree = tree(root, source)
    prefix = 'project/' + intent['ticket'] + '/'
    if any(p.startswith(prefix) for p in source_tree):
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-006', 'Migration must use a new ticket absent from the preserved source')
    new_commits = git(root, 'rev-list', '--reverse', base + '..' + head_sha, '^' + source).decode().splitlines()
    boundaries = [sha for sha in new_commits if git(root, 'show', '-s', '--format=%P', sha).decode().split() == [base, source]]
    if len(boundaries) != 1:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-004', 'Expected one migration commit with exact base and preserved source parents')
    boundary = boundaries[0]
    imported_tree = tree(root, boundary)
    if {p: v for p, v in imported_tree.items() if not p.startswith(prefix)} != source_tree:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-005', 'The migration commit adds or changes files outside its exact snapshot')
    try:
        recorded_intent = json.loads(git(root, 'show', boundary + ':' + prefix + 'intent.json'), object_pairs_hook=unique_object)
        if recorded_intent != intent or prefix + 'README.md' not in imported_tree:
            raise ValueError('intent missing or changed')
    except (ValueError, TypeError) as error:
        raise MigrationError('GOV-SNAPSHOT-MIGRATION-004', 'Approved intent and README must be in the first migration commit') from error
    final_tree = tree(root, head_sha)
    for ticket in grant['historicalTickets']:
        historical_prefix = 'project/' + ticket + '/'
        original = {p: v for p, v in source_tree.items() if p.startswith(historical_prefix)}
        current = {p: v for p, v in final_tree.items() if p.startswith(historical_prefix)}
        if (ticket == intent['ticket'] or historical_prefix + 'intent.json' not in original
                or historical_prefix + 'README.md' not in original or current != original
                or any(workspace_entry(root, p) != v for p, v in original.items())):
            raise MigrationError('GOV-SNAPSHOT-MIGRATION-004', 'Historical ticket projection is not the unchanged authorized source')
    repairs = {p for p in source_tree.keys() | final_tree.keys() if source_tree.get(p) != final_tree.get(p)}
    dirty = git(root, 'diff', '--no-ext-diff', '--name-only', '-z', head_sha)
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    repairs.update(p.decode('utf-8') for p in (dirty + untracked).split(b'\0') if p)
    unchanged = {p for p in imported if source_tree.get(p) == final_tree.get(p)
                 and workspace_entry(root, p) == source_tree.get(p)}
    repairs.update(imported - unchanged)
    return {'sourceSha': source, 'migrationCommit': boundary,
            'repairPaths': sorted(repairs), 'historicalTickets': grant['historicalTickets'],
            'inventorySha256': observed['inventorySha256'], 'importedPaths': sorted(unchanged),
            'authorizedImplementationFiles': len(imported), 'unchangedImportedFiles': len(unchanged),
            'authority': 'VALIDATION_ONLY'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        result = inventory(args.root, args.base, args.source)
    except (MigrationError, UnicodeError) as error:
        print(json.dumps({'status': 'failed', 'code': getattr(error, 'code', 'GOV-SNAPSHOT-MIGRATION-005')}))
        return 1
    print(json.dumps({'status': 'observed', 'authority': 'NONE', **result}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
