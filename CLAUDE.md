# CLAUDE.md

<!-- wellmanifest:source-links:v1 -->
## Managed standard sources

Read the local adoption manifest, lock and package before using this host
projection. The remote links are navigation only; do not fetch them at runtime.

- Local adoption manifest: [.governance/manifest.json](.governance/manifest.json)
- Local adoption lock: [.governance/manifest.lock.json](.governance/manifest.lock.json)
- Local package map: [.governance/package-manifest.json](.governance/package-manifest.json)
- Canonical instructions: [AGENTS template](https://github.com/wellmanifest/new-project/blob/main/template/files/AGENTS.template.md)
- Host contract: [agent-hosts.json](https://github.com/wellmanifest/new-project/blob/main/governance/agent-hosts.json)
- Immutable adoption/updater: [create_adoption_lock.py](https://github.com/wellmanifest/new-project/blob/main/scripts/create_adoption_lock.py)

<!-- end wellmanifest:source-links:v1 -->

This repository follows the `wellmanifest/new-project` policy-as-code standard.
Same contract as `AGENTS.md`, `GEMINI.md`, `.cursor/rules/new-project-standard.mdc`,
`.aider.conf.yml` and `.github/copilot-instructions.md`. Claude Code must follow
it even when the session did not start in an IDE.

1. Read `AGENTS.md` and `.governance/manifest.json` first.
2. Allocate tickets only through `./project/new-ticket.sh`. Never copy a
   `project/ticket-NNN` directory and never invent a ticket number.
3. Work on a branch or worktree whose name contains `ticket-NNN`. Never write on
   `main` or a dirty primary checkout.
4. Stay inside that ticket's `intent.json` `allowedPaths`.
5. Run `./scripts/install-agent-hosts.sh` once per clone so `.githooks/pre-commit`
   is active.
6. Run `./project/governance-check.sh` before claiming done.

The pre-commit hook rejects commits that are not bound to an `IN_PROGRESS`
`ticket-NNN`, and the `governance / enforce` CI job rejects a pull request whose
host contract or packaging declaration drifted. Markdown is not a substitute for
either gate.

Bounded session controls: respect the ticket's `maxActiveMinutes`, create a
`checkpoint` before a context or tool boundary, and leave a `handoff` then
`stop` after a deterministic failure instead of retrying indefinitely.
