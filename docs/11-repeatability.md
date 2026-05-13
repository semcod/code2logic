
[← README](../README.md) | [Docs Index](00-index.md)

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