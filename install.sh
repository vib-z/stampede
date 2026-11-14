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
BASE="${XDG_STATE_HOME:-$HOME/.local/state}/stampede/backup-$(date +%Y%m%d-%H%M%S)"
BACKUP=$BASE
JOURNAL=0   # 1 once this --replace run has made its backup folder, rollback.sh and journal
UNITS=""    # the Linux timer unit files this --replace run wrote, which a rollback leaves
stopped() {  # stopped <what failed>: a --replace run stops here; the journal already names every change it made
  echo "install.sh: $1; stopped" >&2
  [ -z "$UNITS" ] || echo "timer unit files written: $UNITS. They are stampede's own and a rollback leaves them" >&2
  if [ "$JOURNAL" = 1 ] && [ -s "$BACKUP/journal" ]; then echo "rollback: bash $(printf %q "$BACKUP/rollback.sh")" >&2; fi
  exit 1
}
open_backup() {  # the backup folder, rollback.sh and an empty journal, before this --replace run's first change
  [ "$JOURNAL" = 0 ] || return 0
  local n=1
  mkdir -p "$(dirname "$BASE")" || stopped "could not make $(dirname "$BASE")"
  until mkdir "$BACKUP" 2>/dev/null; do   # a name already taken gets a suffix
    { [ -e "$BACKUP" ] || [ -L "$BACKUP" ]; } && [ "$n" -lt 50 ] || stopped "could not make a backup folder in $(dirname "$BASE")"
    n=$((n+1)); BACKUP="$BASE-$n"
  done
  cat > "$BACKUP/rollback.sh" <<'ROLLBACK' && : > "$BACKUP/journal" || stopped "could not write $BACKUP/rollback.sh"
#!/bin/bash
# Undo one install.sh --replace from the journal beside it, newest step first. Each step is checked against what is
# there now: a link the run made is removed, an original goes back when its path is free, a folder it made is removed
# when empty, a step that never happened is skipped. What cannot be undone is named, with where its original is.
# Linux timer unit files are stampede's own and stay; it names them. Exit 0 all undone, 1 something left.
B=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P) || exit 1
status=0
n=0
units=""
step() { n=$((n+1)); K[$n]=$1; P[$n]=$2; T[$n]=${3:-}; S[$n]=${4:-}; }   # step <kind> <path> [<target> [<saved>]]
left() { echo "left $1" >&2; status=1; }
there() { [ -e "$1" ] || [ -L "$1" ]; }
unlink_ours() {  # unlink_ours <path> <target>: remove the link the run made there, if it is still there
  [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] || return 0
  if rm "$1"; then echo "unlinked $1"; else left "$1: could not remove the link install.sh made"; return 1; fi
}
. "$B/journal" || { echo "could not read $B/journal; nothing undone" >&2; exit 1; }
i=$n
while [ "$i" -gt 0 ]; do
  p=${P[$i]} t=${T[$i]} s=${S[$i]}
  case ${K[$i]} in
    link) if unlink_ours "$p" "$t" && there "$p"; then left "$p: something else is there now, not the link install.sh made"; fi;;
    move)
      if ! unlink_ours "$p" "$t"; then there "$s" && echo "  its original is $s" >&2
      elif ! there "$s"; then there "$p" || left "$p: its original is not in $s"   # moved, or never moved: as it was
      elif there "$p"; then left "$p: something else is there now; its original is $s"
      elif mv "$s" "$p"; then echo "restored $p"
      else left "$p: could not move it back; its original is still $s"; fi;;
    made)
      if [ -L "$p" ]; then left "$p: a folder install.sh made is a link now"
      elif [ -d "$p" ]; then rmdir "$p" 2>/dev/null || left "$p: a folder install.sh made, not empty now"
      elif there "$p"; then left "$p: a folder install.sh made is something else now"; fi;;
    unit) units="$p${s:+ (its older copy is $s)}${units:+, }$units";;   # newest first here, so in the order written
    *) left "$p: a step this rollback does not know (${K[$i]})";;
  esac
  i=$((i-1))
done
[ -z "$units" ] || echo "kept stampede's own timer unit files, which a rollback leaves: $units"
if [ "$status" = 0 ]; then echo "rolled back: every link and folder that run made is undone"; else echo "rollback incomplete: each left line says what is where" >&2; fi
exit "$status"
ROLLBACK
  JOURNAL=1
}
step() {  # step <kind> <path> [<target> [<saved>]]: the intent, journaled before the change; a failed write stops the run
  local line
  line=$(printf ' %q' "$@")
  printf 'step%s\n' "$line" >> "$BACKUP/journal" || stopped "could not write $BACKUP/journal"
}
made() {  # made <folder>: make it and each missing parent, each journaled first, so the rollback removes it again if empty
  [ -d "$1" ] && return 0
  if [ -e "$1" ] || [ -L "$1" ]; then stopped "could not make the folder $1: something else is there"; fi
  made "$(dirname "$1")"
  step made "$1"
  mkdir "$1" || stopped "could not make $1"
}
link() {  # link <target> <path>
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then echo "ok $2"
  elif [ "$REPLACE" = 0 ] && [ -L "$2" ] && ours "$(readlink "$2")" "$1"; then
    if [ "$DRY" = 1 ]; then echo "would relink $2 -> $1"; else ln -sfn "$1" "$2" && echo "relinked $2 -> $1"; fi
  elif { [ -e "$2" ] || [ -L "$2" ]; } && [ "$REPLACE" = 0 ]; then echo "skip $2: something else is there; left as is (--replace backs it up and links)"
  elif [ -e "$2" ] || [ -L "$2" ]; then
    if [ "$DRY" = 1 ]; then echo "would replace $2 (backup in $BACKUP)"; return 0; fi
    open_backup
    local saved="$BACKUP/${2#"$HOME"/}"
    mkdir -p "$(dirname "$saved")" || stopped "could not make $(dirname "$saved")"
    step move "$2" "$1" "$saved"
    mv "$2" "$saved" || stopped "could not move $2 to $saved"
    ln -s "$1" "$2" || stopped "could not link $2"
    echo "replaced $2 -> $1 (the old one is in $saved)"
  elif [ "$DRY" = 1 ]; then echo "would link $2 -> $1"
  elif [ "$REPLACE" = 1 ]; then
    open_backup
    made "$(dirname "$2")"
    step link "$2" "$1"
    ln -s "$1" "$2" || stopped "could not link $2"
    echo "linked $2 -> $1"
  else mkdir -p "$(dirname "$2")" && ln -s "$1" "$2" && echo "linked $2 -> $1"; fi
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
  if [ "$REPLACE" = 1 ]; then replace_unit "$@"; return; fi
  if [ "$DRY" = 1 ]; then echo "would write $1"; return 0; fi
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "$2" > "$1"
}
. "$ROOT/skills/grokbot-herdr/scripts/herdr-platform"   # event_loop_running
replace_unit() {  # write_unit under --replace: an older marked unit is saved to the backup first; the same one is kept
  local saved=""
  if [ -e "$1" ] && printf '%s\n' "$2" | cmp -s - "$1"; then echo "ok $1"; return 0; fi
  if [ "$DRY" = 1 ]; then
    if [ -e "$1" ]; then echo "would replace $1 (backup in $BACKUP)"; else echo "would write $1"; fi
    return 0
  fi
  open_backup
  if [ -e "$1" ]; then
    saved="$BACKUP/${1#"$HOME"/}"
    mkdir -p "$(dirname "$saved")" && cp -p "$1" "$saved" || stopped "could not save $1 to $saved"
  fi
  step unit "$1" "" "$saved"
  mkdir -p "$(dirname "$1")" || stopped "could not make $(dirname "$1")"
  printf '%s\n' "$2" > "$1" || stopped "could not write $1"
  UNITS="$UNITS${UNITS:+, }$1${saved:+ (its older copy is $saved)}"
  if [ -n "$saved" ]; then echo "replaced $1 (stampede's own unit; the old one is in $saved)"; fi
}
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
[ -z "$UNITS" ] || echo "timer unit files written: $UNITS. They are stampede's own and a rollback leaves them"
if [ "$JOURNAL" = 1 ] && [ -s "$BACKUP/journal" ]; then echo "rollback: bash $(printf %q "$BACKUP/rollback.sh")"; fi
