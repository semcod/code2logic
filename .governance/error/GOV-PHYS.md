# GOV-PHYS

## Situation

`GOV-PHYS-001` and `002` mean a change reaches a file whose values carry
physical meaning, and the gate cannot see that the change was named and
planned for hardware acceptance.

## Meaning

- `001`: a changed path matches a contract in the adopter's
  `.governance/physical-contracts.json`, but the ticket intent has no
  `physicalChanges` entry for that contract.
- `002`: `physical-contracts.json` is unreadable or incomplete. The gate
  fails closed until it is repaired.

## Safe resolution

1. List every physical property the diff changes: pin, active level, pull,
   capability set, scale, range or timing. A pin move and a polarity change
   are two entries.
2. For each, add `contract`, `property`, `signal`, `before`, `after` and
   `acceptance` to `physicalChanges` in the ticket intent.
3. Write acceptance as observations on the device, for example "forward
   switch reads inactive at rest and active while pressed".
4. When the edit keeps physical meaning, add one entry with
   `property: none` and a rationale.

## Verification

```bash
./project/governance-check.sh
```

Expected result: no `GOV-PHYS-*` finding.

## Do not

- Do not count a unit test that asserts the new configuration as acceptance.
- Do not drop a module from a deployable profile without a `capability-set`
  entry.
- Do not remove the path from the contract to silence the gate.

## Related rules

- `P-PHYS-001`, `P-PHYS-002`, `P-PHYS-003` in `POLICY.md`.
- [Physical interface contracts](../docs/information/physical-interface-contracts.md).
