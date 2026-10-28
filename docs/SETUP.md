# Set up stampede

The short version is in the [README](../README.md#install). This page adds the details: what the installer does, updating, the one-time settings, the optional event relay for a remote bot, uninstalling, and setup problems.

## Contents
- [What you need](#what-you-need)
- [Install](#install)
- [Update](#update)
- [Health check](#health-check)
- [Unattended agents](#unattended-agents)
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
- **Safe to re-run:** a link already in place prints `ok`. Run from a Herdr-managed checkout (`<plugins>/github-installations/stampede-<id>/<N>-<M>/checkout`), a link to the same file in another `<N>-<M>/checkout` of that same install is moved to this checkout and prints `relinked`; a clone relinks nothing. Anything else already at that path prints `skip ... left as is` and is never replaced. That keeps your own copy of a skill or helper.
- **Flags:** `--dry-run` prints `would link` lines and changes nothing; `--from-plugin` is what Herdr's plugin build passes (the same links); `--help`. Exit 0 done, 2 usage.
- **Never** installs Herdr or an agent CLI. Start each CLI once by hand to sign in.

**Install as a Herdr plugin:** the same installer, plus the event hook, from a checkout Herdr manages.

```bash
herdr plugin install vib-z/stampede  # --ref <tag> pins a release; --yes accepts the build non-interactively
export PATH="$HOME/.local/bin:$PATH"
herdr-doctor
herdr-trust ~/code/my-app
```

Herdr does not show the installer's output, and `herdr plugin log list` stays empty, so `herdr-doctor` is how you see it worked. Skills are linked only for agent home folders that already exist. Do not install over a locally linked plugin; unlink it first.

**The event hook on a clone:** from the checkout, `herdr plugin link .` adds the event hook only; a clone needs it only for the event relay to a remote bot. Herdr then runs `scripts/herdr-plugin-event` on every agent status change. Check it with `herdr plugin list`. With no route configured, events are logged locally without sending.

## Update

From a clone on `main`: `stampede update` (`git fetch`, `git merge --ff-only`, then `./install.sh`; it refuses local changes, untracked files, another branch, or an ignored file the update would overwrite, and then changes nothing). Existing skill and command links keep pointing at the same checkout. A locally linked plugin updates the same way, with `stampede update` in its checkout; `herdr plugin update` cannot update it. The daily check that says when a release is out, and how to turn it off: [README, Updating](../README.md#updating).

For a GitHub-managed install: `herdr plugin update stampede` (`--yes` for non-interactive use, over SSH or from a bot). In that install `stampede update` changes nothing and names this command. Herdr keeps the requested ref, so a pinned tag stays pinned; `herdr plugin install vib-z/stampede --yes` drops the pin. Each install or update gets a new checkout folder, and Herdr deletes the old one the next time its server starts ([Herdr CLI reference](https://herdr.dev/docs/cli-reference/#plugins)). The installer it runs moves stampede's links into the new folder (`relinked`), so none dangles.

When the links still point at an old checkout (`herdr-doctor` says `not in the plugin checkout`, or `stampede: command not found` after a Herdr restart), rerun the current checkout's installer:

```bash
M=$(herdr plugin list --json | jq -r '.result.plugins[]|select(.plugin_id=="stampede").source.managed_path')
bash "$M/install.sh"
```

## Health check

Run `herdr-doctor` after installation with the Herdr server already running. It checks `herdr`, `jq`, `git` and `python3`, client/server versions, `stampede --version` against the checkout's `VERSION`, all three skill links for each agent home that exists, owner tags, worktrees and disk. For a GitHub-managed plugin it also checks that `stampede` and the skill links resolve into the checkout `herdr plugin list --json` reports. A missing event plugin, and a missing `FLEET_TRUST_ROOT` folder (`warn no ~/code (FLEET_TRUST_ROOT): create it or set the key before herdr-trust`), are warnings for a core install.

The relay is optional for a lead inside Herdr. Its checks run when a routes directory, either relay launchd plist, a Claude relay hook or a Codex relay notify line exists, or whenever you pass `--relay`. The routes key `HERDR_EVENTS_ROUTES_DIR` is respected. Helper scripts or an enabled plugin alone do not mark the relay installed.

With no relay configuration, one line says `ok event relay not installed (optional): herdr-doctor --relay checks it`. Remote bots always run `herdr-doctor --relay`, even before relay setup, so missing hooks, helpers, timers, plugin or routes remain a `PROBLEM`.

Flags: `--relay` forces relay checks; `-h` / `--help` prints usage. Exit 0 means no `PROBLEM`, 1 means at least one `PROBLEM`, 2 means a usage error. Warnings do not change the exit code. The doctor reads state only and never fixes settings or prints route contents.

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

This is optional for local use and required for a bot that receives job events. A bot outside Herdr (Grok Bot, or any bot with a webhook) hears when an agent is done or stuck through the relay, so it never polls. Set it up in this order:
1. The Herdr plugin (above).
2. A route file per bot, and the tag on each workspace: [remote/events.md](../remote/events.md).
3. The Claude Code and Codex hooks that send turn ends: [remote/events.md, Hooks](../remote/events.md#hooks).
4. The watchdog and the queue flusher, every few minutes: [remote/watchdogs.md](../remote/watchdogs.md).
5. `herdr-doctor --relay`: no `PROBLEM` lines; read and report warnings.

## Uninstall

From a stable checkout, remove only the links that point into it, then unlink the plugin if you linked it. Each link's target is compared with the checkout's path as plain text (`"$M"` is quoted), so no character in a path acts as a pattern:

```bash
M=$(pwd -P)
find ~/.local/bin ~/.claude/skills ~/.codex/skills -maxdepth 1 -type l 2>/dev/null | while IFS= read -r l; do
  t=$(readlink "$l"); [[ "$t" == "$M"/* ]] && rm -v "$l"
done
herdr plugin unlink stampede
```

For a GitHub-managed install, remove the links that point into Herdr's checkout first, while `herdr plugin list` still names it, then uninstall. Herdr unregisters the plugin but removes neither the links nor, until its server next starts, the checkout, so without the first step stampede keeps working:

```bash
M=$(herdr plugin list --json | jq -r '.result.plugins[]|select(.plugin_id=="stampede").source.managed_path // empty')
[ -n "$M" ] && find ~/.local/bin ~/.claude/skills ~/.codex/skills -maxdepth 1 -type l 2>/dev/null | while IFS= read -r l; do
  t=$(readlink "$l"); [[ "$t" == "$M"/* ]] && rm -v "$l"
done
herdr plugin uninstall stampede
```

Already uninstalled? Then `herdr plugin list` no longer names the checkout. Find the exact one first with `ls -d ~/.config/herdr/plugins/github-installations/stampede-*/*/checkout`, set `M` to that path (`M=<the path>`), and run the same `find` loop. Never match links by a pattern such as `stampede-*`: another plugin or a backup can share it. Herdr deletes the old checkout (about 31 MB) the next time its server starts. Never remove a real folder or another checkout's links.

If you set up the relay, unload its two launchd jobs and remove only its hook/notify entries before removing its helper links. See [watchdogs](../remote/watchdogs.md) and [hooks](../remote/events.md#hooks) for their labels and commands. Uninstalling the plugin alone does not remove timers, hooks or route files.

Job folders (`<repo>/.herdr-<slug>/`), `~/.config/stampede/` and `~/.config/herdr-events/` stay until you remove them yourself. So does the daily update check's one-line cache: `rm -rf ~/.cache/stampede` (or `$XDG_CACHE_HOME/stampede` when that is set).

## Setup problems

| what you see | fix |
|---|---|
| relay `PROBLEM` lines on a local install | a relay signal remains; finish relay setup, or remove only the unused relay configuration you own |
| `stampede --version does not match VERSION` | inspect PATH and existing links; the installer skips links to another checkout, so remove only stale links you own and re-run it |
| `~/.claude/skills/... not linked` or `~/.codex/skills/... not linked` | run the installer after the agent home exists; inspect any skipped path before replacing it. On a Mac without Codex, `herdr-trust` makes `~/.codex` when it writes Codex's trust file, so run the installer once more after it |
| `stampede: command not found` | `~/.local/bin` is not on PATH; add it to your shell profile |
| `skip ... left as is` | something of yours is at that path; remove it if you want stampede's link there, then re-run |
| `refused: there is no ~/code folder to trust repos under`, or `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | the trust root (`FLEET_TRUST_ROOT`, default `~/code`) does not exist; create it or change the key |
| `... not in the plugin checkout ...` from `herdr-doctor` | the links point at an old plugin checkout, which Herdr deletes at its next start: rerun the current one's installer ([Update](#update)) |
| `ASK FAILED ... exit 127` in the lead's inbox | `moshi-hook` is not installed, so no question or gate left the Mac, though `stampede ask` printed `ASKED` or `GATE ... on the phone`: type your answer in the lead's pane, or install Moshi or set `FLEET_ASK_CMD` |
| a dialog at an agent's start | [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md) and [failure-modes.md](../skills/herdr-fleet/references/failure-modes.md) |
