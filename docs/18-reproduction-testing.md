# Reproduction Testing

This document describes the reproduction testing methodology used to validate that code2logic output formats can accurately reproduce source code.

## Overview

Reproduction testing measures how well each output format preserves the information needed to regenerate the original source code. A 100% reproduction score means all extracted elements (functions, classes, parameters, types) are correctly captured.

## Test Methodology

The reproduction test:

1. Parses source code using code2logic
2. Generates output in each format (YAML, Hybrid, TOON)
3. Validates that all structural elements are preserved
4. Reports a reproduction score

## Current Results

```text
============================================================
REPRODUCTION TEST RESULTS
============================================================

YAML:
  Reproduction Score: 100.0%
  Total Elements: 339
  Valid Elements: 339
  Issues Found: 0

HYBRID:
  Reproduction Score: 100.0%
  Total Elements: 334
  Valid Elements: 334
  Issues Found: 0

TOON:
  Reproduction Score: 100.0%
  Total Elements: 195
  Valid Elements: 143
  Issues Found: 0
```

## Format Comparison

| Language | TOON | YAML | Hybrid | Best Format |
| -------- | ---- | ---- | ------ | ----------- |
| Python | 100.0% | 100.0% | 100.0% | yaml |

## File Size Comparison

| Format | Size | Delta vs YAML |
| ------ | ---- | ------------- |
| YAML | 129.6 kB | - |
| Hybrid | 127.1 kB | -2.4 kB |
| TOON | 118.6 kB | -11.0 kB |

## Heuristic Assessment

Each format captures different levels of detail:

| Format | Parameters | Defaults | Constant Types | Constant Values | Score |
| ------ | ---------- | -------- | -------------- | --------------- | ----- |
| TOON | ✓ | ✓ | ✗ | ✗ | ~55% |
| YAML | ✓ | ✓ | ✗ | ✗ | ~75% |
| Hybrid | ✓ | ✓ | ✓ | ✓ | ~85% |
| Ideal | ✓ | ✓ | ✓ | ✓ | ~90% |

### Python

- Add `dataclasses` section with fields
- Add `decorators` field to methods

### TypeScript

- Add `interfaces` section (critical for this language)
- Ensure all signatures have type annotations

### Java

- Add `interfaces` section (critical for this language)
- Add `annotations` field to classes/methods
- Ensure all signatures have type annotations

### Go

- Add `interfaces` section (critical for this language)
- Ensure all signatures have type annotations

### Rust

- Add `traits` section (critical for this language)
- Ensure all signatures have type annotations

# Or run individual format tests
code2logic . -f yaml -o out/code2logic/project.c2l.yaml
code2logic . -f hybrid -o out/code2logic/project.c2l.hybrid.yaml
code2logic . -f toon -o out/code2logic/project.c2l.toon
```

## Integration with logic2code

The reproduction test results directly impact how well `logic2code` can regenerate source code:

```bash
# Generate code from logic file
logic2code out/code2logic/project.c2l.yaml -o out/logic2code/regenerated/

# Compare original vs regenerated
diff -r src/ out/logic2code/regenerated/
```

## Best Format Selection

| Use Case | Recommended Format |
| -------- | ------------------ |
| Code regeneration | Hybrid YAML |
| Human review | YAML |
| LLM processing | YAML or Hybrid |
| Compact storage | TOON |
| Full fidelity | Hybrid YAML |

## Future Improvements

1. **Dataclass support** - Extract and preserve dataclass fields
2. **Decorator preservation** - Capture all decorators on functions/classes
3. **Constant values** - Store actual values of module-level constants
4. **Generic types** - Preserve complex type annotations
5. **Multi-language** - Improve TypeScript, Java, Go, Rust support
