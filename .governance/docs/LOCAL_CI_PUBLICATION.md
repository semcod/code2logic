# Local CI publication policy — adopted reference

Canonical policy: [Wellmanifest/new-project 0.20.53](https://github.com/wellmanifest/new-project/blob/d4dab328fbea876eadd3f4ad4e2349d520a2b15a/docs/information/local-ci-publication.md).
Source revision: `d4dab328fbea876eadd3f4ad4e2349d520a2b15a`.
Canonical document SHA-256: `58416ae05eb5513fd1c082c81c9c4be18cb8e6b2672c864bc20e9a8957401b59`.

This managed file is an adoption reference. The authored document and its
metadata remain at the canonical Wellmanifest home; do not register this copy
as a new document owned by the adopting repository.

For every repository, by default, prefer protected local OneDev verification
followed by the independent local Validator App. No organization list limits
this default; only `.governance/local-ci-publication.json` with
`scope.mode: "restricted"` (schema `new-project.local-ci-publication/v1`) may
narrow it, and a restriction never grants or removes authority. Resolve the actual protected profile,
observe existing reconciliation, require fresh verification of the PR head
merged with the current base, then invoke the trusted local Validator adapter
under existing publication authorization. The supported local adapter is
`subactor/validator-agent/bin/run-local-direct-pr.sh`; use its protected deployed
checkout and existing key reference as specified by the canonical runbook.
Never self-approve or merge directly.

A hosted Actions billing or capacity error does not prove local CI is unavailable.
Use hosted dispatch only when explicitly selected by the protected deployment.
Preserve all additional repository checks and required operating systems.
Retire a hosted check only after equivalent deployed local canary evidence and
independent policy review. Missing profiles are gaps, never successful coverage.

Keep declared, configured, deployed, verified and published evidence separate.
Read the canonical policy for the complete workflow, authority boundaries and
migration requirements. This reference grants no execution or merge authority.
