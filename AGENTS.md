# Repository agent instructions

<!-- wellmanifest:local-ci-publication:start -->
## Local CI and independent publication

Adopt the publication policy from [Wellmanifest/new-project 0.20.10](https://github.com/wellmanifest/new-project/blob/d5f77d83b3752477cfb95a535d0e1ce77f148576/docs/information/local-ci-publication.md).
Immutable source revision: `d5f77d83b3752477cfb95a535d0e1ce77f148576`.
Document SHA-256: `44803480f1d51f64eec81a62335b6725747f01b5f2de78105ebfc4017a7922c6`.
This is publication-policy adoption; it does not establish full governance,
adoption of every Wellmanifest pack, deployed CI or successful verification.

For `semcod/*` and `subactor/*`, prefer the protected local OneDev executor
and independent local Validator App. Preserve the repository's own tests,
required platform matrix, protected checks and actor boundaries. Read the
actual protected Validator profile and OneDev configuration; missing profiles
are coverage gaps. GitHub may host code and PRs without hosting test execution.
A GitHub Actions billing/capacity failure does not prove local CI is unavailable.

Before publication, observe existing local reconciliation and reuse its receipt.
Require verification of the exact PR head with the current base and merge result.
Invoke the trusted local Validator adapter or its existing timer under the
user's publication authorization; never self-approve or merge directly.
Use hosted `dispatch-direct-pr.sh` only when the protected deployment explicitly
selects that transport. This rule supersedes older unconditional hosted-dispatch
examples, while retaining all additional repository requirements.

Retire a hosted check only after equivalent local tests and the required OS
matrix have a successful deployed canary and an independently reviewed policy
migration. Never empty required checks or create synthetic success statuses.
Report declared, configured, deployed, verified and published evidence separately.
The complete fleet audit belongs in `subactor/docs/architecture/analysis/local-ci-adoption.md`.
<!-- wellmanifest:local-ci-publication:end -->
