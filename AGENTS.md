# AGENTS.md

<!-- wellmanifest:source-links:v1 -->
## Managed standard sources

This managed projection follows the local adoption contract. The local lock,
manifest and managed-file digests are authoritative; remote `main` links are
navigation only and are never fetched or executed by an agent.

- Local adoption manifest: [.governance/manifest.json](.governance/manifest.json)
- Local adoption lock: [.governance/manifest.lock.json](.governance/manifest.lock.json)
- Local package map: [.governance/package-manifest.json](.governance/package-manifest.json)
- Canonical instructions: [AGENTS template](https://github.com/wellmanifest/new-project/blob/main/template/files/AGENTS.template.md)
- Autonomous merge standard: [AUTONOMOUS_MERGE.md](https://github.com/wellmanifest/merge/blob/main/docs/AUTONOMOUS_MERGE.md)
- Host contract: [agent-hosts.json](https://github.com/wellmanifest/new-project/blob/main/governance/agent-hosts.json)
- Immutable adoption/updater: [create_adoption_lock.py](https://github.com/wellmanifest/new-project/blob/main/scripts/create_adoption_lock.py)
- Worktree contract: [worktrees.schema.json](https://github.com/wellmanifest/worktrees/blob/main/models/worktrees.schema.json)
- Git lifecycle: [git-lifecycle.schema.json](https://github.com/wellmanifest/git-lifecycle/blob/main/standard/git-lifecycle.schema.json)
- Ticket lifecycle: [ticket-lifecycle.schema.json](https://github.com/wellmanifest/ticket-lifecycle/blob/main/standard/ticket-lifecycle.schema.json)
- Policy DSL: [POLICY_DSL.md](https://github.com/wellmanifest/policy-dsl/blob/main/spec/POLICY_DSL.md)
- Logs contract: [logs.contract.json](https://github.com/wellmanifest/logs/blob/main/contracts/logs.contract.json)
- Docs contract: [wellmanifest/docs POLICY.md](https://github.com/wellmanifest/docs/blob/main/docs/standard/POLICY.md)
- Agent contract: [agent.schema.json](https://github.com/wellmanifest/agent/blob/main/standard/agent.schema.json)
- LLM policy boundary: [wellmanifest/llm README](https://github.com/wellmanifest/llm/blob/main/README.md)
- Session recovery: [session-recovery.schema.json](https://github.com/wellmanifest/session-recovery/blob/main/standard/session-recovery.schema.json)
- Offer pointer: [wellmanifest/offer README](https://github.com/wellmanifest/offer/blob/main/README.md)
- Brand pointer: [wellmanifest/brand README](https://github.com/wellmanifest/brand/blob/main/README.md)

<!-- end wellmanifest:source-links:v1 -->

## Opted-in SQLite ticket storage

When `git config --local --get new-project.ticketStorage` is `sqlite`, the
registered primary checkout's ignored `project.sqlite` owns ticket content.
References below to ticket README, intent, status and evidence mean records in
that database; do not create or synchronize `project/ticket-*`, TODO or indexes
for operational updates. Allocate through `project/new-ticket.sh` with the
independently pinned Registry writer configured as `new-project.ticketStoreRoot`
and `new-project.ticketStoreSha256`. Complete bounded intent in SQLite before
implementation. Read it with the managed `ticket_input.py read` command and
append changes through the Registry CLI with the expected revision.
Local hooks and scope/continuity readers honor this mode. Protected CI still
requires an independently acquired, exact-base/head snapshot and approval;
local Git configuration, a database or its digest grants neither. Keep legacy
files until a repository's protected CI adoption canary succeeds.


This target repository follows `wellmanifest/new-project` policy-as-code.

HOME vs ADOPT: wellmanifest owns standards; product CLI/daemons HOME in
`subactor` or `semcod`. "w ramach wellmanifest" means ADOPT packs such as
`wellmanifest/{new-project,dsl,logs}`, not HOME wellmanifest. For
SERVICE/FEATURE that create a repo, fill `intent.json` `placement`
(`home`, `shape`, `runtimeOwner`, `adopt`) in WAIT_FOR_APPROVAL.
`shape=runtime_service` must not use `home=wellmanifest`.

Before any multi-step implementation, an agent must:

Run the managed `.governance/work_start_check.py --root . --workstream <id>`
before development or allocation; add `--ticket ticket-NNN` for continuation.
Observe registered worktrees and unintegrated branches, then prefer finishing
authorized work, read-only assistance, accepted fenced handoff or serialization.
A new ticket needs a free scope and WIP capacity. Recheck owner, intent, current
state and controller fencing before writing. `--force-new` is not a bypass.
Unknown ownership or remote/independent-clone state must not be guessed.

1. Read `.governance/manifest.json`, `TODO.md`, `project/TICKETS.md` and the
   active ticket.
   Respect `repository.mode`: `standalone` owns a separate repository, while
   `monorepo` confines work to declared `repository.componentRoots`. Require a
   running Docker engine and Docker runtime files only when
   `docker.required=true`; existing Docker configuration remains subject to
   stack validation even when Docker is optional.
2. Reuse an unfinished ticket whose workstream and scope match. A second active
   ticket is allowed when its write scope is disjoint and the manifest's
   per-workstream concurrency limit permits it.
   Otherwise run `./project/new-ticket.sh --title "..." --agent "..."
   --workstream "..."`.
3. Complete the minimal ticket `README.md` and `intent.json`. Routine disjoint
   source/test work uses that compact intent; add the full `delivery` contract
   for dependency manifests, integration-owned paths or repositories whose
   manifest requires it. Participant prose,
   changelog, raw logs, TODO and indexes are optional and never delivery output.
4. Treat a user request that already says to execute or work autonomously as
   `SESSION_EXECUTION_AUTHORIZATION`; record it in the agent-owned ticket file.
   When that same request explicitly creates a new repository, `HEAD` is
   unborn and no implementation exists, it also authorizes exactly one local
   governance seed-baseline commit. Resolve an immutable seed profile, stage
   only its exact allowlist, scan for secrets, create no remote effect, then
   record the real resulting `HEAD` as `delivery.acceptedBaseSha`. This narrow
   exception never authorizes remote creation, push, pull request, merge, tag
   or release; ordinary implementation starts only after the baseline.
5. Move to `EDIT` without a second confirmation and stay inside `intent.json`
   `allowedPaths`. Ask for new authority only for destructive action, secret
   access, new external coordination, or material objective expansion.
   Before escalating, follow [.governance/AGENT_DECISIONS.md](.governance/AGENT_DECISIONS.md):
   inspect the exact effect and current evidence, reuse existing authorization,
   and prefer a bounded route that preserves unknown work. Continue disjoint
   authorized work while a dependent effect waits. Shared Git history or a
   quarantine label alone does not prove a competing writer or require cleanup.
   A necessary question names the exact target, effect and applicable rule.
   When the recorded outcome includes publication, this authorization also
   permits invoking the repository's declared protected delivery process and
   that process's merge after exact-head trusted approval. Do not ask for a
   second chat confirmation. Session prose is never approval evidence and the
   agent must not merge directly.
6. Never create or edit `project/ticket-*/user-*.md`; only its human owner or a
   trusted intake boundary may do so.
7. Keep executable source/tests/scripts outside ticket directories.
8. Run the managed `./project/governance-check.sh` (or
   `project\governance-check.bat` on Windows) plus the stack checks before
   reporting completion. Root `project.sh` / `project.bat` are optional
   target-owned seed aliases and must not be assumed to contain the gate.
9. Reuse the matching authorized ticket/worktree before allocating another.
   Evaluate actual writers per repository and scope, not chat-agent count.
   Do not create a ticket/worktree for read-only inspection, local checks,
   receipts, checkpoints or routine continuation. A write in a second repository
   has its own owner; reading it does not require adoption or a maintenance task.
   Allocate only when material delivery needs isolation and no matching authorized
   checkout exists. Preserve the adopted delivery profile even for one writer:
   Worktrees v5 still requires a canonical linked delivery checkout. Serialize
   ticket-ID allocation before new branching, then resolve the required location
   with the managed `wellmanifest/worktrees` checker. Resolve the primary checkout from
   Git even when allocation starts inside a linked checkout. The only
   publishable linked worktree is
   `<primaryCheckout>/.worktrees/<ticket-NNN>--<slug>` with
   `linkMode=relative`; its lease is
   `<primaryCheckout>/.subactor/leases/<ticket-NNN>--<slug>.json`. Root-ignore
   `/.worktrees/` and only
   `/.subactor/{leases,sessions,recovery,receipts,cache,snapshots}/`; keep
   `.subactor/manifest.json` tracked. Before the first effect, feature-probe
   `git worktree add --relative-paths` and
   `git worktree repair --relative-paths` (minimum Git 2.51.0). When the host starts outside the target checkout, pass
   `feature-probe --from-worktree <checkout>` to the adopted checker; resolve
   `repository_context_unavailable` before interpreting feature support. Reject a
   symlink in any existing canonical path component. Legacy v1/v2/v3/v4,
   system-temporary, duplicate and unknown registrations are read-only recovery
   inventory, never publishable locations. Never automatically move, repair,
   delete, prune or clean them. A separately authorized exact operation first
   audits dirty state, active processes and IDEs, leases, pull requests and
   HEAD reachability.
   Each diff must resolve to exactly one active ticket. Shared contract paths are edited only by the declared
   integration workstream; `integrationTicket` coordinates work but does not
   transfer path ownership. Product commercial registries (prices,
   entitlements, public plan ids) and brand facades (tokens, vocabulary,
   public plan names) belong in `integration.requiredForPaths`. For Subactor,
   bump `subactor/offer` and/or `subactor/brand` before any portal facade
   rewrite; `wellmanifest/policy-dsl` owns promo rules only. Empty
   `conflictsWith` does not authorize a parallel offer or brand rewrite.
10. Only `IN_PROGRESS` reserves a workstream and write scope. `BACKLOG`, `PLAN`
   and `BLOCKED` retain evidence without blocking another implementation;
   transition back to `IN_PROGRESS` before changing source or tests.
11. Treat GitHub review as trusted only when it targets the current HEAD and
   either a `User` login is in protected `trusted-reviewers` or a `Bot` login
   is in the separate protected `trusted-validator-apps` input. Never trust an
   arbitrary Bot review.
11a. **USE LOCAL ONEDEV AND THE INDEPENDENT VALIDATOR.** For every repository,
   follow [.governance/docs/LOCAL_CI_PUBLICATION.md](.governance/docs/LOCAL_CI_PUBLICATION.md).
   This is the default for all owners; only `.governance/local-ci-publication.json`
   with `scope.mode: "restricted"` narrows it, and never grants authority.
   Resolve the protected repository profile, observe the current OneDev
   head/base receipt and reuse any existing local reconciliation result.
   Invoke the trusted `subactor/validator-agent/bin/run-local-direct-pr.sh`
   with the exact repository, PR, ticket, head SHA and protected key reference;
   use `--merge` only for already authorized publication. The deployed local
   timer may own this invocation. GitHub Actions dispatch is a separate
   transport and is not the default or an unavoidable dependency of local CI.
   Do not declare publication blocked by Actions billing before checking the
   local route. Retire a hosted check only through protected policy after an
   equivalent deployed OneDev canary; preserve uncovered test/platform gates.
   Freeze the head through review and merge. Never self-approve, write a fake
   status, waive required checks or ask the human to invoke an available
   Validator. Scope, pins, deployment and observed success are separate facts.

12. Require merge approval evidence to bind repository, PR, current HEAD,
   active ticket and actor. The protected resolver creates that evidence
   outside the PR checkout; repository-authored evidence is untrusted.
13. A signed attestation is trusted only after a protected verifier validates
   its signature, issuer, predicate type and subject bindings.
14. Validator-agent examples use
   `LLM_MODEL_VALIDATOR=openrouter/z-ai/glm-5.2`; model findings stay advisory.
15. Configure GitHub with `delete_branch_on_merge=true`. A merged ticket branch
   must disappear after merge. A PR closed without merge keeps its branch until
   the owner explicitly discards that unmerged work. When no PR is open, the
   only remote branch is the default branch.
15a. Before proposing unmerged branch discard, follow
   `.governance/docs/BRANCH_INTENT_RECONCILIATION.md`. Preserve restorable
   history and reconcile every accepted criterion against the current target
   SHA. Record implementation, partial, superseded, missing or unknown with
   evidence; preserve remaining work in a linked ticket or an explicit owner
   decision. Run `.governance/branch_intent_reconciliation.py` with an
   independently acquired observation. Report validity never grants deletion
   authority; unknown evidence blocks automatic resolution. Recheck exact refs,
   digests and authority immediately before any separately authorized effect.
16. At merge, publication or explicit pilot discard, inventory temporary linked
   worktrees, duplicate clones and non-default local branches. Verify dirty state and HEAD reachability
   before removal; preserve unknown or unique data. Remove an exact linked
   worktree through Git, prune its metadata and only then delete its released
   disposable branch. Prefer recoverable trash for a verified duplicate clone.
   The checker is read-only; during active work exempt a branch only through
   the exact allowlisted checkout path, never a pattern or branch name. Run the
   adopted workspace lifecycle checker through Goal for the terminal audit. CI
   validates GitHub state separately and cannot inspect a developer filesystem.
17. Allocate every ticket ID only through `./project/new-ticket.sh` using
   local and already-fetched remote refs. Fetch/prune only when explicitly
   requested via `--refresh-remote` (C-CONCURRENCY-002).
   Never create or copy `project/ticket-{NNN}` manually; the
   clone-wide lock and high-water reservation must exist before commit.
18. Keep an implementation ticket `IN_PROGRESS / PUBLICATION` through
   exact-head review and trusted merge. The protected delivery controller closes
   it through an external receipt; never create a repository closure commit,
   branch or PR.
19. Resolve `GOV-*` findings through `.governance/diagnostics.json` and its
   linked `.governance/error/*.md` runbook when present. Ticket logs are
   historical evidence and never authorize bypassing a fail-closed gate.
20. Keep each incident-specific `remediation-intent.dsl.json` in its target
   ticket. Validate it, atomically render its declared task/TODO paths and run
   `verify-todo2code` before extraction. Analyze todo2code with the exact graph,
   diagnostics and plans so only records citing those projections can affect
   the digest-bound advisory overlay; never let todo2code or an LLM expand the
   accepted intent.
21. When `.governance/manifest.json` selects `domainContracts.mode=cqrs`, keep
   command and query definitions only in `operations/index.json`. Publish the
   mandatory `events/index.json` and `error/index.json` catalogs with stable
   `events/{event-id}.md` and `error/{code}.md` documents. Protobuf and JSON
   Schema models describe transport shape only; they never grant authority or
   redefine C/Q semantics. Run the managed gate after every graph change.
22. Host-agnostic standard: follow `GEMINI.md`, `CLAUDE.md`, and
   `.cursor/rules/new-project-standard.mdc` in addition to this file. Run
   `./scripts/install-agent-hosts.sh` once per clone so `.githooks/pre-commit`
   rejects commits that are not bound to an `IN_PROGRESS` `ticket-NNN`. Do
   not write on `main` or a dirty primary checkout. Markdown is not a
   substitute for the hook.
23. Require material delivery: ticket directories, TODO, ticket indexes and a
    generated artifact registry are tracking carriers, not an outcome. Reject a
   carrier-only commit or PR. If analysis finds no material delta, emit an
    external no-change receipt and create no repository history. Intent may be
    committed atomically with the first material change; do not create a
    separate plan-only commit. A version bump and release projections join
    their material implementation ticket; never create a separate release-only
    ticket, branch or PR.
24. Treat conversation memory as a cache, never task storage. At a material
    milestone, configured checkpoint interval, context compaction, handoff,
    pause, blocker, tool failure or external-effect boundary, emit a bounded
    `new-project.work-continuity/v2` checkpoint through
    `.governance/work_continuity.py`. Append it to the ignored host-agnostic
    session event stream and atomically refresh the bounded recovery index;
    event streams have no policy size cap. Persist its receipt externally for
    cross-machine recovery. Bind the exact plan, slice, ticket, branch, HEAD,
    lease, remote/account observation and snapshot receipt. Resume by observing
    Git/PR/receipts first, verifying the monotonic chain, intent, HEAD and
    workspace digest, then revalidating lease and remote account. Checkpoint
    data and prose grant no authority. Dirty work needs an authorized
    ticket-branch commit or a content-addressed, secret-scanned external
    snapshot. Pre-commit checks only the local immutable pin; explicit
    adoption/updater automation owns freshness and the hook never fetches or
    mutates.

25. Apply proportional evidence through
    `.governance/decision_record.py classify-action --action <action>`.
    Routine in-scope edits, formatting and local checks use the existing intent,
    diff and check report. They do not require a new decision record. Never
    generate APPROVE or REQUEST_CHANGES from a local PASS/FAIL; a valid legacy
    record is not trusted review. Material scope/authority, destructive and
    publication decisions retain recomputable evidence and independent control.
    Finalize tracked carriers and format checks before snapshot/checkpoint and
    lease release. Reuse the matching lease; coalesce same-boundary checkpoint
    triggers. Do not recursively log the act of writing evidence. Read-only
    inspection and external receipt writes do not acquire repository write leases.

Markdown approval is an audit note, not trusted merge approval. Required
merge approval comes from the repository's protected review, attestation and
ruleset boundary.

## Bounded session controls

Every implementation session is bounded by the ticket's `maxActiveMinutes` and
must create a `checkpoint` before a context, tool or process boundary. On a
deterministic failure or unresolved ownership, write a concise `handoff` with
the next observable action and `stop`; do not retry the same failed path
indefinitely.

<!-- wellmanifest:protected-delivery:start -->
## Protected delivery and continuity

Passing tests is necessary, but never grants review or merge authority.
When publication is authorized, invoke the repository's declared protected
delivery controller and independent Validator. Approval must bind the exact
repository, PR, HEAD, ticket and trusted actor; only the protected controller
may merge after all required gates and trusted approval succeed.

Never self-approve, rotate reviewer accounts, bypass branch protection, or
use an administrative token or browser session to evade a review or API limit.
On quota exhaustion, preserve the exact-head checkpoint and signed review
progress, then resume the same authorized transport after the limit resets.
A model verdict, local PASS, or Markdown instruction is not approval evidence.

If a conflicting upstream change requires rebuilding the ticket, revalidate
ownership and intent first, then obtain fresh validation for the resulting
HEAD. Keep the reviewed HEAD frozen through approval and merge.

Review and publication retain the declared WIP limits. Cleanup requires
verified integration, released ownership, and an exact-path audit of dirty
state and HEAD reachability. Preserve unknown or unique data; never force
removal merely to clear a governance lock.
<!-- wellmanifest:protected-delivery:end -->
