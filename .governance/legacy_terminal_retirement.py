#!/usr/bin/env python3
"""Retire one expired, owner-bound legacy slot after a verified merge.

Separate opt-in compatibility adapter. The ordinary lease controllers remain
strict. Plan never writes. Apply archives the exact original bytes before
unlinking only the obsolete lease, never a checkout or branch. A normalized
lease is neither written nor used to grant writer or publication authority.

The closed request extends the existing terminal-owner-release fields with
schema new-project.legacy-terminal-retirement/v1, legacyRepositoryRef (the bare
old label) and canonicalRepositoryRef (OWNER/REPO). Apply requires the existing
NEW_PROJECT_WRITER_ACTOR and NEW_PROJECT_WRITER_SESSION owner context.
"""
import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


def _controller():
    spec = importlib.util.spec_from_file_location(
        '_legacy_terminal_controller', Path(__file__).with_name('terminal_lease_release.py'))
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


release = _controller()
SCHEMA = 'new-project.legacy-terminal-retirement/v1'
FIELDS = release.FIELDS | {'legacyRepositoryRef', 'canonicalRepositoryRef'}
JOURNAL_FIELDS = {'schema', 'request', 'original', 'identity', 'terminal', 'stamp'}
PHASES = {'claimed', 'editing', 'validating', 'merged', 'closed'}


def _request(request):
    release.require(isinstance(request, dict) and set(request) == FIELDS
                    and request['schema'] == SCHEMA, 'invalid_legacy_request')
    projected = {k: request[k] for k in release.FIELDS}
    projected['schema'] = release.REQUEST_SCHEMA
    release.request_identity(projected)
    return projected


def _origin(root, request):
    remote = release.git(root, 'config', '--get', 'remote.origin.url')
    canonical = release.canonical.canonical_owner_repository(remote)
    release.require(canonical is not None and canonical == request['canonicalRepositoryRef'],
                    'repository_identity_mismatch')
    label = canonical.split('/')[1]
    release.require(root.name == request['legacyRepositoryRef'] == label,
                    'legacy_repository_label_mismatch')


def _original(raw, root, request, projected):
    release.require(len(raw) <= release.canonical.MAX_LEASE_BYTES, 'legacy_lease_exceeds_bound')
    release.require(release.sha(raw) == request['expectedLeaseSha256'], 'lease_compare_and_swap_lost')
    lease = release.decode(raw)
    release.require(isinstance(lease, dict)
                    and lease.get('repositoryRef') == request['legacyRepositoryRef'],
                    'legacy_repository_label_mismatch')
    # Shape validation only: this temporary view is never a persisted lease.
    shape = dict(lease, repositoryRef=request['canonicalRepositoryRef'])
    release.require(not release.canonical.validate_lease(shape), 'invalid_legacy_lease')
    ticket, branch = release.request_identity(projected)
    release.require(lease['ticketId'] == ticket and lease['worktreeId'] == request['worktreeId']
                    and lease['branchRef'] == branch, 'lease_scope_mismatch')
    release.require(lease['ownerActor'] == request['ownerActor']
                    and lease['ownerSession'] == request['ownerSession'], 'current_owner_mismatch')
    release.require(lease['leaseRevision'] == request['expectedRevision']
                    and lease['fencingToken'] == request['expectedFencingToken'],
                    'lease_compare_and_swap_lost')
    release.require(lease['phase'] in PHASES and not lease['publicationFrozen'],
                    'legacy_phase_not_retireable')
    expiry = datetime.fromisoformat(lease['expiresAt'].replace('Z', '+00:00').replace('z', '+00:00'))
    release.require(expiry <= datetime.now(timezone.utc), 'legacy_lease_still_live')
    receipt = release._verify_terminal(root, projected, lease)
    release.require(receipt['outcome'] == 'merged', 'verified_merge_required')
    return receipt


def _identity(fd, name):
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    release.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'regular_private_file_required')
    # A filesystem can immediately recycle an unlinked inode. Bind the inode's
    # change timestamp too, so a recreated byte-identical slot is not replayed.
    return {'device': info.st_dev, 'inode': info.st_ino, 'changedAtNs': info.st_ctime_ns}


def _read_slot(fd, name):
    identity = _identity(fd, name)
    raw = release.read_at(fd, name, release.canonical.MAX_LEASE_BYTES, private=True)
    release.require(_identity(fd, name) == identity, 'lease_compare_and_swap_lost')
    return raw, identity


def _unlink_slot(fd, name):
    os.unlink(name, dir_fd=fd)
    os.fsync(fd)


def _execute(root, request, projected, fd, verify, name, apply):
    journal_path = (root / '.subactor/receipts/legacy-terminal-retirement'
                    / (release.sha(release.encoded(request)) + '.json'))
    if os.path.lexists(journal_path):
        journal = release.read_path(journal_path)
        release.require(isinstance(journal, dict) and set(journal) == JOURNAL_FIELDS
                        and journal['schema'] == SCHEMA and journal['request'] == request,
                        'journal_request_mismatch')
        original = base64.b64decode(journal['original'], validate=True)
        terminal = _original(original, root, request, projected)
        release.require(journal['terminal'] == terminal, 'journal_terminal_mismatch')
        identity = journal['identity']
        release.require(isinstance(identity, dict)
                        and set(identity) == {'device', 'inode', 'changedAtNs'}
                        and all(type(v) is int and v >= 0 for v in identity.values()),
                        'journal_identity_mismatch')
        try:
            raw, observed = _read_slot(fd, name)
        except FileNotFoundError:
            verify()
            return {'status': 'idempotent', 'grantsAuthority': False, 'receipt': str(journal_path)}
        release.require(raw == original and observed == identity, 'lease_compare_and_swap_lost')
    else:
        original, identity = _read_slot(fd, name)
        terminal = _original(original, root, request, projected)
        journal = {'schema': SCHEMA, 'request': request,
                   'original': base64.b64encode(original).decode(), 'identity': identity,
                   'terminal': terminal, 'stamp': datetime.now(timezone.utc).isoformat()}
    verify()
    _origin(root, request)
    release.require(_read_slot(fd, name) == (original, identity), 'lease_compare_and_swap_lost')
    if not apply:
        return {'status': 'planned', 'grantsAuthority': False,
                'actions': ['archive-original', 'retire-expired-slot'],
                'worktreeCleanup': 'separate_controller_required'}
    with release.directory(journal_path.parent, create=True) as (journal_fd, verify_journal):
        try:
            release.atomic_at(journal_fd, journal_path.name, release.encoded(journal), exclusive=True)
        except FileExistsError:
            release.require(release.read_at(journal_fd, journal_path.name) == release.encoded(journal),
                            'journal_changed')
        verify_journal()
        verify()
        _origin(root, request)
        release.require(_read_slot(fd, name) == (original, identity), 'lease_compare_and_swap_lost')
        _unlink_slot(fd, name)
        verify()
    return {'status': 'retired', 'grantsAuthority': False, 'receipt': str(journal_path),
            'originalSha256': release.sha(original), 'worktreeCleanup': 'separate_controller_required'}


def retire_owner(root, request, *, apply=False, actor=None, session=None):
    projected = _request(request)
    if apply:
        release.require(actor == request['ownerActor'] and session == request['ownerSession'],
                        'invoking_owner_context_required')
    root, policy, config = release._controller_root(root)
    _origin(root, request)
    with release.directory(root / '.subactor/leases') as (fd, verify_directory):
        def verify():
            verify_directory()
            release.require(release.read_path(policy) == config, 'controller_policy_changed')
        name = request['worktreeId'] + '.json'
        if apply:
            with release.lease_lock(fd, name, verify) as verify_lock:
                return _execute(root, request, projected, fd, verify_lock, name, True)
        return _execute(root, request, projected, fd, verify, name, False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = retire_owner(args.root, release.read_path(args.request.absolute()), apply=args.apply,
                              actor=os.environ.get('NEW_PROJECT_WRITER_ACTOR'),
                              session=os.environ.get('NEW_PROJECT_WRITER_SESSION'))
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, PermissionError,
            release.subprocess.SubprocessError, release.activity.ActivityError):
        print('GOV-CHANGE-LEASE-002: legacy terminal retirement refused; preserve the exact '
              'slot and verify owner, expiry, identity, merged receipt and CAS.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
