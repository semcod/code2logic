# GOV-WORKSPACE-LIFECYCLE

## Situation

Kody `GOV-WORKSPACE-LIFECYCLE-001`–`004` oznaczają pozostały linked worktree,
duplikat klonu, audyt, którego nie da się bezpiecznie zakończyć, albo
non-defaultowy lokalny branch pozostawiony w `refs/heads`.

Zdalny audyt ma osobne, niezamienne kody:

| Kod | Obserwacja | Pierwszy bezpieczny krok |
| --- | --- | --- |
| `GOV-BRANCH-LIFECYCLE-001` | wyłączone usuwanie brancha po merge | sprawdzić chronioną konfigurację repozytorium |
| `GOV-BRANCH-LIFECYCLE-002` | branch bez otwartego PR | odczytać dokładny HEAD, historię PR i pozostały intent |
| `GOV-BRANCH-LIFECYCLE-003` | brak, błąd formatu lub niespójność snapshotu | ponowić obserwację, bez zmiany branchy |

## Meaning

Stan terminalny wymaga jednego podstawowego checkoutu, lecz żaden checker nie
ma prawa automatycznie niszczyć nieznanych danych. Lokalny filesystem i zdalny
GitHub są osobnymi granicami dowodu.

Snapshot branch lifecycle v1 nie zawiera SHA branchy, zamkniętych PR,
aktywnych writerów ani decyzji właściciela. `002` nie dowodzi porzucenia pracy,
konfliktu zapisu ani możliwości bezpiecznego usunięcia. `003` nie jest poleceniem
cleanup. Kod wypchnięty na branch nie jest jeszcze scalony, wydany ani wdrożony;
sam push/draft PR nie uruchamia terminalnego cleanup.

## Safe resolution

### Najpierw skutek i klasyfikacja

1. Ustal, czy zlecono zachowanie postępu, push, merge, release, deploy czy
   terminalny cleanup. Odczytaj aktualne lokalne/zdalne SHA, dirty state i PR.
   Nie ponawiaj push po timeout, zanim sprawdzisz, czy zdalny ref już wskazuje
   oczekiwany commit. Obserwacja identycznego SHA nie dowodzi merge lub wydania.
2. Dla `GOV-BRANCH-LIFECYCLE-001` właściwy operator/kontroler ustawia
   `delete_branch_on_merge=true` w granicach istniejącej autoryzacji. Odczyt
   ustawienia potwierdza efekt; nie usuwa się przy tym niescalonych branchy.
3. Dla `GOV-BRANCH-LIFECYCLE-002` odczytaj również zamknięte PR i ewentualny
   PR następcy. Zachowaj oryginalny HEAD oraz bezpieczny snapshot niezapisanych
   zmian. Kontynuuj istniejący ticket/PR, jeśli odpowiada autoryzowanej pracy.
   Przy zastąpieniu starego brancha uzgodnij wszystkie kryteria intentu przez
   zarządzany `branch_intent_reconciliation.py`. Nie twórz pustego PR ani
   duplikatu zadania dla samego zaspokojenia bramki. Usunięcie wymaga osobno
   zweryfikowanej dyspozycji i ponownego odczytu dokładnego refa przed skutkiem.
4. Dla `GOV-BRANCH-LIFECYCLE-003` uruchom ponowny odczyt z chronionego
   kolektora. Lista branchy i PR może zmienić się między wywołaniami API;
   zweryfikuj wskazane rozbieżne refy. Nie „naprawiaj” JSON przez usunięcie
   wpisu i nie usuwaj zdalnego brancha, aby dopasować go do starego snapshotu.
5. Przy tej samej odmowie i niezmienionych wejściach zapisz jeden oczekujący
   krok w istniejącym journalu/tickecie i nazwij konkretny brak. Wznów próbę
   po zmianie istotnego wejścia lub zgodnie z ograniczonym retry dla awarii
   przejściowej. Nie resetuj licznika przez nowy prompt, ticket lub worktree.
   Kontynuuj niezależną autoryzowaną pracę. Ta recepta nie zamienia FAIL w PASS.

### Cleanup dopiero po klasyfikacji

1. Dla każdego checkoutu zapisz dirty state, branch, HEAD i tożsamość remote.
2. Potwierdź, że HEAD jest zintegrowany albo że właściciel jawnie porzucił
   unmerged pilot. Zweryfikuj wymagany receipt terminalny, zwolnienie lease
   i brak aktywnego procesu korzystającego z checkoutu. Historia wspólna z innym
   branchem nie oznacza sama w sobie konkurującego writera ani prawa usunięcia.
3. Linked worktree usuń przez `git worktree remove <dokładna-ścieżka>`, potem
   `git worktree prune` i dopiero wtedy usuń zwolniony lokalny branch.
4. Zweryfikowany duplikat klonu przenieś do odzyskiwalnego kosza.
5. Dla kodu `004` sprawdź wskazane `branch`, `head`, `defaultBranch`, `checkout`
   i `primary`. Jeśli commit nie jest zintegrowany, zachowaj go pod opisanym,
   zdalnie zweryfikowanym tagiem/refem albo uzyskaj jawną decyzję właściciela.
   Dopiero po zwolnieniu worktree usuń dokładny lokalny ref. W czasie aktywnej
   pracy można zwolnić branch z findingu wyłącznie przez dokładną ścieżkę
   checkoutu przekazaną jako `--allow`; wzorce i sama nazwa brancha nie są
   wyjątkiem.

## Verification

- Lokalny workspace checker kończy się `GOV-WORKSPACE-PASS` bez
  nieallowlistowanych checkoutów.
- Osobny workflow GitHub potwierdza zdalne branche i ich powiązanie z PR oraz
  `delete_branch_on_merge=true`; nie potwierdza lokalnego filesystemu. Oczekiwanie
  „tylko main” dotyczy zakończonego porządkowania, nie aktywnej dostawy.
- Każdy usunięty ref/checkout ma dokładny, zweryfikowany cel i dowód dopuszczalności.
- Status podaje osobno: commit, push, PR, testy, merge, release i deploy. Brak
  publikacji w rejestrze nie jest zastępowany wersją wypisaną przez lokalny runtime.

## Do not

- Nie używaj globów rekurencyjnych ani nie usuwaj primary worktree.
- Nie uznawaj zielonego CI za dowód stanu lokalnego dysku.
- Nie usuwaj danych dirty lub unreachable bez decyzji właściciela.
- Nie traktuj `GOV-WORKSPACE-PASS` jako uprawnienia do usuwania refów; checker
  jest wyłącznie read-only.
- Nie utożsamiaj pustej listy otwartych PR z dowodem, że wszystkie prace scalono.
- Nie wyłączaj sekretów, scope, lease, hooka ani niezależnego review w celu
  skrócenia publikacji. Wadliwą diagnostykę popraw z testem regresji u jej źródła.

## Related rules

- `P-WORKSPACE-001`–`004`
- `C-WORKSPACE-001`–`004`
- `P-BRANCH-001`–`003`
- `P-RECOVERY-001`, `C-RECOVERY-001`, `P-BLOCK-005`
