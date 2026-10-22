# Set up stampede

The short version is in the [README](../README.md#install). This page adds the details: what the installer does, updating, the one-time settings, the event relay for a remote bot, uninstalling, and setup problems.

## Contents
- [What you need](#what-you-need)
- [Install](#install)
- [Unattended agents](#unattended-agents)
- [Update](#update)
- [Configure](#configure)
- [The event relay, for a remote bot](#the-event-relay-for-a-remote-bot)
- [Uninstall](#uninstall)
- [Setup problems](#setup-problems)

## What you need

macOS, Herdr 0.9.4 or later, Claude Code (the lead), optionally Codex and Cursor for workers, Python 3.9 or later, git, jq and curl. Tested versions: [README, Install](../README.md#install). Moshi's `moshi-hook` puts the lead's questions on your phone; without it, `stampede ask` reports `ASK FAILED ... exit 127` to the lead's inbox.

## Install

From a checkout:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
cd ~/stampede
./install.sh --dry-run
./install.sh
```

- **Skills:** `skills/herdr-fleet`, `skills/grokbot-herdr` and `skills/share-plan` are linked into `~/.claude/skills/` and `~/.codex/skills/`, each only when `~/.claude` or `~/.codex` exists.
- **Commands:** `scripts/stampede` (also as `fleet-job`, its first name) and every `skills/grokbot-herdr/scripts/herdr-*` helper are linked into `~/.local/bin`. `stampede --version` prints the version. Put it on your PATH, also for non-interactive SSH shells if a bot will call it.
- **Safe to re-run:** a link already in place prints `ok`; anything else already at that path prints `skip ... left as is` and is never replaced. That keeps your own copy of a skill or helper.
- **Flags:** `--dry-run` prints `would link` lines and changes nothing; `--from-plugin` is what Herdr's plugin build passes (the same links); `--help`. Exit 0 done, 2 usage.
- **Never** installs Herdr or an agent CLI. Start each CLI once by hand to sign in.

**The Herdr plugin** is needed only for the event relay to a remote bot. From the checkout: `herdr plugin link .`. Herdr then runs `scripts/herdr-plugin-event` on every agent status change. Check it with `herdr plugin list`.

## Update

From a clone on `main`: `stampede update` (`git pull --ff-only`, then `./install.sh`; it refuses local changes or another branch and changes nothing). By hand, the same: `git pull --ff-only && ./install.sh`. A GitHub plugin install: `herdr plugin update`. The daily check that says when a release is out, and how to turn it off: [README, Updating](../README.md#updating).

## Unattended agents

Agents start and run without a visit to their pane only after two one-time steps, which you run yourself (an agent cannot change its own permissions):
- `herdr-trust <repo dir>` for each repo, before agents start there. It marks the repo's main checkout trusted for Claude (`~/.claude.json`) and Codex (`~/.codex/config.toml`); worktrees are covered. It refuses a repo outside `FLEET_TRUST_ROOT` (default `~/code`).
- The Claude settings for auto mode and the lead's Herdr commands: [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md).

## Configure

Every key is an environment variable with a default. Copy [config.example](../config.example) to `~/.config/stampede/config`, change only what you need, and source it from your shell profile:

```bash
mkdir -p ~/.config/stampede && cp config.example ~/.config/stampede/config
echo '. ~/.config/stampede/config' >> ~/.zshrc
```

The full table: [README, Configure](../README.md#configure). `stampede`, the hooks and the helpers read the variables from their environment, so set them where your Herdr panes' shells pick them up; the plugin event reads the file itself.

## The event relay, for a remote bot

A bot outside Herdr (Grok Bot, or any bot with a webhook) hears when an agent is done or stuck through the relay, so it never polls. Set it up in this order:
1. The Herdr plugin (above).
2. A route file per bot, and the tag on each workspace: [remote/events.md](../remote/events.md).
3. The Claude Code and Codex hooks that send turn ends: [remote/events.md, Hooks](../remote/events.md#hooks).
4. The watchdog and the queue flusher, every few minutes: [remote/watchdogs.md](../remote/watchdogs.md).
5. `herdr-doctor`: every line `ok`.

## Uninstall

From the checkout, remove only the links that point into it, then the plugin if you linked it:

```bash
for d in ~/.local/bin ~/.claude/skills ~/.codex/skills; do [ -d "$d" ] && find "$d" -maxdepth 1 -type l -lname "$(pwd -P)/*" -print -delete; done
herdr plugin unlink stampede
```

Job folders (`<repo>/.herdr-<slug>/`), `~/.config/stampede/` and `~/.config/herdr-events/` stay until you remove them yourself.

## Setup problems

| what you see | fix |
|---|---|
| `stampede: command not found` | `~/.local/bin` is not on PATH; add it to your shell profile |
| `skip ... left as is` | something of yours is at that path; remove it if you want stampede's link there, then re-run |
| `refused: there is no ~/code folder to trust repos under` | the trust root (`FLEET_TRUST_ROOT`, default `~/code`) does not exist; create it or change the key |
| `ASK FAILED ... exit 127` in the lead's inbox | `moshi-hook` is not installed; install Moshi or set `FLEET_ASK_CMD` |
| a dialog at an agent's start | [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md) and [failure-modes.md](../skills/herdr-fleet/references/failure-modes.md) |
