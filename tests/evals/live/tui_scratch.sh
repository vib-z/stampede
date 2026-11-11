#!/bin/bash
# tui_scratch.sh: the tui-live cases (tui_e2e.py, T01 to T10) on this machine, macOS or Linux, in a scratch HOME.
# It does on a host what linux/inside.sh does in the container: a scratch HOME under /tmp, the owner's one-time setup
# in it (Claude's relay hooks, Codex's notify line, one route for the bot), the stand-in agents as `claude` and `codex`,
# install.sh --no-supervise, the plugin link, a stand-in route on 127.0.0.1, and a Herdr server of its own. Herdr keeps
# its socket under HOME, so that server is never the machine's own: the script checks the socket path before it
# starts or stops anything, and runs everything with a clean environment (no HERDR_*, HC_* or agent variables).
# Nothing is signed in, paired or sent anywhere but 127.0.0.1. The run lands in tests/evals/runs/ (or --out).
#
# usage: tests/evals/live/tui_scratch.sh --label <label> [--cases T01,T02] [--out <dir>] [--keep]
#   --keep   leave the scratch folder and its Herdr server for a look; stop it yourself:
#            env -i HOME=<scratch>/h PATH="$PATH" herdr server stop
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SRC=$(cd "$HERE/../../.." && pwd -P)
LABEL=""; CASES=""; OUT=""; KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL=$2; shift 2;;
    --cases) CASES=$2; shift 2;;
    --out) OUT=$2; shift 2;;
    --keep) KEEP=1; shift;;
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
[ -n "$LABEL" ] || { echo "usage: tui_scratch.sh --label <label> [--cases ...] [--out <dir>] [--keep]" >&2; exit 2; }
for tool in herdr jq git python3 curl; do command -v "$tool" >/dev/null || { echo "$tool is not on PATH" >&2; exit 3; }; done

T=$(mktemp -d /tmp/st.XXXXXX); H=$T/h; BOT=evalbot
mkdir -p "$T/tools" "$H/.claude" "$H/.codex" "$H/code" "$H/.config/stampede" "$H/.config/herdr-events/routes" "$H/.local/bin"
# the tools by link, so the caller's own ~/.local/bin (its stampede, its real agents) never comes along
for tool in herdr jq git python3 curl; do ln -s "$(command -v "$tool")" "$T/tools/$tool"; done
CLEAN="$H/.local/bin:$T/tools:/usr/bin:/bin:/usr/sbin:/sbin"
run() {
  env -i HOME="$H" PATH="$CLEAN" TERM="${TERM:-xterm-256color}" LANG="${LANG:-en_US.UTF-8}" SHELL=/bin/bash \
    STAMPEDE_NO_UPDATE_CHECK=1 FLEET_JOBS_ROOT="$H/code/herdr-jobs" FLEET_TRUST_ROOT="$H/code" HERDR_EVENTS_MACHINE=evalbox \
    GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@example.invalid GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@example.invalid \
    GIT_CONFIG_GLOBAL=/dev/null "$@"
}
# a pane's shell starts as a login shell, which may reorder PATH: put the stand-ins first again in every start file
for rc in .zshenv .zprofile .zshrc .bash_profile .bashrc .profile; do
  printf 'export PATH="%s"\nexport STAMPEDE_NO_UPDATE_CHECK=1 FLEET_JOBS_ROOT="%s" FLEET_TRUST_ROOT="%s" HERDR_EVENTS_MACHINE=evalbox\n' \
    "$CLEAN" "$H/code/herdr-jobs" "$H/code" > "$H/$rc"
done
# herdr's answer is read whole before it is searched: with pipefail, a grep -q that leaves early fails the pipeline
status() { run herdr status 2>/dev/null || true; }
running() { local shown; shown=$(status); [[ $shown == *"status: running"* ]]; }
socket_of() { local shown; shown=$(status); awk '/socket:/{print $2; exit}' <<<"$shown"; }
socket=$(socket_of)
case "$socket" in "$H"/*) ;; *) echo "herdr would use the socket ${socket:-(none shown)}, which is not under $H: nothing was started" >&2; rm -rf "$T"; exit 3;; esac
if running; then echo "a herdr server already answers at $socket: nothing was started" >&2; exit 3; fi

cat > "$H/.config/stampede/config" <<EOF
export STAMPEDE_NO_UPDATE_CHECK=1
export FLEET_JOBS_ROOT=$H/code/herdr-jobs
export FLEET_TRUST_ROOT=$H/code
export HERDR_EVENTS_MACHINE=evalbox
EOF
install -m 755 "$SRC/tests/evals/linux/standin.py" "$H/.local/bin/standin.py"
ln -sfn standin.py "$H/.local/bin/claude"; ln -sfn standin.py "$H/.local/bin/codex"
run python3 - <<'EOF'
import json, os
hook = os.path.expanduser('~/.local/bin/herdr-event-claude-hook')
hooks = {event: [{'hooks': [{'type': 'command', 'command': hook}]}] for event in ('Stop', 'StopFailure', 'Notification')}
json.dump({'hooks': hooks}, open(os.path.expanduser('~/.claude/settings.json'), 'w'), indent=2)
EOF
printf 'notify = ["%s/.local/bin/herdr-event-codex-notify"]\n' "$H" > "$H/.codex/config.toml"
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
printf 'URL=http://127.0.0.1:%s/hook\nKEY=eval-key\n' "$PORT" > "$H/.config/herdr-events/routes/$BOT"; chmod 600 "$H/.config/herdr-events/routes/$BOT"
run git init -q "$H/code/eval-repo" && echo '# eval repo' > "$H/code/eval-repo/README.md" \
  && run git -C "$H/code/eval-repo" add README.md && run git -C "$H/code/eval-repo" commit -q -m start

run python3 "$SRC/tests/evals/linux/route_server.py" --port "$PORT" --log "$H/route-received.jsonl" >"$T/route-server.log" 2>&1 &
ROUTE_PID=$!
run nohup herdr server >"$T/herdr-server.log" 2>&1 &
stop() {
  kill "$ROUTE_PID" 2>/dev/null || true
  if [ "$KEEP" = 1 ]; then echo "kept: $T (stop its server with: env -i HOME=$H PATH=$CLEAN herdr server stop)"; return; fi
  # only this HOME's server, by its own socket; checked again, since a case restarts the server
  case "$(socket_of)" in "$H"/*) run herdr server stop >/dev/null 2>&1 || true;; esac
  rm -rf "$T"
}
trap stop EXIT
for _ in $(seq 60); do running && break; sleep 0.5; done
running || { echo "the scratch herdr server did not start (see $T/herdr-server.log)" >&2; tail -20 "$T/herdr-server.log" >&2; KEEP=1; exit 1; }
run bash "$SRC/install.sh" --no-supervise >"$T/install.log" 2>&1 || { echo "install.sh failed:" >&2; tail -20 "$T/install.log" >&2; exit 1; }
run herdr plugin link "$SRC" >"$T/plugin-link.log" 2>&1 || true
echo "scratch home $H, herdr $(run herdr --version | awk '{print $2}') at $socket, route on 127.0.0.1:$PORT"
run python3 "$SRC/tests/evals/live/tui_e2e.py" --label "$LABEL" --bot "$BOT" --route-log "$H/route-received.jsonl" \
  --repo "$H/code/eval-repo" ${CASES:+--cases "$CASES"} ${OUT:+--out "$OUT"}
