# GOV-TICKET-ALLOCATION i GOV-TICKET-LOCK

## Situation

Runbook obejmuje `GOV-TICKET-ALLOCATION-001`–`004` oraz
`GOV-TICKET-LOCK-001`–`004`. Kody oznaczają
aktywny lub uszkodzony lock, nieczytelny high-water, istniejący katalog,
nieodświeżone zdalne refy, ticket poza rezerwacją albo dwa różne intenty z tym
samym numerem. Kod `003` oznacza brak świeżego receipt z zarejestrowanego
allocatora, a `004` — że receipt wskazuje tożsamość już widoczną w repozytorium.

## Meaning

Numer ticketu jest zasobem całej zadeklarowanej domeny writerów. Dla linked
worktree jednego klonu `project/new-ticket.sh` odświeża refy, zdobywa wspólny
lock i podnosi high-water. Niezależne klony lub node nie współdzielą tego stanu,
więc muszą używać profilu `registered`: jeden atomowy proces przydziela numer i
wydaje krótko żyjący receipt związany z request digest oraz fencing tokenem.
Ręczne `mkdir`, skopiowanie katalogu albo sam `fetch` nie tworzą rezerwacji.

## Safe resolution

1. Zatrzymaj nowe skutki przegrywającego writera i zachowaj dokładny HEAD,
   lease, PR oraz lossless material delta.
2. Wybierz kanoniczną historię wyłącznie z chronionego terminalnego merge
   receiptu; nazwa brancha, czas lokalny i status Markdown nie rozstrzygają.
3. Dla braku receipt wyślij kanoniczny request emitowany przez
   `new-ticket.sh` do skonfigurowanego `processUri`, a następnie ponów dokładne
   wywołanie z otrzymanym receiptem.
4. Przy kolizji odwołaj superseded lease, zaalokuj successor przez registered
   process i odtwórz na aktualnym target wyłącznie zachowany material delta.
5. Zweryfikuj równoważność diffu i wszystkie bramki, utwórz successor PR, a
   dopiero potem zamknij predecessor jako `superseded` i uruchom Validator dla
   exact head.
6. W profilu lokalnym napraw łączność z `origin` i ponów allocator; stale lock
   usuwaj tylko po potwierdzeniu braku procesu.
7. Gdy zarezerwowany ticket (numer nie większy od high-water, rekord w
   `.subactor/leases/`) stracił kanoniczny checkout, branch lub
   niezacommitowane metadane, nie alokuj nowego numeru i nie odtwarzaj ich
   ręcznie. Uruchom `new-ticket.sh --workstream W --restore-request FILE
   --recovery-lease-store DIR`. Request
   `new-project.ticket-restoration-request/v1` wiąże ticket, `worktreeId`,
   dokładny HEAD (`null` oznacza bazę rezerwacji), snapshot
   `new-project.ticket-metadata-snapshot/v1` z jego SHA-256 oraz CAS żywego
   leasu kontrolera w fazie `claimed` lub `editing`. Restoration tworzy tylko
   brakujący branch, względną rejestrację checkoutu oraz `README.md` i
   `intent.json`; ponowienie po przerwaniu kończy brakujące kroki, a gotowy
   stan zwraca `ALREADY_RESTORED`. Nie daje prawa do edycji ani merge: dalej
   obowiązuje `work_start_check.py --ticket`.
8. Dla istniejącej rezerwacji `local-single-clone` bez zewnętrznego store użyj
   jawnego `--restore-local-request FILE`, z własnym writer actor/session oraz
   `NEW_PROJECT_LEASE_REVISION` i `NEW_PROJECT_FENCING_TOKEN`. Request ma te same
   pola co zewnętrzny, schema `new-project.local-ticket-restoration-request/v1`
   i dodatkowe `reservationSha256`: SHA-256 dokładnych bajtów kanonicznego
   `.subactor/leases/{worktreeId}.json`. CAS i właściciel odnoszą się do tego
   pliku. Kontroler utrzymuje jego blokadę, sprawdza repozytorium i zakres oraz
   ponawia kontrolę przed każdym skutkiem. Nie przekazuj `--recovery-lease-store`
   w tej ścieżce; odmowa store nigdy nie przełącza automatycznie na local.
   Wygasła, zamrożona lub zwolniona rezerwacja jest odrzucana. Najpierw wymagane
   jest osobne, uprawnione przejęcie przez kontroler; restoration nie odnawia
   lease, nie zwiększa fencing i nie przywraca źródeł ze snapshotu.

## Verification

- `git worktree list --porcelain` pokazuje każdy sklasyfikowany checkout.
- Wspólny high-water jest nie mniejszy od najwyższego niescalonego claimu.
- Każdy numer ma jedną tożsamość `ticket + summary + workstream`.
- W trybie rozproszonym receipt wiąże repository, request digest, issuer,
  process URI, ticket, fencing token i niewygasły lease.
- Predecessor nie jest zamknięty przed utworzeniem i weryfikacją successora.
- Ponowne uruchomienie workspace checkera nie emituje kodów allocation.

## Do not

- Nie zmieniaj numeru przez ręczne `mv` i nie kopiuj historii obu branchy.
- Nie usuwaj dirty/unreachable worktree ani locka bez identyfikacji procesu.
- Nie przydzielaj numeru offline ze starych refów.
- Nie przejmuj cudzej rezerwacji po wygaśnięciu leasu; zmianę właściciela
  wykonuje kontroler, a restoration jej wymaga.
- Nie traktuj lokalnego high-water, receipt ani samego ERROR jako merge lub
  execution authority.
- Nie zamykaj przegrywającego PR przed zachowaniem delta i utworzeniem
  successora.

## Related rules

- `P-CORE-022`
- `C-CONCURRENCY-001`, `C-CONCURRENCY-002`, `C-CONCURRENCY-003`
- `C-CONCURRENCY-004`, `P-TICKET-ALLOCATION-001`
- `P-WORKSPACE-001`, `C-WORKSPACE-001`
