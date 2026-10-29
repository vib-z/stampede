#!/bin/bash
# Sample-payload checks for the relay scripts (herdr-send has tests/test_herdr_send.py), in a throwaway HOME with fake herdr and curl:
# no live queue, route, Herdr or network is touched. Run: bash test-relay.sh   (prints PASS or the first FAIL)
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T" PATH="$T/.local/bin:/opt/homebrew/bin:/usr/bin:/bin" CODEX_HOME="$T/.codex"
unset HERDR_PANE_ID HERDR_WORKSPACE_ID HERDR_EVENTS_OWNER HERDR_EVENTS_HOME HERDR_EVENTS_ROUTES_DIR
B="$T/.local/bin"; F="$T/fake"; mkdir -p "$B" "$F" "$T/.config/herdr-events/owners" "$T/.config/herdr-events/routes"
for s in herdr-event-post herdr-event-flush herdr-event-watchdog herdr-event-codex-notify herdr-events-owner; do ln -s "$SRC/$s" "$B/$s"; done
for r in bot-alpha default; do printf 'URL=http://example.invalid/hook\nKEY=test\n' > "$T/.config/herdr-events/routes/$r"; done
echo owner=bot-alpha > "$T/.config/herdr-events/owners/w1"

cat > "$B/curl" <<EOF
#!/bin/bash
[ -f "$F/down" ] && { printf 000; exit 7; }
cat >> "$F/sent.jsonl"; echo >> "$F/sent.jsonl"; printf 200
EOF
cat > "$B/herdr" <<EOF
#!/bin/bash
F="$F"
case "\$1 \$2" in
  "agent list") echo '{"result":{"agents":[]}}';;
  "workspace list") [ -f \$F/ws-fail ] && exit 1; echo '{"result":{"workspaces":[{"workspace_id":"w1"}]}}';;
  "workspace get") [ "\$3" = w1 ];;
  "workspace report-metadata") echo "\$*" >> \$F/calls;;
  "pane read") echo;;
esac
EOF
chmod +x "$B/curl" "$B/herdr"
# herdr-event-flush asks for BSD stat (-f %m, -f %z). On a GNU host, answer with the same numbers.
cat > "$B/stat" <<'EOF'
#!/bin/bash
if [ "${1:-}" = -f ] && ! /usr/bin/stat -f %m / >/dev/null 2>&1; then
  fmt=$2; shift 2
  case "$fmt" in
    %m) exec /usr/bin/stat -c %Y "$@";;
    %z) exec /usr/bin/stat -c %s "$@";;
  esac
fi
exec /usr/bin/stat "$@"
EOF
chmod +x "$B/stat"

fail(){ echo "FAIL: $*"; exit 1; }
sent(){ grep -c . "$F/sent.jsonl" 2>/dev/null || echo 0; }
post(){ herdr-event-post "$1"; }
age(){ awk -F'\t' -v d="$1" 'BEGIN{OFS="\t"} {$2-=d; print}' "$T/.local/state/herdr-events/dedupe.tsv" > "$T/a" && mv "$T/a" "$T/.local/state/herdr-events/dedupe.tsv"; }

# B1: one event per turn end per pane
post '{"source":"claude","state":"Stop","pane":"w1:p1"}'
post '{"source":"herdr","state":"done","pane":"w1:p1"}'
HERDR_PANE_ID=w1:p1 herdr-event-codex-notify '{"type":"agent-turn-complete","last-assistant-message":"x"}'
[ "$(sent)" = 1 ] || fail "B1 turn end sent $(sent) times, want 1"
post '{"source":"herdr","state":"blocked","pane":"w1:p1"}'
[ "$(sent)" = 2 ] || fail "B1 blocked was dropped"
post '{"source":"claude","state":"Notification","notification_type":"idle_prompt","pane":"w1:p1"}'
[ "$(sent)" = 2 ] || fail "B1 idle_prompt after a turn end was sent"
post '{"source":"claude","state":"Notification","notification_type":"permission_prompt","pane":"w1:p1"}'
[ "$(sent)" = 2 ] || fail "B1 permission on a pane that just sent blocked was sent again"
post '{"source":"claude","state":"Notification","notification_type":"permission_prompt","pane":"w1:p10"}'
[ "$(sent)" = 3 ] || fail "B1 permission on another pane was dropped"
post '{"source":"claude","state":"Notification","notification_type":"idle_prompt","pane":"w1:p9"}'
[ "$(sent)" = 4 ] || fail "B1 idle_prompt with no turn end was dropped"
post '{"source":"herdr","state":"done","pane":"w1:p2"}'
[ "$(sent)" = 5 ] || fail "B1 another pane's turn end was dropped"
age 20; post '{"source":"codex","state":"agent-turn-complete","pane":"w1:p1"}'
[ "$(sent)" = 6 ] || fail "B1 next turn after 15 s was dropped"
age 400; post '{"source":"claude","state":"Notification","notification_type":"idle_prompt","pane":"w1:p2"}'
[ "$(sent)" = 7 ] || fail "B1 idle_prompt 5+ min after the turn end was dropped"
post '{"source":"x","state":"done"}'; post '{"source":"y","state":"done"}'
[ "$(sent)" = 9 ] || fail "B1 pane-less events were merged"

# B2: Codex sub-agent and side-conversation turns are skipped
R="$CODEX_HOME/sessions/2026/10/16"; mkdir -p "$R"
echo '{"type":"session_meta","payload":{"id":"main-1","source":"cli"}}' > "$R/rollout-2026-10-16T22-23-11-main-1.jsonl"
echo '{"type":"session_meta","payload":{"id":"sub-1","parent_thread_id":"main-1","source":{"subagent":{"thread_spawn":{"parent_thread_id":"main-1"}}}}}' > "$R/rollout-2026-10-16T22-23-21-sub-1.jsonl"
echo '{"type":"session_meta","payload":{"id":"grd-1","parent_thread_id":"main-1","source":{"subagent":{"other":"guardian"}}}}' > "$R/rollout-2026-10-16T22-23-31-grd-1.jsonl"
n=$(sent)
HERDR_PANE_ID=w1:p3 herdr-event-codex-notify '{"type":"agent-turn-complete","thread-id":"sub-1"}'
HERDR_PANE_ID=w1:p4 herdr-event-codex-notify '{"type":"agent-turn-complete","thread-id":"grd-1"}'
HERDR_PANE_ID=w1:p5 herdr-event-codex-notify '{"type":"agent-turn-complete","thread-id":"title-1","input-messages":["Generate a concise, single-line task title"]}'
[ "$(sent)" = "$n" ] || fail "B2 a sub-agent, guardian or side-conversation turn was sent"
grep -q 'skip: codex sub-agent thread=sub-1' "$T/Library/Logs/herdr-events.log" || fail "B2 sub-agent skip not logged"
HERDR_PANE_ID=w1:p6 herdr-event-codex-notify '{"type":"agent-turn-complete","thread-id":"main-1"}'
[ "$(sent)" = $((n+1)) ] || fail "B2 the agent's own turn was not sent"
grep . "$F/sent.jsonl" | tail -1 | jq -e '.thread_id=="main-1" and .owner=="bot-alpha"' >/dev/null || fail "B2 payload wrong"

# B3 + B11: owner tag validation, sidebar label, stale tag pruning
herdr-events-owner '{"workspace_id":"w1K"}' bot-gamma 2>/dev/null && fail "B3 JSON workspace id accepted"
herdr-events-owner w9 bot-alpha 2>/dev/null && fail "B3 tag for a workspace that does not exist accepted"
herdr-events-owner w1 rev >/dev/null 2>&1 || fail "B3 valid tag refused"
grep -q 'owner=rev' "$T/.config/herdr-events/owners/w1" || fail "B3 tag not written"
grep -q -- '--source bots --token owner=rev' "$F/calls" || fail "B11 sidebar token not reported"
herdr-events-owner w1 --clear >/dev/null; [ -f "$T/.config/herdr-events/owners/w1" ] && fail "B3 clear left the tag"
grep -q -- '--clear-token owner' "$F/calls" || fail "B11 sidebar token not cleared"
O="$T/.config/herdr-events/owners"; G="$T/.local/state/herdr-events/watchdog/gone"; mkdir -p "$G"
echo owner=bot-alpha > "$O/w1"; echo owner=bot-beta > "$O/wOLD"; echo owner=bot-beta > "$O/wNEW"; echo owner=bot-gamma > "$O/{bad json}"
echo $(( $(date +%s) - 90000 )) > "$G/wOLD"
touch "$F/ws-fail"; herdr-event-watchdog; rm "$F/ws-fail"
[ -f "$O/wOLD" ] && [ -f "$O/{bad json}" ] || fail "B3 pruned while herdr workspace list failed"
herdr-event-watchdog
[ -f "$O/w1" ] || fail "B3 removed a live workspace's tag"
[ -f "$O/wOLD" ] && fail "B3 kept a tag gone for a day"
[ -f "$O/{bad json}" ] && fail "B3 kept a malformed tag"
[ -f "$O/wNEW" ] && [ -f "$G/wNEW" ] || fail "B3 removed a tag gone for under a day, or did not mark it"

# B10: after an outage only the newest queued event per pane is sent
: > "$F/sent.jsonl"; touch "$F/down"; Q="$T/.herdr-events/queue"
post '{"source":"herdr","state":"blocked","pane":"w1:p7"}'
post '{"source":"herdr","state":"done","pane":"w1:p7"}'
post '{"source":"watchdog","state":"stale","pane":"w1:p8"}'
post '{"source":"cron","state":"done"}'
[ "$(ls "$Q" | wc -l | tr -d ' ')" = 3 ] || fail "B10 queue should hold 3 during the outage (blocked superseded by done)"
rm "$F/down"; herdr-event-flush
[ "$(sent)" = 3 ] || fail "B10 sent $(sent), want 3 (newest w1:p7, w1:p8, the pane-less one)"
grep -q '"state":"blocked"' "$F/sent.jsonl" && fail "B10 an out-of-date state was sent"
[ "$(ls "$T/.herdr-events/dead" | grep -c superseded)" = 1 ] || fail "B10 superseded event not moved to dead/"
[ -z "$(ls "$Q")" ] || fail "B10 queue not empty"

# B12: an open job drops plain turn ends. Finish, blocked, StopFailure and a pane with no marker still post.
mkdir -p "$T/.config/herdr-events/jobs"
printf '%s\n' '/tmp/job-w1' > "$T/.config/herdr-events/jobs/w1"
rm -f "$F/sent.jsonl"
post '{"source":"claude","state":"Stop","pane":"w1:p20","workspace":"w1"}'
post '{"source":"herdr","state":"idle","pane":"w1:p21","workspace":"w1"}'
post '{"source":"herdr","state":"done","pane":"w1:p21","workspace":"w1"}'
post '{"source":"codex","state":"agent-turn-complete","pane":"w1:p22","workspace":"w1"}'
post '{"source":"claude","state":"Notification","notification_type":"idle_prompt","pane":"w1:p23","workspace":"w1"}'
[ "$(sent)" = 0 ] || fail "B12 a plain turn end in an open job was sent ($(sent))"
post '{"source":"claude","state":"StopFailure","pane":"w1:p20","workspace":"w1"}'
[ "$(sent)" = 1 ] || fail "B12 StopFailure in an open job was dropped"
post '{"source":"herdr","state":"blocked","pane":"w1:p24","workspace":"w1"}'
post '{"source":"claude","state":"Notification","notification_type":"permission_prompt","pane":"w1:p24","workspace":"w1"}'
[ "$(sent)" = 2 ] || fail "B12 blocked from two sources sent $(sent), want 2"
post '{"source":"herdr-watchdog","state":"dead","pane":"w1:p20","workspace":"w1"}'
[ "$(sent)" = 3 ] || fail "B12 a dead watchdog in an open job was dropped"
post '{"source":"stampede","state":"done","summary":"shipped","job":"/tmp/job-w1","workspace":"w1"}'
post '{"source":"stampede","state":"done","summary":"shipped","job":"/tmp/job-w1","workspace":"w1"}'
[ "$(sent)" = 4 ] || fail "B12 finish was dropped or sent twice ($(sent))"
post '{"source":"stampede","state":"done","summary":"the other job","job":"/tmp/job-w2","workspace":"w1"}'
[ "$(sent)" = 5 ] || fail "B12 a second job's finish was dropped"
post '{"source":"stampede","state":"question","ask":"abc123abc123","question":"Go?","workspace":"w1"}'
[ "$(sent)" = 6 ] || fail "B12 a question in an open job was dropped"
post '{"source":"herdr","state":"done","pane":"w2:p1","workspace":"w2"}'
[ "$(sent)" = 7 ] || fail "B12 a done in a workspace with no job was dropped"
herdr-event-codex-notify '{"type":"agent-turn-complete","thread-id":"desktop-1","last-assistant-message":"outside"}'
[ "$(sent)" = 7 ] || fail "B12 a codex turn with no pane was sent"
HERDR_PANE_ID=w1:p25 HERDR_WORKSPACE_ID=w1 herdr-event-codex-notify '{"type":"agent-turn-complete","last-assistant-message":"worker"}'
[ "$(sent)" = 7 ] || fail "B12 a codex turn in an open job was sent"
rm "$T/.config/herdr-events/jobs/w1"
post '{"source":"claude","state":"Stop","pane":"w1:p26","workspace":"w1"}'
[ "$(sent)" = 8 ] || fail "B12 a Stop after the job marker was removed was dropped"

echo PASS
