# Agent decisions within an authorized task

This guidance composes session authorization, ticket ownership and workspace
observation. It grants no new Git, deployment, credential or cleanup authority.

## Decide from the requested effect

1. Recover the current request, recorded intent and existing session authority.
   An instruction to execute remains valid for the same outcome across turns;
   do not ask again merely because a phase, tool or checkout changed. A new
   request to improve policy does not approve a previously proposed deletion.
2. Identify the next concrete effect, its owner, target and reversibility. Read
   the applicable rule and its activation condition. A warning about a possible
   destructive operation does not require choosing that operation.
3. Inspect current evidence before interpreting a failure: exact command and
   diagnostic, Git identity and ancestry, actual dirty paths, active ticket,
   protected receipts and, when relevant, active processes and leases.
4. Prefer a bounded route already authorized that preserves unknown work.
   Continue disjoint implementation, tests and read-only diagnosis while a
   dependent effect waits. Keep the original requested outcome active.
5. Ask only when necessary information or authority is still missing. Before
   asking, finish the independent preparation so the choice is reviewable.
   State the exact operation and target, evidence inspected, expected effect,
   preservation or recovery plan, and the rule requiring a new decision.
   Silence, elapsed time, a suggested answer and a diagnostic are not approval.

| Observation | Decision |
| --- | --- |
| Same authorized scope, routine reversible fix and required tests | Proceed within the ticket. |
| Protected delivery is part of the authorized outcome | Invoke the declared validator/controller; its trusted evidence still governs merge/apply. |
| Detached snapshot shares the writer's HEAD and has no competing source delta | Preserve it; common history alone is not a second writer. |
| Branch without a worktree has every unique commit tree present in target history after divergence | Preserve the branch; managed admission can exclude that historical copy from competing deltas, without closing or discarding it. |
| Real competing dirty changes or active overlapping intent | Stop the affected write and resolve ownership; keep disjoint work progressing. |
| Missing or contradictory evidence | Report uncertainty, gather bounded observations; do not infer permission. |
| CI capacity, credentials or another external prerequisite is unavailable | Persist the exact blocker and remaining stages; do not manufacture successful checks. |
| Removing, relocating or repairing unknown work is necessary | Audit and preserve it, then obtain authority for that exact operation unless already explicitly authorized. |

## Separate conflict evidence from cleanup authority

`wellmanifest/worktrees` classifies registrations and their permitted placement.
An `unknown`, legacy or quarantine classification is not proof of a competing
write and does not require cleanup to continue an unrelated canonical ticket.
It also never makes that registration publishable or disposable.

The overlap guard compares dirty changes with the peer's new contribution
since the pair's common ancestor. A shared implementation already present in
both HEADs is inherited context. Two actual dirty writers remain contested;
unresolved ancestry retains conservative checking. Intent ownership remains a
separate check even when Git can merge file contents.

`wellmanifest/git-lifecycle` still owns cleanup effects; `ticket-lifecycle`
owns reservations, and protected merge/publication controllers own external
effects. Fix an incorrect checker at its HOME with a failing regression and
adopt the verified revision. Do not disable a hook, edit a managed hash by
hand, add a blanket ignore, or delete evidence merely to make a gate green.

## Report the achieved stage

### Cheap preflight before expensive validation

First resolve the existing ticket and checkout, dirty paths, actual remote
publication and the next requested effect. The managed work-start query's
optional `--observe-publication` reports remote branch evidence without fetch;
its default local admission and authority boundaries remain unchanged. A local
branch ahead of `main` or its upstream can already be published on a different
remote ticket branch. Reconcile that binding, not an imaginary lost push.

Before launching a long publication suite, use the declared publisher's
read-only preflight, when available, to check ticket/branch identity, accepted
base, commit-message syntax, delivery mode, configuration and pinned tools.
Report an unavailable preflight rather than inventing a command or bypassing
the publisher. Put the cheap checks first; still run required validation and
recheck exact HEAD and fencing at the effect boundary. There is no new gate.

Report the current phase, elapsed time, evidence timestamp, exact HEAD and
next bounded action. Do not reset a retry counter or rerun an unchanged
deterministic failure as if it were progress. Cache only against all evidence
inputs; a cached test result never becomes trusted approval.

### Recovery before another attempt

Resolve the emitted diagnostic in the canonical diagnostics registry and use
its managed runbook. In particular, branch lifecycle `002` means a branch
without an open PR, whereas `003` means a missing, malformed or inconsistent
snapshot. Neither finding grants cleanup authority. Read closed PRs and exact
refs before deciding whether delivery, observation or reconciliation is needed.

Every recovery answer names the next bounded action, its existing authority,
the verification that completes it and what remains preserved if it fails.
Reuse the current ticket, checkout and pending-effect journal. A repeated
deterministic failure with unchanged inputs calls for diagnosis or a changed
prerequisite, not another identical effect, fresh ticket or empty PR. A timed-out
remote operation is observed before retry; a matching remote head means the
push is already present, not that its PR was merged.

Run the gate appropriate to the adopted delivery path; this guidance does not
create a draft-push exemption or waive a failed required check. Continue safe
diagnosis and authorized disjoint work while the dependent effect waits.

### Evidence by stage

Distinguish source edited, tests passed, commit created, PR open, trusted merge,
deployment applied and public behavior verified. Each claim needs evidence
from that stage. A local preview, HTTP 200, an unchanged version number, or a
completed coding ticket alone cannot prove the requested production change.
When blocked, preserve the work and name the remaining dependent effect;
do not describe the overall task as completed.
