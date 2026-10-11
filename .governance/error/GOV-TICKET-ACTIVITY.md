# GOV-TICKET-ACTIVITY

## Situation

`GOV-TICKET-ACTIVITY-001` oznacza, że zarządzana polityka aktywności albo
klonowy rejestr terminalnych receiptów jest nieczytelny, niespójny z repozytorium
lub używa niewspieranego kontraktu.

## Meaning

Resolver nie ma dowodu, że historyczna projekcja aktywnego statusu utraciła
rezerwację. Pozostawia ją aktywną; nie uznaje tekstu, nazwy brancha ani wpisu w
cache za terminalne authority.

## Safe resolution

1. Zachowaj wadliwy plik rejestru jako dowód poza checkoutem i uruchom
   `ticket_activity.py validate`, aby ustalić naruszony binding.
2. Odtwórz rejestr z chronionego źródła receiptów albo przenieś wadliwy cache w
   odzyskiwalne miejsce. Brak opcjonalnego cache bezpiecznie wraca do projekcji
   statusu.
3. Dodaj receipt przez `ticket_activity.py record --receipt <plik>`; komenda
   zapisuje atomowo i odrzuca wpis, który nie zgadza się z lokalnym ancestry
   ani z dokładnym dowodem patch-id chronionego rebase lub squash.
4. Gdy zdarzenie terminalne nie istnieje lub jego typ nie jest jeszcze
   wspierany, skieruj pracę do `BLOCKED` lub `PLAN` przez autoryzowany lifecycle.
   Taki stan zwalnia rezerwację bez fałszowania historii.

## Verification

- `ticket_activity.py validate` zwraca `status=valid`.
- `ticket_activity.py resolve` wskazuje `terminal-receipt` wyłącznie dla SHA
  zintegrowanych z zadeklarowaną gałęzią docelową. Zwykły merge wymaga
  ancestry; rebase wymaga istniejącego liniowego head, równolicznej liniowej
  serii kończącej się terminalnym SHA i identycznych uporządkowanych patch-id.
  Squash wymaga pojedynczego terminalnego commita, którego patch-id jest
  identyczny z agregatem pełnego zakresu od wspólnej bazy do chronionego head.
- Allocator, governance gate i overlap checker zwracają ten sam wynik.

## Do not

- Nie zmieniaj historycznego README na `DONE` tylko po to, aby ominąć blokadę.
- Nie dodawaj wyjątku dla ticketu, brancha, repozytorium ani statusu w kodzie.
- Nie wyłączaj bramki i nie usuwaj unmerged branchy lub evidence jako remediacji.
- Nie traktuj mutable ref, URL, opisu PR ani samego istnienia receipt jako dowodu.
- Nie deklaruj metody merge w receipt jako zamiennika lokalnej weryfikacji Git.

## Related rules

- `P-TICKET-ACTIVITY-001`
- `P-RECOVERY-001`
- `C-TICKET-ACTIVITY-001`
- `C-RECOVERY-001`
