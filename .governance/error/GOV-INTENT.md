# GOV-INTENT

## Situation

Kody `GOV-INTENT-001`–`GOV-INTENT-003` oznaczają, że diff implementacyjny nie
ma ważnego mandatu. Kolejno: ticket nie był w stanie implementacyjnym,
`intent.json` jest nieobecny lub niepoprawny, albo intent nie istnieje w drzewie
pierwszego materialnego commita.

## Meaning

Intent jest planem, który kontroler zapisuje i waliduje **zanim** rozpocznie
edycję. Granica czasowa dotyczy sesji wykonawczej, nie wymaga osobnego commita.
Intent może wejść atomowo z pierwszą materialną zmianą, o ile znajduje się w
drzewie tego commita i wcześniejsza autoryzacja sesji wiąże dokładnie ten zakres.

`GOV-INTENT-003` jest osobnym faktem od `GOV-SCOPE-001`. Zakres może być
idealnie zgodny z `allowedPaths`, a mandat i tak nie powstał na czas.

## Safe resolution

1. Zbuduj jeden atomowy commit zawierający intent i materialną zmianę:

   ```
   feat|fix|chore(ticket-NNN): intent + material implementation
   ```

   Kontroler najpierw waliduje `intent.json` i session authorization, następnie
   edytuje implementację, a na końcu commit obejmuje oba elementy.

2. Po trusted merge nie edytuj repozytorium. Chroniony kontroler zapisuje
   zewnętrzny receipt terminalny związany z PR head, merge SHA i checks.

3. Gdy kod został zacommitowany przed intentem, przebuduj nieopublikowaną gałąź
   atomowo. Nie przepisuj opublikowanej, zaufanej historii.

4. Gdy błąd `delivery ... incomplete` lub `bounded-delivery fields` zawiera
   `move X to PATH`, przenieś pole dokładnie do wskazanej ścieżki zamiast
   przepisywać intent. Pola architektury (`interfaceChanges`, `dataChanges`,
   `components`, `ui`, `rollback`, `status`, `decision`,
   `responsibilityChanges`) należą do `delivery.architecture`, limity `max*` do
   `delivery.budgets`, a pozostałe pola kontraktu bezpośrednio do `delivery`.
   Przeniesione pole nie jest akceptowane jako synonim; nieznane pola pozostają
   odrzucone bez podpowiedzi położenia.

## Verification

`./project/governance-check.sh` bez `--base` na gałęzi `ticket/NNN-*` sam
wyznacza bazę jako `git merge-base HEAD origin/<target>` (target z
`delivery.targetBranches` manifestu, a przy kilku z `delivery.targetBranch`
ticketu) i bada zacommitowany zakres, więc brak kontraktu `delivery` jest
wykrywany lokalnie. Brak `origin/<target>` kończy się `GOV-BASE-001` zamiast
pustego `GOV-PASS`; wykonaj `git fetch origin <target>` albo podaj `--base`.
Jawne `--base` lub `--changed-file` zawsze wygrywa. Na innych gałęziach i przy
odłączonym HEAD wywołanie bez argumentów nadal bada tylko drzewo robocze.
Chroniona bramka zakresowa potwierdza, że intent istnieje w pierwszym
materialnym commicie.

Dowodem jest wyłącznie tryb zakresowy:

```sh
./project/governance-check.sh --base origin/main --head HEAD
```

Uruchom go przed każdym pushem gałęzi ticketowej. Wynik `GOV-PASS` z gołego
wywołania poza gałęzią `ticket/NNN-*` nie jest wystarczającym dowodem.

## Do not

- Nie traktuj `GOV-PASS` z domyślnego, bezargumentowego wywołania jako dowodu
  poprawnej kolejności commitów.
- Nie przepisuj opublikowanej, zaufanej historii.
- Nie zamykaj ticketu na niescalonej gałęzi pełnego diffu.
- Nie twórz osobnego plan-only commita ani closure commita.

## Related rules

- `P-CORE-008`, `P-CORE-014`, `P-CORE-023`
- `C-TICKET-008`, `C-TICKET-017`
- `C-PUBLISH-003`, `C-PUBLISH-009`
