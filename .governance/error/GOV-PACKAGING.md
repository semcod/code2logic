# GOV-PACKAGING: metadane paczki nie egzekwują standardu

Kody: `GOV-PACKAGING-001`, `GOV-PACKAGING-002`, `GOV-PACKAGING-003`
(emitowane przez `scripts/agent_host_check.py`).

## Situation

Repozytorium ma marker stacku (`pyproject.toml` lub `package.json`), ale:

- `001` — brak bloku `[tool.wellmanifest]` / klucza `"wellmanifest"` albo brak
  w nim pola `standard`, `revision` lub `gate`;
- `002` — blok deklaruje inną wersję/rewizję standardu niż
  `.governance/manifest.lock.json`, albo wskazuje nieistniejącą bramę;
- `003` — lifecycle paczki nie uruchamia bramy: `scripts.prepare` w
  `package.json` nie wywołuje instalatora hostów, a `addopts` w
  `[tool.pytest.ini_options]` nie ładuje pluginu governance.

## Meaning

`npm install` i `pytest` wykonują się i tak — również wtedy, gdy agent nie
przeczytał żadnego pliku instrukcji. To jedyny punkt w cyklu pracy, w którym
standard można narzucić bez współpracy modelu. `001`/`002` to utrata
widoczności wersji standardu w metadanych paczki; `003` to brak faktycznej
egzekucji.

## Safe resolution

1. Odczytaj `standard.version` i `standard.sourceRevision` z
   `.governance/manifest.lock.json`.
2. Wpisz je do bloku governance w metadanych paczki wraz ze ścieżką bramy:

   ```toml
   [tool.wellmanifest]
   standard = "0.18.1"
   revision = "<sourceRevision z locka>"
   gate = "project/governance-check.sh"

   [tool.pytest.ini_options]
   addopts = "-p wellmanifest_governance"
   ```

   ```json
   "wellmanifest": { "standard": "0.18.1", "revision": "…", "gate": "project/governance-check.sh" },
   "scripts": { "prepare": "./scripts/install-agent-hosts.sh" }
   ```

3. Po każdym upgrade standardu zaktualizuj blok razem z lockiem — rozjazd jest
   wykrywany deterministycznie.
4. Potwierdź: `python3 scripts/agent_host_check.py --root .`.

## Verification

- `python3 scripts/agent_host_check.py --root . --format json` zwraca `ok: true`.
- `npm install` w czystym klonie ustawia `core.hooksPath` bez ręcznej komendy.
- Zmiana wersji w locku bez zmiany metadanych paczki daje `GOV-PACKAGING-002`.

## Do not

- Nie wpisuj wersji standardu ręcznie „na oko” — pochodzi z locka.
- Nie zastępuj lifecycle hooka dokumentacją w `README.md`.
- Nie wyłączaj `prepare` przez `npm install --ignore-scripts` w CI governance.

## Related rules

- `AGENTS.md` rule 22 (HOST-AGNOSTIC STANDARD)
- `C-HOST-003`
- `GOV-STACK-001` (deklarowany stack musi mieć marker)
