#!/bin/bash
# SessionStart hook: inject branch-aware doc context from sibling cog-docs repo.

input=$(cat)

if command -v jq &>/dev/null; then
  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
else
  cwd=$(printf '%s' "$input" | grep -oP '"cwd"\s*:\s*"\K[^"]+')
fi

[[ -z "$cwd" ]] && exit 0

branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
[[ -z "$branch" || "$branch" == "main" || "$branch" == "master" ]] && exit 0

docsroot="$cwd/../cog-docs/docs"
[[ ! -d "$docsroot" ]] && exit 0

ESC=$(printf '%s' "$branch" | sed 's/[.\\*^$()+?{}[\]|]/\\&/g')
pattern='^\*\*Branch:\*\*[[:space:]]+`?'"$ESC"'(`|[[:space:]]|$)'

matches=()
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  if grep -qEm1 "$pattern" "$f" 2>/dev/null; then
    matches+=("$f")
  fi
done < <(
  find "$docsroot/bugs"     -maxdepth 2 -name 'PHASES.md' 2>/dev/null | sort
  find "$docsroot/features" -maxdepth 2 -name 'PHASES.md' 2>/dev/null | sort
  find "$docsroot/bugs"     -maxdepth 2 -name 'SPEC.md'   2>/dev/null | sort
  find "$docsroot/features" -maxdepth 2 -name 'SPEC.md'   2>/dev/null | sort
)

[[ ${#matches[@]} -eq 0 ]] && exit 0

first="${matches[0]}"
first_dir=$(dirname "$first")

if [[ ${#matches[@]} -gt 1 ]]; then
  unique_dirs=()
  seen=()
  for m in "${matches[@]}"; do
    d=$(dirname "$m")
    already=0
    for s in "${seen[@]}"; do [[ "$s" == "$d" ]] && already=1 && break; done
    if [[ $already -eq 0 ]]; then
      unique_dirs+=("$d")
      seen+=("$d")
    fi
  done
  if [[ ${#unique_dirs[@]} -gt 1 ]]; then
    printf 'load-branch-docs-context: multiple docs match branch '"'"'%s'"'"'; using %s\n' "$branch" "$first_dir" >&2
  fi
fi

rel_dir="${first_dir#$cwd/}/"

entries=()
for e in "$first_dir"/*; do
  name=$(basename "$e")
  [[ -d "$e" ]] && entries+=("$name/") || entries+=("$name")
done
files_line="${entries[*]}"

block="[branch-aware-doc-context] Active branch \`${branch}\` is backed by:
  ${rel_dir}
Files: ${files_line}
→ Before doing any work on this branch, read SPEC.md and PHASES.md in that
  directory to re-familiarize yourself with the in-progress work."

if command -v jq &>/dev/null; then
  jq -n --arg ctx "$block" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}' -c
else
  escaped=$(printf '%s' "$block" \
    | sed 's/\\/\\\\/g' \
    | sed 's/"/\\"/g' \
    | sed ':a;N;$!ba;s/\n/\\n/g' \
    | sed 's/\t/\\t/g' \
    | sed 's/\r/\\r/g')
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$escaped"
fi

exit 0
