# Error Runbooks (`code2logic`)

Index of error runbooks and diagnostic remediation guides for `semcod/code2logic` in accordance with `wellmanifest/logs`.

| Code | Component | Summary | Remediation |
| --- | --- | --- | --- |
| `C2L-PARSE-001` | `code2logic.analyzer` | Source file AST or tree-sitter parse failure | Verify syntax of target source file or exclude generated artifacts |
| `C2L-PERF-001` | `code2logic.code_review` | Performance anti-pattern detected in loop context | Refactor N+1 queries, subprocess spawns, or uncached parses out of loops |
