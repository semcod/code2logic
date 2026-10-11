#!/usr/bin/env bash
# Universal ticket index generator for target System X repositories.

set -euo pipefail

index_file="${T2C_TICKET_INDEX_FILE:-project/TICKETS.md}"
case "$index_file" in
  project/*) ;;
  *)
    echo "Ticket index must stay under project/: $index_file" >&2
    exit 2
    ;;
esac

if [[ "$index_file" == *".."* ]]; then
  echo "Ticket index cannot contain parent traversal: $index_file" >&2
  exit 2
fi

mkdir -p project
if [[ ! -f "$index_file" ]]; then
  if [[ -f template/files/project.template.md ]]; then
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    sed "s/{TIMESTAMP}/$timestamp/g" template/files/project.template.md > "$index_file"
  else
    cat > "$index_file" <<'EOF'
# Ticket index (`project/`)

This file indexes governance tickets without taking ownership of
`project/README.md`, which may belong to an analysis generator.

<!-- AUTO:TICKET_INDEX:START -->
<!-- AUTO:TICKET_INDEX:END -->
EOF
  fi
fi

start_count="$(grep -c '^<!-- AUTO:TICKET_INDEX:START -->$' "$index_file" || true)"
end_count="$(grep -c '^<!-- AUTO:TICKET_INDEX:END -->$' "$index_file" || true)"
if [[ "$start_count" -eq 0 && "$end_count" -eq 0 ]]; then
  printf '\n<!-- AUTO:TICKET_INDEX:START -->\n<!-- AUTO:TICKET_INDEX:END -->\n' >> "$index_file"
  start_count=1
  end_count=1
fi
if [[ "$start_count" != 1 || "$end_count" != 1 ]]; then
  echo "$index_file must contain exactly one ticket-index marker pair" >&2
  exit 2
fi

table_file="$(mktemp "${TMPDIR:-/tmp}/new-project-ticket-table.XXXXXX")"
index_dir="$(dirname "$index_file")"
output_file="$(mktemp "$index_dir/.ticket-index.XXXXXX")"
cleanup() {
  rm -f "$table_file" "$output_file"
}
trap cleanup EXIT INT TERM

printf '%s\n' \
  '| Ticket ID | Spec | Preprompt | Human input | Agent plans | Agent logs | Changelog |' \
  '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |' > "$table_file"

for dir in project/ticket-*; do
  [[ -d "$dir" ]] || continue
  # A ticket git does not track yet belongs to work in flight, often somebody
  # else's. Indexing it writes rows whose links resolve in no commit but that
  # author's working tree, so whoever regenerates the index next ships broken
  # links. An untracked ticket appears in the index once it is committed.
  if git rev-parse --git-dir >/dev/null 2>&1 && [[ -z "$(git ls-files -- "$dir")" ]]; then
    printf 'skipping untracked %s; commit it to have it indexed\n' "$dir" >&2
    continue
  fi
  ticket_name="$(basename "$dir")"
  spec='-'
  preprompt='-'
  changelog='-'
  [[ -f "$dir/README.md" ]] && spec="[\`README.md\`](./$ticket_name/README.md)"
  [[ -f "$dir/preprompt.md" ]] && preprompt="[\`preprompt.md\`](./$ticket_name/preprompt.md)"
  [[ -f "$dir/changelog.md" ]] && changelog="[\`changelog.md\`](./$ticket_name/changelog.md)"

  humans=""
  for file in "$dir"/user-*.md; do
    [[ -f "$file" ]] || continue
    name="$(basename "$file")"
    humans+=" [\`$name\`](./$ticket_name/$name)"
  done
  [[ -n "$humans" ]] || humans='-'

  agents=""
  for file in "$dir"/ai-*.md; do
    [[ -f "$file" ]] || continue
    name="$(basename "$file")"
    agents+=" [\`$name\`](./$ticket_name/$name)"
  done
  [[ -n "$agents" ]] || agents='-'

  logs=""
  for file in "$dir"/ai-*-logs.txt; do
    [[ -f "$file" ]] || continue
    name="$(basename "$file")"
    logs+=" [\`$name\`](./$ticket_name/$name)"
  done
  [[ -n "$logs" ]] || logs='-'

  printf '| **%s** | %s | %s | %s | %s | %s | %s |\n' \
    "$ticket_name" "$spec" "$preprompt" "$humans" "$agents" "$logs" "$changelog" >> "$table_file"
done

awk -v table="$table_file" '
  /^<!-- AUTO:TICKET_INDEX:START -->$/ {
    print
    while ((getline line < table) > 0) print line
    close(table)
    inside = 1
    next
  }
  /^<!-- AUTO:TICKET_INDEX:END -->$/ {
    inside = 0
    print
    next
  }
  !inside { print }
' "$index_file" > "$output_file"

chmod 0644 "$output_file"
mv "$output_file" "$index_file"
echo "Updated $index_file ticket index successfully."
