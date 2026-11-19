---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "continuity-namespaces",
  "kind": "information",
  "version": 1,
  "title": "Preserve continuity history in explicit repository namespaces",
  "status": "proposed",
  "owner": "wellmanifest/new-project",
  "scope": "repository",
  "created": "2026-11-12",
  "updated": "2026-11-12",
  "review_after": "2026-12-12",
  "source_revision": "511eb0ab1c0f9f8697c44f5748ba93b25da5e0d9",
  "affected_repositories": ["wellmanifest/new-project"],
  "evidence": [
    "https://github.com/wellmanifest/new-project/issues/604",
    "repo://wellmanifest/new-project@511eb0ab1c0f9f8697c44f5748ba93b25da5e0d9/scripts/work_continuity.py",
    "repo://wellmanifest/new-project/scripts/continuity_namespace.py",
    "repo://wellmanifest/new-project/tests/continuity_namespace_test.py"
  ]
}
---

# Explicit repository continuity namespaces

<!-- docs:section purpose -->
## Purpose

A canonical origin change can leave the legacy journal bound to its former
repository reference. The baseline revision in the metadata correctly refuses
that foreign binding. This changeset adds an explicit isolated advisory store
while preserving the complete old journal, index and original receipt identities.

<!-- docs:section scope -->
## Scope

`work_continuity.py init-namespace` plans by default. Initialization creates a
selector keyed by SHA-256 of the current canonical repository reference under
`.subactor/recovery/continuity-namespaces/`. Its selected journal and index are
confined to the corresponding ignored repository namespace directories.
Existing matching journals keep their original behavior without initialization.

<!-- docs:section evidence -->
## Evidence

`tests/continuity_namespace_test.py` reproduces the refusal with real Git
origins and CLI commands. It checks planning, capture/resolve/verify, complete
chain validation, original-byte preservation, foreign event rejection, exact
replay, idempotency, occupied stores, links, process contention and interrupted
publication. `tests/work-continuity.test.sh` includes it in the existing gate.
These fixture results establish source behavior, not consumer deployment.

<!-- docs:section content -->
## Procedure and contract

Observe Git, accepted intent, current owner/fencing, PR and terminal receipts
first. Record the actual former repository reference and SHA-256 of the entire
legacy stream. With the published runtime, inspect the read-only plan:

```bash
python3 .governance/work_continuity.py init-namespace --root . \
  --expected-legacy-repository repository:github.com/example/former-name \
  --expected-legacy-sha256 "$OBSERVED_LEGACY_SHA256"
```

Add `--apply` only for the already authorized initialization. It holds the
existing native storage transaction, revalidates the complete legacy chain and
digest, refuses occupied unselected storage and publishes the selector without
replacing any concurrent file. An exact repeat returns `already-enabled`.
All ordinary capture, record, resolve and index operations then use that store.

The new namespace starts empty. Restore only a complete chain already bound to
the current repository through `record`; retain its original digests and order.
Never rewrite old event repository fields or manufacture predecessor receipts.
Historical events remain recoverable under their original identity. A new
canonical origin needs its own explicit initialization; selectors are not aliases.

<!-- docs:section limitations -->
## Limits and authority

This operation does not prove two repository references identify the same
project. A controller handling a rename must separately verify stable repository
identity before treating the histories as related. It neither rebinds old
events nor changes tickets, leases, approvals, protected checks or source scope.
Its result always states `grantsAuthority: false`.

Storage locks serialize cooperating writers. Required identity, digest and
anchored-path checks remain conservative on concurrent changes. Unsupported
filesystem hard links fail initialization while retaining the old store.
Preserve selectors and both histories for recovery; rollback is not deletion.
Published source, qualified consumer support and target activation are separate.
