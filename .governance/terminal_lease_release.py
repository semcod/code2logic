#!/usr/bin/env python3
"""Explicit current-owner release or verified controller settlement after merged delivery; never takeover.

This POSIX local-single-clone controller does not repair invalid projections,
remove worktrees, infer owner death, or approve publication. Plan is read-only.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

REQUEST_SCHEMA = 'new-project.terminal-owner-release/v1'
SETTLEMENT_SCHEMA = 'new-project.terminal-controller-settlement/v1'
SETTLEMENT_REPORT_SCHEMA = 'new-project.terminal-settlement-report/v1'
SETTLED_BY = 'controller:verified-terminal-receipt'
SETTLEABLE_PHASES = {'claimed', 'editing', 'validating', 'approved', 'merged', 'closed'}
WORKTREE_ID_RE = re.compile(r'(ticket-([0-9]{3,}))--([a-z0-9]+(?:-[a-z0-9]+)*)')
TICKET_ID_RE = re.compile(r'ticket-[0-9]{3,}')
FIELDS = {'schema', 'requestId', 'worktreeId', 'ownerActor', 'ownerSession', 'ownerHandoff',
          'expectedRevision', 'expectedFencingToken', 'expectedLeaseSha256', 'terminalReceiptRef'}
MAX_BYTES = 1024 * 1024
IDENTITY_FAILURES = frozenset({'invalid_canonical_lease', 'current_owner_mismatch',
                               'lease_scope_mismatch', 'repository_identity_mismatch'})


def require(condition, message):
    if not condition:
        raise PermissionError(message)


def sibling(name):
    spec = importlib.util.spec_from_file_location('_terminal_owner_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


canonical = sibling('change_lease_check')
activity = sibling('ticket_activity')


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    result = subprocess.run(['git', '-C', str(root), *args], env=env, capture_output=True, timeout=20)
    if check:
        require(result.returncode == 0, 'git_observation_unavailable')
    return result.stdout.decode().strip()


@contextmanager
def directory(path, create=False):
    """Keep all parents anchored; operations use the held directory descriptor."""
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'posix_controller_required')
    path = Path(os.path.abspath(path))
    require('..' not in path.parts, 'unsafe_path')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors = [os.open(path.anchor, flags)]
    try:
        for part in path.parts[1:]:
            if create:
                try: os.mkdir(part, 0o700, dir_fd=descriptors[-1])
                except FileExistsError: pass
            descriptors.append(os.open(part, flags, dir_fd=descriptors[-1]))
        def verify():
            for parent, child, part in zip(descriptors, descriptors[1:], path.parts[1:]):
                named, held = os.stat(part, dir_fd=parent, follow_symlinks=False), os.fstat(child)
                require(stat.S_ISDIR(named.st_mode) and (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino), 'directory_identity_changed')
        verify()
        yield descriptors[-1], verify
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)


def read_at(fd, name, limit=MAX_BYTES, private=False):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and (not private or info.st_nlink == 1), 'regular_private_file_required')
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'input_exceeds_bound')
    return raw


def read_path(path):
    with directory(path.parent) as (fd, verify):
        raw = read_at(fd, path.name)
        verify()
        return decode(raw)


@contextmanager
def lease_lock(fd, name, verify):
    import fcntl
    descriptor = os.open(name + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe_lock')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def verify_lock():
            verify()
            named = os.stat(name + '.lock', dir_fd=fd, follow_symlinks=False)
            require(stat.S_ISREG(named.st_mode) and named.st_nlink == 1
                    and (named.st_dev, named.st_ino) == (info.st_dev, info.st_ino), 'lock_identity_changed')
        verify_lock()
        yield verify_lock
    finally:
        os.close(descriptor)


def atomic_at(fd, name, raw, exclusive=False):
    temporary = '.terminal-' + secrets.token_hex(12)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        else:
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try: os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError: pass


def _replace_lease(fd, name, raw):
    atomic_at(fd, name, raw)


def request_identity(request):
    require(isinstance(request, dict) and set(request) == FIELDS, 'invalid_request_fields')
    require(request['schema'] == REQUEST_SCHEMA and request['ownerHandoff'] is True, 'explicit_owner_handoff_required')
    for key in ('ownerActor', 'ownerSession', 'requestId', 'terminalReceiptRef'):
        require(isinstance(request[key], str) and 0 < len(request[key]) <= 160, 'invalid_request_identity')
    for key in ('expectedRevision', 'expectedFencingToken'):
        require(type(request[key]) is int and request[key] > 0, 'invalid_request_fencing')
    require(isinstance(request['expectedLeaseSha256'], str) and re.fullmatch('[0-9a-f]{64}', request['expectedLeaseSha256']), 'invalid_request_digest')
    value = request['worktreeId']
    match = WORKTREE_ID_RE.fullmatch(value) if isinstance(value, str) else None
    require(match is not None, 'invalid_worktree_identity')
    return match[1], 'refs/heads/ticket/' + match[2] + '-' + match[3]


def _verify_terminal(root, request, lease):
    # Activity receipts establish landed delivery, not approval authority. A
    # finished lease releases only when receipt policy, Git ancestry and any
    # remaining checkout state all verify fail-closed.
    with activity.ActivityReadBatch(root):
        policy = activity.load_policy(root)
        rows = activity._validate_registry(activity._load(activity.registry_path(root, policy)), activity.repository_ref(root))
        receipt = next((r for r in rows if r['receiptRef'] == request['terminalReceiptRef']), None)
        # Any terminal outcome the managed policy declares with
        # releasesReservation=true may release an already-finished lease;
        # landed delivery is still verified against Git ancestry below.
        rule = policy['terminalOutcomes'].get(receipt['outcome']) if receipt is not None else None
        require(receipt is not None and receipt['ticket'] == lease['ticketId']
                and rule is not None and rule.get('releasesReservation') is True
                and receipt['targetBranch'] == lease['targetBranch'], 'matching_merged_receipt_required')
        require(rule and rule.get('releasesReservation') is True
                and activity._terminal_verified(root, receipt, rule, activity._target_ref(root, receipt['targetBranch'])), 'terminal_delivery_unverified')
        if lease['phase'] in {'approved', 'merged', 'closed'}:
            require(lease['headSha'] == receipt['headSha'], 'publication_head_mismatch')
        tree = root / '.worktrees' / lease['worktreeId']
        branch_head = git(root, 'rev-parse', '--verify', lease['branchRef'], check=False)
        if not branch_head and lease['phase'] in {'claimed', 'editing', 'validating'}:
            # An allocation head is the accepted base, not the later published
            # commit. Explicit release/settlement may release an already-removed
            # delivery, but may neither remove nor normalize remaining state.
            require(not os.path.lexists(tree), 'terminal_checkout_still_present')
            require(not git(root, 'for-each-ref', '--format=%(refname)', lease['branchRef']),
                    'terminal_ref_still_present')
            registrations = git(root, 'worktree', 'list', '--porcelain', '-z')
            require(not any('worktree ' + str(tree) in fields or 'branch ' + lease['branchRef'] in fields
                            for fields in (row.split('\0') for row in registrations.split('\0\0'))),
                    'terminal_checkout_still_registered')
            require(lease['headSha'] is not None
                    and git(root, '--no-replace-objects', 'merge-base', lease['headSha'], receipt['headSha'])
                    == lease['headSha'], 'terminal_allocation_base_unverified')
        else:
            require((branch_head or lease['headSha']) == receipt['headSha'], 'terminal_head_mismatch')
        if tree.exists():
            with directory(tree): pass
            require(git(tree, 'rev-parse', 'HEAD') == receipt['headSha']
                    and git(tree, 'symbolic-ref', 'HEAD') == lease['branchRef']
                    and not git(tree, 'status', '--porcelain', '--untracked-files=all'), 'worktree_has_unpublished_work')
        return receipt


def _apply_transitions(lease, *, request_digest, requested_by, idempotency_prefix, authority_ref, stamp):
    require(not canonical.validate_lease(lease), 'invalid_canonical_lease')
    phase = lease['phase']
    if phase in {'claimed', 'editing', 'validating'}: actions = ['cancel', 'release']
    elif phase == 'approved': actions = ['record-merge', 'close', 'release']
    elif phase == 'merged': actions = ['close', 'release']
    elif phase in {'closed', 'cancelled'}: actions = ['release']
    else: raise PermissionError('phase_requires_existing_controller_reconciliation')
    current, receipts = dict(lease), []
    for action in actions:
        transition = {'schema': canonical.REQUEST_SCHEMA, 'requestId': request_digest + '-' + action,
            'leaseId': current['leaseId'], 'action': action, 'expectedRevision': current['leaseRevision'],
            'expectedFencingToken': current['fencingToken'], 'expectedPhase': current['phase'],
            'requestedBy': requested_by, 'idempotencyKey': idempotency_prefix + ':' + action,
            'targetHeadSha': current['headSha'], 'replacementReceiptRef': None,
            'authorityRef': authority_ref, 'requestedAt': stamp}
        receipt, errors = canonical.evaluate_transition(current, transition)
        require(not errors and receipt is not None, 'canonical_transition_refused')
        current.update(phase=receipt['phaseAfter'], leaseRevision=receipt['leaseRevision'],
            fencingToken=receipt['fencingToken'], eventSequence=current['eventSequence'] + 1,
            publicationFrozen=receipt['phaseAfter'] in canonical.FROZEN_PHASES, previousReceiptRef=receipt['receiptRef'])
        receipts.append(receipt)
    require(not canonical.validate_lease(current), 'invalid_release_result')
    return current, receipts


def replacement(lease, request, stamp):
    return _apply_transitions(
        lease,
        request_digest=sha(encoded(request)),
        requested_by=request['ownerActor'],
        idempotency_prefix=request['requestId'],
        authority_ref=request['terminalReceiptRef'],
        stamp=stamp,
    )


def _settlement_replacement(lease, settlement, stamp):
    require(lease.get('phase') in SETTLEABLE_PHASES, 'phase_requires_existing_controller_reconciliation')
    digest = sha(encoded(settlement))
    return _apply_transitions(
        lease,
        request_digest=digest,
        requested_by=SETTLED_BY,
        idempotency_prefix='settlement:' + digest[:48],
        authority_ref=settlement['terminalReceiptRef'],
        stamp=stamp,
    )


def _accepted_repositories(root):
    accepted = {'local/' + sha(str(root).encode())}
    origin_url = git(root, 'config', '--get', 'remote.origin.url', check=False)
    try:
        canonical_identity = canonical.canonical_owner_repository(origin_url) if origin_url else None
    except Exception:
        # An origin that cannot be canonicalized leaves the local digest authoritative.
        canonical_identity = None
    if canonical_identity:
        accepted.add(canonical_identity)
    return accepted


def _controller_root(root):
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'posix_controller_required')
    root = Path(root).absolute()
    with directory(root): pass
    root = Path(git(root, 'worktree', 'list', '--porcelain').splitlines()[0].removeprefix('worktree '))
    require(root.is_absolute(), 'primary_checkout_unavailable')
    policy = root / '.governance/ticket-allocation.json'
    if not policy.exists(): policy = root / 'governance/ticket-allocation.json'
    config = read_path(policy)
    require(isinstance(config, dict) and set(config) == {'$schema', 'schema', 'mode'}
            and config['schema'] == 'new-project.ticket-allocation/v1'
            and config['mode'] == 'local-single-clone', 'registered_controller_required')
    return root, policy, config


def _execute(root, request, fd, verify, name, apply):
    raw = read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True)
    current = decode(raw)
    require(not canonical.validate_lease(current), 'invalid_canonical_lease')
    ticket, branch = request_identity(request)
    accepted_repositories = _accepted_repositories(root)
    expected = {'ticketId': ticket, 'worktreeId': request['worktreeId'], 'branchRef': branch}
    require(all(current[k] == v for k, v in expected.items()), 'lease_scope_mismatch')
    require(current['ownerActor'] == request['ownerActor']
            and current['ownerSession'] == request['ownerSession'], 'current_owner_mismatch')
    require(current['repositoryRef'] in accepted_repositories, 'repository_identity_mismatch')
    journal_path = root / '.subactor/receipts/terminal-owner-release' / (sha(encoded(request)) + '.json')
    if journal_path.exists() or journal_path.is_symlink():
        journal = read_path(journal_path)
        original = base64.b64decode(journal['original'], validate=True)
        require(journal['request'] == request and sha(original) == request['expectedLeaseSha256'], 'journal_request_mismatch')
        prior = decode(original)
        require(prior['leaseRevision'] == request['expectedRevision']
                and prior['fencingToken'] == request['expectedFencingToken'], 'journal_fencing_mismatch')
        target, receipts = replacement(prior, request, journal['stamp'])
        require(journal['replacement'] == target and journal['transitions'] == receipts, 'journal_transition_mismatch')
        if raw == encoded(target):
            return {'status': 'idempotent', 'leaseRevision': target['leaseRevision'], 'fencingToken': target['fencingToken']}
        require(raw == original, 'journal_lease_compare_and_swap_lost')
    else:
        require(sha(raw) == request['expectedLeaseSha256'] and current['leaseRevision'] == request['expectedRevision']
                and current['fencingToken'] == request['expectedFencingToken'], 'lease_compare_and_swap_lost')
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        target, receipts = replacement(current, request, stamp)
        journal = {'schema': REQUEST_SCHEMA, 'request': request, 'original': base64.b64encode(raw).decode(),
                   'replacement': target, 'transitions': receipts, 'stamp': stamp}
    _verify_terminal(root, request, current)
    verify()
    require(read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True) == raw, 'lease_compare_and_swap_lost')
    if not apply:
        return {'status': 'planned', 'grantsAuthority': False, 'actions': [r['action'] for r in receipts]}
    with directory(journal_path.parent, create=True) as (journal_fd, verify_journal):
        try: atomic_at(journal_fd, journal_path.name, encoded(journal), exclusive=True)
        except FileExistsError:
            require(read_at(journal_fd, journal_path.name) == encoded(journal), 'journal_changed')
        verify_journal()
        verify()
        require(read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True) == raw, 'lease_compare_and_swap_lost')
        _replace_lease(fd, name, encoded(target))
        verify()
    return {'status': 'released', 'leaseRevision': target['leaseRevision'], 'fencingToken': target['fencingToken'],
            'receipt': str(journal_path), 'worktreeCleanup': 'separate_controller_required'}


def release_owner(root, request, *, apply=False, actor=None, session=None):
    request_identity(request)
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'posix_controller_required')
    if apply:
        require(actor == request['ownerActor'] and session == request['ownerSession'], 'invoking_owner_context_required')
    root, policy, config = _controller_root(root)
    with directory(root / '.subactor/leases') as (fd, verify_directory):
        def verify():
            verify_directory()
            require(read_path(policy) == config, 'controller_policy_changed')
        name = request['worktreeId'] + '.json'
        if apply:
            with lease_lock(fd, name, verify) as verify_lock:
                return _execute(root, request, fd, verify_lock, name, True)
        return _execute(root, request, fd, verify, name, False)


def _index_releasing_receipts(root):
    with activity.ActivityReadBatch(root):
        policy = activity.load_policy(root)
        reg_path = activity.registry_path(root, policy)
        if not os.path.lexists(reg_path):
            return {}
        rows = activity._validate_registry(activity._load(reg_path), activity.repository_ref(root))
        by_ticket_branch = {}
        for row in rows:
            rule = policy['terminalOutcomes'].get(row['outcome'])
            if rule is not None and rule.get('releasesReservation') is True:
                by_ticket_branch.setdefault((row['ticket'], row['targetBranch']), []).append(row)
        return by_ticket_branch


def _select_verified_receipt(root, candidates, lease):
    require(bool(candidates), 'matching_merged_receipt_required')
    verified = []
    last_error = 'matching_merged_receipt_required'
    for candidate in candidates:
        try:
            verified.append(_verify_terminal(root, {'terminalReceiptRef': candidate['receiptRef']}, lease))
        except (OSError, ValueError, TypeError, KeyError, PermissionError, subprocess.SubprocessError, activity.ActivityError) as exc:
            last_error = str(exc) or type(exc).__name__
    require(bool(verified), last_error)
    require(len({item['headSha'] for item in verified}) == 1, 'ambiguous_terminal_receipts')
    return verified[-1]


def _settle_one(root, fd, verify, name, stem, file_ticket, expected_branch, accepted_repositories, receipts_index, apply):
    raw = read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True)
    current = decode(raw)
    require(not canonical.validate_lease(current), 'invalid_canonical_lease')
    require(current['ticketId'] == file_ticket and current['worktreeId'] == stem
            and current['branchRef'] == expected_branch, 'lease_scope_mismatch')
    require(current['repositoryRef'] in accepted_repositories, 'repository_identity_mismatch')
    if current['phase'] == 'released':
        return None, 'already_released'
    require(current['phase'] in SETTLEABLE_PHASES,
            'phase_requires_existing_controller_reconciliation')
    candidates = receipts_index.get((current['ticketId'], current['targetBranch']), ())
    receipt = _select_verified_receipt(root, candidates, current)
    settlement = {
        'schema': SETTLEMENT_SCHEMA,
        'settledBy': SETTLED_BY,
        'worktreeId': stem,
        'ticketId': current['ticketId'],
        'leaseId': current['leaseId'],
        'expectedRevision': current['leaseRevision'],
        'expectedFencingToken': current['fencingToken'],
        'expectedLeaseSha256': sha(raw),
        'terminalReceiptRef': receipt['receiptRef'],
    }
    journal_path = root / '.subactor/receipts/terminal-owner-release' / ('settlement-' + sha(encoded(settlement)) + '.json')
    if journal_path.exists() or journal_path.is_symlink():
        journal = read_path(journal_path)
        original = base64.b64decode(journal['original'], validate=True)
        require(journal.get('schema') == SETTLEMENT_SCHEMA
                and journal.get('settledBy') == SETTLED_BY
                and journal.get('terminalReceiptRef') == receipt['receiptRef']
                and journal.get('settlement') == settlement
                and sha(original) == settlement['expectedLeaseSha256'], 'journal_request_mismatch')
        prior = decode(original)
        require(prior['leaseRevision'] == settlement['expectedRevision']
                and prior['fencingToken'] == settlement['expectedFencingToken'], 'journal_fencing_mismatch')
        target, transitions = _settlement_replacement(prior, settlement, journal['stamp'])
        require(journal['replacement'] == target and journal['transitions'] == transitions, 'journal_transition_mismatch')
        require(raw == original, 'journal_lease_compare_and_swap_lost')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        target, transitions = _settlement_replacement(current, settlement, stamp)
        journal = {
            'schema': SETTLEMENT_SCHEMA,
            'settledBy': SETTLED_BY,
            'terminalReceiptRef': receipt['receiptRef'],
            'settlement': settlement,
            'original': base64.b64encode(raw).decode(),
            'replacement': target,
            'transitions': transitions,
            'stamp': stamp,
        }
    verify()
    require(read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True) == raw, 'lease_compare_and_swap_lost')
    if not apply:
        return ({
            'worktreeId': stem,
            'ticketId': current['ticketId'],
            'status': 'planned',
            'grantsAuthority': False,
            'settledBy': SETTLED_BY,
            'terminalReceiptRef': receipt['receiptRef'],
            'actions': [r['action'] for r in transitions],
        }, None)
    with directory(journal_path.parent, create=True) as (journal_fd, verify_journal):
        try: atomic_at(journal_fd, journal_path.name, encoded(journal), exclusive=True)
        except FileExistsError:
            require(read_at(journal_fd, journal_path.name) == encoded(journal), 'journal_changed')
        verify_journal()
        verify()
        require(read_at(fd, name, canonical.MAX_LEASE_BYTES, private=True) == raw, 'lease_compare_and_swap_lost')
        _replace_lease(fd, name, encoded(target))
        verify()
    return ({
        'worktreeId': stem,
        'ticketId': current['ticketId'],
        'status': 'released',
        'leaseRevision': target['leaseRevision'],
        'fencingToken': target['fencingToken'],
        'settledBy': SETTLED_BY,
        'terminalReceiptRef': receipt['receiptRef'],
        'receipt': str(journal_path),
        'worktreeCleanup': 'separate_controller_required',
    }, None)


def settle_verified_leases(root, *, ticket=None, apply=False):
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'posix_controller_required')
    if ticket is not None:
        require(isinstance(ticket, str) and TICKET_ID_RE.fullmatch(ticket) is not None, 'invalid_ticket_identity')
    root, policy, config = _controller_root(root)
    leases_dir = root / '.subactor/leases'
    if not os.path.lexists(leases_dir):
        require(ticket is None, 'matching_lease_not_found')
        return {
            'schema': SETTLEMENT_REPORT_SCHEMA,
            'mode': 'apply' if apply else 'plan',
            'grantsAuthority': False,
            'settledBy': SETTLED_BY,
            'settled': [],
            'skipped': [],
        }
    accepted_repositories = _accepted_repositories(root)
    receipts_index = _index_releasing_receipts(root)
    settled, skipped = [], []
    matched_ticket = 0
    with directory(leases_dir) as (fd, verify_directory):
        def verify():
            verify_directory()
            require(read_path(policy) == config, 'controller_policy_changed')
        names = sorted(entry for entry in os.listdir(fd) if entry.endswith('.json'))
        for name in names:
            stem = name[:-5]
            match = WORKTREE_ID_RE.fullmatch(stem)
            if match is None:
                if ticket is None:
                    skipped.append({'worktreeId': stem, 'ticketId': None, 'reason': 'invalid_worktree_identity'})
                continue
            file_ticket = match[1]
            if ticket is not None and file_ticket != ticket:
                continue
            matched_ticket += 1
            expected_branch = 'refs/heads/ticket/' + match[2] + '-' + match[3]
            try:
                if apply:
                    with lease_lock(fd, name, verify) as verify_lock:
                        record, skip_reason = _settle_one(
                            root, fd, verify_lock, name, stem, file_ticket,
                            expected_branch, accepted_repositories, receipts_index, True,
                        )
                else:
                    record, skip_reason = _settle_one(
                        root, fd, verify, name, stem, file_ticket,
                        expected_branch, accepted_repositories, receipts_index, False,
                    )
                if record is not None:
                    settled.append(record)
                elif skip_reason is not None:
                    skipped.append({'worktreeId': stem, 'ticketId': file_ticket, 'reason': skip_reason})
            except (OSError, ValueError, TypeError, KeyError, PermissionError, subprocess.SubprocessError, activity.ActivityError) as exc:
                verify()
                skipped.append({
                    'worktreeId': stem,
                    'ticketId': file_ticket,
                    'reason': str(exc) or type(exc).__name__,
                })
    if ticket is not None:
        require(matched_ticket > 0, 'matching_lease_not_found')
        refused = [item for item in skipped if item['reason'] != 'already_released']
        require(not refused, refused[0]['reason'] if refused else 'settlement_refused')
    return {
        'schema': SETTLEMENT_REPORT_SCHEMA,
        'mode': 'apply' if apply else 'plan',
        'grantsAuthority': False,
        'settledBy': SETTLED_BY,
        'settled': settled,
        'skipped': skipped,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--request', type=Path)
    mode.add_argument('--settle-verified', action='store_true')
    parser.add_argument('--ticket', default=None)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.settle_verified:
            print(json.dumps(settle_verified_leases(args.root, ticket=args.ticket, apply=args.apply)))
            return 0
        require(args.ticket is None, 'ticket_filter_requires_settle_verified')
        print(json.dumps(release_owner(args.root, read_path(args.request.absolute()), apply=args.apply,
            actor=os.environ.get('NEW_PROJECT_WRITER_ACTOR'), session=os.environ.get('NEW_PROJECT_WRITER_SESSION'))))
        return 0
    except (OSError, ValueError, TypeError, KeyError, PermissionError, subprocess.SubprocessError, activity.ActivityError) as exc:
        # These labels are static controller predicates, never exception text
        # from a path, Git process, JSON input or private owner identifier.
        reason = exc.args[0] if (type(exc) is PermissionError and len(exc.args) == 1
                                and type(exc.args[0]) is str and exc.args[0] in IDENTITY_FAILURES) else None
        detail = f' reason={reason};' if reason else ''
        print(f'GOV-CHANGE-LEASE-002: terminal owner release refused;{detail} preserve evidence and reconcile the exact owner, CAS, receipt and controller.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
