# GOV-PUSH: bezpośredni push do gałęzi docelowej

Kod: `GOV-PUSH-001` emitowany przez zarządzany hook `.githooks/pre-push`
i zarejestrowany w `governance/diagnostics.json`.

## Situation

`git push` próbuje zaktualizować gałąź zadeklarowaną w
`delivery.targetBranches` (domyślnie `main`): wprost (`git push origin main`),
przez refspec (`HEAD:main`) albo usuwając ją. Repozytoria z profilem dostarczania
`main-only-planfile`, `main-only-files` lub `local-audit` są zwolnione.

## Meaning

Gałąź docelowa przyjmuje zmiany wyłącznie przez przejrzany pull request scalany
przez validatora. Bezpośredni push omija review, required checks i CI, które w
wielu repozytoriach uruchamia się tylko dla PR; 19.10.2026 trzynaście takich
commitów w paxlet-com/willmux pogorszyło `main` z 1 do 4 błędów i 32 wyjątków testów.

## Safe resolution

1. Zostaw lokalny commit na gałęzi ticketu (`ticket/NNN-...`); nie przenoś go na `main`.
2. Wypchnij gałąź ticketu: `git push -u origin ticket/NNN-...`.
3. Otwórz pull request do gałęzi docelowej i poczekaj na validatora oraz CI.
4. Jeśli commit powstał już na lokalnym `main`, utwórz z niego gałąź ticketu
   (`git branch ticket/NNN-... main`) i przywróć `main` do `origin/main` dopiero
   po sprawdzeniu, że gałąź ticketu zawiera całą pracę.

## Verification

`git push origin ticket/NNN-...` kończy się kodem 0, a pull request pokazuje
uruchomione required checks. `git push origin main` nadal kończy się `GOV-PUSH-001`.

## Do not

- Nie omijaj hooka (`--no-verify`, zmiana `core.hooksPath`); agentom nie wolno omijać hooków.
- Nie wymuszaj pusha (`--force`) na gałąź docelową ani nie usuwaj jej.
- Nie zmieniaj `delivery.targetBranches` ani profilu dostarczania, żeby obejść blokadę.

## Related rules

`C-HOST-001` (zarządzane hooki są aktywne), zasada hosta „Never commit on main”.
