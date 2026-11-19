#!/usr/bin/env python3
"""Local lease handoff for a protected invoker that authenticates old-owner consent.

Request fields and file descriptors are data, never credentials. The public API
requires an independently supplied verifier on every apply, including recovery.
The standalone CLI deliberately provides observation only.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def _sibling(name):
    spec = importlib.util.spec_from_file_location('_owner_handoff_' + name,
                                                 Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


control = _sibling('terminal_lease_release')
SCHEMA = 'new-project.owner-handoff/v1'
JOURNAL_SCHEMA = 'new-project.owner-handoff-journal/v1'
RESUME_SCHEMA = 'new-project.released-owner-resume/v1'
RESUME_JOURNAL_SCHEMA = 'new-project.released-owner-resume-journal/v1'
MAX_BYTES = 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
FIELDS = {'schema', 'requestId', 'worktreeId', 'ownerActor', 'ownerSession', 'consent',
          'expectedRevision', 'expectedFencingToken', 'expectedLeaseSha256',
          'expectedHeadSha', 'expectedDirtySha256', 'expectedIntentSha256',
          'expectedScopeHash', 'primaryCheckout', 'repositoryRef', 'targetOwnerActor', 'targetOwnerSession', 'ttlSeconds'}
RESUME_FIELDS = FIELDS | {'releaseEvidenceRef', 'expectedTerminalStateSha256'}


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return control.encoded(value)


def _require(value, message):
    if not value:
        raise ValueError(message)


def _request(request):
    _require(isinstance(request, dict), 'invalid handoff request')
    released = request.get('schema') == RESUME_SCHEMA
    _require(set(request) == (RESUME_FIELDS if released else FIELDS)
             and request['schema'] in {SCHEMA, RESUME_SCHEMA}, 'invalid handoff request')
    _require(request['consent'] is True, 'explicit consent required')
    for key in ('requestId', 'worktreeId', 'ownerActor', 'ownerSession',
                'targetOwnerActor', 'targetOwnerSession', 'repositoryRef'):
        value = request[key]
        _require(isinstance(value, str) and 0 < len(value) <= 160
                 and not any(ord(c) < 32 for c in value), 'invalid handoff identity')
    _require(isinstance(request['primaryCheckout'], str) and Path(request['primaryCheckout']).is_absolute()
             and '..' not in Path(request['primaryCheckout']).parts, 'invalid primary checkout')
    match = control.WORKTREE_ID_RE.fullmatch(request['worktreeId'])
    _require(match is not None, 'invalid worktree identity')
    _require(request['ownerSession'] != request['targetOwnerSession'], 'fresh successor session required')
    for key in ('expectedRevision', 'expectedFencingToken', 'ttlSeconds'):
        _require(type(request[key]) is int and request[key] > 0, 'invalid handoff bounds')
    _require(request['ttlSeconds'] <= 7200, 'handoff lifetime exceeds bound')
    for key in ('expectedLeaseSha256', 'expectedDirtySha256', 'expectedIntentSha256', 'expectedScopeHash'):
        _require(isinstance(request[key], str) and re.fullmatch('[0-9a-f]{64}', request[key]),
                 'invalid handoff digest')
    if released:
        _require(isinstance(request['releaseEvidenceRef'], str)
                 and re.fullmatch(r'receipt:[A-Za-z0-9][A-Za-z0-9._:/-]{0,510}', request['releaseEvidenceRef']),
                 'protected release evidence reference required')
        _require(isinstance(request['expectedTerminalStateSha256'], str)
                 and re.fullmatch('[0-9a-f]{64}', request['expectedTerminalStateSha256']),
                 'invalid terminal observation digest')
    _require(isinstance(request['expectedHeadSha'], str)
             and re.fullmatch('[0-9a-f]{40}', request['expectedHeadSha']), 'invalid HEAD')
    return match[1], 'refs/heads/ticket/' + match[2] + '-' + match[3]


def _git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    result = subprocess.run(['git', '-C', str(root), *args], env=env,
                            capture_output=True, timeout=20, check=True)
    return result.stdout


def _read(path, limit=MAX_BYTES):
    with control.directory(path.parent) as (fd, verify):
        raw = control.read_at(fd, path.name, limit)
        verify()
        return raw


def _file_row(root, name):
    relative = Path(name)
    _require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe snapshot path')
    path = root / relative
    with control.directory(path.parent) as (fd, verify):
        try:
            info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            verify()
            return [name, 'missing']
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path.name, dir_fd=fd)
            verify()
            return [name, 'symlink', stat.S_IMODE(info.st_mode), target]
        _require(stat.S_ISREG(info.st_mode), 'unsafe snapshot node')
        _require(info.st_size <= MAX_FILE_BYTES, 'snapshot file exceeds bound')
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            _require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), 'snapshot changed')
            digest, count = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                _require(count <= MAX_FILE_BYTES, 'snapshot file exceeds bound')
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        named = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
        _require(identity(opened) == identity(after) == identity(named), 'snapshot changed')
        verify()
        return [name, 'file', stat.S_IMODE(info.st_mode), digest.hexdigest()]


def _repository_matches(root, request, lease):
    original, selected = lease['repositoryRef'], request['repositoryRef']
    accepted = control._accepted_repositories(root)
    if original == selected and selected in accepted:
        return True
    if request['schema'] != RESUME_SCHEMA or '/' in original:
        return False
    # Only this explicit operation can translate a historical basename. Its
    # verifier must bind both names and the exact raw old lease, independently
    # of the request. A local digest is not a remote repository mapping.
    origin = _git(root, 'config', '--get', 'remote.origin.url').decode().strip()
    canonical = control.canonical.canonical_owner_repository(origin)
    return (canonical == selected and selected in accepted
            and original == canonical.rsplit('/', 1)[-1])


def _validate_original(root, request, lease):
    projected = lease
    if request['schema'] == RESUME_SCHEMA:
        _require(_repository_matches(root, request, lease), 'repository mismatch')
        # The original is always archived and CASed byte-for-byte. Validation
        # projects only the explicitly authorized historical identity mapping;
        # no other malformed field is repaired or accepted.
        projected = dict(lease, repositoryRef=request['repositoryRef'])
    _require(not control.canonical.validate_lease(projected), 'invalid canonical lease')


def _released_state(root, tree, ticket, lease, intent):
    # Use the allocator's actual scope algorithm; the independent full current
    # intent digest is also bound, while the historical birth plan is retained.
    paths = intent.get('allowedPaths')
    _require(isinstance(paths, list) and paths and all(isinstance(p, str) and p for p in paths),
             'invalid resume scope')
    scope = _digest(json.dumps(paths, sort_keys=True, separators=(',', ':')).encode())
    _require(scope == lease['scopeHash'], 'resume scope changed since allocation')
    carrier = _read(tree / 'project' / ticket / 'README.md').decode()
    _require(control.activity.parse_ticket_state_text(carrier) == ('BLOCKED', 'HANDOFF'),
             'resume requires an unfinished blocked handoff')
    policy_path = control.activity.policy_path(root)
    policy_raw = _read(policy_path)
    override_path = control.activity.override_path(root)
    override_raw = _read(override_path) if override_path is not None else None
    expected_policy = control.decode(policy_raw)
    if override_raw is not None:
        override = control.decode(override_raw)
        expected_policy = dict(expected_policy, registry=dict(expected_policy['registry'],
                                                             missingPolicy=override.get('missingPolicy')))
    policy = control.activity.load_policy(root)
    _require(policy == expected_policy, 'activity policy observation differs')
    _require(_read(policy_path) == policy_raw, 'activity policy changed')
    _require(control.activity.override_path(root) == override_path
             and (override_path is None or _read(override_path) == override_raw), 'activity override changed')
    registry_path = control.activity.registry_path(root, policy)
    registry = control.decode(_read(registry_path))  # Missing/partial is never an empty registry.
    rows = control.activity._validate_registry(registry, control.activity.repository_ref(root))
    _require(not any(row['ticket'] == ticket and row['targetBranch'] == lease['targetBranch']
                     and policy['terminalOutcomes'].get(row['outcome'], {}).get('releasesReservation') is True
                     for row in rows), 'terminal delivery cannot be resumed')
    target = _git(root, 'rev-parse', 'refs/heads/' + lease['targetBranch']).decode().strip()
    return _digest(_encoded({'policy': policy, 'registry': registry, 'targetHead': target}))


def _snapshot(root, request, lease, *, check_expected=True):
    ticket, branch = _request(request)
    expected = {'ticketId': ticket, 'worktreeId': request['worktreeId'], 'branchRef': branch}
    _require(all(lease[k] == v for k, v in expected.items()), 'lease scope mismatch')
    _require(request['primaryCheckout'] == str(root) and _repository_matches(root, request, lease),
             'repository mismatch')
    tree = root / '.worktrees' / request['worktreeId']
    with control.directory(tree) as (_, verify_tree):
        rows = _git(root, 'worktree', 'list', '--porcelain', '-z').decode().split('\0\0')
        matches = [row.split('\0') for row in rows if 'worktree ' + str(tree) in row.split('\0')]
        _require(len(matches) == 1 and 'branch ' + branch in matches[0], 'unregistered worktree')
        _require(_git(tree, 'rev-parse', '--show-toplevel').decode().strip() == str(tree),
                 'noncanonical worktree')
        link = _read(tree / '.git', 4096).decode().strip()
        _require(link.startswith('gitdir: ') and not Path(link[8:]).is_absolute(), 'relative Git link required')
        common = Path(_git(tree, 'rev-parse', '--git-common-dir').decode().strip())
        if not common.is_absolute():
            common = tree / common
        _require(common.resolve() == root / '.git', 'foreign Git registration')
        head = _git(tree, 'rev-parse', 'HEAD').decode().strip()
        _require(_git(tree, 'symbolic-ref', 'HEAD').decode().strip() == branch, 'branch changed')
        intent_path = tree / 'project' / ticket / 'intent.json'
        intent_raw = _read(intent_path)
        intent = control.decode(intent_raw)
        _require(intent.get('ticket') == ticket and intent.get('workstream') == lease['workstream'],
                 'intent identity mismatch')
        terminal = (_released_state(root, tree, ticket, lease, intent)
                    if request['schema'] == RESUME_SCHEMA else None)
        names = sorted(set(filter(None, _git(tree, 'ls-files', '-co', '--exclude-standard', '-z')
                                  .decode().split('\0'))))
        _require(len(names) <= 100000, 'snapshot exceeds bound')
        files = [_file_row(tree, name) for name in names]
        # Include index blob IDs and status, not only worktree contents: changing
        # an already-staged file must invalidate the observation too.
        dirty = _digest(_encoded({'files': files,
                                 'index': _git(tree, 'ls-files', '--stage', '-z').decode(),
                                 'status': _git(tree, 'status', '--porcelain=v1', '-z',
                                                '--untracked-files=all').decode()}))
        verify_tree()
    observation = {'head': head, 'dirty': dirty, 'intent': _digest(intent_raw),
                   'scope': lease['scopeHash'], 'branch': branch}
    if terminal is not None:
        observation['terminal'] = terminal
        if check_expected:
            _require(terminal == request['expectedTerminalStateSha256'], 'terminal observation changed')
    if check_expected:
        _require(head == request['expectedHeadSha'] and dirty == request['expectedDirtySha256']
                 and observation['intent'] == request['expectedIntentSha256']
                 and lease['scopeHash'] == request['expectedScopeHash'], 'workspace observation changed')
    return observation


def observe(root, worktree_id, *, released=False):
    """Read the exact snapshot for a caller's subsequent protected authorization.

    No grant is produced. The authority must independently authenticate consent
    and bind these observations into the complete request before applying it.
    """
    _require(isinstance(worktree_id, str) and control.WORKTREE_ID_RE.fullmatch(worktree_id), 'invalid worktree identity')
    root, _, _ = control._controller_root(Path(root).absolute())
    lease = control.decode(_read(root / '.subactor/leases' / (worktree_id + '.json')))
    # Observation construction shares the same implementation and canonical
    # checks as apply, with expected values filled only after the full snapshot.
    repository = lease['repositoryRef']
    if released:
        _require(lease['phase'] == 'released' and not lease['publicationFrozen'], 'released slot required')
        if '/' not in repository:
            origin = _git(root, 'config', '--get', 'remote.origin.url').decode().strip()
            repository = control.canonical.canonical_owner_repository(origin)
            _require(isinstance(repository, str), 'canonical origin required')
    _validate_original(root, {'schema': RESUME_SCHEMA if released else SCHEMA,
                              'repositoryRef': repository}, lease)
    return dict(_observe_unbound(root, worktree_id, lease, released=released, repository=repository),
                primaryCheckout=str(root), repositoryRef=repository)


def _observe_unbound(root, worktree_id, lease, *, released=False, repository=None):
    # Placeholder expected values are used only by the read-only observer.
    # Apply always checks a complete, independently authorized request.
    request = {'schema': SCHEMA, 'requestId': 'observation', 'worktreeId': worktree_id,
               'ownerActor': lease['ownerActor'], 'ownerSession': lease['ownerSession'],
               'consent': True, 'expectedRevision': lease['leaseRevision'],
               'expectedFencingToken': lease['fencingToken'], 'expectedLeaseSha256': '0' * 64,
               'expectedHeadSha': '0' * 40, 'expectedDirtySha256': '0' * 64,
               'expectedIntentSha256': '0' * 64, 'expectedScopeHash': lease['scopeHash'],
               'primaryCheckout':str(root), 'repositoryRef':lease['repositoryRef'],
               'targetOwnerActor': lease['ownerActor'], 'targetOwnerSession':'observation' if lease['ownerSession']!='observation' else 'observation-2',
               'ttlSeconds': 1}
    if released:
        request.update(schema=RESUME_SCHEMA, repositoryRef=repository,
                       releaseEvidenceRef='receipt:observation', expectedTerminalStateSha256='0' * 64)
    return _snapshot(root, request, lease, check_expected=False)


def _authorization(request, descriptor, verifier):
    _require(descriptor is not None and callable(verifier), 'protected verifier required')
    info = os.fstat(descriptor)
    _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, 'bounded authorization FD required')
    raw = os.pread(descriptor, MAX_BYTES + 1, 0)
    _require(len(raw) <= MAX_BYTES, 'authorization exceeds bound')
    authorization = control.decode(raw)
    evidence = verifier(request, authorization)
    _require(isinstance(evidence, dict)
             and evidence.get('requestDigest') == _digest(_encoded(request))
             and isinstance(evidence.get('verificationRef'), str) and evidence['verificationRef'],
             'protected authorization rejected')
    return raw, evidence


def _identity(fd, name):
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe lease slot')
    return {'device':info.st_dev, 'inode':info.st_ino, 'ctimeNs':info.st_ctime_ns}


def _ttl_limit(root):
    for path in (root / '.governance/manifest.json', root / 'governance/manifest.hub.json'):
        if os.path.lexists(path):
            value = control.read_path(path).get('delivery', {}).get('maxActiveMinutes', 120)
            _require(type(value) is int and value > 0, 'invalid lifetime policy')
            return min(value * 60, 7200)
    return 7200


def _successor(lease, request, stamp):
    successor = dict(lease)
    successor.update(ownerActor=request['targetOwnerActor'], ownerSession=request['targetOwnerSession'],
                     leaseRevision=lease['leaseRevision'] + 1, fencingToken=lease['fencingToken'] + 1,
                     eventSequence=lease['eventSequence'] + 1, headSha=request['expectedHeadSha'],
                     issuedAt=stamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                     heartbeatAt=stamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                     expiresAt=(stamp + timedelta(seconds=request['ttlSeconds'])).strftime('%Y-%m-%dT%H:%M:%SZ'),
                     previousReceiptRef='receipt:owner-handoff/' + _digest(_encoded(request)))
    if request['schema'] == RESUME_SCHEMA:
        successor.update(phase='claimed', repositoryRef=request['repositoryRef'],
                         pullRequest=None, validatorRunId=None,
                         previousReceiptRef='receipt:released-owner-resume/' + _digest(_encoded(request)))
    _require(not control.canonical.validate_lease(successor), 'invalid successor lease')
    return successor


def _result(successor):
    return {'status':'handoff', 'grantsAuthority':True, 'leaseRevision':successor['leaseRevision'],
            'fencingToken':successor['fencingToken'], 'head':successor['headSha'],
            'branch':successor['branchRef'], 'writerEnvironment':{
                'NEW_PROJECT_WRITER_ACTOR':successor['ownerActor'],
                'NEW_PROJECT_WRITER_SESSION':successor['ownerSession'],
                'NEW_PROJECT_LEASE_REVISION':str(successor['leaseRevision']),
                'NEW_PROJECT_FENCING_TOKEN':str(successor['fencingToken'])}}


def _execute(root, request, fd, verify, name, policy, config, apply, authorization_fd, verifier):
    auth_raw, evidence = _authorization(request, authorization_fd, verifier) if apply else (None, None)
    identity = _identity(fd, name)
    raw = control.read_at(fd, name, control.canonical.MAX_LEASE_BYTES, private=True)
    _require(_identity(fd, name) == identity, 'lease identity changed')
    _require(request['ttlSeconds'] <= _ttl_limit(root), 'lifetime exceeds project policy')
    request_hash = _digest(_encoded(request))
    released = request['schema'] == RESUME_SCHEMA
    namespace = 'released-owner-resume' if released else 'owner-handoff'
    journal_schema = RESUME_JOURNAL_SCHEMA if released else JOURNAL_SCHEMA
    journal_path = root / '.subactor/receipts' / namespace / (request_hash + '.json')
    try:
        journal = control.decode(_read(journal_path))
    except FileNotFoundError:
        journal = None
    if journal is not None:
        _require(isinstance(journal, dict) and set(journal) == {'schema','request','original','successor',
                 'observation','authorization','evidence','result','stamp','leaseIdentity'}
                 and journal.get('schema') == journal_schema and journal.get('request') == request,
                 'journal request mismatch')
        original = base64.b64decode(journal['original'], validate=True)
        _require(_digest(original) == request['expectedLeaseSha256'], 'journal original mismatch')
        _require(raw in (original, _encoded(journal['successor'])), 'journal CAS lost')
        if raw == original:
            _require(identity == journal['leaseIdentity'], 'journal lease identity changed')
        if apply:
            _require(auth_raw == base64.b64decode(journal['authorization'], validate=True)
                     and evidence == journal['evidence'], 'journal authorization mismatch')
        lease = control.decode(original)
    else:
        original, lease = raw, control.decode(raw)
        _require(_digest(raw) == request['expectedLeaseSha256'], 'lease CAS mismatch')
    _validate_original(root, request, lease)
    _require(lease['ownerActor'] == request['ownerActor'] and lease['ownerSession'] == request['ownerSession']
             and lease['leaseRevision'] == request['expectedRevision']
             and lease['fencingToken'] == request['expectedFencingToken'], 'owner fencing mismatch')
    _require(lease['phase'] in ({'released'} if released else {'claimed', 'editing', 'validating'})
             and not lease['publicationFrozen'],
             'frozen ownership cannot be handed off')
    if released and apply:
        proof = evidence.get('releasedOwner')
        expected = {'leaseId': lease['leaseId'], 'leaseSha256': request['expectedLeaseSha256'],
                    'revision': lease['leaseRevision'], 'fencingToken': lease['fencingToken'],
                    'repositoryRef': lease['repositoryRef'], 'canonicalRepositoryRef': request['repositoryRef'],
                    'releaseEvidenceRef': request['releaseEvidenceRef']}
        _require(isinstance(proof, dict) and set(proof) == set(expected) | {'writerState'}
                 and all(type(proof[k]) is type(value) and proof[k] == value for k, value in expected.items())
                 and isinstance(proof['writerState'], str)
                 and proof['writerState'] in {'explicitly-released', 'controller-observed-stopped'},
                 'authenticated released-owner proof required')
    observation = _snapshot(root, request, lease)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if journal is None:
        successor = _successor(lease, request, now)
        journal = {'schema':journal_schema, 'request':request, 'original':base64.b64encode(original).decode(),
                   'successor':successor, 'observation':observation,
                   'authorization':base64.b64encode(auth_raw).decode() if auth_raw is not None else None,
                   'evidence':evidence, 'result':_result(successor), 'stamp':now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                   'leaseIdentity':identity}
    stamp = datetime.fromisoformat(journal['stamp'].replace('Z', '+00:00'))
    _require(stamp.tzinfo is not None and stamp <= now, 'invalid journal clock')
    _require(journal['successor'] == _successor(lease, request, stamp)
             and journal['result'] == _result(journal['successor'])
             and journal['observation'] == observation, 'journal result mismatch')
    successor = journal['successor']
    _require(not control.canonical.validate_lease(successor), 'invalid successor lease')
    _require(datetime.fromisoformat(successor['expiresAt'].replace('Z', '+00:00')) > now,
             'successor lease expired; new authenticated handoff required')
    if not apply:
        return {'status': 'planned', 'grantsAuthority': False, 'head': observation['head'],
                'nextRevision': successor['leaseRevision'], 'nextFencingToken': successor['fencingToken']}
    verify()
    _require(control.read_path(policy) == config, 'controller policy changed')
    if raw == _encoded(successor):
        return dict(journal['result'], status='idempotent')
    with control.directory(journal_path.parent, create=True) as (journal_fd, verify_journal):
        try:
            control.atomic_at(journal_fd, journal_path.name, _encoded(journal), exclusive=True)
        except FileExistsError:
            _require(control.read_at(journal_fd, journal_path.name) == _encoded(journal), 'journal changed')
        verify_journal()
        verify()
        _require(_snapshot(root, request, lease) == observation, 'workspace changed before replacement')
        auth_again, evidence_again = _authorization(request, authorization_fd, verifier)
        _require(auth_again == auth_raw and evidence_again == evidence, 'authorization changed')
        _require(request['ttlSeconds'] <= _ttl_limit(root), 'lifetime policy changed')
        _require(control.read_path(policy) == config, 'controller policy changed')
        _require(_snapshot(root, request, lease) == observation, 'workspace changed after authorization')
        _require(_identity(fd, name) == identity, 'lease identity changed before replacement')
        _require(control.read_at(fd, name, control.canonical.MAX_LEASE_BYTES, private=True) == original,
                 'lease changed before replacement')
        control._replace_lease(fd, name, _encoded(successor))
        verify()
    return journal['result']


def handoff(root, request, *, apply=False, authorization_fd=None, verifier=None):
    """Apply only from a protected caller whose verifier authenticates consent.

    The callable is trusted executable authority, never selected by the request
    or loaded from candidate paths. A caller that cannot authenticate the owner
    must not provide it. Actor/session, FD data and request digests alone do not
    implement authentication. The standalone CLI has no such verifier.
    """
    _require(isinstance(request, dict) and request.get('schema') == SCHEMA, 'ordinary handoff schema required')
    return _handoff(root, request, apply=apply, authorization_fd=authorization_fd, verifier=verifier)


def resume_released(root, request, *, apply=False, authorization_fd=None, verifier=None):
    """Protected same-ticket resume; the verifier authenticates old-writer termination.

    Neither a released lease nor a caller's assertion proves a safe handoff.
    The trusted host must acquire fresh, independent controller/owner evidence,
    bind releasedOwner to this exact request and authenticate every replay.
    """
    _require(isinstance(request, dict) and request.get('schema') == RESUME_SCHEMA, 'released resume schema required')
    return _handoff(root, request, apply=apply, authorization_fd=authorization_fd, verifier=verifier)


def _handoff(root, request, *, apply, authorization_fd, verifier):
    _request(request)
    if apply:
        _require(authorization_fd is not None and callable(verifier), 'protected verifier required')
    root, policy, config = control._controller_root(Path(root).absolute())
    name = request['worktreeId'] + '.json'
    with control.directory(root / '.subactor/leases') as (fd, verify_directory):
        def verify():
            verify_directory()
            _require(control.read_path(policy) == config, 'controller policy changed')
        lock = control.lease_lock(fd, name, verify) if apply else nullcontext(verify)
        with lock as verify_lock:
            return _execute(root, request, fd, verify_lock, name, policy, config,
                            apply, authorization_fd, verifier)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='requires a registered protected invoker; CLI refuses')
    args = parser.parse_args()
    print(json.dumps(handoff(args.root, control.read_path(args.request.absolute()), apply=args.apply)))
