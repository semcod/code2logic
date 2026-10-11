#!/usr/bin/env python3
"""Custom Git merge driver for Wellmanifest project/TICKETS.md and TODO.md tables.

Merge unambiguous AUTO:TICKET_INDEX changes against the ancestor. Preserve
deletions and surrounding prose; conflicting or ambiguous input falls back to Git.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

START_MARKER = "<!-- AUTO:TICKET_INDEX:START -->"
END_MARKER = "<!-- AUTO:TICKET_INDEX:END -->"
ROW_PATTERN = re.compile(r"^[ \t]*\|[ \t]*\*\*ticket-([0-9]+)\*\*[ \t]*\|")


def extract_table_rows(content: str) -> tuple[str, list[str], str] | None:
    if content.count(START_MARKER) != 1 or content.count(END_MARKER) != 1:
        return None
    start_idx = content.find(START_MARKER)
    end_idx = content.find(END_MARKER)
    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        return None

    header_part = content[: start_idx + len(START_MARKER)]
    footer_part = content[end_idx:]
    middle = content[start_idx + len(START_MARKER) : end_idx]

    lines = middle.strip("\n").split("\n") if middle.strip("\n") else []
    return header_part, lines, footer_part


def parse_ticket_rows(lines: list[str]) -> tuple[list[str], dict[int, str]]:
    table_headers: list[str] = []
    ticket_rows: dict[int, str] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = ROW_PATTERN.match(stripped)
        if match:
            ticket_id = int(match.group(1))
            ticket_rows[ticket_id] = stripped
        elif stripped.startswith("|") and (
            "Ticket ID" in stripped or ":---" in stripped or ":-" in stripped
        ):
            table_headers.append(stripped)

    return table_headers, ticket_rows


def checked_table(content: str):
    parts = extract_table_rows(content)
    if parts is None:
        return None
    prefix, lines, suffix = parts
    headers, rows = parse_ticket_rows(lines)
    row_lines = [line.strip() for line in lines if ROW_PATTERN.match(line.strip())]
    if len(row_lines) != len(rows):
        return None  # Duplicate identities must not silently overwrite a row.
    if any(line.strip() and line.strip() not in headers and not ROW_PATTERN.match(line.strip())
           for line in lines):
        return None  # The custom driver must not drop unknown target-owned text.
    return prefix, headers, rows, suffix


def three_way(ancestor, current, other):
    if current == other:
        return True, current
    if current == ancestor:
        return True, other
    if other == ancestor:
        return True, current
    return False, None


def merge_ticket_index_content(ancestor_text: str, current_text: str, other_text: str) -> str | None:
    parts = [checked_table(text) for text in (ancestor_text, current_text, other_text)]
    if any(part is None for part in parts):
        return None
    ancestor, current, other = parts
    merged = []
    for position in (0, 1, 3):
        clean, value = three_way(ancestor[position], current[position], other[position])
        if not clean:
            return None
        merged.append(value)
    ancestor_rows, current_rows, other_rows = ancestor[2], current[2], other[2]
    rows = []
    for ticket in sorted(set(ancestor_rows) | set(current_rows) | set(other_rows)):
        clean, value = three_way(ancestor_rows.get(ticket), current_rows.get(ticket), other_rows.get(ticket))
        if not clean:
            return None
        if value is not None:
            rows.append(value)
    prefix, headers, suffix = merged
    return prefix + "\n" + "\n".join(headers + rows) + "\n" + suffix


def run_merge(ancestor_file: Path, current_file: Path, other_file: Path) -> int:
    try:
        current_text = current_file.read_text(encoding="utf-8")
        other_text = other_file.read_text(encoding="utf-8")
        ancestor_text = ancestor_file.read_text(encoding="utf-8") if ancestor_file.is_file() else ""
    except Exception:
        return subprocess.run(
            ["git", "merge-file", str(current_file), str(ancestor_file), str(other_file)]
        ).returncode

    merged_text = merge_ticket_index_content(ancestor_text, current_text, other_text)
    if merged_text is not None:
        current_file.write_text(merged_text, encoding="utf-8")
        return 0

    return subprocess.run(
        ["git", "merge-file", str(current_file), str(ancestor_file), str(other_file)]
    ).returncode


def self_test() -> int:
    ancestor = (
        "# Ticket index\n\n"
        "<!-- AUTO:TICKET_INDEX:START -->\n"
        "| Ticket ID | Spec |\n"
        "| :--- | :--- |\n"
        "| **ticket-100** | [`README.md`](./ticket-100/README.md) |\n"
        "<!-- AUTO:TICKET_INDEX:END -->\n"
    )
    current = (
        "# Ticket index\n\n"
        "<!-- AUTO:TICKET_INDEX:START -->\n"
        "| Ticket ID | Spec |\n"
        "| :--- | :--- |\n"
        "| **ticket-100** | [`README.md`](./ticket-100/README.md) |\n"
        "| **ticket-136** | [`README.md`](./ticket-136/README.md) |\n"
        "<!-- AUTO:TICKET_INDEX:END -->\n"
    )
    other = (
        "# Ticket index\n\n"
        "<!-- AUTO:TICKET_INDEX:START -->\n"
        "| Ticket ID | Spec |\n"
        "| :--- | :--- |\n"
        "| **ticket-100** | [`README.md`](./ticket-100/README.md) |\n"
        "| **ticket-127** | [`README.md`](./ticket-127/README.md) |\n"
        "<!-- AUTO:TICKET_INDEX:END -->\n"
    )
    merged = merge_ticket_index_content(ancestor, current, other)
    assert merged is not None
    assert "| **ticket-100** |" in merged
    assert "| **ticket-127** |" in merged
    assert "| **ticket-136** |" in merged
    pos_100 = merged.find("**ticket-100**")
    pos_127 = merged.find("**ticket-127**")
    pos_136 = merged.find("**ticket-136**")
    assert pos_100 < pos_127 < pos_136, f"Order error: {merged}"
    print("Self-test passed: ticket-100 < ticket-127 < ticket-136 sorted perfectly without conflict.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--self-test" in args:
        return self_test()
    if len(args) < 3:
        print(
            "Usage: ticket_index_merge_driver.py <ancestor-path> <current-path> <other-path>",
            file=sys.stderr,
        )
        return 2
    return run_merge(Path(args[0]), Path(args[1]), Path(args[2]))


if __name__ == "__main__":
    sys.exit(main())
