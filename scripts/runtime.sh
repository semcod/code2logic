#!/usr/bin/env bash
set -euo pipefail

runtime_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v node >/dev/null 2>&1; then
  echo "EVD-RUNTIME-001: Node.js 20 or newer is required" >&2
  exit 2
fi

node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [[ ! "$node_major" =~ ^[0-9]+$ ]] || (( node_major < 20 )); then
  echo "EVD-RUNTIME-001: Node.js 20 or newer is required" >&2
  exit 2
fi

# The body is valid TypeScript and executable JavaScript. Keeping it inside the
# Bash entrypoint avoids a transpiler/runtime dependency while preserving one
# portable file for adopted TypeScript repositories.
exec node --input-type=commonjs - "$runtime_root" "$@" <<'TYPESCRIPT'
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const argv = process.argv.slice(2);
const packagedRoot = path.resolve(argv.shift() || ".");
const command = argv.shift() || "help";

function usage(message) {
  if (message) process.stderr.write(`EVD-RUNTIME-002: ${message}\n`);
  process.stderr.write(
    "Usage:\n" +
      "  bash scripts/runtime.sh policy [--policy CONTRIBUTING.md]\n" +
      "  bash scripts/runtime.sh validate --evaluation FILE --intent FILE " +
      "--manifest-lock FILE [--policy FILE] [--repository-root DIR] " +
      "[--json-out FILE] [--markdown-out FILE]\n",
  );
  process.exit(message ? 2 : 0);
}

function parseOptions(items) {
  const options = new Map();
  for (let index = 0; index < items.length; index += 1) {
    const key = items[index];
    if (!key.startsWith("--")) usage(`unexpected argument ${key}`);
    if (options.has(key)) usage(`option ${key} was repeated`);
    const value = items[index + 1];
    if (value === undefined || value.startsWith("--")) usage(`option ${key} requires a value`);
    options.set(key, value);
    index += 1;
  }
  return options;
}

function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sortDeep(value[key])]),
    );
  }
  return value;
}

function canonical(value) {
  return JSON.stringify(sortDeep(value));
}

function sha256Bytes(value) {
  return `sha256:${crypto.createHash("sha256").update(value).digest("hex")}`;
}

function sha256File(filePath) {
  return sha256Bytes(fs.readFileSync(filePath));
}

function readText(filePath, label) {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch (error) {
    throw new Error(`${label} is unreadable: ${error.message}`);
  }
}

function readJson(filePath, label) {
  try {
    return JSON.parse(readText(filePath, label));
  } catch (error) {
    if (error.message.startsWith(`${label} is unreadable:`)) throw error;
    throw new Error(`${label} is not valid JSON: ${error.message}`);
  }
}

function diagnostic(code, message, evidence, remediation) {
  return {
    code,
    severity: "BLOCKING",
    message,
    evidence: Array.isArray(evidence) ? evidence : [evidence].filter(Boolean),
    remediation: Array.isArray(remediation) ? remediation : [remediation].filter(Boolean),
  };
}

const requiredEvaluationRules = Array.from(
  { length: 10 },
  (_, index) => `C-EVALUATION-${String(index + 1).padStart(3, "0")}`,
);

function validatePolicyText(policyText) {
  const diagnostics = [];
  const counts = new Map();
  for (const match of policyText.matchAll(/^\s*RULE\s+(C-EVALUATION-\d{3})\b/gm)) {
    counts.set(match[1], (counts.get(match[1]) || 0) + 1);
  }
  for (const rule of requiredEvaluationRules) {
    if (counts.get(rule) !== 1) {
      diagnostics.push(
        diagnostic(
          "EVD-POLICY-001",
          `${rule} must occur exactly once in the policy`,
          `observed=${counts.get(rule) || 0}`,
          `restore the canonical ${rule} block from wellmanifest/new-project`,
        ),
      );
    }
  }
  const requiredClauses = [
    "CHANGE_EVALUATION_SCHEMA = \"t2c.change-evaluation/v1\"",
    "PUBLICATION_MODE = PULL_REQUEST_REQUIRED_FOR_IMPLEMENTATION",
    "DIRECT_PUSH = FORBIDDEN_FOR_IMPLEMENTATION",
    "FORBID COMPENSATE_REQUIRED_GATE_WITH_NUMERIC_SCORE",
    "FORBID LLM_OUTPUT_AS_TRUSTED_APPROVAL",
  ];
  for (const clause of requiredClauses) {
    if (!policyText.includes(clause)) {
      diagnostics.push(
        diagnostic(
          "EVD-POLICY-002",
          `required policy clause is missing: ${clause}`,
          "CONTRIBUTING.md",
          "restore the canonical CHANGE EVALUATION contract",
        ),
      );
    }
  }
  return diagnostics;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isSha(value) {
  return typeof value === "string" && /^[0-9a-f]{40}$/.test(value);
}

function isDigest(value) {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function validateMinimumShape(evaluation) {
  const diagnostics = [];
  const requiredObjects = [
    "subject",
    "contract",
    "changeSet",
    "gates",
    "dimensions",
    "approval",
    "contribution",
    "verdict",
    "confidence",
    "provenance",
  ];
  if (!isObject(evaluation) || evaluation.schemaVersion !== "t2c.change-evaluation/v1") {
    diagnostics.push(
      diagnostic(
        "EVD-SCHEMA-001",
        "schemaVersion must equal t2c.change-evaluation/v1",
        "change-evaluation.json",
        "generate the report with the published v1 schema",
      ),
    );
    return diagnostics;
  }
  for (const key of requiredObjects) {
    if (!isObject(evaluation[key])) {
      diagnostics.push(
        diagnostic("EVD-SCHEMA-001", `${key} must be an object`, key, "provide the required v1 object"),
      );
    }
  }
  for (const key of ["actors", "criteriaEvaluation", "findings"]) {
    if (!Array.isArray(evaluation[key])) {
      diagnostics.push(
        diagnostic("EVD-SCHEMA-001", `${key} must be an array`, key, "provide the required v1 array"),
      );
    }
  }
  const allowedTopLevel = new Set([
    "schemaVersion",
    "subject",
    "contract",
    "actors",
    "changeSet",
    "criteriaEvaluation",
    "gates",
    "dimensions",
    "approval",
    "findings",
    "contribution",
    "verdict",
    "confidence",
    "provenance",
  ]);
  for (const key of Object.keys(evaluation)) {
    if (!allowedTopLevel.has(key)) {
      diagnostics.push(
        diagnostic(
          "EVD-SCHEMA-001",
          `unsupported top-level property: ${key}`,
          key,
          "remove the property or publish a new schema version",
        ),
      );
    }
  }
  if (isObject(evaluation.subject)) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(evaluation.subject.repository || "")) {
      diagnostics.push(diagnostic("EVD-SCHEMA-001", "subject.repository is invalid", "subject.repository", "use owner/repository"));
    }
    if (!["commit", "push", "pull_request", "merge_group"].includes(evaluation.subject.event)) {
      diagnostics.push(diagnostic("EVD-SCHEMA-001", "subject.event is invalid", "subject.event", "use a v1 event"));
    }
    if (
      ["pull_request", "merge_group"].includes(evaluation.subject.event) &&
      (!Number.isInteger(evaluation.subject.pullRequest) || evaluation.subject.pullRequest < 1)
    ) {
      diagnostics.push(diagnostic("EVD-SCHEMA-001", "subject.pullRequest is required", "subject.pullRequest", "provide the PR number"));
    }
  }
  if (isObject(evaluation.contract)) {
    if (!/^ticket-[0-9]{3,}$/.test(evaluation.contract.ticket || "")) {
      diagnostics.push(diagnostic("EVD-SCHEMA-001", "contract.ticket is invalid", "contract.ticket", "use ticket-NNN"));
    }
    if (!Array.isArray(evaluation.contract.criteria) || evaluation.contract.criteria.length === 0) {
      diagnostics.push(diagnostic("EVD-SCHEMA-001", "contract.criteria must not be empty", "contract.criteria", "declare required criteria"));
    }
  }
  if (isObject(evaluation.changeSet)) {
    for (const key of ["commits", "changedPaths", "changedSymbols", "publicApiChanges", "dependencyChanges"]) {
      if (!Array.isArray(evaluation.changeSet[key])) {
        diagnostics.push(diagnostic("EVD-SCHEMA-001", `changeSet.${key} must be an array`, `changeSet.${key}`, "provide the v1 field"));
      }
    }
  }
  if (Array.isArray(evaluation.actors)) {
    for (const actor of evaluation.actors) {
      if (!isObject(actor) || typeof actor.id !== "string" || !Array.isArray(actor.contributionTypes)) {
        diagnostics.push(diagnostic("EVD-SCHEMA-001", "actor entry is invalid", "actors", "provide id, role and contributionTypes"));
      }
    }
  }
  if (Array.isArray(evaluation.criteriaEvaluation)) {
    const statuses = ["SATISFIED", "PARTIAL", "FAILED", "UNKNOWN", "NOT_APPLICABLE"];
    for (const criterion of evaluation.criteriaEvaluation) {
      if (
        !isObject(criterion) ||
        !/^AC-[0-9]+$/.test(criterion.criterion || "") ||
        !statuses.includes(criterion.status) ||
        !Array.isArray(criterion.implementationEvidence) ||
        !Array.isArray(criterion.validationEvidence) ||
        !Array.isArray(criterion.missingEvidence) ||
        typeof criterion.confidence !== "number" ||
        criterion.confidence < 0 ||
        criterion.confidence > 1
      ) {
        diagnostics.push(diagnostic("EVD-SCHEMA-001", "criterion evaluation entry is invalid", "criteriaEvaluation", "conform to the v1 criterion contract"));
      }
    }
  }
  if (isObject(evaluation.contribution) && !Array.isArray(evaluation.contribution.claims)) {
    diagnostics.push(diagnostic("EVD-SCHEMA-001", "contribution.claims must be an array", "contribution.claims", "provide evidence-backed claims"));
  }
  return diagnostics;
}

function findNumericScore(value, prefix = "") {
  const paths = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => paths.push(...findNumericScore(item, `${prefix}[${index}]`)));
  } else if (isObject(value)) {
    for (const [key, item] of Object.entries(value)) {
      const current = prefix ? `${prefix}.${key}` : key;
      if (/score$/i.test(key) && typeof item === "number") paths.push(current);
      paths.push(...findNumericScore(item, current));
    }
  }
  return paths;
}

function globToRegExp(glob) {
  let expression = "^";
  for (let index = 0; index < glob.length; index += 1) {
    const char = glob[index];
    if (char === "*" && glob[index + 1] === "*" && glob[index + 2] === "/"
        && (index === 0 || glob[index - 1] === "/")) {
      expression += "(?:[^/]+/)*";
      index += 2;
    } else if (char === "*" && glob[index + 1] === "*") {
      expression += ".*";
      index += 1;
    } else if (char === "*") {
      expression += "[^/]*";
    } else if (char === "?") {
      expression += "[^/]";
    } else {
      expression += char.replace(/[\\^$+?.()|{}\[\]]/g, "\\$&");
    }
  }
  return new RegExp(`${expression}$`);
}

function pathAllowed(changedPath, patterns) {
  return patterns.some((pattern) => typeof pattern === "string" && globToRegExp(pattern).test(changedPath));
}

function git(repositoryRoot, args) {
  const result = spawnSync("git", ["-C", repositoryRoot, ...args], {
    encoding: "utf8",
    shell: false,
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "git command failed").trim());
  }
  return result.stdout;
}

function exactStringSet(left, right) {
  const normalize = (items) => [...new Set(items)].sort();
  return canonical(normalize(left)) === canonical(normalize(right));
}

function approvalScopeDigest(evaluation) {
  return sha256Bytes(
    canonical({
      actor: evaluation.approval.actor,
      headSha: evaluation.subject.headSha,
      pullRequest: evaluation.subject.pullRequest ?? null,
      repository: evaluation.subject.repository,
      ticket: evaluation.contract.ticket,
    }),
  );
}

function expectedVerdict(evaluation) {
  const blockingGate = Object.values(evaluation.gates).some((status) =>
    ["FAILED", "UNKNOWN", "WAITING"].includes(status),
  );
  const blockingDimension = Object.values(evaluation.dimensions).some((status) =>
    ["FAILED", "INSUFFICIENT_EVIDENCE"].includes(status),
  );
  const blockingCriterion = evaluation.criteriaEvaluation.some((criterion) =>
    ["PARTIAL", "FAILED", "UNKNOWN"].includes(criterion.status),
  );
  const blockingFinding = evaluation.findings.some((finding) => finding.severity === "BLOCKING");
  const approvalMissing = evaluation.approval.status !== "VERIFIED";
  if (blockingGate || blockingDimension || blockingCriterion || blockingFinding || approvalMissing) {
    return "BLOCKED";
  }
  const reviewFinding = evaluation.findings.some((finding) => finding.severity === "REVIEW_REQUIRED");
  if (Object.values(evaluation.dimensions).includes("REVIEW_REQUIRED") || reviewFinding) {
    return "REVIEW_REQUIRED";
  }
  return "ALLOWED";
}

function validateEvaluation(evaluation, intent, paths, policyText) {
  const diagnostics = [...validatePolicyText(policyText), ...validateMinimumShape(evaluation)];
  if (diagnostics.some((item) => item.code === "EVD-SCHEMA-001")) return diagnostics;

  const scorePaths = findNumericScore(evaluation);
  if (scorePaths.length > 0) {
    diagnostics.push(
      diagnostic(
        "EVD-SCORE-001",
        "numeric score fields are forbidden because they can compensate hard failures",
        scorePaths,
        "use independent status dimensions and non-compensable gates",
      ),
    );
  }

  const subject = evaluation.subject;
  const contract = evaluation.contract;
  for (const [label, value] of [
    ["baseSha", subject.baseSha],
    ["headSha", subject.headSha],
    ["mergeBaseSha", subject.mergeBaseSha],
  ]) {
    if (!isSha(value)) {
      diagnostics.push(
        diagnostic("INT-BINDING-001", `${label} must be a full lowercase commit SHA`, label, "record the exact Git SHA"),
      );
    }
  }
  if (contract.ticket !== intent.ticket || contract.workstream !== intent.workstream) {
    diagnostics.push(
      diagnostic(
        "INT-BINDING-002",
        "evaluation ticket/workstream does not match the approved intent",
        [`evaluation=${contract.ticket}/${contract.workstream}`, `intent=${intent.ticket}/${intent.workstream}`],
        "regenerate the report for the active ticket intent",
      ),
    );
  }
  if (
    isObject(intent.delivery) &&
    isSha(intent.delivery.acceptedBaseSha) &&
    intent.delivery.acceptedBaseSha !== subject.baseSha
  ) {
    diagnostics.push(
      diagnostic(
        "INT-BASE-001",
        "subject.baseSha does not match the base accepted in ticket intent",
        [`evaluation=${subject.baseSha}`, `intent=${intent.delivery.acceptedBaseSha}`],
        "rebase the change or obtain approval for a refreshed intent base",
      ),
    );
  }

  const expectedHashes = {
    intentHash: sha256File(paths.intent),
    policyHash: sha256File(paths.policy),
    manifestLockHash: sha256File(paths.manifestLock),
  };
  for (const [key, expected] of Object.entries(expectedHashes)) {
    if (!isDigest(contract[key]) || contract[key] !== expected) {
      diagnostics.push(
        diagnostic(
          "INT-HASH-001",
          `${key} does not match the evaluated source`,
          [`expected=${expected}`, `observed=${contract[key]}`],
          "regenerate the evaluation after loading the current contract files",
        ),
      );
    }
  }

  const declaredPaths = Array.isArray(evaluation.changeSet.changedPaths)
    ? evaluation.changeSet.changedPaths
    : [];
  const allowedPaths = Array.isArray(intent.allowedPaths) ? intent.allowedPaths : [];
  for (const changedPath of declaredPaths) {
    if (!pathAllowed(changedPath, allowedPaths)) {
      diagnostics.push(
        diagnostic(
          "GOV-SCOPE-001",
          `changed path is outside intent.allowedPaths: ${changedPath}`,
          changedPath,
          "remove the path or obtain a fresh approved intent",
        ),
      );
    }
  }

  if (paths.repositoryRoot) {
    try {
      git(paths.repositoryRoot, ["cat-file", "-e", `${subject.baseSha}^{commit}`]);
      git(paths.repositoryRoot, ["cat-file", "-e", `${subject.headSha}^{commit}`]);
      const observedMergeBase = git(paths.repositoryRoot, [
        "merge-base",
        subject.baseSha,
        subject.headSha,
      ]).trim();
      if (observedMergeBase !== subject.mergeBaseSha) {
        diagnostics.push(
          diagnostic(
            "COM-GIT-001",
            "mergeBaseSha does not match Git",
            [`expected=${observedMergeBase}`, `observed=${subject.mergeBaseSha}`],
            "regenerate the report for the current branch base and head",
          ),
        );
      }
      const observedPaths = git(paths.repositoryRoot, [
        "diff",
        "--name-only",
        "-z",
        subject.mergeBaseSha,
        subject.headSha,
        "--",
      ])
        .split("\0")
        .filter(Boolean);
      if (!exactStringSet(observedPaths, declaredPaths)) {
        diagnostics.push(
          diagnostic(
            "COM-GIT-002",
            "changeSet.changedPaths does not match the exact Git range",
            [`git=${observedPaths.sort().join(",")}`, `report=${[...declaredPaths].sort().join(",")}`],
            "extract changed paths from mergeBaseSha..headSha",
          ),
        );
      }
      const observedCommits = git(paths.repositoryRoot, [
        "rev-list",
        "--reverse",
        `${subject.mergeBaseSha}..${subject.headSha}`,
      ])
        .split("\n")
        .filter(Boolean);
      const declaredCommits = Array.isArray(evaluation.changeSet.commits)
        ? evaluation.changeSet.commits
        : [];
      if (!exactStringSet(observedCommits, declaredCommits)) {
        diagnostics.push(
          diagnostic(
            "COM-GIT-003",
            "changeSet.commits does not match the exact Git range",
            [`git=${observedCommits.join(",")}`, `report=${declaredCommits.join(",")}`],
            "extract every commit from mergeBaseSha..headSha",
          ),
        );
      }
    } catch (error) {
      diagnostics.push(
        diagnostic(
          "COM-GIT-001",
          `exact Git range could not be verified: ${error.message}`,
          paths.repositoryRoot,
          "provide an existing repository and reachable full SHAs",
        ),
      );
    }
  }

  const requiredCriteria = Array.isArray(contract.criteria) ? contract.criteria : [];
  const evaluations = Array.isArray(evaluation.criteriaEvaluation)
    ? evaluation.criteriaEvaluation
    : [];
  const evaluatedCriteria = evaluations.map((item) => item.criterion);
  if (!exactStringSet(requiredCriteria, evaluatedCriteria)) {
    diagnostics.push(
      diagnostic(
        "EVD-CRITERION-001",
        "criteriaEvaluation must cover every declared criterion exactly once",
        [`required=${requiredCriteria.join(",")}`, `evaluated=${evaluatedCriteria.join(",")}`],
        "add one evidence record for each required acceptance criterion",
      ),
    );
  }
  if (new Set(evaluatedCriteria).size !== evaluatedCriteria.length) {
    diagnostics.push(
      diagnostic(
        "EVD-CRITERION-001",
        "criteriaEvaluation contains duplicate criteria",
        evaluatedCriteria,
        "keep exactly one record per criterion",
      ),
    );
  }
  for (const criterion of evaluations) {
    if (
      criterion.status === "SATISFIED" &&
      (!Array.isArray(criterion.implementationEvidence) ||
        criterion.implementationEvidence.length === 0 ||
        !Array.isArray(criterion.validationEvidence) ||
        criterion.validationEvidence.length === 0)
    ) {
      diagnostics.push(
        diagnostic(
          "EVD-CRITERION-002",
          `${criterion.criterion} is SATISFIED without implementation and validation evidence`,
          criterion.criterion,
          "attach both evidence classes or lower the criterion status",
        ),
      );
    }
  }

  const requiredGates = [
    "governance",
    "scope",
    "secrets",
    "tests",
    "regression",
    "documentation",
    "approval",
    "evidenceCompleteness",
  ];
  for (const gate of requiredGates) {
    if (!["PASS", "FAILED", "UNKNOWN", "WAITING", "NOT_APPLICABLE"].includes(evaluation.gates[gate])) {
      diagnostics.push(
        diagnostic("EVD-GATE-001", `required gate ${gate} has no valid status`, gate, "set an explicit gate status"),
      );
    }
  }
  const dimensionStatuses = [
    "PASS",
    "REVIEW_REQUIRED",
    "FAILED",
    "INSUFFICIENT_EVIDENCE",
    "NOT_APPLICABLE",
  ];
  const requiredDimensions = [
    "governanceCompliance",
    "intentAlignment",
    "implementationCorrectness",
    "projectDirection",
    "changeReasonableness",
    "contributionValue",
    "evidenceConfidence",
  ];
  for (const dimension of requiredDimensions) {
    if (!dimensionStatuses.includes(evaluation.dimensions[dimension])) {
      diagnostics.push(
        diagnostic(
          "EVD-DIMENSION-001",
          `required dimension ${dimension} has no valid status`,
          dimension,
          "set an explicit independent dimension status",
        ),
      );
    }
  }

  const approval = evaluation.approval;
  if (approval.status === "VERIFIED") {
    const sourceContract = {
      "github-review": ["human", "github-api-allowlist"],
      "github-app-review": ["validator-app", "github-api-allowlist"],
      "signed-attestation": ["attestation-issuer", "signed-attestation"],
    }[approval.source];
    if (!sourceContract || approval.actorRole !== sourceContract[0] || approval.verificationMethod !== sourceContract[1]) {
      diagnostics.push(
        diagnostic(
          "APR-AUTHORITY-001",
          "approval source, actor role and verification method are inconsistent",
          `${approval.source}/${approval.actorRole}/${approval.verificationMethod}`,
          "use the protected source-specific approval resolver",
        ),
      );
    }
    if (approval.headSha !== subject.headSha) {
      diagnostics.push(
        diagnostic(
          "APR-STALE-001",
          "approval is bound to a previous headSha",
          [`approval=${approval.headSha}`, `head=${subject.headSha}`],
          "obtain a new independent approval for the exact current head",
        ),
      );
    }
    const expectedScope = approvalScopeDigest(evaluation);
    if (
      approval.approvalScopeHash !== expectedScope ||
      contract.approvalScopeHash !== expectedScope
    ) {
      diagnostics.push(
        diagnostic(
          "APR-BINDING-001",
          "approvalScopeHash does not match repository, PR, head, ticket and actor",
          [
            `expected=${expectedScope}`,
            `approval=${approval.approvalScopeHash}`,
            `contract=${contract.approvalScopeHash}`,
          ],
          "recreate approval evidence in the protected verifier",
        ),
      );
    }
    if (!isDigest(approval.evidenceDigest)) {
      diagnostics.push(
        diagnostic(
          "APR-BINDING-002",
          "verified approval requires a SHA-256 evidence digest",
          approval.evidenceDigest,
          "bind the protected approval evidence artifact by digest",
        ),
      );
    }
    const authors = evaluation.actors
      .filter((actor) => actor.role === "author" || actor.role === "last-push-author")
      .map((actor) => actor.id);
    if (authors.includes(approval.actor)) {
      diagnostics.push(
        diagnostic(
          "APR-INDEPENDENCE-001",
          "approval actor is also an author or last-push author",
          approval.actor,
          "obtain review from an independent trusted authority",
        ),
      );
    }
    if (evaluation.gates.approval !== "PASS") {
      diagnostics.push(
        diagnostic(
          "APR-GATE-001",
          "verified approval requires gates.approval=PASS",
          evaluation.gates.approval,
          "reconcile the approval gate with protected evidence",
        ),
      );
    }
  } else if (evaluation.gates.approval === "PASS") {
    diagnostics.push(
      diagnostic(
        "APR-GATE-001",
        "approval gate cannot pass without VERIFIED approval",
        approval.status,
        "attach exact-head protected approval evidence",
      ),
    );
  }

  const derivedMerge = expectedVerdict(evaluation);
  if (evaluation.verdict.merge !== derivedMerge) {
    diagnostics.push(
      diagnostic(
        "INT-VERDICT-001",
        "declared merge verdict does not match hard gates, criteria, findings and dimensions",
        [`expected=${derivedMerge}`, `observed=${evaluation.verdict.merge}`],
        "use the deterministic derived verdict; do not average failures",
      ),
    );
  }
  const criteriaComplete = evaluations.every((item) =>
    ["SATISFIED", "NOT_APPLICABLE"].includes(item.status),
  );
  const expectedCompletion =
    derivedMerge === "ALLOWED" && criteriaComplete
      ? "ACCEPTED"
      : derivedMerge === "REVIEW_REQUIRED" && criteriaComplete
        ? "CANDIDATE"
        : "NOT_DONE";
  if (evaluation.verdict.completion !== expectedCompletion) {
    diagnostics.push(
      diagnostic(
        "INT-COMPLETION-001",
        "declared completion does not match accepted evidence and merge verdict",
        [`expected=${expectedCompletion}`, `observed=${evaluation.verdict.completion}`],
        "mark incomplete work NOT_DONE until every required criterion is accepted",
      ),
    );
  }
  return diagnostics;
}

function markdownReport(valid, evaluation, diagnostics, evaluationDigest) {
  const lines = ["# Change Evaluation", ""];
  lines.push(`Validation: ${valid ? "PASS" : "FAILED"}`);
  if (evaluation && isObject(evaluation.subject) && isObject(evaluation.contract)) {
    lines.push(`Merge verdict: ${evaluation.verdict?.merge || "UNKNOWN"}`);
    lines.push(`Completion: ${evaluation.verdict?.completion || "UNKNOWN"}`);
    lines.push(`Ticket: ${evaluation.contract.ticket || "UNKNOWN"}`);
    lines.push(`Base: ${evaluation.subject.baseSha || "UNKNOWN"}`);
    lines.push(`Head: ${evaluation.subject.headSha || "UNKNOWN"}`);
    lines.push(`Intent hash: ${evaluation.contract.intentHash || "UNKNOWN"}`);
    lines.push(`Policy hash: ${evaluation.contract.policyHash || "UNKNOWN"}`);
  }
  lines.push(`Evaluation digest: ${evaluationDigest || "UNAVAILABLE"}`, "");
  lines.push(`Blocking diagnostics: ${diagnostics.length}`);
  if (diagnostics.length > 0) {
    lines.push("", "## Diagnostics", "");
    for (const item of diagnostics) lines.push(`- ${item.code}: ${item.message}`);
  }
  return `${lines.join("\n")}\n`;
}

function writeResult(options, envelope, markdown) {
  const json = `${JSON.stringify(sortDeep(envelope), null, 2)}\n`;
  if (options.has("--json-out")) fs.writeFileSync(path.resolve(options.get("--json-out")), json);
  if (options.has("--markdown-out")) {
    fs.writeFileSync(path.resolve(options.get("--markdown-out")), markdown);
  }
  process.stdout.write(json);
}

if (command === "help" || command === "--help" || command === "-h") usage();

const options = parseOptions(argv);
const policyPath = path.resolve(options.get("--policy") || path.join(packagedRoot, "CONTRIBUTING.md"));

if (command === "policy") {
  const policyText = readText(policyPath, "policy");
  const diagnostics = validatePolicyText(policyText).sort((left, right) =>
    `${left.code}:${left.message}`.localeCompare(`${right.code}:${right.message}`),
  );
  const result = {
    schemaVersion: "t2c.change-evaluation-policy-validation/v1",
    valid: diagnostics.length === 0,
    policyHash: sha256File(policyPath),
    ruleIds: requiredEvaluationRules,
    diagnostics,
  };
  process.stdout.write(`${JSON.stringify(sortDeep(result), null, 2)}\n`);
  process.exit(result.valid ? 0 : 1);
}

if (command !== "validate") usage(`unknown command ${command}`);
for (const required of ["--evaluation", "--intent", "--manifest-lock"]) {
  if (!options.has(required)) usage(`${required} is required`);
}

const paths = {
  evaluation: path.resolve(options.get("--evaluation")),
  intent: path.resolve(options.get("--intent")),
  manifestLock: path.resolve(options.get("--manifest-lock")),
  policy: policyPath,
  repositoryRoot: options.has("--repository-root")
    ? path.resolve(options.get("--repository-root"))
    : null,
};

let evaluation;
let intent;
let diagnostics = [];
try {
  evaluation = readJson(paths.evaluation, "evaluation");
  intent = readJson(paths.intent, "intent");
  readJson(paths.manifestLock, "manifest lock");
  const policyText = readText(paths.policy, "policy");
  diagnostics = validateEvaluation(evaluation, intent, paths, policyText);
} catch (error) {
  diagnostics = [
    diagnostic(
      "EVD-INPUT-001",
      error.message,
      "runtime input",
      "provide readable, valid contract inputs",
    ),
  ];
}

diagnostics.sort((left, right) =>
  `${left.code}:${left.message}`.localeCompare(`${right.code}:${right.message}`),
);
let evaluationDigest = null;
if (evaluation !== undefined) {
  const digestSubject = JSON.parse(JSON.stringify(evaluation));
  if (isObject(digestSubject.provenance)) delete digestSubject.provenance.evaluationDigest;
  evaluationDigest = sha256Bytes(canonical(digestSubject));
}
const valid = diagnostics.length === 0;
const mergeAllowed = valid && evaluation?.verdict?.merge === "ALLOWED";
const envelope = {
  schemaVersion: "t2c.change-evaluation-validation/v1",
  valid,
  mergeAllowed,
  evaluationDigest,
  verdict: evaluation?.verdict || null,
  diagnostics,
};
writeResult(options, envelope, markdownReport(valid, evaluation, diagnostics, evaluationDigest));
process.exit(mergeAllowed ? 0 : 1);
TYPESCRIPT
