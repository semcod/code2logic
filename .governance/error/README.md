# Kanoniczne rozwiązania diagnostyk

Katalog `error/` zawiera runbooki dla stabilnych kodów `GOV-*`, których
rozwiązanie jest wieloetapowe, wymaga klasyfikacji danych albo może prowadzić
do destrukcyjnej operacji. Krótka, maszynowa remediacja zawsze pozostaje w
`governance/diagnostics.json`; pole `documentation` wskazuje ten katalog.

Runbook nie jest wyjątkiem od polityki. W razie konfliktu obowiązuje kolejno
`POLICY.md`, `CONTRIBUTING.md`, finding z bieżącego uruchomienia i dopiero
procedura pomocnicza. Historyczne pliki ticketów wyjaśniają, dlaczego standard
się zmienił, ale nie są instrukcją operacyjną dla kolejnych zdarzeń.

Każdy podlinkowany runbook musi zawierać dokładnie rozpoznawalne sekcje:

- `Situation` — kiedy kod występuje;
- `Meaning` — który invariant został naruszony;
- `Safe resolution` — niedestrukcyjne kroki naprawy;
- `Verification` — deterministyczne sprawdzenie wyniku;
- `Do not` — zabronione skróty i ryzyka;
- `Related rules` — stabilne identyfikatory reguł.

Nazwy plików są stabilne i mogą grupować rodzinę kodów, np.
`GOV-TICKET-ALLOCATION.md`. Linki muszą być względne i pozostawać wewnątrz
`error/`.
