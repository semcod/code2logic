# GOV-HOST-MERGE: przestarzały blok autonomicznego scalania w instrukcjach hosta

Kod: `GOV-HOST-MERGE-001` (ostrzeżenie) emitowany przez `governance_check.py`
i zarejestrowany w `governance/diagnostics.json`.

## Situation

`AGENTS.md`, `CLAUDE.md` lub `GEMINI.md` w katalogu głównym repozytorium zawiera
blok `<!-- wellmanifest:autonomous-merge:start -->` w starej treści, powołującej
się na `wellmanifest/merge@ticket-008` („Prymat Zielonych Testów”).

## Meaning

Stary blok pozwala agentowi scalać PR po zielonych testach, rotować konta
recenzentów, używać `gh pr merge --admin` i luzować limity WIP. Obowiązujący
standard dopuszcza wyłącznie niezależnego Validatora do zatwierdzania i
scalania; agent czeka na limity API i nie omija reguł. Agenci czytający stary
blok scalali PR samodzielnie (issue #507).

## Safe resolution

1. Przydziel ticket w repozytorium, którego plik dotyczy; nie edytuj pliku na `main`.
2. Podgląd: `python3 <standard>/scripts/host_publication_policy.py --path <plik>
   --expected-sha256 <bieżący sha256>` (bez `--apply`); sprawdź `changed`.
3. Zastosuj z kopią zapasową (`--apply --backup-directory <katalog spoza repo>`)
   w worktree ticketu, zatwierdź i opublikuj przez zwykły PR i Validatora.
4. Plik hosta spoza Git (np. `~/github/subactor/AGENTS.md`) uzgadnia jego właściciel
   z kopią zapasową; nie twórz w tym celu repozytorium.

## Verification

`./project/governance-check.sh` nie zgłasza `GOV-HOST-MERGE-001`, a plik zawiera
zdanie „Only the independent Validator may approve and merge.”.

## Do not

- Nie usuwaj znaczników bloku ani nie przepisuj go ręcznie poza narzędziem.
- Nie scalaj PR samodzielnie, nie używaj `--admin` i nie zmieniaj kont recenzentów.
- Nie stosuj zmiany do wielu repozytoriów jednym commitem ani bez ticketu.

## Related rules

`GOV-HOST-MERGE-001`, `GOV-AGENT-HOST-001`, `GOV-PUSH-001`; issue #507.
