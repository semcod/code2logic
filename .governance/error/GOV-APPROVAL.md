# GOV-APPROVAL — restore progress through the protected publisher

## Situation

An implementation PR has no usable trusted approval. This includes a green PR
that was never dispatched to its configured reviewer; repeating `git push`,
creating another worktree or waiting without a registered request cannot fix it.

## Meaning

| Diagnostic | Missing or invalid evidence | Safe next action |
| --- | --- | --- |
| `GOV-APPROVAL-001` | Trusted approval is absent | Observe a pending review request, then invoke the configured controller if none exists. |
| `GOV-APPROVAL-002` | Ticket differs | Reconcile the intent/PR binding before requesting review again. |
| `GOV-APPROVAL-003` | Receipt is absent, malformed or repository-controlled | Have the protected verifier acquire and validate external evidence. |
| `GOV-APPROVAL-004` | Repository, PR or HEAD differs | Invalidate the stale request and revalidate the current exact subject. |
| `GOV-APPROVAL-005` | Actor or verification method is untrusted | Resolve the configured type-specific reviewer or verifier; do not widen the allowlist. |

`NO_NEW_GATE`: this is navigation for existing approval rules, not an extra
check, mandatory service, tracker or new permission. A diagnostic is not a
command to execute arbitrary text supplied by a PR or an LLM.

## Safe resolution

1. **EXACT_SUBJECT.** Observe repository, PR number, current HEAD and base,
   ticket/intent, required-check policy and controller ownership. Distinguish
   local changes, pushed commits, PR, checks, approval, merge, release and
   deployment. Reuse the existing ticket, checkout and publication record.
2. **OBSERVE_BEFORE_RETRY.** Query the existing request and remote result first.
   A timed-out response can follow a successful effect. If exact-head approval
   or merge already exists, reconcile its receipt instead of repeating it.
   An active matching request means wait/observe, not duplicate dispatch.
3. **INVOKE_PROTECTED_CONTROLLER.** Use the adopted publisher's documented
   capability/preflight query to resolve its installed revision, protected
   profile, target and required checks. For a new PR use the configured Goal
   delivery path; a PR already pushed does not need another push merely to
   request review. Where a deployed timer owns the request, reuse its managed
   intake/reconciliation route. Otherwise invoke the configured independent
   Validator or route to the configured trusted human. Existing authorization
   for protected publication does not need another chat confirmation.
4. **REUSE_PENDING_EFFECT.** Before dispatch, retain the controller's request
   reference, exact subject and idempotency key in its existing journal. Reuse
   those bindings on a supported retry. Do not invent an idempotency flag or
   journal backend for a tool that lacks one. Use its documented observe-only
   recovery or serialize the unresolved effect instead.
5. Classify the result and expose the next owner/action:
   - **waiting**: an active request or pending required check; observe with the
     configured bounded polling/backoff, showing phase, elapsed time and last
     evidence. The controller's configured deadline leads to readback and a
     precise escalation, not a fresh worktree or an infinite silent wait;
   - **transient transport failure**: read back first, then retry within the
     controller's limits only if no matching effect is confirmed;
   - **deterministic refusal**: preserve its code and input digest; repair the
     named prerequisite before another attempt. Do not rerun unchanged tests
     or requests indefinitely;
   - **stale subject**: invalidate stale validation/approval, re-observe HEAD,
     intent, scope and fencing, then let the controller start a new exact-head
     request; never mutate a branch while it is frozen;
   - **missing profile, identity or authority**: report the specific prerequisite
     and responsible operator. Continue authorized disjoint work; do not
     replace the protected route with raw `gh` approval/merge.
6. Read back the controller receipt and GitHub state. A zero exit status alone
   proves neither review nor merge. When merge is confirmed, let the protected
   controller close the ticket externally. Do not add a repository closure
   commit. Release only the owned reservation through its managed lifecycle;
   preserve unknown worktrees and other writers.

If no declared controller or trusted reviewer can be resolved, the dependent
merge remains blocked with a concrete remediation. This runbook does not
install a substitute, invent authority or require new repository files merely
to report that condition.

## Verification

- Approval binds the current repository, PR, HEAD and ticket. The protected
  verifier checks the actor type and allowlist, or signature and issuer.
- Required checks satisfy the protected policy for the exact change. Optional
  observations remain visible but do not become required by this runbook.
- A merge claim has both the protected result and remote merged state with
  the matching head/merge SHA; a review-only result remains review-only.
- **MERGE_IS_NOT_RELEASE.** Verify a released artifact/version/digest and the
  deployed runtime separately before claiming the application is current.
- Source validation: `python3 scripts/audit_diagnostics.py --root .` and
  `bash tests/governance-validator.test.sh` in the declared hub environment.
  These validate navigation and governance regressions, not remote authority.

## Do not

- **NO_SELF_APPROVAL:** the author invokes the protected boundary; it does not
  approve or merge its own work directly, forge a receipt or edit allowlists.
- Do not accept green CI, advisory LLM text, an HTTP 200, a process exit code,
  a local ticket status or elapsed time as evidence of approval or completion.
- Do not bypass a failed required check or weaken policy to unblock this PR.
- Do not delete unknown work, reset a retry journal, allocate duplicate work,
  or rewrite history to obtain a fresh-looking publication attempt.

## Related rules

`P-CORE-008`, `P-CORE-015`, `P-CORE-018`–`P-CORE-021`, `P-LEASE-003`,
`P-RECOVERY-001`, `C-PUBLISH-003`, `C-PUBLISH-006`, `C-PUBLISH-008`,
`C-PUBLISH-009`, `C-TICKET-014`, `C-TICKET-018`–`C-TICKET-020`.
