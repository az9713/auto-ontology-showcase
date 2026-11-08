#!/bin/sh
# P7 arm f: Claude + raw DDL + certified definitions as prompt text. Same command form as arm d (p7/baseline).
# --setting-sources local keeps ~/.claude/CLAUDE.md (it holds the audit numbers) out of the context.
cd "$(dirname "$0")"
for r in 1 2 3; do
  out="$(pwd -W)/r$r.jsonl"
  claude -p "$(cat PROMPT.md; printf '\nOutput file: %s\n' "$out")" --setting-sources local --model claude-opus-5-5 \
    --allowedTools Bash Write --output-format json > r$r.run.json 2> r$r.err &
done
wait
echo ALL_DONE
