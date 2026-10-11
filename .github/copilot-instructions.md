# GitHub Copilot instructions

<!-- wellmanifest:source-links:v1 -->
## Managed standard sources

The local adoption manifest, lock and package are authoritative. Remote links
are navigation only and must not be fetched or executed at runtime.

- Local adoption manifest: [.governance/manifest.json](.governance/manifest.json)
- Local adoption lock: [.governance/manifest.lock.json](.governance/manifest.lock.json)
- Local package map: [.governance/package-manifest.json](.governance/package-manifest.json)
- Canonical instructions: [AGENTS template](https://github.com/wellmanifest/new-project/blob/main/template/files/AGENTS.template.md)
- Host contract: [agent-hosts.json](https://github.com/wellmanifest/new-project/blob/main/governance/agent-hosts.json)
- Immutable adoption/updater: [create_adoption_lock.py](https://github.com/wellmanifest/new-project/blob/main/scripts/create_adoption_lock.py)

<!-- end wellmanifest:source-links:v1 -->

This repository follows the `wellmanifest/new-project` policy-as-code standard.
Same fail-closed contract as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` and the Cursor
rule. Copilot Chat and the Copilot coding agent load this file automatically.

1. Read `AGENTS.md` before proposing any change.
2. Allocate tickets only through `./project/new-ticket.sh`. Never copy a
   `project/ticket-NNN` directory and never invent a ticket number.
3. Work on a branch or worktree whose name contains `ticket-NNN`. Never write on
   `main` or a dirty primary checkout.
4. Stay inside that ticket's `intent.json` `allowedPaths`.
5. Run `./scripts/install-agent-hosts.sh` once per clone so `.githooks/pre-commit`
   is active, then `./project/governance-check.sh` before claiming done.

Suggestions that skip these steps are rejected by the pre-commit hook and by the
`governance / enforce` CI job. Markdown is not a substitute for either.

Bounded session controls: respect the ticket's `maxActiveMinutes`, create a
`checkpoint` before a context or tool boundary, and leave a `handoff` then
`stop` after a deterministic failure instead of retrying indefinitely.
