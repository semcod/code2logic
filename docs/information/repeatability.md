---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "repeatability",
  "kind": "information",
  "version": 1,
  "title": "Test powtarzalno\u015bci (3 runy)",
  "status": "proposed",
  "owner": "semcod/code2logic",
  "created": "2026-09-09",
  "updated": "2026-09-09",
  "review_after": "2026-10-09",
  "source_revision": "670066ca7c2383de95c85ab13740a3c34b1d9acb",
  "affected_repositories": [
    "semcod/code2logic"
  ],
  "evidence": [
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/docs/11-repeatability.md"
  ]
}
---

# Test powtarzalności (3 runy)

<!-- docs:section purpose -->
## Purpose

Preserve this reference while migrating links to the maintained canonical API documentation.

<!-- docs:section scope -->
## Scope

The original material below is retained from the source revision in metadata. This migration updates its placement and relative links; it is not a fresh validation of every historical example.

<!-- docs:section evidence -->
## Evidence

The immutable original document is linked in metadata. Current API corrections are documented in the project documentation index.

<!-- docs:section content -->

[← README](../../README.md) | [Docs Index](index.md)

### Wyniki Testu (3 uruchomienia)

| Format | Avg Similarity | Line Variance | Syntax OK | Różnice |
|--------|---------------|---------------|-----------|---------|
| **LogicML** | **56.9%** | 94.9 | 100% | 98 linii |
| YAML | 41.0% | **8.7** | 100% | 57 linii |
| Gherkin | 14.1% | 374.9 | 100% | 118 linii |

### 💡 Kluczowe Wnioski

| Wniosek | Szczegóły |
|---------|-----------|
| **LogicML = najwyższa spójność** | 56.9% podobieństwo między runami |
| **YAML = najniższa wariancja** | 8.7 linii (stabilny rozmiar) |
| **Gherkin = niestabilny** | 14.1% podobieństwo, 375 wariancja |

### 📈 Charakterystyka Formatów

```
YAML:
  ✓ Stabilny rozmiar (100-107 linii)
  ✓ 100% syntax OK
  ✗ Średnia spójność logiki (41%)

LogicML:
  ✓ Najwyższa spójność (56.9%)
  ✓ 100% syntax OK
  ⚠ Większa wariancja rozmiaru

Gherkin:
  ✗ Bardzo niestabilny (14.1%)
  ✗ Ogromna wariancja (374.9)
  ✗ Kod bardzo różni się między runami
```

### 📁 Nowe Pliki

```
docs/benchmark.md              # Pełna dokumentacja benchmarków
examples/14_repeatability_test.py  # Test powtarzalności
examples/output/repeatability_test.json  # Wyniki
```

# Test powtarzalności (3 runy)
python examples/14_repeatability_test.py \
  --file tests/samples/sample_class.py

# Test z 5 runami
python examples/14_repeatability_test.py \
  --file tests/samples/sample_class.py \
  --runs 5 \
  --formats yaml logicml gherkin
```

### 🎯 Rekomendacje

| Cel | Zalecany Format |
|-----|-----------------|
| **Stabilny rozmiar** | YAML (8.7 variance) |
| **Spójna logika** | LogicML (56.9% similarity) |
| **Unikać** | Gherkin (14.1% similarity) |
| **Produkcja** | YAML + LogicML |

### 📋 Co Różni Się Między Runami?

1. **Importy** - różna kolejność, różne moduły
2. **Docstringi** - różne formatowanie
3. **Implementacja** - różne podejście do tej samej logiki
4. **Nazwy zmiennych** - czasem różne nazwy pomocnicze
5. **Komentarze** - dodatkowe lub brakujące

<!-- docs:section limitations -->
## Limits

Unchanged historical examples remain subject to their original assumptions. Placement conformance does not establish semantic correctness or deployment.

<!-- docs:section next_actions -->
## Maintenance

Update this declared version when changing its substantive findings.
