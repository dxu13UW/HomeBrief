#!/usr/bin/env bash
# Claude Code Stop hook: speak a one-sentence summary of what was just finished.
#
# Loop guard: the summary comes from `claude -p`, which fires Stop hooks too. Exit at once
# if we're already inside a HomeBrief run; otherwise mark the environment before going on.
[ -n "$HOMEBRIEF_HOOK" ] && exit 0
export HOMEBRIEF_HOOK=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/logs"
# Run in the background so the session isn't held up while it summarizes and speaks.
cat | nohup "$ROOT/.venv/bin/python" "$ROOT/hooks/announce_done.py" >>"$ROOT/logs/hook.err" 2>&1 &
exit 0
