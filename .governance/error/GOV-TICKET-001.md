# GOV-TICKET-001: brak aktywnego właściciela implementacji

## Situation

Kod pojawia się, gdy diff implementacyjny nie ma dokładnie jednego ticketu ze
statusem `IN_PROGRESS`. Typowy przypadek to ustawienie `DONE / DONE` na branchu
PR przed trusted merge.

## Meaning

Zamknięty ticket nie udziela już uprawnienia do swojego `allowedPaths`.
Implementacyjny PR musi zachować `IN_PROGRESS / PUBLICATION` aż exact-head
review zostanie zintegrowany z gałęzią domyślną.

## Safe resolution

1. Sprawdź, czy PR nadal wskazuje oczekiwany HEAD i dokładnie jeden ticket.
2. Jeżeli implementacja nie została scalona, przywróć ticket do
   `IN_PROGRESS / PUBLICATION` na tym samym branchu i ponów bramę.
3. Po trusted merge nie zmieniaj repozytorium. Chroniony kontroler zapisuje
   terminalny receipt z PR head, merge SHA i post-merge checks oraz zwalnia
   workstream.

## Verification

- Diff implementacyjnego PR zawiera aktywny ticket i przechodzi governance
  gate.
- Zewnętrzny receipt wiąże merge SHA będący przodkiem bieżącego `main` i nie
  tworzy commita ani PR-a.
- Zdalny branch implementacyjny znika dopiero po merge.

## Do not

- Nie osłabiaj `activeStatuses` i nie zezwalaj `DONE` na autoryzowanie diffu.
- Nie twórz closure commita, brancha ani PR-a.
- Nie traktuj lokalnego statusu Markdown jako trusted approval.

## Related rules

- `P-CORE-014`, `P-CORE-023`
- `C-TICKET-017`
- `C-PUBLISH-003`, `C-PUBLISH-009`
