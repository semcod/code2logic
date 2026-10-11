# GOV-VERSION: rozjazd wersji między VERSION a deklaracjami w pakiecie

Kody: `GOV-VERSION-001` (emitowany przez `scripts/governance_check.py`).

## Situation

W repozytorium znajduje się plik `VERSION`, ale deklaracja wersji w manifestach pakietów (`pyproject.toml`, `setup.py`, `package.json`, `Cargo.toml`) lub statyczne `__version__` w kodzie źródłowym (`__init__.py`) różni się od wartości w `VERSION`.

## Meaning

Plik `VERSION` jest jedynym autorytatywnym źródłem prawdy (SSOT) dla wersji repozytorium i jego pakietu. Rozbieżność prowadzi do publikacji pakietów o niewłaściwych numerach na rejestrach (PyPI, npm, crates.io), błędu regresji (`Local version state regresses behind released evidence`) oraz fałszywych stanów synchronizacji.

Ponadto w modelach podziału na workstreamy (`manifest.json`), workstream `integration` posiada `VERSION` i manifesty pakietów, podczas gdy `application` posiada kod źródłowy. Zahardkodowanie `__version__ = "X.Y.Z"` w kodzie źródłowym uniemożliwia podbicie wersji przez `integration` bez naruszenia izolacji ścieżek (`GOV-WORKSTREAM-003`).

## Safe resolution

1. Upewnij się, że `VERSION` zawiera docelowy numer wersji (np. `2.2.51`).
2. W manifestach pakietów zaktualizuj wersję do zgodnej z `VERSION`:
   - `pyproject.toml`: `version = "2.2.51"` w `[project]` lub sekcji narzędzia;
   - `setup.py`: `version = "2.2.51"` (lub dynamiczny odczyt z `VERSION`);
   - `package.json`: `"version": "2.2.51"`;
   - `Cargo.toml`: `version = "2.2.51"` w `[package]`.
3. W kodzie źródłowym Pythona (`__init__.py`) preferuj dynamiczny odczyt wersji:
   ```python
   try:
       from importlib.metadata import version as _meta_version
       __version__ = _meta_version("my-package")
   except Exception:
       __version__ = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
   ```
   Jeśli w kodzie pozostaje statyczne przypisanie `__version__ = "..."`, jego wartość musi być identyczna z `VERSION`.
4. Uruchom bramkę: `./project/governance-check.sh`.

## Verification

- `governance_check.py` zwraca sukces i brak naruszeń `GOV-VERSION-001`.
- Narzędzia budowania (`python -m build`, `uv build`, `npm pack`) generują artefakty o numerze zgodnym z `VERSION`.
- `goal check-versions` potwierdza spójność deklaracji lokalnych.

## Do not

- Nie hardkoduj różnych wersji w różnych manifestach w tym samym repozytorium.
- Nie pozostawiaj przestarzałego `setup.py` podczas migracji do `pyproject.toml`.
- Nie pomijaj synchronizacji wersji przy przygotowywaniu wydań.

## Related rules

- `P-CORE-027`
- `AGENTS.md` rule 23
