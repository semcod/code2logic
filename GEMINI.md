# GEMINI.md

<!-- wellmanifest:source-links:v1 -->
## Managed standard sources

The local adoption manifest, lock and package are authoritative. These remote
links are navigation only and must not be fetched or executed at runtime.

- Local adoption manifest: [.governance/manifest.json](.governance/manifest.json)
- Local adoption lock: [.governance/manifest.lock.json](.governance/manifest.lock.json)
- Local package map: [.governance/package-manifest.json](.governance/package-manifest.json)
- Canonical instructions: [AGENTS template](https://github.com/wellmanifest/new-project/blob/main/template/files/AGENTS.template.md)
- Host contract: [agent-hosts.json](https://github.com/wellmanifest/new-project/blob/main/governance/agent-hosts.json)
- Immutable adoption/updater: [create_adoption_lock.py](https://github.com/wellmanifest/new-project/blob/main/scripts/create_adoption_lock.py)

<!-- end wellmanifest:source-links:v1 -->

This repository follows the `wellmanifest/new-project` policy-as-code standard.
This file is the Gemini / Antigravity entry; the same rules are in `AGENTS.md`,
`CLAUDE.md`, `.cursor/rules/new-project-standard.mdc`, `.aider.conf.yml` and
`.github/copilot-instructions.md`.

Fail-closed. Do not write code until this contract is followed.

1. Read `AGENTS.md` and `.governance/manifest.json`.
2. Allocate tickets only through `./project/new-ticket.sh`. Never copy
   `project/ticket-*`.
3. Work on a branch or worktree whose name contains `ticket-NNN`. Never commit on
   `main` or a dirty primary checkout.
4. Stay inside that ticket's `intent.json` `allowedPaths`.
5. Run `./scripts/install-agent-hosts.sh` once per clone so the git hook is active.
6. Run `./project/governance-check.sh` before claiming done.

If authority or ownership remains unclear, pause the dependent effect and
follow [.governance/AGENT_DECISIONS.md](.governance/AGENT_DECISIONS.md) to inspect evidence and existing authorization.
Continue disjoint authorized work. Do not invent a ticket number.

Bounded session controls: respect the ticket's `maxActiveMinutes`, create a
`checkpoint` before a context or tool boundary, and leave a `handoff` then
`stop` after a deterministic failure instead of retrying indefinitely.
