#!/bin/bash
# Fleet events for a herdr lead, one line per event, for Claude Code's Monitor tool.
# Every line starts with the local time `YYYY-MM-DD HH:MM ` (same form as `date '+%F %R'`):
#   REPORT <file>                 a new report file landed
#   BLOCKED <name>                an agent is at an approval or question dialog
#   GONE <name>                   a named agent left its pane (exited, crashed, replaced)
#   STALL? <name> log idle <N>m   status says working but its session log has not moved
#   HERDR_ERROR <msg>             a herdr agent list call failed (server down, socket, PATH)
# Usage: fleet-watch.sh <reports-dir> [workspace-id] [stall-minutes]
# STALL? and GONE also push to the owner's phone through Moshi (`moshi-hook notify`, best effort),
# because Moshi's own agent hooks already cover completions, questions and approvals but cannot
# see a hung or vanished agent. FLEET_WATCH_NOTIFY=0 turns the push off.
# FLEET_WATCH_PASSES=N stops after N passes and FLEET_WATCH_INTERVAL sets the seconds between
# them (default 30), for testing. Needs herdr and jq; stat -f is the macOS form.
set -u
emit() { printf '%s %s\n' "$(date '+%F %R')" "$*"; }
REPORTS=${1:?usage: fleet-watch.sh <reports-dir> [workspace-id] [stall-minutes]}
WS=${2:-${HERDR_WORKSPACE_ID:-}}
STALL_MIN=${3:-15}
SEEN=$(mktemp "${TMPDIR:-/tmp}/fleet-watch.XXXXXX")   # portable form (macOS and GNU)
LIVE=$(mktemp "${TMPDIR:-/tmp}/fleet-live.XXXXXX")
ERR=$(mktemp "${TMPDIR:-/tmp}/fleet-err.XXXXXX")
trap 'rm -f "$SEEN" "$LIVE" "$LIVE.new" "$ERR"' EXIT
shopt -s nullglob

once() { grep -qxF "$1" "$SEEN" || { echo "$1" >> "$SEEN"; emit "$2"; }; }

# Phone push for what Moshi can't see by itself. Never fails the watch.
phone() {
  [ "${FLEET_WATCH_NOTIFY:-1}" = 1 ] && command -v moshi-hook >/dev/null || return 0
  moshi-hook notify --source herdr-fleet --label "herdr fleet" "$@" >/dev/null 2>&1 || true
}

# Session log for a Claude or Codex session id; prints nothing when not found.
session_log() {
  local f
  for f in ~/.claude/projects/*/"$1".jsonl ~/.codex/sessions/*/*/*/rollout-*"$1".jsonl; do
    echo "$f"; return
  done
}

# Reports already present when the watch starts are not news.
for f in "$REPORTS"/*.md; do echo "rep:$f" >> "$SEEN"; done

while true; do
  for f in "$REPORTS"/*.md; do once "rep:$f" "REPORT $f"; done

  now=$(date +%s)
  # A failed herdr call must not look like "no agents": report it and keep last pass's roster.
  out=$(herdr agent list 2>"$ERR"); rc=$?
  if [ "$rc" != 0 ]; then
    emit "HERDR_ERROR exit $rc $(tr '\n' ' ' < "$ERR" | cut -c1-200)"
    cp "$LIVE" "$LIVE.new"
  elif ! printf '%s' "$out" | jq -r --arg ws "$WS" '.result.agents[]
      | select(.name != null and ($ws == "" or .workspace_id == $ws))
      | "\(.name) \(.agent_status) \(.agent_session.value // "-")"' > "$LIVE.new" 2>/dev/null; then
    emit "HERDR_ERROR unparseable agent list: $(printf '%s' "$out" | tr '\n' ' ' | cut -c1-200)"
    cp "$LIVE" "$LIVE.new"
  fi

  while read -r name status sid; do
    [ "$status" = blocked ] && once "blk:$name:$(( now / 600 ))" "BLOCKED $name"
    [ "$status" = working ] && [ "$sid" != - ] || continue
    log=$(session_log "$sid"); [ -n "$log" ] || continue
    age=$(( now - $(stat -f %m "$log") ))
    [ "$age" -gt $(( STALL_MIN * 60 )) ] || continue
    msg=$(once "stall:$name:$(( now / 1800 ))" "STALL? $name log idle $(( age / 60 ))m")
    [ -n "$msg" ] && { echo "$msg"; phone --title "$name may be stuck" "Working, but its log has not moved for $(( age / 60 ))m (herdr workspace ${WS:-?})."; }
  done < "$LIVE.new"

  # Names present last pass and missing now.
  while read -r name _; do
    grep -q "^$name " "$LIVE.new" && continue
    emit "GONE $name"
    phone --error --title "$name left its pane" "Exited, crashed or self-updated (herdr workspace ${WS:-?})."
  done < "$LIVE"
  mv "$LIVE.new" "$LIVE"

  pass=$(( ${pass:-0} + 1 ))
  [ "$pass" = "${FLEET_WATCH_PASSES:-0}" ] && break
  sleep "${FLEET_WATCH_INTERVAL:-30}"
done
