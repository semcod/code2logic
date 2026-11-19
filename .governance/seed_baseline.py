#!/usr/bin/env python3
"""Explicit native-adopter seed transaction; no product or remote authority.

The caller supplies an external exact-state request under existing session
authorization. The installed adoption lock pins the named seed profile. The
allocator owns reservation/locking; the normal Git hook checks the prepared
transaction. This is a local accidental-writer boundary, not hostile-OS-user
authentication or trusted publication approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

SCHEMA = 'new-project.seed-baseline-request/v1'
PROFILE = 'seed-profile:new-project-native'
FIELDS = {'schema', 'root', 'repositoryRef', 'authorizationRef', 'createRepository',
          'execute', 'sourceRevision', 'lockSha256', 'seedProfileRef',
          'ownerActor', 'ownerSession', 'files'}
METADATA = {'README.md', 'VERSION', 'CHANGELOG.md', 'TODO.md', 'project/TICKETS.md',
            '.gitignore', '.governance/manifest.json', '.governance/manifest.lock.json',
            '.governance/required-checks.json'}
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
                    rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}')


class SeedError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise SeedError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def regular(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink_path')
    require(path.is_file(), 'regular_file_required')


def load(path):
    regular(path)
    raw = path.read_bytes()
    require(len(raw) <= 131072, 'document_too_large')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    require(isinstance(value, dict), 'object_required')
    return value


def git(root, *args, check=True, env=None):
    clean = {k: v for k, v in (env or os.environ).items() if not k.startswith('GIT_')}
    return subprocess.run(['git', '-C', str(root), *args], check=check,
                          capture_output=True, env=clean)


def stage(root):
    result = {}
    total = 0
    for row in git(root, 'ls-files', '--stage', '-z').stdout.split(b'\0'):
        if not row:
            continue
        header, raw_name = row.split(b'\t', 1)
        mode, oid, level = header.decode().split()
        name = raw_name.decode()
        path = PurePosixPath(name)
        require(path.as_posix() == name and not path.is_absolute()
                and '..' not in path.parts and not any(ord(c) < 32 for c in name), 'unsafe_name')
        require(mode in ('100644', '100755') and level == '0', 'regular_stage_required')
        regular(root / name)
        raw = git(root, 'cat-file', 'blob', oid).stdout
        total += len(raw)
        require(total <= 16 * 1024 * 1024 and len(result) < 512, 'seed_size_limit')
        require(raw == (root / name).read_bytes(), 'index_worktree_drift')
        require(not SECRET.search(raw), 'secret_material')
        result[name] = digest(raw)
    return result


def context(root, request_path, actor, session, *, allowed_untracked=()):
    require(root.is_absolute() and root == root.resolve(), 'canonical_root_required')
    require(not any(p.is_symlink() for p in (root, *root.parents)), 'symlink_path')
    require(request_path == request_path.resolve() and root not in request_path.parents, 'external_request_required')
    request = load(request_path)
    require(set(request) == FIELDS and request['schema'] == SCHEMA, 'request_shape')
    require(request['root'] == str(root) and request['seedProfileRef'] == PROFILE, 'request_binding')
    require(request['createRepository'] is True and request['execute'] is True
            and re.fullmatch(r'authorization:session/[a-z0-9._/-]+', request['authorizationRef']),
            'explicit_new_repository_authority_required')
    require(request['ownerActor'] == actor and request['ownerSession'] == session
            and actor and session, 'writer_binding')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', request['repositoryRef']), 'repository_binding')
    require(git(root, 'rev-parse', '--verify', 'HEAD', check=False).returncode != 0, 'head_must_be_unborn')
    require(not git(root, 'for-each-ref', '--format=%(refname)').stdout.strip(), 'existing_ref')
    require(not git(root, 'remote').stdout.strip(), 'remote_forbidden')
    require((root / '.git').is_dir() and not (root / '.git').is_symlink(), 'primary_checkout_required')
    require(git(root, 'config', '--get', 'core.hooksPath', check=False).stdout.strip() == b'.githooks'
            and os.access(root / '.githooks/pre-commit', os.X_OK), 'managed_hook_required')
    branch = git(root, 'symbolic-ref', '--short', 'HEAD').stdout.decode().strip()
    manifest = load(root / '.governance/manifest.json')
    require(manifest['delivery']['targetBranches'] == [branch], 'target_branch_required')
    lock_path = root / '.governance/manifest.lock.json'
    lock = load(lock_path)
    require(digest(lock_path.read_bytes()) == request['lockSha256'], 'adoption_lock_drift')
    pin = lock.get('standard', {})
    require(pin.get('id') == 'wellmanifest/new-project'
            and pin.get('sourceRepository') == 'wellmanifest/new-project'
            and pin.get('publicationStatus') == 'published'
            and re.fullmatch('[a-f0-9]{40}', request['sourceRevision'])
            and pin.get('sourceRevision') == request['sourceRevision'], 'published_profile_required')
    managed = lock.get('managedFiles', {})
    mapping_path = root / '.governance/package-manifest.json'
    require(managed.get('.governance/package-manifest.json') == digest(mapping_path.read_bytes()),
            'package_manifest_drift')
    mapping = load(mapping_path)
    allowed = METADATA | {row['target'] for row in mapping['files']}
    require(set(managed) <= allowed, 'profile_managed_paths')
    initial = request['files']
    require(isinstance(initial, dict) and set(managed) <= set(initial) <= allowed,
            'concrete_seed_allowlist_required')
    require(all(re.fullmatch('[a-f0-9]{64}', value) for value in initial.values()), 'file_digest_required')
    require(all(initial.get(name) == sha for name, sha in managed.items()), 'managed_pin_drift')
    require(set(METADATA) <= set(initial), 'seed_prerequisites_required')
    require(load(root / '.governance/required-checks.json')['repository'] == request['repositoryRef'],
            'check_repository_binding')
    # Validate carrier paths before Git classifies a symlinked parent as an
    # unrelated untracked path, and before any ticket contents are read.
    for name in allowed_untracked:
        regular(root / name)
    untracked = set(git(root, 'ls-files', '--others', '-z').stdout.decode().split('\0')) - {''}
    require(untracked <= set(allowed_untracked), 'untracked_path')
    return request


def preflight(root, request_path, actor, session):
    request = context(root, request_path, actor, session)
    require(stage(root) == request['files'], 'exact_seed_stage_required')
    require(not (root / '.git/new-project-seed-reservation.json').exists(), 'seed_already_reserved')
    require(not (root / '.git/new-project-ticket-high-water').exists(), 'existing_ticket_reservation')
    probe = subprocess.run(['python3', '-B', str(root / '.governance/worktree_path_check.py'),
                            'feature-probe', '--from-worktree', str(root)],
                           check=True, capture_output=True)
    require(json.loads(probe.stdout).get('supported') is True, 'relative_worktrees_required')
    return request


def prepare(root, request_path, actor, session, ticket):
    # Validate without changing files or the index. Only this allocator's two
    # ticket carriers may be untracked; other context callers stay strict.
    require(re.fullmatch('ticket-[0-9]{3,}', ticket), 'native_ticket_required')
    carriers = [f'project/{ticket}/README.md', f'project/{ticket}/intent.json']
    request = context(root, request_path, actor, session, allowed_untracked=carriers)
    readme, intent_path = (root / name for name in carriers)

    # The managed allocator has reserved this exact ID under its clone lock.
    counter = root / '.git/new-project-ticket-high-water'
    regular(counter)
    require(counter.read_text().strip() == str(int(ticket.removeprefix('ticket-'))), 'native_reservation_required')
    require((root / '.git/new-project-ticket-allocation.lock').is_dir(), 'allocator_lock_required')
    reservation = root / '.git/new-project-seed-reservation.json'
    require(not reservation.exists() and not reservation.is_symlink(), 'seed_already_reserved')
    intent = load(intent_path)
    require(intent['ticket'] == ticket and 'delivery' not in intent, 'unborn_ticket_binding')
    seed_files = request['files']
    initial = stage(root)
    require(set(initial) == set(seed_files), 'exact_seed_stage_required')
    require(all(initial[name] == sha for name, sha in seed_files.items()
                if name != 'project/TICKETS.md'), 'seed_content_drift')
    text = readme.read_text()
    require('SESSION_EXECUTION_AUTHORIZATION' not in text, 'unexpected_ticket_content')
    text += '\nSESSION_EXECUTION_AUTHORIZATION: explicit new-repository seed request; no product implementation before the real baseline.\n'
    carrier_bytes = [text.encode(), intent_path.read_bytes()]
    require(not any(SECRET.search(raw) for raw in carrier_bytes), 'secret_material')
    require(len(initial) + len(carriers) <= 512
            and sum((root / name).stat().st_size for name in initial)
            + sum(map(len, carrier_bytes)) <= 16 * 1024 * 1024, 'seed_size_limit')
    request_sha256 = digest(request_path.read_bytes())

    # Mutate only after request, paths, reservation, intent and seed validation.
    readme.write_text(text)
    names = [*seed_files, *carriers]
    git(root, 'add', '--', *names)
    actual = stage(root)
    require(set(actual) == set(names), 'seed_stage_expansion')
    require(all(actual[name] == sha for name, sha in seed_files.items()
                if name != 'project/TICKETS.md'), 'seed_content_drift')
    record = {'requestSha256': request_sha256, 'ticket': ticket,
              'files': actual, 'actor': actor, 'session': session}
    with reservation.open('x') as stream:
        json.dump(record, stream, sort_keys=True)
    return record


def hook_check(root, request_path, actor, session):
    context(root, request_path, actor, session)
    record = load(root / '.git/new-project-seed-reservation.json')
    require(record['actor'] == actor and record['session'] == session
            and record['requestSha256'] == digest(request_path.read_bytes()), 'prepared_request_drift')
    require((root / '.git/new-project-ticket-allocation.lock').is_dir(), 'allocator_lock_required')
    counter = root / '.git/new-project-ticket-high-water'
    require(counter.read_text().strip() == str(int(record['ticket'].removeprefix('ticket-'))), 'reservation_drift')
    require(stage(root) == record['files'], 'prepared_stage_drift')
    return record


def commit(root, request_path, actor, session):
    record = hook_check(root, request_path, actor, session)
    env = dict(os.environ, NEW_PROJECT_SEED_REQUEST=str(request_path),
               NEW_PROJECT_WRITER_ACTOR=actor, NEW_PROJECT_WRITER_SESSION=session)
    result = git(root, 'commit', '-m', f'chore: establish governed baseline ({record["ticket"]})',
                 env=env, check=False)
    require(result.returncode == 0, 'seed_commit_rejected: ' +
            (result.stdout + result.stderr).decode(errors='replace')[:200])
    head = git(root, 'rev-parse', 'HEAD').stdout.decode().strip()
    require(len(git(root, 'rev-list', '--all').stdout.splitlines()) == 1, 'one_root_commit_required')
    receipt = {'schema': 'new-project.seed-baseline-receipt/v1', 'ticket': record['ticket'],
               'baselineSha': head, 'requestSha256': record['requestSha256'],
               'seedProfileRef': PROFILE, 'sourceAuthority': 'session-new-repository-only',
               'productSourcePresent': False, 'remoteEffects': 0}
    path = root / '.subactor/receipts/seed-baseline.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(receipt, stream, sort_keys=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preflight', 'prepare', 'hook-check', 'commit'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--actor', default=os.environ.get('NEW_PROJECT_WRITER_ACTOR', ''))
    parser.add_argument('--session', default=os.environ.get('NEW_PROJECT_WRITER_SESSION', ''))
    parser.add_argument('--ticket')
    parser.add_argument('--message-file', type=Path)
    args = parser.parse_args()
    try:
        common = args.root.absolute(), args.request.absolute(), args.actor, args.session
        result = (prepare(*common, args.ticket) if args.operation == 'prepare'
                  else {'preflight': preflight, 'hook-check': hook_check, 'commit': commit}[args.operation](*common))
        if args.message_file is not None:
            require(args.operation == 'hook-check', 'message_check_requires_hook')
            regular(args.message_file)
            require(args.message_file.read_text().strip() ==
                    f'chore: establish governed baseline ({result["ticket"]})', 'seed_message_binding')
        print(json.dumps({'status': 'passed', 'operation': args.operation,
                          **({'receipt': result} if args.operation == 'commit' else {})}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)[:250]}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
