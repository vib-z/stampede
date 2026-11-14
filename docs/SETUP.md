# Set up stampede

The short version is in the [README](../README.md#install). This page has the whole install: what you need, the installer, updating, the one-time settings, the optional event relay for a remote bot, uninstalling, and setup problems.

## Contents
- [What you need](#what-you-need)
- [Install](#install)
- [Update](#update)
- [Health check](#health-check)
- [Unattended agents](#unattended-agents)
- [Configure](#configure)
- [The event relay, for a remote bot](#the-event-relay-for-a-remote-bot)
- [Herdr Core](#herdr-core)
- [Uninstall](#uninstall)
- [Setup problems](#setup-problems)

## What you need

macOS or Linux, Herdr 0.9.4 or later, Claude Code (the lead by default), optionally Codex (workers, or the lead with `stampede new --lead codex`) and Cursor for workers, Python 3.9 or later, git, jq and curl (on Linux also `flock` from util-linux and `ps` from procps). Tested versions: the table below; Linux in detail: [LINUX.md](LINUX.md). Moshi's `moshi-hook` puts the lead's questions on your phone; without it, `stampede ask` reports `ASK FAILED ... exit 127` to the lead's inbox.

**Prerequisites** (tested on macOS 27.2 and Ubuntu 24.04 arm64, 8 to 13 Nov 2026; Linux in detail: [docs/LINUX.md](LINUX.md)):

| tool | version tested | needed for |
|---|---|---|
| [Herdr](https://herdr.dev/docs/install/) | 0.9.5 (0.9.4 or later: the plugin and `herdr-doctor` check it) | the panes |
| [Herdr Core](https://herdr.dev/core/) `hc` | 0.1.20 (0.1.13 or later; below 0.1.20 `herdr-doctor` warns); the Core-native path ran on 0.1.21 | a job on Herdr Core, optional |
| [Claude Code](https://code.claude.com/docs/en/setup) | 2.1.306 (2.1.295 or later on Herdr Core, for its status) | the lead, and workers |
| [Codex CLI](https://developers.openai.com/codex/cli) | 0.163.0 (0.165.0 checked for `--no-daemon` on Herdr Core, 0.167.1 for a Codex lead's empty prompt) | workers, optional |
| [Cursor Agent](https://cursor.com/docs/cli/installation) | 2026.10.19 | workers, optional |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 0.22.5 (flags checked with `--help`) | handed workers of a Herdr Core job, optional |
| [Kimi Code](https://moonshotai.github.io/kimi-code/) | 2.2.0 (flags checked with `--help`) | handed workers of a Herdr Core job, optional |
| Python 3, git, jq, curl; on Linux also `flock` (util-linux) and `ps` (procps) | Python 3.9 (the tests need 3.11), git 2.56, jq 1.7 | the scripts |
| [Moshi](https://getmoshi.app/docs/herdr) `moshi-hook` | 0.4.50 (`ask`, `notify` and `job` flags checked with `--help`; on Linux, unpaired) | questions on your phone, optional |
| [Tailscale](https://tailscale.com/kb/1017/install) | 1.104.1 | a bot on another computer, optional |

## Install

**Step by step**, on a Mac or a Linux machine with Herdr, Claude Code (signed in), Python 3 and git:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
cd ~/stampede
./install.sh --dry-run               # prints each link it would make, changes nothing
./install.sh                         # links the skills and the commands
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede --version                   # the version in VERSION
herdr-trust ~/code/my-app            # once per repo, before agents start there
stampede config set backend core     # optional: Herdr Core by default (the default is the Herdr TUI)
```

- **Skills:** `skills/stampede` (the front door), `skills/herdr-fleet`, `skills/grokbot-herdr` and `skills/share-plan` are linked into `~/.claude/skills/` and `~/.codex/skills/`, each only when `~/.claude` or `~/.codex` exists.
- **Commands:** `scripts/stampede` (also as `fleet-job`, its first name) and every `skills/grokbot-herdr/scripts/herdr-*` helper are linked into `~/.local/bin`. `stampede --version` prints the version. Put it on your PATH, also for non-interactive SSH shells if a bot will call it.
- **Safe to re-run:** a link already in place prints `ok`. Run from a Herdr-managed checkout (`<plugins>/github-installations/stampede-<id>/<N>-<M>/checkout`), a link to the same file in another `<N>-<M>/checkout` of that same install is moved to this checkout and prints `relinked`; a clone relinks nothing. Anything else already at that path prints `skip ... left as is (--replace backs it up and links)` and is never replaced. That keeps your own copy of a skill or helper.
- **Replace:** `--replace` takes over an older install. Each thing in the way (a copy of a command, a link into another checkout, a real skill folder) is moved into one backup folder for the run, `${XDG_STATE_HOME:-~/.local/state}/stampede/backup-<date>-<time>/` (with a `-2` style suffix when that name is taken), at its path under your home, and this checkout is linked in its place (`replaced <path> -> <target> (the old one is in <backup>)`). Before each change, the move, the new link or a folder it makes is written to the folder's `journal`; a change it cannot journal is not made. The last line is the command that undoes the run, ready to paste: `rollback: bash <backup>/rollback.sh`. Rollback goes through the journal newest first and checks each step against what is there now: it removes a link the run made (`unlinked`), moves an original back when its path is free (`restored`), removes a folder the run made when it is empty, skips a step that never happened, and ends `rolled back: every link and folder that run made is undone`. What it cannot undo (a path that changed since, a folder it made that is now a file or a link, a link or a move the file system refuses) it names in a `left <path>: ...` line, with where the original is, carries on with the rest and exits 1. A move, link, folder or journal write that fails stops the run at once with exit 1, and the rollback line on stderr. A run in which every link (and, on Linux, every timer unit) is already right makes no backup folder; a run that makes new links journals them, so they can be undone too. The rollback covers links and folders. On Linux the timer unit files are stampede's own: an install without `--replace` rewrites each one that has the marker; with `--replace` a unit that is already right is left untouched (`ok <unit>`), and an older marked unit that differs is saved in the backup folder first (`replaced <unit> (stampede's own unit; the old one is in <backup>)`), and both the install and the rollback name the unit files a rollback leaves ([LINUX, the event timers](LINUX.md#the-event-timers)). Nothing is ever deleted; remove a backup folder yourself once you are sure.
- **Flags:** `--dry-run` prints `would link` lines and changes nothing (with `--replace`, also `would replace <path> (backup in <folder>)`); `--replace` as above; `--no-skills` links the commands only, and leaves `~/.claude/skills` and `~/.codex/skills` alone; `--from-plugin` is what Herdr's plugin build passes (the same links); `--no-supervise` skips the Linux event timers; `--supervise` starts them even when `HOME` is not the login home; `--help`. Exit 0 done, 1 a failed link or move, 2 usage.
- **Linux timers:** when `systemctl --user` answers, systemd user timers for the watchdog (5 minutes) and the flusher (2 minutes); otherwise one flock-guarded loop. A `HOME` that is not the login home is skipped, so a throwaway home never enables a real user manager. macOS still loads its launchd jobs by hand ([watchdogs](../remote/watchdogs.md)).
- **Last line:** it ends with the line `New jobs run on the Herdr TUI. For Herdr Core by default: stampede config set backend core; for one job: stampede new --core` (a `--replace` run's rollback line comes after it).
- **Never** installs Herdr or an agent CLI. Start each CLI once by hand to sign in.

**Install as a Herdr plugin:** the same installer, plus the event hook, from a checkout Herdr manages.

```bash
herdr plugin install vib-z/stampede  # shows a preview and asks y/N; add --yes over SSH or from a bot; --ref <tag> pins a release
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede doctor                      # exit 0 on a clean install, with Herdr running
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

Herdr does not show the installer's output, and `herdr plugin log list` stays empty, so `stampede doctor` is how you see it worked. Skills are linked only for agent home folders that already exist. Do not install over a locally linked plugin; unlink it first.

**The event hook on a clone:** from the checkout, `herdr plugin link .` adds the event hook only; a clone needs it only for the event relay to a remote bot. Herdr then runs `scripts/herdr-plugin-event` on every agent status change. Check it with `herdr plugin list`. With no route configured, events are logged locally without sending.

Then open your repo in Herdr, start Claude in a pane, and ask: *"With stampede: ..."*. The [walkthrough](GUIDE.md#use-one-job-start-to-finish) shows a whole job.

## Update

Once a day stampede tells you when a newer release is out; it never updates anything by itself. Then you update:

| installed with | update with |
|---|---|
| a clone and `./install.sh` | `stampede update` |
| `herdr plugin install vib-z/stampede` | `herdr plugin update stampede` (add `--yes` from a bot, a script or SSH) |

**The daily check.** At most once a day, `stampede --version`, `stampede update --check` and `herdr-doctor` ask GitHub for the latest release: one request without a token, given 3 s in all (DNS, connect and the reply), the answer cached for 24 h in `${XDG_CACHE_HOME:-~/.cache}/stampede/`. When a newer release is out they print one line:

```text
$ stampede --version
0.2.1
stampede 0.2.2 is out, this is 0.2.1: run stampede update
```

In a plugin install the line ends `run herdr plugin update stampede --yes`. `stampede --version` puts that line on stderr and still exits 0; `herdr-doctor` prints it as a `warn`. Any failure (offline, rate-limited, a malformed reply) prints nothing and is cached too. Turn the check off with `export STAMPEDE_NO_UPDATE_CHECK=1` ([Configure](CONFIGURE.md)). How a release is cut: [RELEASING.md](../RELEASING.md).

**`stampede update`** is the guided updater: it updates only a clean checkout on `main`, and never overwrites a file of yours. It runs `git fetch`, fast-forwards with `git merge --ff-only`, reruns `./install.sh` (which links any new skill or command), and ends with `stampede 0.2.1 -> 0.2.2`. It refuses with the reason, and changes no file, when the checkout has local changes or untracked files, is on another branch, or holds an ignored file at a path the update adds. In a Herdr plugin install it changes nothing and prints `herdr plugin update stampede --yes` to run instead. Existing skill and command links keep pointing at the same checkout. A locally linked plugin updates the same way, with `stampede update` in its checkout; `herdr plugin update` cannot update it.

For a GitHub-managed install: `herdr plugin update stampede` (`--yes` for non-interactive use, over SSH or from a bot). In that install `stampede update` changes nothing and names this command. Herdr keeps the requested ref, so a pinned tag stays pinned; `herdr plugin install vib-z/stampede --yes` drops the pin. Each install or update gets a new checkout folder, and Herdr deletes the old one the next time its server starts ([Herdr CLI reference](https://herdr.dev/docs/cli-reference/#plugins)). The installer it runs moves each stampede link from the older checkout of that same install into the new folder (`relinked`), so none dangles, and leaves any other link alone; `herdr-doctor` reports a `PROBLEM` if `stampede` or a skill still resolves outside the checkout Herdr reports.

When the links still point at an old checkout (`herdr-doctor` says `not in the plugin checkout`, or `stampede: command not found` after a Herdr restart), rerun the current checkout's installer:

```bash
M=$(herdr plugin list --json | jq -r '.result.plugins[]|select(.plugin_id=="stampede").source.managed_path')
bash "$M/install.sh"
```

**From 0.1.0, once.** 0.1.0 has no `stampede update` (`invalid choice: 'update'`). Move the old clone aside, clone again to the same path and rerun the installer; the links keep their paths, so they work at once:

```bash
mv ~/stampede ~/stampede-0.1.0
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
```

Keep anything of yours from `~/stampede-0.1.0`, then delete it. From then on, `stampede update`. A plugin install pinned with `--ref v0.1.0` stays pinned under `herdr plugin update`: `herdr plugin install vib-z/stampede --yes` drops the pin, and its installer moves the links.

## Health check

Run `stampede doctor` after installation with the Herdr server already running. It checks Python, this checkout (its VERSION, and that every module imports) and that `stampede`, `fleet-job` and the `herdr-*` helpers on PATH point into it, then passes on the lines of `herdr-doctor`, which you can also run alone with the flags below (`stampede doctor` passes `--core` and `--tui` on). `herdr-doctor` checks each backend that is installed (the Herdr TUI, and Herdr Core when `hc` is on PATH: one usable backend is enough, and the last backend line names it; `--tui` or `--core` checks one strictly, which is what a bot runs before a job on that backend). It checks `herdr`, `jq`, `git` and `python3`, client/server versions, `stampede --version` against the checkout's `VERSION`, all three skill links for each agent home that exists, owner tags, worktrees and disk. For a GitHub-managed plugin it also checks that `stampede` and the skill links resolve into the checkout `herdr plugin list --json` reports. A missing event plugin, and a missing `FLEET_TRUST_ROOT` folder (`warn no ~/code (FLEET_TRUST_ROOT): create it or set the key before herdr-trust`), are warnings for a core install.

The relay is optional for a lead inside Herdr. Its checks run when a routes directory, either relay launchd plist, a Claude relay hook or a Codex relay notify line exists, or whenever you pass `--relay`. The routes key `HERDR_EVENTS_ROUTES_DIR` is respected. Helper scripts, an enabled plugin, or the Linux timers `install.sh` starts do not by themselves mark the relay installed.

With no relay configuration, one line says `ok event relay not installed (optional): herdr-doctor --relay checks it`. Remote bots always run `herdr-doctor --relay`, even before relay setup, so missing hooks, helpers, timers, plugin or routes remain a `PROBLEM`. On macOS the timers are the two launchd jobs in [watchdogs](../remote/watchdogs.md). On Linux, `install.sh` enables systemd user timers when `systemctl --user` answers, and otherwise starts one flock-guarded loop (`herdr-event-supervise`); `--relay` checks that one. `--no-supervise` leaves them off.

Flags: `--relay` forces relay checks; `--core` checks Herdr Core in place of the Herdr TUI ([Herdr Core](#herdr-core)); `-h` / `--help` prints usage. Exit 0 means no `PROBLEM`, 1 means at least one `PROBLEM`, 2 means a usage error. Warnings do not change the exit code. The doctor reads state only and never fixes settings or prints route contents.

## Unattended agents

Agents start and run without a visit to their pane only after two one-time steps, which you run yourself (an agent cannot change its own permissions):
- `herdr-trust <repo dir>` for each repo, before agents start there. It marks the repo's main checkout trusted for Claude (`~/.claude.json`) and, when `~/.codex` exists, for Codex (`~/.codex/config.toml`); worktrees are covered. It refuses a repo outside `FLEET_TRUST_ROOT` (default `~/code`).
- The Claude settings for auto mode and the lead's Herdr commands: run the one command in [unattended-setup.md, The settings](../skills/herdr-fleet/references/unattended-setup.md#the-settings-claudesettingsjson-user-scope) yourself, in a terminal. It backs up `~/.claude/settings.json`, then adds the rules, and is safe to run again; `claude auto-mode config` shows the result. Without it, Claude's auto mode refuses the lead's `herdr agent start`, so the lead cannot start other agents, and Claude stops at the end of a turn to offer its own auto-mode setup.

## Configure

Every setting has a default; nothing needs setting. The layers, every key with its default, and the environment-only variables (and the shell file the relay scripts read): [CONFIGURE.md](CONFIGURE.md).

## The event relay, for a remote bot

This is optional for local use and required for a bot that receives job events. A bot outside Herdr hears when a job finishes or an agent is stuck through the relay, so it never polls. While a stampede job is open, ordinary turn ends in that workspace stay on the machine; `stampede finish` is the done event ([remote/events.md](../remote/events.md)). Set it up in this order:
1. The Herdr plugin (above).
2. A route file per bot, and the tag on each workspace: [remote/events.md](../remote/events.md).
3. The Claude Code and Codex hooks that send turn ends: [remote/events.md, Hooks](../remote/events.md#hooks).
4. The watchdog and the queue flusher, every few minutes: [remote/watchdogs.md](../remote/watchdogs.md).
5. `herdr-doctor --relay`: no `PROBLEM` lines; read and report warnings.

## Herdr Core

Optional: a job can run on [Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later) in place of the Herdr TUI ([CORE.md](CORE.md)). A job runs on it only when you ask: `stampede new --core`, or `backend = "core"` in your config, which `stampede config set backend core` writes (the default is `tui`). Install it with its own installer (`curl -fsSL https://releases.herdr.dev/core/install.sh | sh`), start its core yourself, then run `herdr-doctor` (both backends when both are installed) or `herdr-doctor --core`. The installer puts `hc` and `herdr-core` in `~/.local/bin`; on macOS, from Herdr Core 0.1.18, they are links into its own app bundle (`~/.local/share/herdr-core/current`), and macOS asks once to let Herdr Core reach your local network and once for the microphone. What the doctor checks:
- `hc` 0.1.13 or later (it warns below 0.1.20, the release this version was checked against: update with `hc update`), and the selected core answering on its socket (`HC_SESSION`, `HC_SOCKET`; asked for `hello` directly, so the check never starts a core).
- Claude Code 2.1.295 or later, which reports its status (OSC 7501); Codex with `--no-daemon`, if installed. Cursor is a `warn`: `cursor-agent reports no OSC 7501 status on Herdr Core: a Core-native job runs it as a program (stampede start <job> <name> -- cursor-agent ...), a --core --relay job hands it to a Herdr TUI pane`.
- Warns, each with what to do: on macOS, terminals opened before the core's current bundle was installed (reopen each once: they keep the old holder, so the local network, the microphone and what an update fixed may not reach them); a core that was started from inside an agent or a pane (run `hc server restart --fresh` yourself from a terminal outside Herdr, Herdr Core 0.1.20 on). The doctor never starts, stops or restarts a core.

The rest of the setup is the same: `herdr-trust` for each repo, and the [unattended settings](../skills/herdr-fleet/references/unattended-setup.md). `HC`, `HC_SESSION` and `HC_SOCKET` are environment-only: export them with the others; stampede passes them, with the rest of your settings, to every terminal of a Core job; a setting left empty (as config.example's `HC_SOCKET=`) is not passed, and Herdr Core reads an empty `HC_SOCKET` as unset too. A bot that starts a Core job and tags it uses the job's key (`hc-<12 hex>`) in place of a workspace id ([remote/events.md](../remote/events-core.md)).

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

If you set up the relay, unload its two launchd jobs on macOS, or on Linux disable the systemd user timers or stop the flock loop, and remove only its hook/notify entries before removing its helper links. See [watchdogs](../remote/watchdogs.md) and [hooks](../remote/events.md#hooks) for their labels and commands. Uninstalling the plugin alone does not remove timers, hooks or route files.

Job folders (`~/code/herdr-jobs/`, or `FLEET_JOBS_ROOT`; older Core jobs in `<repo>/.herdr-<slug>/`), `~/.config/stampede/` and `~/.config/herdr-events/` stay until you remove them yourself. So does the daily update check's one-line cache: `rm -rf ~/.cache/stampede` (or `$XDG_CACHE_HOME/stampede` when that is set).

## Setup problems

| what you see | fix |
|---|---|
| relay `PROBLEM` lines on a local install | a relay signal remains; finish relay setup, or remove only the unused relay configuration you own |
| `stampede --version does not match VERSION` | inspect PATH and existing links; the installer skips links to another checkout: `./install.sh --dry-run --replace` names them, and `./install.sh --replace` backs them up and links this checkout, with a `rollback.sh` |
| `~/.claude/skills/... not linked` or `~/.codex/skills/... not linked` | run the installer after the agent home exists; inspect any skipped path, then `./install.sh --replace` backs it up and links it |
| `stampede: command not found` | `~/.local/bin` is not on PATH; add it to your shell profile |
| `skip ... left as is` | something of yours is at that path; remove it if you want stampede's link there, then re-run |
| `refused: there is no ~/code folder to trust repos under`, or `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | the trust root (`FLEET_TRUST_ROOT`, default `~/code`) does not exist; create it or change the key |
| `... not in the plugin checkout ...` from `herdr-doctor` | the links point at an old plugin checkout, which Herdr deletes at its next start: rerun the current one's installer ([Update](#update)) |
| `ASK FAILED ... exit 127` in the lead's inbox | `moshi-hook` is not installed, so no question or gate left the Mac, though `stampede ask` printed `ASKED` or `GATE ... on the phone`: type your answer in the lead's pane, or install Moshi or set `FLEET_ASK_CMD` |
| a dialog at an agent's start | [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md) and [failure-modes.md](../skills/herdr-fleet/references/failure-modes.md) |
