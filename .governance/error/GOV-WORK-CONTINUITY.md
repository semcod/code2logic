# GOV-WORK-CONTINUITY

## Situation

- `GOV-CONTINUITY-001` oznacza niepoprawny checkpoint albo próbę handoffu
  brudnego workspace bez autoryzowanego commita lub bezpiecznego snapshotu.
- `GOV-CONTINUITY-002` oznacza przerwany, cofnięty lub ponownie związany chain
  receiptów.
- `GOV-CONTINUITY-003` oznacza, że bieżący Git, intent albo workspace nie
  odpowiada zapisowi, od którego agent próbuje wznowić pracę.

## Meaning

Nie można dowieść, że materialna delta i zakres zadania są odtwarzalne bez
pamięci rozmowy. Checkpoint jest projekcją nawigacyjną, więc rozjazd nie
uprawnia go do nadpisania bieżącego filesystemu, odtworzenia snapshotu ani
użycia zapisanego fencing tokenu.

## Safe resolution

1. Zatrzymaj efekty repozytorium i zewnętrzne; zachowaj bieżący worktree bez
   resetu, cleanowania i automatycznego stasha.
2. Odczytaj bieżący branch/HEAD, `git status`, intent, PR, Validator run,
   terminalne receipt'y i authority lease z ich źródeł prawdy.
3. Uruchom `work_continuity.py validate` dla checkpointu oraz całego rejestru.
   Dla `002` odtwórz pełny chain z chronionego receipt store; nie dopisuj
   sztucznego poprzednika.
4. Uruchom `work_continuity.py verify --root . --ticket ticket-NNN`.
5. Dla `001` zapisz materialną deltę w autoryzowanym commicie albo zleć
   chronionemu kontrolerowi content-addressed snapshot po secret scan. Jeżeli
   żadna droga nie jest dozwolona, ustaw ticket na `BLOCKED` i zachowaj dane.
6. Dla `003` przejdź do `reconcile`: porównaj obie delty, wybierz authority z
   aktualnego intentu i receiptów, a przed dalszym zapisem pozyskaj aktualny
   lease/fencing token oraz uruchom governance gate.

## Verification

```bash
python3 .governance/work_continuity.py validate <checkpoint-or-registry.json>
python3 .governance/work_continuity.py verify --root . --ticket ticket-NNN
./project/governance-check.sh --actor agent
```

Oczekiwany wynik `verify` to `matches-observed-state` wraz z
`authorityVerified=false`. Kontroler osobno potwierdza aktualne authority i
lease przed efektem.

## Do not

- Nie traktuj streszczenia rozmowy, ticket prose, TODO ani raw logu jako kopii
  danych roboczych.
- Nie używaj `git reset`, `git clean`, force push, automatycznego restore ani
  usuwania worktree do usunięcia rozjazdu.
- Nie kopiuj sekretu, pełnego diffu, review body lub absolutnej ścieżki hosta do
  checkpointu, logu lub receiptu.
- Nie uznawaj lokalnego rejestru `.git` za ochronę przed utratą dysku i nie
  deklaruj cross-machine durability bez zewnętrznego receipt store.
- Nie odnawiaj sesji ani lease wyłącznie na podstawie checkpointu.

## Related rules

- `P-CONTINUITY-001`
- `P-CONTINUITY-002`
- `P-CONTINUITY-003`
- `C-CONTINUITY-001`
- `C-CONTINUITY-002`
- `C-CONTINUITY-003`
