# Set up stampede

This page installs stampede, keeps it up to date and removes it. The short version is in the [README](../README.md#install).

## Contents
- [What you need](#what-you-need)
- [Install](#install)
- [Update](#update)
- [Health check](#health-check)
- [Your preferences](#your-preferences): `stampede setup`, and [pstack](#pstack) for coding jobs
- [Unattended agents](#unattended-agents): the one-time settings
- [Configure](#configure)
- [The event relay, for a remote bot](#the-event-relay-for-a-remote-bot)
- [Herdr Core](#herdr-core)
- [Uninstall](#uninstall)
- [Setup problems](#setup-problems)

## What you need

A Mac or a Linux computer with these tools. We tested on macOS 27.2 and Ubuntu 24.04 arm64, 8 to 13 Nov 2026. Linux in detail: [LINUX.md](LINUX.md).

| tool | version tested | needed for |
|---|---|---|
| [Herdr](https://herdr.dev/docs/install/) | 0.9.5 (0.9.4 or later: the plugin and `herdr-doctor` check it) | the panes |
| [Herdr Core](https://herdr.dev/core/) `hc` | 0.1.20 (0.1.13 or later; below 0.1.20 `herdr-doctor` warns); the Core-native path ran on 0.1.21 | a job on Herdr Core, optional |
| [Claude Code](https://code.claude.com/docs/en/setup) | 2.1.306 (2.1.295 or later on Herdr Core, for its status) | the lead, and workers |
| [Codex CLI](https://developers.openai.com/codex/cli) | 0.163.0 (0.165.0 checked for `--no-daemon` on Herdr Core, 0.167.1 and 0.170.0 for a Codex lead's empty prompt) | workers, or the lead with `stampede new --lead codex`; optional |
| [Cursor Agent](https://cursor.com/docs/cli/installation) | 2026.10.19 | workers, optional |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 0.22.5 (flags checked with `--help`) | handed workers of a Herdr Core job, optional |
| [Kimi Code](https://moonshotai.github.io/kimi-code/) | 2.2.0 (flags checked with `--help`) | handed workers of a Herdr Core job, optional |
| [pstack](https://github.com/michael-denyer/pstack-claude) | 0.9.159 as a Claude Code plugin and as a Codex plugin, on macOS, 28 Nov 2026: each install command below ran against an empty config folder, and stampede found the result | the lead's working rules on coding jobs, optional and recommended ([pstack](#pstack)) |
| Python 3, git, jq, curl; on Linux also `flock` (util-linux) and `ps` (procps) | Python 3.9 (3.9 or later; the tests need 3.11), git 2.56, jq 1.7 | the scripts |
| [Moshi](https://getmoshi.app/docs/herdr) `moshi-hook` | 0.4.50 (`ask`, `notify` and `job` flags checked with `--help`; on Linux, unpaired) | questions on your phone, optional (without it, see [Setup problems](#setup-problems)) |
| [Tailscale](https://tailscale.com/kb/1017/install) | 1.104.1 | a bot on another computer, optional |

## Install

You need Herdr, Claude Code (signed in), Python 3 and git. Open a terminal (the app where you type commands) and run these lines one at a time:

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

Then run the [health check](#health-check), set [your preferences](#your-preferences) with `stampede setup`, and do the [one-time settings](#unattended-agents). Read on here when the installer skips something, or to see what it changes.

**What the installer does.** It makes links (pointers to files), so the files stay in this checkout (your copy of the stampede repo).
- It links the four skills into `~/.claude/skills/` and `~/.codex/skills/`, each only when `~/.claude` or `~/.codex` exists. A skill is a set of instructions an agent reads. The four are `skills/stampede` (the front door, the part you talk to), `skills/herdr-fleet`, `skills/grokbot-herdr` and `skills/share-plan`.
- It links `scripts/stampede` (also as `fleet-job`, its first name) and every `skills/grokbot-herdr/scripts/herdr-*` helper into `~/.local/bin`.
- Your PATH (the list of folders your terminal looks in for commands) must hold `~/.local/bin`. If a bot will run stampede over SSH, set it for non-interactive SSH shells too.
- On Linux, when the machine supports it, it sets up the event relay's schedule for its watchdog and flusher: two systemd timers, or one loop. When `--replace` first saves an older timer file of stampede's, it prints `replaced <unit> (stampede's own unit; the old one is in <backup>)`. The rest: [LINUX, the event timers](LINUX.md#the-event-timers). On macOS you load them by hand ([watchdogs](../remote/watchdogs.md)).
- It never installs Herdr or an agent CLI. Start each agent CLI once by hand to sign in.
- Its last two lines are `New jobs run on the Herdr TUI. For Herdr Core by default: stampede config set backend core; for one job: stampede new --core` and `Your preferences, once: stampede setup   (it asks about pstack for coding jobs, the lead, effort, where jobs run and the review step)`. A `--replace` run that recorded changes in its journal prints its rollback line after them.

**Running it again** is safe.
- A link already in place prints `ok`.
- When you run it without `--replace` from a checkout Herdr manages (`<plugins>/github-installations/stampede-<id>/<N>-<M>/checkout`), a link to the same file in another `<N>-<M>/checkout` of that same install moves to this checkout, and prints `relinked`. With `--replace`, it backs that link up and replaces it instead. A clone relinks nothing.
- Anything else at that path prints `skip ... left as is (--replace backs it up and links)`. Your own copy of a skill or helper is never replaced.

**Take over an older install with `--replace`.**
- Each thing in the way moves into one backup folder for the run: a copy of a command, a link into another checkout, or a real skill folder. The folder is `${XDG_STATE_HOME:-~/.local/state}/stampede/backup-<date>-<time>/`, with a `-2` style suffix when that name is taken. Each thing keeps its path under your home there.
- This checkout is linked in its place: `replaced <path> -> <target> (the old one is in <backup>)`.
- Before each change (a move, a new link or a new folder), it writes the change to the folder's `journal`. If it cannot write a change there, it does not make it.
- When the run recorded changes in its journal, its last line is the command that undoes its link and folder changes, ready to paste: `rollback: bash <backup>/rollback.sh`.
- If a move, link, folder or journal write fails, the run stops at once with exit 1. Once it has journaled a change, it also prints the rollback line on stderr (the error output).
- If every link (and, on Linux, every timer unit) is already right, the run makes no backup folder. New links are journaled too, so they can be undone.
- Nothing is ever deleted. Remove a backup folder yourself once you are sure.

**The rollback** undoes the run's links and folders. It reads the journal newest first, and checks each step against what is there now.
- It removes a link the run made (`unlinked`), moves an original back when its path is free (`restored`), and removes a folder the run made when it is empty. It skips a step that never happened.
- On success it ends `rolled back: every link and folder that run made is undone`. It keeps stampede's own timer unit files, and says so.
- Some things it cannot undo: a path that changed since, a folder it made that is now a file or a link, or a link or a move the file system refuses. It names each one in a `left <path>: ...` line, with where the original is. It carries on with the rest, ends `rollback incomplete: each left line says what is where`, and exits 1.

**Installer flags.** Exit 0 means done, 1 a failed link or move, 2 a usage error.

| flag | what it does |
|---|---|
| `--dry-run` | prints `would link` lines and changes nothing; with `--replace`, also `would replace <path> (backup in <folder>)` |
| `--replace` | takes over an older install, as above |
| `--no-skills` | links the commands only, and leaves `~/.claude/skills` and `~/.codex/skills` alone |
| `--from-plugin` | what Herdr's plugin build passes; it makes the same links |
| `--no-supervise` | skips the Linux event timers |
| `--supervise` | starts them even when `HOME` is not the login home |
| `--help` | prints how to use it |

**Install as a Herdr plugin.** A plugin is an add-on that Herdr installs and manages. This runs the same installer, plus the event hook, from a checkout Herdr manages:

```bash
herdr plugin install vib-z/stampede  # shows a preview and asks y/N; add --yes over SSH or from a bot; --ref <tag> pins a release
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede doctor                      # exit 0 on a clean install, with Herdr running
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

Herdr does not show the installer's output, and `herdr plugin log list` stays empty. So `stampede doctor` is how you see it worked. Do not install over a locally linked plugin: unlink it first.

**The event hook on a clone.** A hook is a script a program runs when something happens. In your checkout, `herdr plugin link .` adds the event hook only. Herdr then runs `scripts/herdr-plugin-event` each time an agent's status changes.
A clone needs it only for the event relay to a remote bot. Check it with `herdr plugin list`. With no route set up, stampede logs the events on your computer and sends nothing.

Then open your repo in Herdr, start Claude in a pane, and ask: *"With stampede: ..."*. The [walkthrough](GUIDE.md#use-one-job-start-to-finish) shows a whole job.

## Update

stampede never updates anything by itself. You update this way:

| installed with | update with |
|---|---|
| a clone and `./install.sh` | `stampede update` |
| `herdr plugin install vib-z/stampede` | `herdr plugin update stampede` (add `--yes` from a bot, a script or SSH) |

**The daily check.** At most once a day, `stampede --version`, `stampede update --check` and `herdr-doctor` ask GitHub for the latest release.
That is one request without a token, given 3 s in all (DNS, connect and the reply). The answer is kept for 24 h in `${XDG_CACHE_HOME:-~/.cache}/stampede/`. When a newer release is out, they print one line:

```text
$ stampede --version
0.2.5
stampede 0.2.6 is out, this is 0.2.5: run stampede update
```

- In a plugin install the line ends `run herdr plugin update stampede --yes`.
- `stampede --version` puts that line on stderr and still exits 0. `herdr-doctor` prints it as a `warn`.
- Any failure (offline, rate-limited, a malformed reply) prints nothing, and is kept too.
- Turn the check off with `export STAMPEDE_NO_UPDATE_CHECK=1` ([Configure](CONFIGURE.md)). How a release is made: [RELEASING.md](../RELEASING.md).

**`stampede update`** updates only a clean checkout on `main`, and never overwrites a file of yours.
- It runs `git fetch`, moves forward with `git merge --ff-only`, and runs `./install.sh` again, which links any new skill or command. It ends with `stampede 0.2.5 -> 0.2.6`.
- It refuses, says why and changes no file when the checkout has local changes or untracked files, is on another branch, or holds an ignored file at a path the update adds.
- In a Herdr plugin install it changes nothing, and prints `herdr plugin update stampede --yes` to run instead.
- Your links keep pointing at the same checkout.
- A locally linked plugin updates the same way, with `stampede update` in its checkout. `herdr plugin update` cannot update it.

**A plugin install.** Herdr keeps the version you asked for, so a pinned tag stays pinned. `herdr plugin install vib-z/stampede --yes` drops the pin.
Each install or update gets a new checkout folder, and Herdr deletes the old one the next time its server starts ([Herdr CLI reference](https://herdr.dev/docs/cli-reference/#plugins)).
The installer it runs moves each stampede link from the older checkout of that same install into the new one (`relinked`), so no link points at nothing. It leaves any other link alone.

If the links still point at an old checkout, run the current checkout's installer. You see this as `not in the plugin checkout` from `herdr-doctor`, or `stampede: command not found` after a Herdr restart:

```bash
M=$(herdr plugin list --json | jq -r '.result.plugins[]|select(.plugin_id=="stampede").source.managed_path')
bash "$M/install.sh"
```

**From 0.1.0, once.** 0.1.0 has no `stampede update` (`invalid choice: 'update'`). Move the old clone aside, clone again to the same path and run the installer. The links keep their paths, so they work at once:

```bash
mv ~/stampede ~/stampede-0.1.0
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
```

Keep anything of yours from `~/stampede-0.1.0`, then delete it. From then on, use `stampede update`. A plugin install pinned with `--ref v0.1.0` stays pinned until you drop the pin, as above.

## Health check

Run `stampede doctor` after you install, while the Herdr server is running.

`stampede doctor` checks Python, this checkout (its `VERSION`, and that every module imports), and that `stampede`, `fleet-job` and the `herdr-*` helpers on your PATH point into this checkout.
It checks your settings files too. While you have none of your own, one `ok` line says so and names `stampede setup` ([Your preferences](#your-preferences)).
It also says whether [pstack](#pstack) is installed for the agent program that leads your jobs: `ok` when it is found or switched off, a `warn` with the install line when it is missing, never a `PROBLEM`.
Then it passes on the lines of `herdr-doctor`. You can run `herdr-doctor` alone too; `stampede doctor` passes `--core` and `--tui` on to it.

`herdr-doctor` checks each backend that is installed. A backend is where a job runs: the Herdr TUI (Herdr's window, with tabs and panes), and Herdr Core when `hc` is on PATH.
One usable backend is enough, and the last backend line names it. While one is usable, the other's gaps are only `warn` lines.
`--tui` or `--core` checks only that one, and each gap there is a `PROBLEM`; a bot runs that before a job on that backend. It also checks:
- `herdr`, `jq`, `git` and `python3`, and the Herdr client and server versions;
- `stampede --version` against the checkout's `VERSION`;
- all four skill links, for each agent home folder that exists;
- owner tags, worktrees and disk space;
- for a GitHub-managed plugin, that `stampede` and the skill links point into the checkout `herdr plugin list --json` reports.

Without the relay, a missing event plugin is only a warning. So is a missing `FLEET_TRUST_ROOT` folder: `warn no ~/code (FLEET_TRUST_ROOT): create it or set the key before herdr-trust`.

**The relay checks.** The [event relay](#the-event-relay-for-a-remote-bot) is optional for a lead inside Herdr.
- Its checks run when any of these exists: a routes folder, either relay launchd plist, a Claude relay hook or a Codex relay notify line. They also run whenever you pass `--relay`.
- The doctor respects the routes key `HERDR_EVENTS_ROUTES_DIR`. Helper scripts, an enabled plugin or the Linux timers `install.sh` starts do not by themselves mark the relay installed.
- With no relay set up, one line says `ok event relay not installed (optional): herdr-doctor --relay checks it`.
- Remote bots always run `herdr-doctor --relay`, even before relay setup. So missing hooks, helpers, timers, plugin or routes stay a `PROBLEM` for them.

**Exit codes.** 0 means no `PROBLEM`, 1 at least one, 2 a usage error; warnings do not change it. `-h` or `--help` prints how to use it. The doctor only reads: it never fixes settings and never prints what a route holds.

## Your preferences

Run this once, after the install:

```bash
stampede setup
```

It asks seven questions about new jobs. Press Enter to keep the answer in brackets. Here every answer is kept but the last, on a computer with no settings file yet:

```text
stampede setup: your default preferences for new jobs.
Press Enter to keep the answer in [brackets]. Nothing is saved before the end.

1 of 7  Use pstack for coding jobs? It is a set of working rules for a coding agent. yes or no [yes]:
2 of 7  Which agent leads a job? claude or codex [claude]:
3 of 7  The lead's model [<model id>]:
4 of 7  The lead's effort: none, minimal, low, medium, high, xhigh, max or ultra [xhigh]:
5 of 7  Every worker's effort [medium]:
6 of 7  Where do jobs run? tui (the Herdr TUI), core (Herdr Core) or auto (the TUI inside Herdr, else Core) [tui]:
7 of 7  When is the work reviewed? end (one pass at the end), each (every pull request or step) or none [end]: each
New file ~/.config/stampede/config.toml:
  # stampede settings, written by `stampede setup`. Edit this file by hand, or run setup again.
  # Every key with its default: config.example in the stampede checkout. What applies now: stampede config show

  [review]
  step = "each"
SAVED ~/.config/stampede/config.toml
What new jobs use now:
  dev.pstack = true  (default)
  lead.kind = "claude"  (default)
  lead.claude.model = "<model id>"  (default)
  lead.claude.effort = "xhigh"  (default)
  backend = "tui"  (default)
  review.step = "each"  (user)
  every worker's effort = "medium"
pstack is not installed for a Claude lead yet. Install it with: claude plugin marketplace add michael-denyer/pstack-claude && claude plugin install pstack@pstack-claude
```

The command prints your home folder in full where this page shows `~`, and the model's id where it shows `<model id>` (the ids are in [config.example](../config.example)).

**What it does.**
- It saves your answers in your own settings file, `~/.config/stampede/config.toml`, which every job reads ([Configure](CONFIGURE.md)).
- It writes only an answer that differs from what your settings already say. A default you keep stays a default, so it follows later releases.
- In a file you already have, it changes only the values of its own answers. Your comments, on a line of their own or at the end of a line, and every key it does not ask about, stay as they are.
- It never changes a file you already have without showing the change first and getting your yes. At that last question you type `yes`; Enter alone means no.
- It is safe to run again. The brackets show what is set now, and the same answers a second time write nothing.
- An answer it does not take is asked again, with the reason.

**The questions.** Each has a flag, for a run with no typing.

| question | flag | answers | the setting it writes |
|---|---|---|---|
| pstack for coding jobs | `--pstack` | `yes` or `no` | `dev.pstack` |
| which agent leads a job | `--lead` | `claude` or `codex` | `lead.kind` |
| the lead's model | `--lead-model` | a model of that agent program | `lead.claude.model` or `lead.codex.model`, for the agent that leads |
| the lead's effort | `--lead-effort` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` or `ultra` | `lead.claude.effort` or `lead.codex.effort` |
| every worker's effort | `--worker-effort` | the same levels | `roles.<role>.effort`, for every role |
| where jobs run | `--backend` | `tui`, `core` or `auto` | `backend` |
| when the work is reviewed | `--review` | `end`, `each` or `none` | `review.step` |

Your own rules still hold: the lead's model must pass `lead.allow` and `lead.forbid`, and a worker's effort must stay under `workers.max_effort`. Setup refuses an answer they rule out.

**Without questions.** A flag answers its question, and at a terminal the questions with no flag are still asked. `--defaults` asks nothing: a question with no flag keeps its answer. With no terminal (a bot, a script), nothing is asked either.
When nothing is asked, a file you already have changes only with `--yes`. Without it, setup prints the change, writes nothing and exits 2.

```bash
stampede setup --defaults                                      # a new computer: a settings file, with every default
stampede setup --defaults --pstack no --lead-effort max        # prints the change, exit 2, nothing written
stampede setup --defaults --pstack no --lead-effort max --yes  # the same change, saved
```

Run on the settings file that the questions at the top of this section saved (the one with `step = "each"`), the last line prints the change in the form of a diff (`+` marks a new line, `-` one that goes):

```text
--- now
+++ with your answers
@@ -3,3 +3,9 @@

 [review]
 step = "each"
+
+[dev]
+pstack = false
+
+[lead.claude]
+effort = "max"
SAVED ~/.config/stampede/config.toml
What new jobs use now:
  dev.pstack = false  (user)
  lead.kind = "claude"  (default)
  lead.claude.model = "<model id>"  (default)
  lead.claude.effort = "max"  (user)
  backend = "tui"  (default)
  review.step = "each"  (user)
  every worker's effort = "medium"
```

With `--json` it prints one object, whose `status` is `SAVED` or `UNCHANGED` ([CLI-JSON.md](CLI-JSON.md)).
If it cannot change your file safely, it names the key, writes nothing, and you edit the file by hand ([Troubleshoot](TROUBLESHOOT.md#install-update-and-the-health-check)).

### pstack

[pstack](https://github.com/michael-denyer/pstack-claude) is optional, and recommended for coding jobs. With it installed, the lead follows its working rules on coding work ([the guide](GUIDE.md#works-well-with)).
Install it for the agent program that leads your jobs. Each line is one command for a terminal:

```bash
claude plugin marketplace add michael-denyer/pstack-claude && claude plugin install pstack@pstack-claude   # a Claude lead
codex plugin marketplace add michael-denyer/pstack-claude && codex plugin add pstack@pstack-claude         # a Codex lead
```

stampede looks for pstack where each agent program loads it from:

| the lead | pstack counts as installed when |
|---|---|
| Claude | `~/.claude/plugins/installed_plugins.json` lists a plugin named `pstack`, from any marketplace, installed for you or for the job's repo, and `~/.claude/settings.json` does not switch it off; or a skill folder `poteto-mode` sits in `~/.claude/skills` or in the repo's `.claude/skills` |
| Codex | `~/.codex/config.toml` has a `[plugins."pstack@<marketplace>"]` table that does not say `enabled = false`; or a skill folder `poteto-mode` sits in `~/.agents/skills`, `~/.codex/skills` or the repo's `.agents/skills` |

- `poteto-mode` is pstack's entry skill, the one that starts its way of working. Every way of installing pstack brings it.
- So other installs count too: the plugin from pstack's own home (`pstack@cursor-plugins`), and plain skill folders, such as the ones `npx skills add backnotprop/pstack` makes.
- `CLAUDE_CONFIG_DIR` and `CODEX_HOME` move the two home folders, as they do for the agent programs.
- A job on Herdr Core is the exception: a Core terminal gets the core's own environment, never those two variables from your shell. So for a Core job stampede looks in the default folders, `~/.claude` and `~/.codex`, where that lead looks.
- pstack for Claude does not reach a Codex lead, nor the other way round: each is checked by itself.
- A missing pstack never stops a job. `stampede new` prints one line with the install command, and `stampede doctor` shows a `warn`.
- To stop both lines, switch pstack off: `stampede setup --pstack no`.

## Unattended agents

These two one-time steps let agents start and run without you visiting their pane. Run both yourself: an agent cannot change its own permissions.

1. **Trust each repo.** Run `herdr-trust <repo dir>` for each repo (a project folder that uses git), before agents start there.
   - It marks the repo's main checkout trusted for Claude (`~/.claude.json`) and, when `~/.codex` exists, for Codex (`~/.codex/config.toml`).
   - Worktrees (extra working folders of the same repo) are covered.
   - It refuses a repo outside `FLEET_TRUST_ROOT` (default `~/code`).
2. **Set Claude's settings** for auto mode and the lead's Herdr commands. Run the one command in [unattended-setup.md, The settings](../skills/herdr-fleet/references/unattended-setup.md#the-settings-claudesettingsjson-user-scope) yourself, in a terminal.
   - It adds the rules missing from `~/.claude/settings.json`, and makes the file when there is none.
   - It sets `skillOverrides["auto-mode-setup"]` to `off`, and keeps every other setting.
   - Before it changes the file, it saves a backup beside it, never over an older one.
   - When nothing would change, it writes nothing and prints `already set`. It is safe to run again.
   - `claude auto-mode config` shows the result.

   Without it, Claude's auto mode refuses the lead's `herdr agent start`, so the lead cannot start other agents. Claude also stops at the end of a turn to offer its own auto-mode setup.

## Configure

Every setting has a default, so you need to set nothing. `stampede setup` asks the ones most people choose ([Your preferences](#your-preferences)). Every setting, its default and where to change it: [CONFIGURE.md](CONFIGURE.md).

## The event relay, for a remote bot

The event relay sends a job's events from your computer to a bot outside Herdr. The bot then hears when a job finishes or an agent is stuck, without asking.
While a stampede job is open, ordinary turn ends in that workspace stay on your computer; `stampede finish` sends the done event ([remote/events.md](../remote/events.md)). Set it up in this order:
1. The Herdr plugin (above).
2. A route file per bot, and the tag on each workspace: [remote/events.md](../remote/events.md).
3. The Claude Code and Codex hooks that send turn ends: [remote/events.md, Hooks](../remote/events.md#hooks).
4. The watchdog and the queue flusher, every few minutes: [remote/watchdogs.md](../remote/watchdogs.md).
5. `herdr-doctor --relay`: no `PROBLEM` lines; read and report warnings.

## Herdr Core

[Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later) is an optional second place to run a job, without the Herdr TUI ([CORE.md](CORE.md)).
A job runs on it only when you ask: with `stampede new --core`, with `backend = "core"` in your config (`stampede config set backend core` writes it), or with `backend = "auto"` for a job started outside a Herdr pane ([CORE.md](CORE.md#when-a-job-runs-on-herdr-core)). The default is `tui`.

1. Install it with its own installer: `curl -fsSL https://releases.herdr.dev/core/install.sh | sh`. It puts `hc` and `herdr-core` in `~/.local/bin`. On macOS, from Herdr Core 0.1.18, they are links into its own app bundle (`~/.local/share/herdr-core/current`). macOS asks once to let Herdr Core reach your local network, and once for the microphone.
2. Start its core yourself (`hc server start`).
3. Run `herdr-doctor`, or `herdr-doctor --core`.
4. The rest of the setup is the same: `herdr-trust` for each repo, and the [one-time settings](#unattended-agents).

The doctor's checks on Herdr Core:
- `hc` 0.1.13 or later. It warns below 0.1.20, the release this version was checked against: update with `hc update`.
- That the selected core answers on its socket (`HC_SESSION`, `HC_SOCKET`). It asks the socket for `hello`, so the check never starts a core.
- Claude Code 2.1.295 or later, which reports its status (OSC 7501). Codex with `--no-daemon`, if it is installed.
- Cursor is a `warn`, as in [CORE.md's check](CORE.md#check-the-computer-first): a Core job runs it as a program.
- It warns about terminals opened before the core's current bundle was installed (macOS), and a core started from inside an agent or a pane (`hc server restart --fresh` fixes it from Herdr Core 0.1.20 on). Each fix: [Troubleshoot, Install](TROUBLESHOOT.md#install-update-and-the-health-check).
- The doctor never starts, stops or restarts a core.

**Its settings.** `HC`, `HC_SESSION` and `HC_SOCKET` are environment-only: export them with the others ([Configure](CONFIGURE.md#environment-only-with-defaults)).
A Core job does not pass on one left empty (such as config.example's `HC_SOCKET=`), and Herdr Core reads an empty `HC_SOCKET` as unset too.
A bot that starts a Core job and tags it uses the job's key (`hc-<12 hex>`) in place of a workspace id ([remote/events-core.md](../remote/events-core.md)).

## Uninstall

From a stable checkout (one you cloned or linked yourself), remove only the links that point into it, then unlink the plugin if you linked it. Run this in the checkout's folder. Each link's target is compared with the checkout's path as plain text (`"$M"` is quoted), so no character in a path acts as a pattern:

```bash
M=$(pwd -P)
find ~/.local/bin ~/.claude/skills ~/.codex/skills -maxdepth 1 -type l 2>/dev/null | while IFS= read -r l; do
  t=$(readlink "$l"); [[ "$t" == "$M"/* ]] && rm -v "$l"
done
herdr plugin unlink stampede
```

For a GitHub-managed install (one `herdr plugin install` made), remove the links that point into Herdr's checkout first, while `herdr plugin list` still names it. Then uninstall. Herdr unregisters the plugin but removes neither the links nor, until its server next starts, the checkout. Without the first step, stampede keeps working:

```bash
M=$(herdr plugin list --json | jq -r '.result.plugins[]|select(.plugin_id=="stampede").source.managed_path // empty')
[ -n "$M" ] && find ~/.local/bin ~/.claude/skills ~/.codex/skills -maxdepth 1 -type l 2>/dev/null | while IFS= read -r l; do
  t=$(readlink "$l"); [[ "$t" == "$M"/* ]] && rm -v "$l"
done
herdr plugin uninstall stampede
```

Already uninstalled? Then `herdr plugin list` no longer names the checkout.
1. Find the exact one with `ls -d ~/.config/herdr/plugins/github-installations/stampede-*/*/checkout`.
2. Set `M` to that path (`M=<the path>`).
3. Run the same `find` loop.

Never match links by a pattern such as `stampede-*`: another plugin or a backup can share it. Never remove a real folder or another checkout's links. Herdr deletes the old checkout (about 31 MB) the next time its server starts.

If you set up the relay, remove it too.
- Its timers: on macOS, unload its two launchd jobs; on Linux, disable the systemd user timers or stop the flock loop.
- Remove only its hook and notify entries, and do that before you remove its helper links. Their labels and commands: [watchdogs](../remote/watchdogs.md) and [hooks](../remote/events.md#hooks).
- Uninstalling the plugin alone does not remove timers, hooks or route files.

These stay until you remove them yourself: the job folders (`~/code/herdr-jobs/`, or `FLEET_JOBS_ROOT`; older Core jobs in `<repo>/.herdr-<slug>/`), `~/.config/stampede/` and `~/.config/herdr-events/`. So does the daily update check's one-line cache: `rm -rf ~/.cache/stampede` (or `$XDG_CACHE_HOME/stampede` when that is set).

## Setup problems

Every other message, with its fix: [TROUBLESHOOT.md](TROUBLESHOOT.md).

| what you see | fix |
|---|---|
| relay `PROBLEM` lines on a local install | a piece of the relay is still set up: finish the relay setup, or remove only the unused relay configuration you own |
| `stampede --version does not match VERSION` | check your PATH and links. The installer skips links to another checkout: `./install.sh --dry-run --replace` names them, and `./install.sh --replace` backs them up and links this checkout, with a `rollback.sh` |
| `~/.claude/skills/... not linked` or `~/.codex/skills/... not linked` | run the installer after the agent home folder exists. Check any path it skipped; `./install.sh --replace` backs it up and links it |
| `stampede: command not found` | `~/.local/bin` is not on your PATH: add it to your shell profile |
| `skip ... left as is` | something of yours is at that path. Remove it if you want stampede's link there, then run the installer again |
| `refused: there is no ~/code folder to trust repos under`, or `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | the trust root (`FLEET_TRUST_ROOT`, default `~/code`) does not exist: create it or change the key |
| `... not in the plugin checkout ...` from `herdr-doctor` | the links point at an old plugin checkout, which Herdr deletes at its next start: run the current one's installer ([Update](#update)) |
| `stampede ask: the ask command is not installed (moshi-hook is not on PATH), so the owner could never answer: ...` (exit 2) | stampede asks nothing without `moshi-hook`. A Claude lead on the Herdr TUI asks on a question card in its pane instead, and you answer there. For questions on your phone, install Moshi or set `ask.command` (`FLEET_ASK_CMD`) |
| a dialog at an agent's start | [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md) and [failure-modes.md](../skills/herdr-fleet/references/failure-modes.md) |
