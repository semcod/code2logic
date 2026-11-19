#!/usr/bin/env python3
"""Explicit current-owner scope correction for first native packaging adoption.

Only unchanged, existing packaging markers in the installed published contract
may be added. The controller changes the intent and fenced reservation, never
packaging source, expiry, owner, publication state or another checkout.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import re
import sys


def sibling(name):
    path = Path(__file__).parent
    sys.path.insert(0, str(path))
    try:
        spec = importlib.util.spec_from_file_location('_packaging_scope_' + name, path / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


store = sibling('terminal_lease_release')
start = sibling('work_start_check')
allocation = sibling('snapshot_allocation')
FIELDS = {'schema', 'requestId', 'ticket', 'headSha', 'paths', 'leaseRevision',
          'fencingToken', 'leaseSha256', 'intentSha256', 'bootstrapReceiptSha256'}
# Closed capability of this published controller. A target-owned contract and
# its rewritten hashes cannot introduce another executable source path.
SUPPORTED_MARKERS = frozenset({'pyproject.toml', 'package.json'})
require, sha, encoded = store.require, store.sha, store.encoded


def raw(path):
    with store.directory(path.parent) as (fd, verify):
        value = store.read_at(fd, path.name, private=True)
        verify()
        return value


def request_value(path, primary):
    path = path.absolute()
    require(not path.is_relative_to(primary), 'request_must_be_external')
    request = store.decode(raw(path))
    require(isinstance(request, dict) and set(request) == FIELDS
            and request['schema'] == 'new-project.bootstrap-packaging-scope/v1', 'invalid_request')
    require(isinstance(request['requestId'], str)
            and re.fullmatch('[a-z0-9][a-z0-9.-]{0,95}', request['requestId']), 'invalid_request_id')
    require(isinstance(request['ticket'], str) and re.fullmatch('ticket-[0-9]{3,}', request['ticket']), 'invalid_ticket')
    for key in ('leaseSha256', 'intentSha256', 'bootstrapReceiptSha256'):
        require(isinstance(request[key], str) and re.fullmatch('[0-9a-f]{64}', request[key]), 'invalid_digest')
    require(isinstance(request['headSha'], str) and re.fullmatch('[0-9a-f]{40}', request['headSha']), 'invalid_head')
    require(all(type(request[k]) is int and request[k] > 0 for k in ('leaseRevision', 'fencingToken')), 'invalid_cas')
    paths = request['paths']
    require(isinstance(paths, list) and 0 < len(paths) <= 8
            and all(isinstance(p, str) and re.fullmatch('[A-Za-z0-9_.-]+', p)
                    and p not in {'.', '..'} for p in paths)
            and len(paths) == len(set(paths)), 'literal_unique_packaging_markers_required')
    return request


def pinned_packaging(root, primary, request):
    receipt_path = root / '.subactor/receipts/bootstrap-adoption.json'
    receipt_raw = raw(receipt_path)
    require(sha(receipt_raw) == request['bootstrapReceiptSha256'], 'bootstrap_receipt_changed')
    receipt = store.decode(receipt_raw)
    lock_raw = raw(root / '.governance/manifest.lock.json')
    lock = store.decode(lock_raw)
    standard = lock.get('standard', {})
    require(receipt.get('schema') == 'new-project.bootstrap-adoption/v1'
            and receipt.get('bootstrapKind') in {'legacy-scaffold', 'fresh'}
            and receipt.get('baseSha') == request['headSha']
            and receipt.get('commonGitDir') == store.git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')
            and receipt.get('sourceRevision') == standard.get('sourceRevision')
            and standard.get('sourceRepository') == 'wellmanifest/new-project'
            and standard.get('publicationStatus') == 'published'
            and re.fullmatch('[0-9a-f]{40}', str(standard.get('sourceRevision', ''))), 'published_bootstrap_required')
    files = receipt.get('files', {})
    require(isinstance(files, dict) and files.get('.governance/manifest.lock.json') == sha(lock_raw), 'bootstrap_lock_changed')
    managed = lock.get('managedFiles')
    require(isinstance(managed, dict) and managed, 'managed_pin_required')
    for name, digest in managed.items():
        require(isinstance(name, str) and not Path(name).is_absolute()
                and '..' not in Path(name).parts, 'unsafe_managed_path')
        require(sha(raw(root / name)) == digest, 'managed_pin_drift')
    contract_path = '.governance/agent-hosts.json'
    contract_raw = raw(root / contract_path)
    require(files.get(contract_path) == sha(contract_raw)
            and managed.get(contract_path) == sha(contract_raw), 'packaging_contract_unbound')
    contract = store.decode(contract_raw).get('packaging', {})
    require(isinstance(contract, dict), 'packaging_contract_invalid')
    markers = {row.get('marker') for row in contract.values() if isinstance(row, dict)}
    require(set(request['paths']) <= markers & SUPPORTED_MARKERS, 'path_is_not_published_packaging_marker')
    if receipt['bootstrapKind'] == 'legacy-scaffold':
        start.bootstrap_scaffold_at_head(root, request['headSha'])
    else:
        require(not store.git(root, 'ls-tree', request['headSha'], '--', '.governance'), 'fresh_base_has_governance')
    for name in request['paths']:
        content = raw(root / name)
        row = store.git(root, 'ls-tree', request['headSha'], '--', name)
        require(row.startswith(('100644 blob ', '100755 blob ')) and row.endswith('\t' + name), 'committed_regular_marker_required')
        require(store.git(root, 'hash-object', '--no-filters', '--', name)
                == row.split()[2], 'packaging_source_changed')
        require(store.git(root, 'diff', 'HEAD', '--', name) == '', 'packaging_index_or_mode_changed')
        require(content == raw(root / name), 'packaging_observation_changed')
    return standard['sourceRevision']


def transaction(root, primary, request, lease_raw, intent_raw, actor, session, stamp):
    lease, intent = store.decode(lease_raw), store.decode(intent_raw)
    require(sha(lease_raw) == request['leaseSha256'] and sha(intent_raw) == request['intentSha256'], 'scope_cas_changed')
    require(not store.canonical.validate_lease(lease), 'invalid_canonical_lease')
    require((lease['ownerActor'], lease['ownerSession']) == (actor, session), 'current_owner_required')
    require((lease['leaseRevision'], lease['fencingToken'])
            == (request['leaseRevision'], request['fencingToken']), 'stale_fencing')
    require(lease['phase'] in {'claimed', 'editing', 'validating'} and not lease['publicationFrozen'], 'inactive_or_frozen_lease')
    now = datetime.now(timezone.utc)
    issued, heartbeat, expiry = (datetime.fromisoformat(lease[k].replace('Z', '+00:00'))
                                 for k in ('issuedAt', 'heartbeatAt', 'expiresAt'))
    require(issued <= heartbeat <= now < expiry, 'live_owner_required')
    require(root.name == lease['worktreeId'] and lease['ticketId'] == request['ticket']
            and lease['workstream'] == intent.get('workstream') == 'governance'
            and intent.get('ticket') == request['ticket']
            and intent.get('schema') == 'new-project.intent/v3', 'ticket_scope_mismatch')
    match = store.WORKTREE_ID_RE.fullmatch(root.name)
    require(match is not None and match[1] == request['ticket'], 'canonical_worktree_required')
    branch = 'refs/heads/ticket/' + match[2] + '-' + match[3]
    require(lease['headSha'] == request['headSha'] and lease['branchRef'] == branch
            and store.git(root, 'symbolic-ref', 'HEAD') == branch
            and store.git(root, 'rev-parse', 'HEAD') == request['headSha'], 'branch_or_head_changed')
    accepted = store._accepted_repositories(primary)
    require(lease['repositoryRef'] in accepted, 'repository_binding_mismatch')
    old_paths = intent.get('allowedPaths')
    require(isinstance(old_paths, list) and start.digest(old_paths) == lease['scopeHash'], 'intent_scope_unbound')
    require(not set(request['paths']) & set(old_paths)
            and not any(start.path_ignored(p, tuple(intent.get('forbiddenPaths', []))) for p in request['paths']), 'path_already_owned_or_forbidden')
    revision = pinned_packaging(root, primary, request)
    delivery = intent.get('delivery', {})
    require(delivery.get('acceptedBaseSha') == request['headSha']
            and delivery.get('targetBranch') == lease['targetBranch']
            and delivery.get('standardAdoption') == {'sourceRepository': 'wellmanifest/new-project',
                    'fromRevision': None, 'toRevision': revision}, 'initial_adoption_intent_required')
    report = start.inspect(root, 'governance', request['paths'])
    require(not report.get('diagnostic') and all(
        b['path'] == str(root) and b['ticket'] == request['ticket'] and b['reason'] == 'scope-reservation'
        for b in report['blockers']), 'packaging_scope_contested')
    intent['allowedPaths'] = [*old_paths, *request['paths']]
    command = {'schema': store.canonical.REQUEST_SCHEMA, 'requestId': request['requestId'] + '-scope',
               'leaseId': lease['leaseId'], 'action': 'heartbeat', 'expectedRevision': lease['leaseRevision'],
               'expectedFencingToken': lease['fencingToken'], 'expectedPhase': lease['phase'],
               'requestedBy': actor, 'idempotencyKey': request['requestId'] + ':scope',
               'targetHeadSha': request['headSha'], 'replacementReceiptRef': None,
               'authorityRef': 'policy:explicit-bootstrap-packaging-scope', 'requestedAt': stamp}
    receipt, errors = store.canonical.evaluate_transition(lease, command)
    require(not errors, 'scope_transition_refused')
    lease.update(scopeHash=start.digest(intent['allowedPaths']), leaseRevision=receipt['leaseRevision'],
                 fencingToken=receipt['fencingToken'], heartbeatAt=stamp,
                 previousReceiptRef=receipt['receiptRef'], eventSequence=lease['eventSequence'] + 1)
    require(not store.canonical.validate_lease(lease), 'invalid_amended_lease')
    return encoded(lease), encoded(intent), receipt


def amend(root, request_path, actor, session, *, apply=False):
    root = Path(root).absolute()
    registrations = start.worktrees(root)
    _, primary, common = allocation.context(root)
    require(root == root.resolve() == primary / '.worktrees' / root.name
            and any(row['worktree'] == str(root) for row in registrations), 'canonical_registered_checkout_required')
    request = request_value(Path(request_path), primary)
    request_digest = sha(encoded({'request': request, 'actor': actor, 'session': session}))
    journal_dir = primary / '.subactor/receipts/bootstrap-packaging-scope'
    journal_name = request['requestId'] + '.json'
    lease_name = root.name + '.json'
    intent_dir = root / 'project' / request['ticket']
    with (allocation.allocation_lock(common) if apply else nullcontext()), \
            store.directory(primary / '.subactor/leases') as (lfd, verify_lease), \
            store.directory(intent_dir) as (ifd, verify_intent):
        with (store.lease_lock(lfd, lease_name, verify_lease) if apply else nullcontext(verify_lease)) as verify:
            current_lease = store.read_at(lfd, lease_name, private=True)
            current_intent = store.read_at(ifd, 'intent.json', private=True)
            saved = None
            try:
                saved = store.decode(raw(journal_dir / (journal_name + '.prepared')))
            except FileNotFoundError:
                pass
            if saved is not None:
                require(saved.get('requestSha256') == request_digest, 'request_identity_reused')
                before_lease = base64.b64decode(saved['beforeLease'], validate=True)
                before_intent = base64.b64decode(saved['beforeIntent'], validate=True)
                stamp = saved['stamp']
            else:
                before_lease, before_intent = current_lease, current_intent
                stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
            after_lease, after_intent, transition = transaction(
                root, primary, request, before_lease, before_intent, actor, session, stamp)
            record = {'schema': 'new-project.bootstrap-packaging-scope-receipt/v1',
                      'requestSha256': request_digest, 'stamp': stamp,
                      'beforeLease': base64.b64encode(before_lease).decode(),
                      'beforeIntent': base64.b64encode(before_intent).decode(),
                      'afterLeaseSha256': sha(after_lease), 'afterIntentSha256': sha(after_intent),
                      'paths': request['paths'], 'transition': transition}
            require(saved is None or saved == record, 'prepared_transaction_changed')
            require((current_lease, current_intent) in ((before_lease, before_intent),
                    (after_lease, before_intent), (after_lease, after_intent)), 'partial_transaction_changed')
            if not apply:
                return {'status': 'planned', 'paths': request['paths'], 'grantsAuthority': False}
            with store.directory(journal_dir, create=True) as (jfd, verify_journal):
                if saved is None:
                    store.atomic_at(jfd, journal_name + '.prepared', encoded(record), exclusive=True)
                # Re-observe pins, packaging bytes and competing reservations at
                # the effect boundary; the durable preparation is not authority.
                require(transaction(root, primary, request, before_lease, before_intent,
                                    actor, session, stamp) == (after_lease, after_intent, transition),
                        'scope_observation_changed')
                verify(); verify_intent(); verify_journal()
                require(store.read_at(lfd, lease_name, private=True) == current_lease
                        and store.read_at(ifd, 'intent.json', private=True) == current_intent, 'scope_cas_changed')
                require(store.git(root, 'rev-parse', 'HEAD') == request['headSha'], 'head_changed_before_apply')
                # Fence the prior reservation before exposing its expanded intent.
                if current_lease == before_lease:
                    store.atomic_at(lfd, lease_name, after_lease)
                if current_intent == before_intent:
                    store.atomic_at(ifd, 'intent.json', after_intent)
                require(store.read_at(lfd, lease_name, private=True) == after_lease
                        and store.read_at(ifd, 'intent.json', private=True) == after_intent, 'applied_scope_changed')
                verify(); verify_intent(); verify_journal()
                try:
                    require(store.read_at(jfd, journal_name) == encoded(record), 'completed_receipt_changed')
                except FileNotFoundError:
                    store.atomic_at(jfd, journal_name, encoded(record), exclusive=True)
            lease = store.decode(after_lease)
            return {'status': 'amended', 'ticket': request['ticket'], 'worktreePath': str(root),
                    'receipt': str(journal_dir / journal_name), 'paths': request['paths'],
                    'leaseRevision': lease['leaseRevision'], 'fencingToken': lease['fencingToken'],
                    'expiresAt': lease['expiresAt'], 'grantsEditAuthority': False, 'grantsMergeAuthority': False,
                    'writerEnvironment': {'NEW_PROJECT_WRITER_ACTOR': actor, 'NEW_PROJECT_WRITER_SESSION': session,
                        'NEW_PROJECT_LEASE_REVISION': str(lease['leaseRevision']),
                        'NEW_PROJECT_FENCING_TOKEN': str(lease['fencingToken'])}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(amend(args.root, args.request, args.actor, args.session, apply=args.apply), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, PermissionError, start.ObservationError) as error:
        print('GOV-BOOTSTRAP-PACKAGING: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
