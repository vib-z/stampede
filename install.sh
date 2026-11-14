#!/bin/bash
# Install stampede from this checkout: link its four skills into Claude Code and Codex, and its commands into
# ~/.local/bin. Safe to re-run. Never replaces what is already there, except its own link into another checkout of this
# same Herdr plugin install (Herdr deletes that one at its next start); never installs Herdr or an agent CLI.
# --replace takes over an older install: whatever else is at a target (a copy, a link elsewhere, a folder) is moved into
# one backup folder for this run, then linked; that folder's rollback.sh puts everything back. Nothing is deleted.
# --no-skills links the commands only.
set -euo pipefail
usage() { echo 'usage: install.sh [--dry-run] [--replace] [--no-skills] [--from-plugin] [--supervise] [--no-supervise]'; }
DRY=0
REPLACE=0
SKILLS=1
NO_SUPERVISE=0
FORCE_SUPERVISE=0
for option in "$@"; do
  case "$option" in
    --dry-run) DRY=1;; --replace) REPLACE=1;; --no-skills) SKILLS=0;; --from-plugin) ;; --no-supervise) NO_SUPERVISE=1;; --supervise) FORCE_SUPERVISE=1;;
    -h|--help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# Herdr keeps a plugin at <plugins>/github-installations/stampede-<id>/<N>-<M>/checkout, a new <N>-<M> per update
INSTALL=""
[[ "$ROOT" =~ ^(.+/plugins/github-installations/stampede-[^/]+)/[0-9]+-[0-9]+/checkout$ ]] && INSTALL=${BASH_REMATCH[1]}
ours() {  # ours <link value> <target>: the same file in another checkout of this install; compared literally, no glob
  local rest
  [ -n "$INSTALL" ] && [[ "$1" == "$INSTALL"/* ]] || return 1
  rest=${1#"$INSTALL"/}
  [[ "$rest" =~ ^[0-9]+-[0-9]+/checkout/ ]] && [ "${rest#"${BASH_REMATCH[0]}"}" = "${2#"$ROOT"/}" ]
}
BACKUP="${XDG_STATE_HOME:-$HOME/.local/state}/stampede/backup-$(date +%Y%m%d-%H%M%S)"
JOURNAL=0   # 1 once this --replace run has made its backup folder, rollback.sh and journal
open_backup() {  # the backup folder, rollback.sh and an empty journal, on this --replace run's first change
  if [ "$JOURNAL" = 0 ]; then
    mkdir -p "$(dirname "$BACKUP")"
    mkdir "$BACKUP" || { echo "install.sh: $BACKUP is already there; run it again in a second" >&2; exit 1; }
    JOURNAL=1
    cat > "$BACKUP/rollback.sh" <<'ROLLBACK'
#!/bin/bash
# Undo one install.sh --replace: remove each link it made, and move back what it moved into this folder.
# A path that changed since is left as it is, and named. Exit 0 all undone, 1 something left.
B=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
status=0
back() {  # back <target> <path> <where the old one was moved, or empty>
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then rm "$2" && echo "unlinked $2"
  elif [ -z "$3" ]; then echo "left $2: not the link install.sh made" >&2; status=1; return 0; fi
  [ -n "$3" ] || return 0
  if [ -e "$2" ] || [ -L "$2" ]; then echo "left $2: something else is there now; its original is $3" >&2; status=1
  elif [ ! -e "$3" ] && [ ! -L "$3" ]; then echo "left $2: $3 is gone" >&2; status=1
  else mv "$3" "$2" && echo "restored $2"; fi
}
. "$B/journal"
exit "$status"
ROLLBACK
    : > "$BACKUP/journal"
  fi
}
journal() {  # journal <target> <path> <where the old one was moved, or empty>: one line rollback.sh reads
  [ "$REPLACE" = 1 ] || return 0
  open_backup
  printf 'back %q %q %q\n' "$1" "$2" "$3" >> "$BACKUP/journal"
}
stopped() {  # stopped <what failed>: a --replace that cannot move or link stops here; the journal holds what it did
  echo "install.sh: $1; stopped" >&2
  if [ "$JOURNAL" = 1 ]; then echo "rollback: bash $BACKUP/rollback.sh" >&2; fi
  exit 1
}
link() {  # link <target> <path>
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then echo "ok $2"
  elif [ "$REPLACE" = 0 ] && [ -L "$2" ] && ours "$(readlink "$2")" "$1"; then
    if [ "$DRY" = 1 ]; then echo "would relink $2 -> $1"; else ln -sfn "$1" "$2" && echo "relinked $2 -> $1"; fi
  elif { [ -e "$2" ] || [ -L "$2" ]; } && [ "$REPLACE" = 0 ]; then echo "skip $2: something else is there; left as is (--replace backs it up and links)"
  elif [ -e "$2" ] || [ -L "$2" ]; then
    local saved="$BACKUP/${2#"$HOME"/}"
    if [ "$DRY" = 1 ]; then echo "would replace $2 (backup in $BACKUP)"; return 0; fi
    open_backup
    mkdir -p "$(dirname "$saved")" && mv "$2" "$saved" || stopped "could not move $2 to $saved"
    journal "$1" "$2" "$saved"   # before the link: a link that fails still has its move undone
    ln -s "$1" "$2" || stopped "could not link $2"
    echo "replaced $2 -> $1 (the old one is in $saved)"
  elif [ "$DRY" = 1 ]; then echo "would link $2 -> $1"
  else mkdir -p "$(dirname "$2")" && ln -s "$1" "$2" && journal "$1" "$2" "" && echo "linked $2 -> $1"; fi
}
for app in .claude .codex; do
  [ "$SKILLS" = 1 ] || { echo "skip ~/$app/skills: --no-skills"; continue; }
  [ -d "$HOME/$app" ] || { echo "skip ~/$app/skills: no ~/$app"; continue; }
  for skill in stampede herdr-fleet grokbot-herdr share-plan; do link "$ROOT/skills/$skill" "$HOME/$app/skills/$skill"; done
done
for f in "$ROOT/scripts/stampede" "$ROOT"/skills/grokbot-herdr/scripts/*; do
  [ -f "$f" ] || continue   # files only: a __pycache__ folder left by the tests is not a command
  case "${f##*/}" in test-*) continue;; esac
  link "$f" "$HOME/.local/bin/${f##*/}"
done
link "$ROOT/scripts/stampede" "$HOME/.local/bin/fleet-job"  # the same command under its first name; it also answers --version

# Linux timers, the launchd pair. macOS still loads its own plists (remote/watchdogs.md).
# Skipped when HOME is not the login home, so a test home never enables a real user manager.
# --supervise forces them; --no-supervise skips them. systemd --user when that bus answers,
# otherwise one flock-guarded loop.
write_unit() {  # write_unit <path> <text>. A file without the stampede marker is left alone.
  if [ -e "$1" ] && ! grep -q 'stampede-unit' "$1" 2>/dev/null; then echo "skip $1: something else is there; left as is"; return 1; fi
  if [ "$DRY" = 1 ]; then echo "would write $1"; return 0; fi
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "$2" > "$1"
}
. "$ROOT/skills/grokbot-herdr/scripts/herdr-platform"   # event_loop_running
linux_timers() {
  [ "$(uname -s)" = Linux ] || return 0
  [ "$NO_SUPERVISE" = 1 ] && return 0
  local login
  login=$(python3 -c 'import os,pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || printf '%s\n' "$HOME")
  if [ "$HOME" != "$login" ] && [ "$FORCE_SUPERVISE" != 1 ]; then echo "skip event timers: HOME is not this user's login home"; return 0; fi
  if systemctl --user show-environment >/dev/null 2>&1; then
    local dir="$HOME/.config/systemd/user" n=0
    write_unit "$dir/herdr-event-watchdog.service" '# stampede-unit
[Unit]
Description=Stampede herdr event watchdog

[Service]
Type=oneshot
ExecStart=%h/.local/bin/herdr-event-watchdog' && n=$((n+1))
    write_unit "$dir/herdr-event-watchdog.timer" '# stampede-unit
[Unit]
Description=Stampede herdr event watchdog every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target' && n=$((n+1))
    write_unit "$dir/herdr-events-flush.service" '# stampede-unit
[Unit]
Description=Stampede herdr event flush

[Service]
Type=oneshot
ExecStart=%h/.local/bin/herdr-event-flush' && n=$((n+1))
    write_unit "$dir/herdr-events-flush.timer" '# stampede-unit
[Unit]
Description=Stampede herdr event flush every 2 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target' && n=$((n+1))
    [ "$n" = 4 ] || return 0
    if [ "$DRY" = 1 ]; then echo "would enable systemd user timers (watchdog every 5 min, flush every 2 min)"; return 0; fi
    # the timers replace a running flock loop; a stale pid file is never signalled
    if event_loop_running; then kill "$(cat "${XDG_STATE_HOME:-$HOME/.local/state}/herdr-events/supervise.pid")" 2>/dev/null || true; fi
    systemctl --user daemon-reload
    systemctl --user enable --now herdr-event-watchdog.timer herdr-events-flush.timer
    echo "ok systemd user timers"
  elif command -v flock >/dev/null 2>&1; then
    local state
    state="${XDG_STATE_HOME:-$HOME/.local/state}/herdr-events"
    if [ "$DRY" = 1 ]; then echo "would start the event loop (flock, nohup): watchdog every 5 min, flush every 2 min"; return 0; fi
    mkdir -p "$state"
    if event_loop_running; then echo "ok event loop"; return 0; fi
    nohup "$HOME/.local/bin/herdr-event-supervise" >>"$state/supervise.log" 2>&1 &
    disown || true
    local i
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do   # until the pid file names the new loop
      event_loop_running && break
      sleep 0.1
    done
    event_loop_running || { echo "event loop did not start; see $state/supervise.log" >&2; exit 1; }
    echo "started the event loop"
  else
    echo "skip event timers: no systemd --user and no flock" >&2
  fi
}
linux_timers
echo "Next, once per repo: herdr-trust <repo dir>   (pre-trusts it for Claude and Codex, so agents start without a dialog)"
if [ "$JOURNAL" = 1 ]; then echo "rollback: bash $BACKUP/rollback.sh"; fi
