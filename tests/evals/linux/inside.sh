#!/bin/bash
# inside.sh: the in-container half of run.sh, run as the unprivileged user with the checkout under test at ~/stampede.
# It plays the owner's one-time setup (remote/events.md: Claude's relay hooks, Codex's notify line, a route for the
# bot), puts the stand-in agents on PATH as claude and codex, starts the stand-in webhook route, a real herdr server
# and a real hc core in a scratch session, then runs the install cases, the TUI cases and, when run.sh copied it in, the
# Core cases. Everything stays in this home: nothing is paired, signed in or sent anywhere but 127.0.0.1.
# usage: inside.sh <label>      (run.sh passes STAMPEDE_EVAL_COMMIT, STAMPEDE_EVAL_DIRTY and EVAL_EXTRA_JSON; EVAL_ONLY=install|tui|core
#                                runs one runner; the TUI and Core runners then get install.sh and the plugin link done here)
set -uo pipefail
LABEL=${1:-baseline-linux}
ONLY=${EVAL_ONLY:-all}
SRC=$HOME/stampede
cd "$SRC"
export STAMPEDE_NO_UPDATE_CHECK=1 FLEET_JOBS_ROOT=$HOME/code/herdr-jobs FLEET_TRUST_ROOT=$HOME/code HERDR_EVENTS_MACHINE=evalbox
export HC_SESSION=evals XDG_RUNTIME_DIR=$HOME/run   # the scratch core: its socket under this home, never a machine's own
export GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@example.invalid GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@example.invalid
BOT=evalbot; PORT=8765; ROUTE_LOG=$HOME/route-received.jsonl
mkdir -p "$XDG_RUNTIME_DIR" ~/.claude ~/.codex ~/code ~/.config/stampede ~/.config/herdr-events/routes
cat > ~/.config/stampede/config <<EOF
export STAMPEDE_NO_UPDATE_CHECK=1
export FLEET_JOBS_ROOT=$FLEET_JOBS_ROOT
export FLEET_TRUST_ROOT=$FLEET_TRUST_ROOT
export HERDR_EVENTS_MACHINE=$HERDR_EVENTS_MACHINE
EOF
# the stand-in agents, where a pane's shell finds them first
install -m 755 tests/evals/linux/standin.py ~/.local/bin/standin.py
ln -sfn standin.py ~/.local/bin/claude; ln -sfn standin.py ~/.local/bin/codex
# the owner's setup from remote/events.md: Claude's three relay hooks, Codex's notify, one route per bot (mode 600)
python3 - <<'EOF'
import json, os
hook = os.path.expanduser('~/.local/bin/herdr-event-claude-hook')
hooks = {event: [{'hooks': [{'type': 'command', 'command': hook}]}] for event in ('Stop', 'StopFailure', 'Notification')}
json.dump({'hooks': hooks}, open(os.path.expanduser('~/.claude/settings.json'), 'w'), indent=2)
EOF
printf 'notify = ["%s/.local/bin/herdr-event-codex-notify"]\n' "$HOME" > ~/.codex/config.toml
printf 'URL=http://127.0.0.1:%s/hook\nKEY=eval-key\n' "$PORT" > ~/.config/herdr-events/routes/$BOT; chmod 600 ~/.config/herdr-events/routes/$BOT
# a scratch repo under FLEET_TRUST_ROOT with one commit
if [ ! -d ~/code/eval-repo/.git ]; then
  git init -q ~/code/eval-repo && echo '# eval repo' > ~/code/eval-repo/README.md && git -C ~/code/eval-repo add README.md && git -C ~/code/eval-repo commit -q -m 'start'
fi
# the stand-in route, the herdr server, the scratch core
python3 tests/evals/linux/route_server.py --port "$PORT" --log "$ROUTE_LOG" >"$HOME/route-server.log" 2>&1 &
ROUTE_PID=$!
nohup herdr server >"$HOME/herdr-server.log" 2>&1 &
for _ in $(seq 60); do herdr status 2>/dev/null | grep -q 'status: running' && break; sleep 0.5; done
herdr status | grep -E 'status|version' | head -4
hc server start --json >"$HOME/hc-start.log" 2>&1 || true
for _ in $(seq 40); do "$SRC/skills/grokbot-herdr/scripts/herdr-event-core" --alive && break; sleep 0.5; done
"$SRC/skills/grokbot-herdr/scripts/herdr-event-core" --alive && echo "core evals answers" || echo "core evals does not answer (see hc-start.log)"
EXTRA=${EVAL_EXTRA_JSON:-{\}}
rc=0
if [ "$ONLY" = all ] || [ "$ONLY" = install ]; then
  python3 tests/evals/linux/install_checks.py --label "$LABEL-install" --bot "$BOT" --repo ~/code/eval-repo --extra "$EXTRA" || rc=1
else   # the install cases did not run: do what they would have left behind
  bash install.sh >"$HOME/install.log" 2>&1 || echo "install.sh failed (see install.log)"
  herdr plugin link "$SRC" >/dev/null 2>&1 || true
fi
if [ "$ONLY" = all ] || [ "$ONLY" = tui ]; then
  python3 tests/evals/live/tui_e2e.py --label "$LABEL-tui" --bot "$BOT" --route-log "$ROUTE_LOG" --repo ~/code/eval-repo --extra "$EXTRA" || rc=1
fi
if [ "$ONLY" = all ] || [ "$ONLY" = core ]; then
  if [ -f tests/evals/live/core_e2e.py ]; then
    python3 tests/evals/live/core_e2e.py --label "$LABEL-core" || rc=1   # qa-core's runner: its own scratch core and stand-ins
  else
    echo "no tests/evals/live/core_e2e.py in this checkout: the Core cases did not run here"
  fi
fi
herdr server stop >/dev/null 2>&1 || true
hc server stop --json >/dev/null 2>&1 || true
kill "$ROUTE_PID" 2>/dev/null || true
exit $rc
