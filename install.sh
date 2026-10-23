#!/bin/bash
# Install stampede from this checkout: link its three skills into Claude Code and Codex, and its commands into
# ~/.local/bin. Safe to re-run. Never replaces what is already there, except its own links into an older Herdr-managed
# checkout (Herdr deletes that one at its next start); never installs Herdr or an agent CLI.
set -euo pipefail
usage() { echo 'usage: install.sh [--dry-run] [--from-plugin]'; }
DRY=0
for option in "$@"; do
  case "$option" in
    --dry-run) DRY=1;; --from-plugin) ;; -h|--help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
link() {  # link <target> <path>
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then echo "ok $2"
  elif [ -L "$2" ] && [[ "$(readlink "$2")" == */herdr/plugins/github-installations/stampede-*/checkout/* ]]; then
    if [ "$DRY" = 1 ]; then echo "would relink $2 -> $1"; else ln -sfn "$1" "$2" && echo "relinked $2 -> $1"; fi
  elif [ -e "$2" ] || [ -L "$2" ]; then echo "skip $2: something else is there; left as is"
  elif [ "$DRY" = 1 ]; then echo "would link $2 -> $1"
  else mkdir -p "$(dirname "$2")" && ln -s "$1" "$2" && echo "linked $2 -> $1"; fi
}
for app in .claude .codex; do
  [ -d "$HOME/$app" ] || { echo "skip ~/$app/skills: no ~/$app"; continue; }
  for skill in herdr-fleet grokbot-herdr share-plan; do link "$ROOT/skills/$skill" "$HOME/$app/skills/$skill"; done
done
for f in "$ROOT/scripts/stampede" "$ROOT"/skills/grokbot-herdr/scripts/*; do
  case "${f##*/}" in test-*) continue;; esac
  link "$f" "$HOME/.local/bin/${f##*/}"
done
link "$ROOT/scripts/stampede" "$HOME/.local/bin/fleet-job"  # the same command under its first name; it also answers --version
echo "Next, once per repo: herdr-trust <repo dir>   (pre-trusts it for Claude and Codex, so agents start without a dialog)"
