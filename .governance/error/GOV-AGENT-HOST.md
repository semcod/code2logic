# GOV-AGENT-HOST: kontrakt host-agnostyczny nie jest aktywny

Kody: `GOV-AGENT-HOST-001`, `GOV-AGENT-HOST-002`, `GOV-AGENT-HOST-003`,
`GOV-AGENT-HOST-007`
emitowane przez `.githooks/pre-commit`, oraz `GOV-AGENT-HOST-004`,
`GOV-AGENT-HOST-005`, `GOV-AGENT-HOST-006` emitowane przez
`scripts/agent_host_check.py`. Wszystkie siedem jest zarejestrowanych w
`governance/diagnostics.json`; `scripts/audit_diagnostics.py` skanuje teraz
również `.githooks`, więc kod emitowany przez hooka nie może już wypaść z
katalogu niezauważony.

Ten sam audyt emituje `GOV-AGENT-HOST-004`, gdy instrukcje przekraczają limit
hosta, tracą `checkpoint`/`handoff`/`stop`, zawierają skonfigurowaną sprzeczność
albo deklarują required check, którego workflow nie publikuje. To są blokery
przed rozpoczęciem długiej sesji, a nie sygnały do kolejnych ślepych retry.

## Situation

`001`–`003` oraz `007` pojawiają się przy commicie: branch nie jest związany z ticketem
`IN_PROGRESS`, brakuje `project/ticket-NNN/README.md` w stagowanej migawce albo
commit próbuje zapisać terminalne zamknięcie w repozytorium lub zawiera
wyłącznie nośniki śledzenia ticketu bez materialnego rezultatu.

`004`–`006` pojawiają się w bramie: brakuje pliku instrukcji deklarowanego przez
`agent-hosts.json`, hook nie istnieje lub nie jest wykonywalny, albo
`core.hooksPath` nie wskazuje na katalog zarządzanego hooka.

## Meaning

Plik instrukcji (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, reguła Cursora,
`.aider.conf.yml`, instrukcje Copilota) jest sugestią dla modelu — każdy host
może go zignorować. Jedyne warstwy, które nie są sugestią, to hook gita,
`governance / enforce` w CI oraz lifecycle paczek. `GOV-AGENT-HOST-006`
oznacza, że repozytorium wygląda na zgodne, ale żaden commit nie jest w
rzeczywistości sprawdzany.

## Safe resolution

1. Aktywuj hooka w klonie: `git config core.hooksPath .githooks` oraz
   `chmod +x .githooks/pre-commit`. Wartość `core.hooksPath` pochodzi z
   `agent-hosts.json` (`hook.hooksPathConfig`), nie z konwencji.
2. Gdy brakuje plików hostów, zbootstrapuj je z huba:
   `./scripts/install-agent-hosts.sh --source <hub> --target <repo>`, albo
   zaadoptuj bieżącą wersję standardu (`scripts/create_adoption_lock.py`).
3. Dla `001`, `002` i `007` zaalokuj ticket przez `./project/new-ticket.sh`,
   przełącz się na branch zawierający `ticket-NNN`, ustaw status `IN_PROGRESS`
   i dołącz materialną zmianę poza katalogiem ticketu, TODO, indeksem i
   registry. Dla `003` nie twórz commita: chroniony kontroler dostawy zapisuje
   terminalny receipt poza checkoutem autora.
4. Potwierdź stan: `python3 scripts/agent_host_check.py --root .`.
   Przy findingu anomalii napraw źródłowy kontrakt/projekcję lub CI, a potem
   uruchom audyt ponownie; nie obchodź go przez `--no-verify`.

## Verification

- `python3 scripts/agent_host_check.py --root .` kończy się kodem 0.
- `git config --get core.hooksPath` zwraca wartość z `agent-hosts.json`.
- Próbny commit na branchu bez ticketu jest odrzucony przez hook.
- `./project/governance-check.sh` nie zgłasza kodów `GOV-AGENT-HOST-*`.

## Do not

- Nie usuwaj hooka ani nie commituj z `--no-verify`, żeby przejść bramę.
- Nie dopisuj reguły do Markdown zamiast naprawy mechanizmu; Markdown nie jest
  substytutem hooka.
- Nie ustawiaj `core.hooksPath` na katalog spoza standardu.
- Nie edytuj plików hostów lokalnie — są zarządzane digestem i drift wykryje
  `GOV-SYNC-001`.

## Related rules

- `AGENTS.md` rule 22 (HOST-AGNOSTIC STANDARD)
- `C-HOST-001`, `C-HOST-002`
- `GOV-SYNC-001` (drift zarządzanych plików hostów)
