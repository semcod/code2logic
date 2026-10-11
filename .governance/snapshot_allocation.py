#!/usr/bin/env python3
"""Managed local snapshot allocation. Proposals grant no writer/merge authority.

Materialization requires an externally pinned grant and an existing controller
lease, then validates the detached candidate before atomically creating its ref.
The standard never issues grants, acquires leases, pushes or approves a merge.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

sys.dont_write_bytecode = True
import governance_check as governance
import snapshot_migration as migration
import ticket_recovery as recovery
import work_start_check as start
from ticket_allocation import canonical_repository_ref, parse_config

REQUEST_SCHEMA = 'new-project.snapshot-proposal-request/v1'
PROPOSAL_SCHEMA = 'new-project.snapshot-proposal/v1'
MATERIAL_SCHEMA = 'new-project.snapshot-materialization-request/v1'
REQUEST_FIELDS = {'schema', 'requestId', 'repository', 'baseSha', 'sourceSha', 'targetBranch', 'slug', 'intentTemplate'}
MATERIAL_FIELDS = {'schema', 'proposalPath', 'proposalSha256', 'leaseId', 'leaseRevision', 'fencingToken', 'ownerActor', 'ownerSession'}
require = recovery.require
safe = recovery.safe_path
load = recovery.load


def raw_digest(path):
    return hashlib.sha256(safe(path).read_bytes()).hexdigest()


def intent_bytes(intent):
    return (json.dumps(intent, indent=2) + '\n').encode()


def atomic_write(path, raw):
    path = safe(path)
    temporary = path.with_name(path.name + '.pending')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def allocation_lock(common):
    lock = safe(common / 'new-project-ticket-allocation.lock')
    lock.mkdir()  # Never steal an existing lock, including after interruption.
    try:
        yield
    finally:
        lock.rmdir()


def context(root):
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'POSIX adapter required')
    root = safe(start.git(safe(root), 'rev-parse', '--show-toplevel').strip())
    common = safe(start.git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    primary = safe(start.worktrees(root)[0]['worktree'])
    require(start.configured_mode(root) == 'files' and not (primary / 'project.sqlite').exists(), 'File allocation required')
    policy = next((p for p in (root / '.governance/ticket-allocation.json', root / 'governance/ticket-allocation.json') if p.exists()), None)
    if policy:
        require(parse_config(policy)['mode'] == 'local-single-clone', 'Registered allocation requires its own controller')
    return root, primary, common


def external(root, common, path):
    path = safe(path)
    require(not path.is_relative_to(common), 'Authority cannot reside in Git metadata')
    for entry in start.worktrees(root):
        require(not path.is_relative_to(safe(entry['worktree'])), 'Authority must be outside all candidate checkouts')
    return path


def repository(root):
    origin = urlparse(canonical_repository_ref(start.git(root, 'config', '--get', 'remote.origin.url').strip()))
    require(origin.hostname == 'github.com' and origin.scheme in {'https', 'git+ssh'}, 'Canonical GitHub identity required')
    return origin.path.lstrip('/')


def worktree_contract(root):
    installed = Path(__file__).resolve().parent
    path = next((p for p in (installed / 'worktree_path_check.py', installed.parent / 'subprojects/worktrees/conformance.py') if p.is_file()), None)
    require(path is not None, 'Managed Worktrees v5 checker required')
    spec = importlib.util.spec_from_file_location('snapshot_worktree_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_request(root, request, workstream):
    require(isinstance(request, dict) and set(request) == REQUEST_FIELDS and request['schema'] == REQUEST_SCHEMA, 'Closed proposal request required')
    require(isinstance(request['requestId'], str) and re.fullmatch(r'[A-Za-z0-9._/-]{1,160}', request['requestId']), 'Stable request identity required')
    require(isinstance(request['slug'], str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', request['slug']), 'Canonical slug required')
    require(request['repository'] == repository(root), 'Repository mismatch')
    template = request['intentTemplate']
    require(isinstance(template, dict) and 'ticket' not in template and 'delivery' in template, 'Full intent template without a manual identity required')
    require(isinstance(template.get('summary'), str) and not any(ord(c) < 32 for c in template['summary']), 'Single-line summary required')
    require(template.get('workstream') == workstream and template.get('schema') == 'new-project.intent/v3', 'Workstream or intent mismatch')
    delivery = template['delivery']
    require(isinstance(delivery, dict) and 'snapshotMigration' not in delivery, 'Allocator owns the migration contract')
    require(delivery.get('acceptedBaseSha') == request['baseSha'] and delivery.get('targetBranch') == request['targetBranch'], 'Delivery subject mismatch')
    observed = migration.inventory(root, request['baseSha'], request['sourceSha'])
    require(observed['entries'], 'Material source delta required')
    migration.git(root, 'merge-base', '--is-ancestor', request['baseSha'], request['sourceSha'])
    return observed


def proposal_value(root, primary, request, ticket, workstream):
    observed = check_request(root, request, workstream)
    intent = json.loads(json.dumps(request['intentTemplate']))
    intent['ticket'] = ticket
    own = 'project/' + ticket + '/**'
    intent['allowedPaths'] = sorted(set(intent['allowedPaths'] + [own]))
    intent['delivery']['snapshotMigration'] = {'schema': migration.CONTRACT_SCHEMA,
        'repository': request['repository'], 'baseSha': request['baseSha'], 'sourceSha': request['sourceSha'],
        'sourceTree': observed['sourceTree'], 'inventorySha256': observed['inventorySha256'],
        'authorizationRef': 'authorization:snapshot/' + ticket}
    _, error = governance.validate_intent_value(intent, ticket)
    require(error is None, 'Complete bounded intent required')
    manifest = start.manifest_at(root)
    owned = manifest['coordination']['workstreams'][workstream]['ownedPaths']
    require(manifest['delivery']['targetBranches'] == [request['targetBranch']], 'Target mismatch')
    require(all(any(governance.pattern_covered_by(p, owner) for owner in owned)
                for p in start.material(intent['allowedPaths'])), 'Repair scope exceeds workstream ownership')
    require(not any(p.startswith('project/' + ticket + '/') for p in migration.tree(root, request['sourceSha'])), 'Identity already in source')
    layout = worktree_contract(root).plan(repository=request['repository'], repository_name=primary.name,
        ticket=ticket, slug=request['slug'], primary_checkout=str(primary))
    return {'schema': PROPOSAL_SCHEMA, 'request': request, 'requestDigest': start.digest(request),
            'ticket': ticket, 'intent': intent, 'layout': layout, 'grantsAuthority': False,
            'primaryHead': start.git(primary, 'rev-parse', 'HEAD').strip()}


def highest_identity(root, common):
    highwater = safe(common / 'new-project-ticket-high-water')
    value = highwater.read_text().strip() if highwater.exists() else '0'
    require(re.fullmatch(r'[0-9]+', value), 'Invalid high-water reservation')
    numbers = [int(value)]
    for entry in start.worktrees(root):
        for path in safe(entry['worktree']).glob('project/ticket-*'):
            match = re.fullmatch(r'ticket-([0-9]{3,})', path.name)
            if match:
                numbers.append(int(match[1]))
    refs = start.git(root, 'for-each-ref', '--format=%(refname)', 'refs/heads', 'refs/remotes').splitlines()
    for ref in refs:
        match = re.search(r'/ticket(?:/|-)([0-9]{3,})(?:-|$)', ref)
        if match:
            numbers.append(int(match[1]))
        paths = start.git(root, 'ls-tree', '-d', '-r', '--name-only', ref, 'project').splitlines()
        numbers.extend(int(m[1]) for p in paths if (m := re.fullmatch(r'project/ticket-([0-9]{3,})', p)))
    return max(numbers)


def prepare(root, request_path, workstream):
    root, primary, common = context(root)
    request = load(safe(request_path))
    check_request(root, request, workstream)
    with allocation_lock(common):
        # Observation does not authorize an import. No branch, checkout, lease
        # or source carrier is created in this reservation-only phase.
        observation = start.inspect(root, workstream, request['intentTemplate']['allowedPaths'])
        require(observation['targetObservations'].get('refs/remotes/origin/' + request['targetBranch'], observation['targetObservations'].get('refs/heads/' + request['targetBranch'])) == request['baseSha'], 'Stale proposal base')
        directory = safe(common / 'new-project-snapshot-reservations')
        directory.mkdir(exist_ok=True)
        path = directory / (hashlib.sha256(request['requestId'].encode()).hexdigest() + '.json')
        if path.exists():
            proposal = load(path)
            require(proposal.get('requestDigest') == start.digest(request), 'Proposal idempotency collision')
            require(proposal == proposal_value(root, primary, request, proposal['ticket'], workstream), 'Proposal changed; preserve and reconcile')
        else:
            number = highest_identity(root, common) + 1
            proposal = proposal_value(root, primary, request, f'ticket-{number:03d}', workstream)
            # Reserve first. A crash can leave a gap, never a duplicate identity.
            atomic_write(common / 'new-project-ticket-high-water', (str(number) + '\n').encode())
            atomic_write(path, (json.dumps(proposal, indent=2) + '\n').encode())
        return {'proposalPath': str(path), 'proposalSha256': raw_digest(path), **proposal}


def admit(root, intent, grant):
    report = start.inspect(root, intent['workstream'], intent['allowedPaths'])
    contract = intent['delivery']['snapshotMigration']
    require(report['targetObservations'].get('refs/remotes/origin/' + intent['delivery']['targetBranch'], report['targetObservations'].get('refs/heads/' + intent['delivery']['targetBranch'])) == contract['baseSha'], 'Protected base moved')
    require(report['activeTicketCount'] < report['workstreamLimit'], 'Workstream already occupied')
    source_tree = migration.tree(root, contract['sourceSha'])
    imports = set(grant['implementationPaths'])
    for blocker in report['blockers']:
        require(blocker['reason'] in {'pending-delta', 'unassigned-branch-delta'}, 'Live repair scope is contested')
        if blocker['path']:
            peer = next(e for e in report['worktrees'] if e['path'] == blocker['path'])
            require(not start.intersects(report['requestedPaths'], peer['allDirtyPaths']), 'Dirty repair scope is contested')
            head = peer['headSha']
        else:
            head = start.git(root, 'rev-parse', blocker['branch']).strip()
        migration.git(root, 'merge-base', '--is-ancestor', contract['sourceSha'], head)
        peer_tree = migration.tree(root, head)
        contested = [p for p in start.changes(root, contract['baseSha'], head)
                     if start.path_ignored(p, tuple(report['requestedPaths']))]
        require(all(p in imports and source_tree.get(p) == peer_tree.get(p) for p in contested), 'Peer carries an independent repair')
    return report


def validate_candidate(root, proposal, authorization, digest, head):
    # Run this installed managed checker, never executable code from candidate.
    adopted = (root / '.governance/manifest.json').exists()
    argv = ['--root', str(root), '--base', proposal['request']['baseSha'], '--head', head,
        '--manifest', '.governance/manifest.json' if adopted else 'governance/manifest.hub.json',
        '--stack-profiles', '.governance/stack-profiles.json' if adopted else 'governance/stack-profiles.json',
        '--work-classification', '.governance/work-classification.dsl.json' if adopted else 'governance/work-classification.dsl.json',
        '--expected-repository', proposal['request']['repository'], '--migration-branch', proposal['layout']['branch'],
        '--migration-authorization', str(authorization), '--migration-authorization-sha256', digest,
        '--actor', 'ci', '--no-cache']
    if adopted:
        argv += ['--lock', '.governance/manifest.lock.json']
    with redirect_stdout(io.StringIO()):
        result = governance.main(argv)
    require(result == 0, 'Candidate governance validation failed; preserve detached checkout')


def materialize(root, request_path, store, authorization, authorization_digest, workstream):
    root, primary, common = context(root)
    request_path, store, authorization = [external(root, common, p) for p in (request_path, store, authorization)]
    request = load(request_path)
    require(isinstance(request, dict) and set(request) == MATERIAL_FIELDS and request['schema'] == MATERIAL_SCHEMA, 'Closed materialization request required')
    for field in ('leaseRevision', 'fencingToken'):
        require(type(request[field]) is int and request[field] > 0, 'Exact positive CAS required')
    path = safe(request['proposalPath'])
    require(path.parent == common / 'new-project-snapshot-reservations', 'Unknown reservation path')
    require(migration.matches(migration.DIGEST, request['proposalSha256']) and raw_digest(path) == request['proposalSha256'], 'Proposal digest mismatch')
    proposal = load(path)
    with allocation_lock(common), recovery.controller_lock(store):
        require(proposal == proposal_value(root, primary, proposal['request'], proposal['ticket'], workstream), 'Reserved subject changed')
        intent, layout = proposal['intent'], proposal['layout']
        branch = 'refs/heads/' + layout['branch']
        grant = migration.load_authorization(root, authorization, authorization_digest)
        contract = intent['delivery']['snapshotMigration']
        expected = {'grantId': contract['authorizationRef'], 'repository': proposal['request']['repository'],
            'ticket': intent['ticket'], 'branch': layout['branch'], 'targetBranch': intent['delivery']['targetBranch'],
            'baseSha': contract['baseSha'], 'contractSha256': migration.digest(contract), 'intentSha256': migration.digest(intent)}
        require(all(grant[k] == v for k, v in expected.items()), 'Grant subject mismatch')
        lease = recovery.validate_lease(store, request, intent, expected['repository'], branch, Path(layout['worktreePath']).name)
        require(lease.get('planHash') == hashlib.sha256(intent_bytes(intent)).hexdigest(), 'Controller plan differs')
        before_refs = start.git(root, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes')
        before = admit(root, intent, grant)
        require(start.git(root, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes') == before_refs, 'Refs changed during admission')
        checker = worktree_contract(root)
        require(checker.feature_probe(from_worktree=str(primary))['supported'], 'Relative worktrees unsupported')
        require(not checker.validate(layout) and not checker.validate_filesystem(layout), 'Unsafe layout')
        candidate = safe(layout['worktreePath'])
        lease_path = safe(layout['leasePath'])
        require(not candidate.exists() and not lease_path.exists() and not start.git(root, 'show-ref', '--verify', branch, optional=True), 'Candidate already exists; preserve and reconcile')
        # Build an unpublished object with an isolated temporary index. This is
        # the managed import transport, not an ordinary author commit. The full
        # trusted gate runs before creating a branch ref; no hooks are disabled.
        index = common / ('snapshot-index-' + intent['ticket'])
        require(not index.exists(), 'Interrupted candidate index exists')
        environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        environment['GIT_INDEX_FILE'] = str(index)
        def git(*args, data=None):
            return subprocess.check_output(['git', '--no-replace-objects', '-C', str(root), *args], input=data, env=environment, stderr=subprocess.PIPE).decode().strip()
        try:
            git('read-tree', contract['sourceSha'])
            prefix = 'project/' + intent['ticket'] + '/'
            readme = f"# {intent['ticket']}: {intent['summary']}\n\n- **Status**: IN_PROGRESS\n- **Workflow state**: EDIT\n\n## Acceptance criteria\n\n"
            readme += ''.join(f"- [ ] {v['criterion']}: Validate accepted intent.\n" for v in intent['delivery']['validation'])
            for name, raw in (('README.md', readme.encode()), ('intent.json', intent_bytes(intent))):
                oid = git('hash-object', '-w', '--stdin', data=raw)
                git('update-index', '--add', '--cacheinfo', '100644', oid, prefix + name)
            tree = git('write-tree')
            head = git('commit-tree', tree, '-p', contract['baseSha'], '-p', contract['sourceSha'], '-m', intent['ticket'] + ': preserve approved snapshot')
        finally:
            if index.exists():
                index.unlink()  # Only this exact private scratch index.
        migration.git(root, 'worktree', 'add', '--relative-paths', '--detach', str(candidate), head)
        require(not Path((Path(start.git(candidate, 'rev-parse', '--absolute-git-dir').strip()) / 'gitdir').read_text().strip()).is_absolute(), 'Relative backlink required')
        migration.prove(candidate, intent, base=contract['baseSha'], head=head, repository=expected['repository'], branch=layout['branch'], authorization_path=authorization, authorization_sha256=authorization_digest)
        validate_candidate(candidate, proposal, authorization, authorization_digest, head)
        # Compare all original checkouts and refs immediately before the one ref
        # effect. A concurrent changed source/dirty scope never grants takeover.
        require(start.git(root, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes') == before_refs, 'Refs changed before publication')
        for entry in before['worktrees']:
            require(start.git(Path(entry['path']), 'rev-parse', 'HEAD').strip() == entry['headSha'] and start.dirty_observation(Path(entry['path']))[1] == entry['dirtyDigest'], 'Peer changed before publication')
        migration.load_authorization(candidate, authorization, authorization_digest)
        lease = recovery.validate_lease(store, request, intent, expected['repository'], branch, candidate.name)
        require(lease.get('planHash') == hashlib.sha256(intent_bytes(intent)).hexdigest(), 'Controller plan changed before publication')
        require(raw_digest(path) == request['proposalSha256'], 'Proposal changed before publication')
        for ref, observed in before['targetObservations'].items():
            require(start.git(root, 'rev-parse', ref).strip() == observed, 'Target changed before publication')
        lease_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(lease_path, (json.dumps(lease, indent=2) + '\n').encode())
        migration.git(root, 'update-ref', branch, head, '0' * 40)
        migration.git(candidate, 'symbolic-ref', 'HEAD', branch)
        return {'schema': 'new-project.snapshot-materialization-result/v1', 'ticket': intent['ticket'],
            'headSha': head, 'worktree': str(candidate), 'branch': layout['branch'],
            'leaseId': lease['leaseId'], 'leaseRevision': lease['leaseRevision'], 'fencingToken': lease['fencingToken'],
            'grantsMergeAuthority': False, 'proposalSha256': request['proposalSha256']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workstream', required=True)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument('--prepare', type=Path)
    command.add_argument('--materialize', type=Path)
    parser.add_argument('--lease-store', type=Path)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--authorization-sha256')
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            require(not any((args.lease_store, args.authorization, args.authorization_sha256)), 'Proposal has no authority inputs')
            result = prepare(args.root, args.prepare, args.workstream)
        else:
            require(all((args.lease_store, args.authorization, args.authorization_sha256)), 'Protected materialization inputs required')
            result = materialize(args.root, args.materialize, args.lease_store, args.authorization, args.authorization_sha256, args.workstream)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.CalledProcessError):
        print('GOV-TICKET-ALLOCATION-003: snapshot allocation rejected; preserve reservations and candidate state, reobserve subject and controller ownership.', file=sys.stderr)
        return 5


if __name__ == '__main__':
    raise SystemExit(main())
