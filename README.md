<h1 align="center">stampede</h1>

**You text a task to your Grok Bot. It reaches your Mac over Tailscale, where a Claude Code lead does the job in [Herdr](https://herdr.dev) and adds Codex or Cursor panes only when parallel work helps. Nothing is merged, pushed, sent or spent until you say yes.**

Grok Bot is the setup we recommend, but you don't need it: stampede also runs when you start it straight from Claude, Codex or any agent ([Without a bot](#without-a-bot)). Either way you can watch every agent in Herdr, and every question comes back to you.

**Let a Grok Bot set it up.** [Stompy](https://x.ai/bot/_mNMq-0M5aA02AQMNOHTy) is a Grok Bot that sets up stampede between your Grok Bot and your Mac, end to end, and keeps it healthy.

<p align="center">
  <a href="https://github.com/vib-z/stampede/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/vib-z/stampede/actions/workflows/ci.yml/badge.svg"></a>
  <a href="CHANGELOG.md"><img alt="Version 0.2.1" src="https://img.shields.io/badge/version-0.2.1-black"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-black"></a>
  <a href="https://github.com/vib-z/stampede/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/vib-z/stampede?style=flat&color=black&label=stars"></a>
  <a href="https://herdr.dev"><img alt="Herdr 0.9.4 or later" src="https://img.shields.io/badge/Herdr-0.9.4%2B-black"></a>
  <img alt="Python 3.9 or later" src="https://img.shields.io/badge/python-3.9%2B-black">
</p>

<p align="center">
  <img src="assets/demo.gif" alt="Demo: a task texted to Grok Bot reaches a Mac over Tailscale, a Claude Code lead works on it in Herdr with a Codex and a Cursor worker beside it, the bot asks before merging, then reports back." width="640">
</p>

<p align="center"><sub>An animated mock-up of one job, 27 Oct 2026.</sub></p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#updating">Updating</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#use-one-job-start-to-finish">Walkthrough</a> ·
  <a href="#front-doors">Front doors</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#reference">Reference</a> ·
  <a href="#docs">Docs</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">New releases: on <a href="https://github.com/vib-z/stampede">GitHub</a>, <b>Watch</b>, then <b>Custom</b>, then <b>Releases</b>.<br>
  The site: <a href="https://vib-z.github.io/stampede/">vib-z.github.io/stampede</a></p>

---

## How it flows

Started from Grok Bot, the setup we recommend:

```mermaid
flowchart LR
    you(["You, in chat"]) --> bot["Grok Bot"]
    bot -- "SSH over Tailscale" --> mac["Your Mac, always on,<br/>running Herdr"]
    mac --> lead["Claude Code lead"]
    lead -- "only when it's worth it" --> workers["Codex and Claude Code<br/>workers, in Herdr panes"]
    workers -- "reports, by hooks" --> lead
    lead -- "gate question" --> bot
    bot -- "asks you in chat,<br/>records your yes" --> merge(["Draft PR merged"])
    lead -. "or Moshi, if you<br/>started it locally" .-> phone(["Your phone"])
    phone -. "your tap" .-> merge
    mac -. "or answer in Herdr" .-> merge
    lead -. "result, by webhook" .-> bot
```

## Without a bot

stampede works fully on its own with Herdr, Claude Code and this repo: start a job straight from Claude, Codex, Cursor or any agent, or from a Claude pane in Herdr ([Front doors](#front-doors)). Gate questions then reach your phone through Moshi, if you use it, or you answer in Herdr.

Either way:
- **One ask, one lead.** A Claude Code lead plans the job and does it.
- **Workers only when it's worth it.** The lead opens a Codex or Claude Code worker in its own Herdr pane for parallel work, another model or a reviewer, and works alone otherwise.
- **Hooks, not polling.** Workers report to the lead through hooks, and you can watch every pane in Herdr.
- **Your yes on every merge, push, send, spend or close.** The gate question goes back to whoever started the job ([Safety](#safety)), and the lead keeps working while it waits.

## Quick start

**An agent told to run a job with stampede:** start at [USING.md](USING.md), one short page.

On a Mac or a Linux machine with [Herdr](https://herdr.dev/docs/install/) 0.9.4 or later, Claude Code signed in, Python 3.9 or later, git, jq and curl:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
export PATH="$HOME/.local/bin:$PATH"   # add this line to your shell profile too
stampede doctor                        # exit 0, with Herdr running: each check with its fix
```

**Your first ask.** Once per Mac, run the [unattended setup](skills/herdr-fleet/references/unattended-setup.md), so the lead can start workers with no visit to their panes. Run `herdr-trust ~/code/my-app` once for your repo, open it in Herdr, start Claude in a pane, and type:

> With stampede: add a /health endpoint with a test, have a reviewer on another model check it, then open a draft PR.

**Then from your phone (recommended).** Set up Grok Bot's SSH, Tailscale and webhook once ([remote/grokbot/](remote/grokbot/README.md)), and send the same ask in chat.

**On Herdr Core instead of the Herdr TUI.** With [Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later) installed and running, run `herdr-doctor`, then ask *"With stampede: ..."* from anywhere outside a Herdr pane. `stampede new` runs the job on Herdr Core there by itself ([Herdr Core](#herdr-core)).

**Limits.**
- macOS and Linux. On macOS you load the event relay's two launchd jobs yourself; on Linux `install.sh` starts the same timers. What ran live on Linux, and what has not yet: [docs/LINUX.md](docs/LINUX.md).
- The lead is Claude by default, or Codex with `stampede new --lead codex`. Workers can be Claude, Codex or Cursor; on Herdr Core any program runs as a helper.
- Early: commands and files may still change.
- For big jobs. A small job runs as one agent session in a single tagged Herdr pane ([FAQ](#troubleshoot)).

The full install, with every prerequisite: [Install](#install). A whole job, command by command: [the walkthrough](#use-one-job-start-to-finish).

## What is stampede?

stampede is multi-agent orchestration for Claude Code and Codex in Herdr: four skills and one command, installed by script or as a Herdr plugin. You ask once, in plain words: in a Claude pane in Herdr, from Claude or Codex desktop or Cursor, or, as we recommend, from your phone through Grok Bot.

stampede starts **one lead agent** for the job. The lead writes a short plan and starts working at once. It brings in Codex workers, or Claude Code or Cursor ones, each in its own Herdr pane, only when that agent earns its place: work that runs in parallel, a different model, one reviewer, or the same task many times over. Workers report through hooks, so nobody polls. Gate questions come back to wherever you asked, and nothing that matters happens without your own yes.

**Why.** Running many agents by hand means stops between steps, too many small agents, rounds that wait on each other, and a lead that spends its day writing briefs. Real jobs showed all four ([docs/RUNS.md](docs/RUNS.md)). stampede is the lean answer: plan and go, work alone by default, wake on hooks, and ask you only what is yours to decide.

**Who it is for.** Anyone who runs Claude Code, Codex or Cursor and wants a whole job done from one ask, watched in Herdr and answered from a phone.

**What it is.** Four skills and one command:

| part | what it does |
|---|---|
| [`stampede`](skills/stampede/SKILL.md) (skill) | the front door: say "use stampede" in any project chat and it writes the ask, opens a Herdr workspace for the project and starts the lead |
| [`herdr-fleet`](skills/herdr-fleet/SKILL.md) | the playbook the lead follows: plan, panes, hooks, review, gates, report, reopen |
| [`grokbot-herdr`](skills/grokbot-herdr/SKILL.md) | the front door for a bot that reaches your machine over SSH |
| [`share-plan`](skills/share-plan/SKILL.md) | shows you the plan before any agent starts, only when you ask |
| [`stampede`](scripts/stampede) (command) | the command: `new`, `start`, `tell`, `ask`, `cancel`, `approve` |

## Works with

**Agents.** The lead runs on Claude Code, or on Codex when you pick it (`stampede new --lead codex`, on the Herdr TUI or on Herdr Core). Workers run on Claude Code, Codex or Cursor, each started by `stampede start --kind claude|codex|cursor` with its own hooks and auto mode. A [Herdr Core](#herdr-core) job runs any other CLI as a program, and the earlier `--core --relay` path hands Hermes and Kimi workers to Herdr TUI panes.

<table>
  <tr>
    <td align="center" width="150">
      <img src="docs/images/logos/claude.svg" width="44" height="44" alt="Claude Code logo"><br>
      <b>Claude Code</b><br><sub>the lead, and workers</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/logos/codex-dark.svg">
        <img src="docs/images/logos/codex.svg" width="44" height="44" alt="Codex logo">
      </picture><br>
      <b>Codex</b><br><sub>the lead if you pick it, workers and reviewers</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/logos/cursor-dark.svg">
        <img src="docs/images/logos/cursor.svg" width="44" height="44" alt="Cursor logo">
      </picture><br>
      <b>Cursor</b><br><sub>workers</sub>
    </td>
  </tr>
</table>

**Tools.**

<table>
  <tr>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/logos/herdr-dark.svg">
        <img src="docs/images/logos/herdr.svg" width="44" height="44" alt="Herdr logo">
      </picture><br>
      <b>Herdr</b><br><sub>the panes you watch</sub>
    </td>
    <td align="center" width="150">
      <img src="docs/images/logos/moshi.svg" width="44" height="44" alt="Moshi logo"><br>
      <b>Moshi</b><br><sub>questions on your phone</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/logos/grokbot-dark.svg">
        <img src="docs/images/logos/grokbot.svg" width="44" height="44" alt="Grok Bot logo">
      </picture><br>
      <b>Grok Bot</b><br><sub>the preferred bot</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/logos/tailscale-dark.svg">
        <img src="docs/images/logos/tailscale.svg" width="44" height="44" alt="Tailscale logo">
      </picture><br>
      <b>Tailscale</b><br><sub>a bot's private link</sub>
    </td>
  </tr>
</table>

**Herdr Core** (`hc` 0.1.13 or later), Herdr's terminal runtime, can run a whole job in place of the Herdr TUI: [Herdr Core](#herdr-core).

Herdr itself detects many more agent CLIs (its `herdr agent start --help` lists 24, from Gemini and Kimi to OpenCode and Copilot). That is Herdr's support, not stampede's yet: `stampede start` refuses any other kind (a Core job runs any CLI as a plain program), and starting workers on them is [planned](#status-and-roadmap). The marks belong to their owners and imply no endorsement ([sources](docs/images/logos/SOURCES.md)).

## Works well with

**[pstack](https://github.com/michael-denyer/pstack-claude), optional.** For coding jobs, the lead picks up pstack if you have it: data shape first, a contract commit, proof on the real surface. The lead is a normal Claude Code session, so an installed pstack loads on its own, and stampede's rules keep pstack's fan-out as Herdr panes you can watch. Not required: without it nothing changes. The rules: [references/pstack.md](skills/herdr-fleet/references/pstack.md).

## See it

![The build tab of a fleet in Herdr: four panes side by side. build-steps-plan and build-steps-run are Claude Code agents that have just finished; build-scripts and build-app are Codex agents still working.](docs/images/fleet-build-tab.png)

<sub>Real, drawn: the <code>build</code> tab of the fleet that built stampede's first version, drawn from each pane's own screen text (<code>herdr agent read</code>), personal paths replaced with <code>~</code>, 18 Oct 2026. A lean job opens fewer panes; each looks the same.</sub>

## How it works

The flow is the [diagram at the top](#how-it-flows), step by step, for any front door:

1. **You ask once**, in plain words, in a [front door](#front-doors). It writes the ask to a file, runs `stampede new --file <ask.md>`, tells you the lead's name, and steps back.
2. **One lead plans and goes.** `lead-<slug>` starts on Claude (Opus 5.5 at `xhigh` effort by default), or on Codex (GPT-6 Astra at `ultra`) with `--lead codex`, in auto mode, in a `lead` tab. It writes `plan.md` (the tasks, who does each, questions with a safe default, and the gates) and starts work.
3. **A pane only when it's worth it:** parallel pieces of about 30 minutes or more (at most 4), another model or tool, one reviewer on another model, or the same task many times (6 at once). Each worker gets its own Herdr pane.
4. **Hooks, not polling.** A worker's report, turn end, question or exit lands as a line in `<job>/inbox.log` (`REPORT`, `TURN`, `QUESTION`, `GONE`, and `UNDELIVERED` for a question, gate or post its bot has not heard), and Claude's file hook wakes the lead. A Codex lead has no file hook: stampede types each new line into its pane, marked `[fleet-job inbox for <lead>, not typed by the owner]`, once it is idle and unfocused.
5. **Review only what ships**, on another model, at most two rounds.
6. **Questions and gates go back to whoever started the job**: a bot gets a `question` or `gate` event, asks you in chat and passes your answer back (a gate's yes recorded with `approve-gate`); a job you started locally asks on your phone through Moshi. Which yes counts where: [Safety](#safety). The lead keeps working while it waits, and an agent's own say-so never counts.
7. **The lead reports back once.** When the job is done or stopped for good it runs `stampede finish <job> "<summary>"`, the one done event a bot outside Herdr gets for the job. While the job is open, plain turn ends stay on the machine; blocked, permission prompts, StopFailure, a stale or dead pane, questions, gates and the lead's posts (`stampede post`) still go out. Then the lead asks whether to close.
8. **Workers exit when their work is merged** or accepted. Nothing closes without your yes, and `reopen.sh` brings a closed job back.

**Stateful lead, stateless workers.** The lead holds your ask, the plan, the decisions and the judgement. A worker gets one brief and nothing else, so that brief carries the state: Goal, Why, Inputs, Constraints, Done when, Report back and If blocked, on the [hand-off template](skills/herdr-fleet/references/brief.md). A thin brief is the usual cause of weak worker output. `stampede start` refuses a worker brief with a missing or empty section before starting anything. Pick a strong planner for the lead and a fast, capable executor for workers; both are [settings](#configure), not code.

**What lives where.** Your Mac, always on, runs Herdr, the lead and the workers. A bot such as Grok Bot runs on its own computer and reaches the Mac over SSH and Tailscale. Or the whole thing runs on one remote computer. Either way, the lead and its workers share one machine; workers on a second machine are [planned](#status-and-roadmap).

**On Herdr Core** the flow keeps its steps, but Core holds the tree: the lead is a root terminal, each helper its Core child (any depth, at most 12 working at once), and the lead is woken by Core's notes about its children and by messages sent with `hc send`, never by hooks or inbox files. Questions, gates, posts and finish reach the owner as above; a blocked, failed, dead or stalled lead reaches the owner from the machine's watchdog within about 5 minutes ([Herdr Core](#herdr-core)).

<details>
<summary><b>The job folder</b></summary>

`stampede new` makes `~/code/herdr-jobs/jobs/<date>-<bot or local>-<slug>/` on every backend (the setting `jobs_root` moves the root), never inside your repo, so nothing lands in git. A job an older stampede made in `<repo>/.herdr-<slug>` keeps working. The repo stays the agents' working folder, and every agent gets `--add-dir <job>` to write there:

```text
ask.md        your ask, word for word
settings.json the settings stampede new resolved (not the user-only ones), and the layer that set each; every later
              command of the job reads it (stampede config show --job <job>)
workdir       the repo the agents work in
lead          the lead's name
plan.md       the lead's plan
briefs/       the generated lead brief, then worker briefs on the hand-off template
hooks/        each agent's hook settings and wake state; deliver.log for a Codex lead (not on Core)
inbox.log     REPORT, TURN, QUESTION, GONE and UNDELIVERED lines that wake the lead (not on Core)
inbox/        messages to each agent, one file per agent (not on Core)
questions/    a worker's questions, as files for the lead
asks/         questions out to your phone, while they wait; on Core, a phone answer the lead could not take
owner         the bot that started the job, when one did: its gates go back to it
workspace     the Herdr workspace id, or a Herdr Core job's key hc-<12 hex>; while the job is open,
              ~/.config/herdr-events/jobs/<id> names this job
backend       native for a Herdr Core job, core for one on --relay (no file: the Herdr TUI)
endpoint      the Herdr Core a Core job was made on (HC_SESSION, HC_SOCKET);
              every later command uses it
space         a Core job's space name (the lead's stampede.space label)
max-helpers   a Core job's cap, only when the owner set one
closed        a Core job closed whole by stampede close; stampede reopen removes it
tree.json     a Core job's reopen record: every node, its parent, kind, session, brief,
              and how to start it again
queue/        a Core job's helper starts waiting under the cap; dropped/ those whose parent ended
core.json, locks/, relay-state.json, start-failed, reopen-pending
              the --relay path's record (core-relay.md)
finished      the one-line summary written by stampede finish
gates/        each gate asked (action, PR, commit) and your recorded yes
gates.log     one line per gate switched off for the job, and each merge or push made without one
merges.log    one line per stampede merge: PR, reviewed commit, merge commit, review report, gate
agents.tsv    who was started, and how: the reopen record (not on Core)
approved      the plan's fingerprint, for a --review job
front-door    present when a chat outside Herdr relays for you (new --front-door)
outbox/       what the lead posts for that chat to relay: NNN.md and NNN/ files
outbox.log    one line per post, read by stampede wait
REOPEN.md, reopen.sh   written by herdr-reopen-snapshot before a close (a Core job: at every start
              and by stampede snapshot)
```
</details>

## Install

**Prerequisites** (tested on macOS 27.2 and Ubuntu 24.04 arm64, 8 to 13 Nov 2026; Linux in detail: [docs/LINUX.md](docs/LINUX.md)):

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

**Step by step**, on a Mac or a Linux machine with Herdr, Claude Code (signed in), Python 3 and git:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
cd ~/stampede
./install.sh --dry-run               # prints each link it would make, changes nothing
./install.sh                         # links the skills and the commands
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede --version                   # 0.2.1
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

**Or as a Herdr plugin**, where Herdr keeps the checkout and runs the same `install.sh`, plus the event hook:

```bash
herdr plugin install vib-z/stampede  # shows a preview and asks y/N; add --yes over SSH or from a bot
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede doctor                      # Herdr hides the installer's output; exit 0 on a clean install, with Herdr running
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

Then open your repo in Herdr, start Claude in a pane, and ask: *"With stampede: ..."*. The [walkthrough](#use-one-job-start-to-finish) shows a whole job.

What `install.sh` does:
- It links the four skills into `~/.claude/skills/` and `~/.codex/skills/` (each only when `~/.claude` or `~/.codex` exists), and `stampede`, `fleet-job` and the `herdr-*` helpers into `~/.local/bin`.
- It is safe to re-run (`ok` for a link already in place) and, without `--replace`, never replaces anything already there (`skip ... left as is`). The one exception, in a Herdr plugin install, is its own link to the same file in an older checkout of that same install, which it moves to the new one (`relinked`).
- **Taking over an older install:** when `skip` names a copy of a command, a link into another checkout or a real skill folder that you want replaced, run `./install.sh --dry-run --replace` to see what would move, then `./install.sh --replace`. It moves each one into one backup folder, `~/.local/state/stampede/backup-<date>-<time>/` (under `$XDG_STATE_HOME` when that is set), links this checkout in its place, prints `replaced ...` for each, and ends with the line to undo it all: `rollback: bash ~/.local/state/stampede/backup-<date>-<time>/rollback.sh`. Each link and folder it makes is journaled first, so the rollback can undo them, new links included: it removes each link the run made and moves everything back, and what it cannot undo (a path you changed since, a refused move) it names, with where the original is, and exits 1. A run in which every link (and, on Linux, every timer unit) is already right makes no backup. On Linux the timer unit files are stampede's own: an older one is saved in the backup, and a rollback leaves them and says so ([LINUX.md](docs/LINUX.md#the-event-timers)). Nothing is deleted. `--no-skills` links the commands only and leaves `~/.claude/skills` and `~/.codex/skills` alone.
- On Linux it also starts the event timers: systemd user timers when `systemctl --user` answers, otherwise one flock-guarded loop. `--no-supervise` skips that, `--dry-run` only prints it, and a `HOME` that is not the login home is skipped. macOS loads its launchd jobs by hand ([watchdogs](remote/watchdogs.md)).

`herdr-trust` marks a repo trusted for Claude, and for Codex when `~/.codex` exists, so agents start without the folder-trust dialog. It refuses a repo outside `FLEET_TRUST_ROOT` (default `~/code`), so keep your repos there or set the key.

**Then, once:** the settings that let agents start and run without a visit to their pane, which you run yourself: [unattended-setup.md](skills/herdr-fleet/references/unattended-setup.md). A remote bot also needs the event relay. Both: [docs/SETUP.md](docs/SETUP.md). To uninstall: [docs/SETUP.md, Uninstall](docs/SETUP.md#uninstall).

## Updating

Once a day stampede tells you when a newer release is out; it never updates anything by itself. Then you update:

| installed with | update with |
|---|---|
| a clone and `./install.sh` | `stampede update` |
| `herdr plugin install vib-z/stampede` | `herdr plugin update stampede` (add `--yes` from a bot, a script or SSH) |

**The daily check.** At most once a day, `stampede --version`, `stampede update --check` and `herdr-doctor` ask GitHub for the latest release: one request without a token, given 3 s in all (DNS, connect and the reply), the answer cached for 24 h in `${XDG_CACHE_HOME:-~/.cache}/stampede/`. When a newer release is out they print one line:

```text
$ stampede --version
0.2.0
stampede 0.2.1 is out, this is 0.2.0: run stampede update
```

In a plugin install the line ends `run herdr plugin update stampede --yes`. `stampede --version` puts that line on stderr and still exits 0; `herdr-doctor` prints it as a `warn`. Any failure (offline, rate-limited, a malformed reply) prints nothing and is cached too. Turn the check off with `export STAMPEDE_NO_UPDATE_CHECK=1` ([Configure](#configure)). How a release is cut: [RELEASING.md](RELEASING.md).

**`stampede update`** is the guided updater: it updates only a clean checkout on `main`, and never overwrites a file of yours. It runs `git fetch`, fast-forwards with `git merge --ff-only`, reruns `./install.sh` (which links any new skill or command), and ends with `stampede 0.2.0 -> 0.2.1`. It refuses with the reason, and changes no file, when the checkout has local changes or untracked files, is on another branch, or holds an ignored file at a path the update adds. In a Herdr plugin install it changes nothing and prints `herdr plugin update stampede --yes` to run instead.

**A plugin update moves the links.** Herdr gives each plugin install or update a new checkout folder and deletes the old one the next time its server starts. The installer moves each stampede link from the older checkout of that same install to the new one, and leaves any other link alone; `herdr-doctor` reports a `PROBLEM` if `stampede` or a skill still resolves outside the checkout Herdr reports.

**From 0.1.0, once.** 0.1.0 has no `stampede update` (`invalid choice: 'update'`). Move the old clone aside, clone again to the same path and rerun the installer; the links keep their paths, so they work at once:

```bash
mv ~/stampede ~/stampede-0.1.0
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
```

Keep anything of yours from `~/stampede-0.1.0`, then delete it. From then on, `stampede update`. A plugin install pinned with `--ref v0.1.0` stays pinned under `herdr plugin update`: `herdr plugin install vib-z/stampede --yes` drops the pin, and its installer moves the links.

## Use: one job, start to finish

In a Herdr pane in your repo, ask your Claude chat: *"With stampede: make hello.txt with hi, then have a reviewer on another model confirm it."* The chat (a front door) writes the ask and starts the lead:

```console
$ printf 'Make hello.txt with hi.\nThen have a reviewer on another model confirm it.\n' > ask.md
$ stampede new --file ask.md
recorded lead-make-hello-txt-with-hi (claude) in ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi/agents.tsv
DELIVERED lead-make-hello-txt-with-hi (inbox file)
lead-make-hello-txt-with-hi ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi
```

Inside Herdr, `--workspace` defaults to the current workspace and the lead gets a new `lead` tab; `--pane <id>` puts it in an empty pane instead, and `--name <slug>` names the job. A front door outside Herdr has no current workspace: with no flag the job runs on Herdr Core, and for the Herdr TUI it passes `--workspace` or `--pane` ([skills/stampede](skills/stampede/SKILL.md)). The chat tells you `lead-make-hello-txt-with-hi` and stops.

**Plan in chat, then fork it into the lead.** A Claude chat where you and Claude already worked out the plan adds `--fork "$CLAUDE_CODE_SESSION_ID"`: the lead starts as a fork of that chat (`claude --resume <id> --fork-session`), keeps the whole conversation and writes the agreed plan into `plan.md`. Your chat stays as it was. Put the agreed plan in the ask file too: it stays the source of truth. Guide: [remote/claude-code.md](remote/claude-code.md#plan-here-then-fork-the-lead).

**Pick the lead.** The lead is Claude unless you ask for Codex: then the front door adds `--lead codex` (`FLEET_LEAD_KIND=codex` makes it your standing choice). A Codex lead runs GPT-6 Astra at `ultra` with its hooks and `--approve-for-me`; its brief pointer is typed into its pane at once:

```console
$ stampede new --file ask.md --lead codex
recorded lead-make-hello-txt-with-hi (codex) in ~/code/herdr-jobs/jobs/2026-11-03-local-make-hello-txt-with-hi/agents.tsv
SUBMITTED lead-make-hello-txt-with-hi
lead-make-hello-txt-with-hi ~/code/herdr-jobs/jobs/2026-11-03-local-make-hello-txt-with-hi
$ stampede new --file ask.md --lead codex --fork "$CLAUDE_CODE_SESSION_ID"
stampede new: --fork forks a Claude chat, so it takes a Claude lead: drop --lead codex, or start without --fork
```

A Codex lead has no file hook: a short-lived deliverer types its new inbox lines into its pane once it is idle, unfocused and has nothing typed in its prompt (on Herdr Core, Core delivers them). Because text is typed there, it acts on a gate only after `stampede gate-ok` prints `APPROVED`.

The lead reads `ask.md`, writes `plan.md` and goes on at once. Here it writes `briefs/review-hello.md` on the [hand-off template](skills/herdr-fleet/references/brief.md), then starts one reviewer on another model:

```console
$ J=~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi
$ stampede start $J review-hello --kind claude --pane <pane id> \
    --brief $J/briefs/review-hello.md \
    --model <another model> --effort max --report reports/review-hello.md
recorded review-hello (claude) in ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi/agents.tsv
DELIVERED review-hello (inbox file)
```

When the reviewer writes `reports/review-hello.md` with `Status: PASS` in its first 10 lines and ends its turn, its hook adds `REPORT reports/review-hello.md` to `inbox.log`, which wakes the lead. A question for you, with the lead still working:

```console
$ stampede ask $J "Keep the file in the repo root?" \
    --option Yes --option No
ASKED 1fecfa0be4dc (the answer goes to the lead inbox; cancel with: stampede cancel <job> 1fecfa0be4dc)
```

Your tap comes back as `ANSWER ...` in the lead's inbox. A gate (say, merging the draft PR) goes back to whoever started the job ([Safety](#safety)); you started this one in Herdr, so it goes to your phone. The lead merges only with `stampede merge`, which checks the review report and the PR head first and names the gate it needs:

```console
$ sha=$(gh pr view 12 --json headRefOid -q .headRefOid)
$ stampede merge $J 12 --sha $sha --review $J/reports/review-hello.md
stampede merge: the merge gate is on: ask the owner with the next line, then run this again with --gate <id>
stampede ask <job> --gate --kind merge --sha 4e1b0c2f9a7d3e5b6c8a0f1e2d3c4b5a69788766 --pr 12 'merge PR 12'
$ stampede ask $J --gate --kind merge --sha $sha --pr 12 "merge PR 12"
GATE 3288fa0757e0 on the phone; act after stampede gate-ok <job> 3288fa0757e0 --sha <the commit you act on> prints APPROVED
$ stampede merge $J 12 --sha $sha --review $J/reports/review-hello.md --gate 3288fa0757e0     # after your tap
MERGED 12 9c2d7e1f0a4b6c8d3e5f7a9b1c2d4e6f8a0b1c3d
```

It marked the draft ready, merged with `--match-head-commit $sha`, and wrote `<job>/merges.log`: a `MERGING` line before it touched GitHub, then `MERGED`. Only the recorded yes opens a merge gate ([Safety](#safety)). Then the lead writes a short report and asks whether to close the workspace; `<job>/reopen.sh` brings it back later.

### Share the plan first

Say "share the plan first" and the front door adds `--review`. The lead then writes `plan.md` and ends its turn, and no pane can open until you approve that exact plan:

```console
$ stampede new --file ask.md --name hello-review --review
recorded lead-hello-review (claude) in ~/code/herdr-jobs/jobs/2026-10-29-local-hello-review/agents.tsv
DELIVERED lead-hello-review (inbox file)
lead-hello-review ~/code/herdr-jobs/jobs/2026-10-29-local-hello-review
$ J=~/code/herdr-jobs/jobs/2026-10-29-local-hello-review
$ stampede start $J review-hello --kind codex \
    --pane <pane id> --brief <brief>
stampede start: the owner asked to see this plan: run fleet-job approve after their yes, and again after any change to the plan
$ stampede approve $J --by "owner in chat"
DELIVERED lead-hello-review (inbox file)
$ cat $J/approved
Approved: 2026-10-21 21:35 by owner in chat, plan 6ef5e2effdb06d6adf70e17da8726c05dd2d057a4a7ba23c4fbe3836eed14ffa
```

The `start` refusal exits 2. The approval holds a fingerprint of `plan.md`; any later change locks `start` again until a new approve. A change you ask for goes to the lead with `stampede tell <job> lead "<your words>"`. The steps: [share-plan](skills/share-plan/SKILL.md).

### A front door outside Herdr (the Claude desktop app)

When you talk to a chat outside Herdr, nobody watches the lead's pane. The front door then starts the job with `--front-door`: the lead posts everything that is for you (the plan, questions, gates, files, its report) to `<job>/outbox/`, a hook turns its own question cards and SendUserFile into posts, and the front door waits on the outbox in the background and relays each item. Here a review job:

```console
$ stampede new --file ask.md --pane <pane id> --name seller-copy --front-door --review
lead-seller-copy ~/code/herdr-jobs/jobs/2026-10-29-local-seller-copy
$ J=~/code/herdr-jobs/jobs/2026-10-29-local-seller-copy
$ stampede approve $J --by "owner in desktop chat: 'ok - lets go'"
stampede approve: the owner has not been shown this plan.md: the lead posts it (fleet-job post <job> "PLAN READY" --file plan.md), the front door sends it to the owner, and only their yes to it is approved
$ stampede post $J "PLAN READY: one Sonnet build, one review" --file $J/plan.md      # the lead
POSTED 001 for the front door to relay (~/code/herdr-jobs/jobs/2026-10-29-local-seller-copy/outbox/001.md)
$ stampede wait $J                                                                   # the front door, in the background
# 001 post

PLAN READY: one Sonnet build, one review

Files:
- ~/code/herdr-jobs/jobs/2026-10-29-local-seller-copy/outbox/001/plan.md
$ stampede approve $J --by "owner in desktop chat: 'approve as written'"
DELIVERED lead-seller-copy (inbox file)
$ stampede ask $J --gate --sha <commit> --pr 12 "mark PR #12 ready for review"        # the lead
GATE 83307febaa1a posted to the front door as outbox 002; act after stampede gate-ok ... prints APPROVED, or on the owner's yes typed in your pane
$ stampede approve-gate $J 83307febaa1a --sha <commit> --by "owner in desktop chat: 'mark it ready'"
APPROVED 83307febaa1a at <commit>
```

The front door shows you the plan file itself, and a yes to its own summary is never an approval. A gate's item carries the exact `approve-gate` line, which the front door runs with your words quoted. If the lead is held at a card anyway, `stampede wait` and `stampede tell` say `BLOCKED_ON_CARD`. The lead's `finish` posts a `done` item, and `stampede wait` says `LEAD_GONE` when Herdr no longer has the lead. The front door's loop: [skills/stampede](skills/stampede/SKILL.md#steps); the lead's side: [front-door.md](skills/herdr-fleet/references/front-door.md).

**On Herdr Core** the same loop runs with `stampede new --front-door` from a chat outside Herdr. One run against the test suite's fake `hc`, every command from outside Herdr:

```console
$ stampede new --file ask.md --name login --front-door --review
on Herdr Core (backend auto: not inside a Herdr pane), repo <repo>
STARTED lead-login (t1)
lead-login ~/code/herdr-jobs/jobs/2026-11-14-local-login
$ J=~/code/herdr-jobs/jobs/2026-11-14-local-login
$ stampede post $J "PLAN READY: two helpers" --file $J/plan.md                     # the lead
POSTED 001 for the front door to relay (~/code/herdr-jobs/jobs/2026-11-14-local-login/outbox/001.md)
$ stampede wait $J                                                                # the chat, in the background
# 001 post
...
$ stampede approve $J --by "owner in desktop chat: 'go'"
SUBMITTED lead-login (t1)
$ stampede ask $J --gate --kind merge --sha <commit> --pr 12 "merge PR #12"       # the lead
GATE daf2e0132e56 posted to the front door as outbox 002; act after stampede gate-ok ~/code/herdr-jobs/jobs/2026-11-14-local-login daf2e0132e56 --sha <the commit you act on> prints APPROVED
$ stampede wait $J                                                                # the chat
# 002 gate

Gate daf2e0132e56 (merge): merge PR #12 (PR #12) at <commit, 12 hex>?
One exact action, yes or no. Show the owner this action as written.

Answer with: fleet-job approve-gate ~/code/herdr-jobs/jobs/2026-11-14-local-login daf2e0132e56 --sha <commit> --digest 999675042abdf0d7 --by "owner in <chat>: <their exact words>"   (a no: fleet-job tell ~/code/herdr-jobs/jobs/2026-11-14-local-login lead 'GATE daf2e0132e56 NO: <their words>')

$ stampede approve-gate $J daf2e0132e56 --sha <commit> --digest 999675042abdf0d7 --by "owner in desktop chat: 'merge it'"   # on the owner's yes
SUBMITTED lead-login (t1)
APPROVED daf2e0132e56 at <commit>
$ stampede wait $J                                                                # the lead waits at a permission dialog
BLOCKED lead-login: permission. Core says it waits at a dialog in its terminal t1 (hc read t1). Its screen:
Allow this command?
...
```

`SUBMITTED` means Core typed the line into the lead's terminal: there is no inbox file. The lead has no hooks there, so its brief tells it never to use a question card or a file-send tool. [Front door](docs/CORE-NATIVE.md#front-door) has the whole contract.

## Herdr Core

[Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later; checked against 0.1.20) is Herdr's terminal runtime: programs in persistent terminals that report their own status (OSC 7501), with parent links, labels and an event stream, and no workspaces, tabs or panes. `stampede new` runs a job there the way Core itself works: Core holds the tree of terminals, and stampede adds only the space's name, the owner tag, the reopen record, the owner's gates, a cap on helpers and the layout labels.

Which backend a job takes is the setting `backend`: `auto` (the default) runs it on the Herdr TUI inside a Herdr pane and on Herdr Core everywhere else, saying so on the first line; `tui` and `core` make either the standing choice; `--core` forces Core, and `--pane` or `--workspace` the TUI. The shape a client reads (labels, parent links, events): [docs/CORE-NATIVE.md](docs/CORE-NATIVE.md). The lead's playbook: [references/core.md](skills/herdr-fleet/references/core.md). For Core's own basics read `hc --skill`.

**The tree and the roles.**
- **The owner** asks, answers questions and gives every gate's yes.
- **The front door** writes the ask, runs `stampede new` (outside a Herdr pane, or with `--core`), passes the owner's words to the lead with `stampede tell <job> lead "..."` and records a gate's yes with `approve-gate`. It reads the lead or a helper with `hc read <address>` and never types into one. A chat outside Herdr adds `--front-door`, as on the TUI ([Front door](docs/CORE-NATIVE.md#front-door)).
- **The lead** is the root: one Core terminal with no parent, one per job. The space has no terminal of its own: its name is the lead's `stampede.space` label.
- **Helpers** are the lead's real Core children, started with `stampede start`: Claude, Codex or any program. A helper may start its own helpers, at any depth. Core ends a branch when its parent ends, unless a helper was started with `--outlive-parent`. Core sets a parent once, so such a helper still names its old parent after a lead is reopened: `stampede tree` shows it at depth 1 as `outlived <its old parent>`, the cap counts it, and a whole-job `close` ends it with the rest.
- **The reviewer** is one helper on another model: a `review-<scope>` helper gets the setting `roles.review` (Codex by default). The lead's brief says when to review, from the setting `review.step`: `end` (one pass at the end, the default), `each` (one per pull request or step) or `none` (the owner switched it off).
- **Plain children** (a CI wait, a build) are started with a bare `hc run`; they are in the tree by their parent link alone.

**What lives where.** Core holds the tree and each terminal's status; read it with `stampede tree <job>`. The job folder holds the ask, the plan, the briefs, the reports, the owner's gates and `tree.json`, the reopen record. Messages go only through Core: `hc send`, Core's notes to a parent about each child (its turn ended, it is blocked, it exited), `hc wait --children`, and results in files with the path sent. A Core job has no follower terminal, no inbox files and no hooks.

Check the machine once, then start the job from the repo. `herdr-doctor` checks each backend that is installed; one usable backend is enough, and the last backend line says where a job can run. This ran on a Mac with Herdr 0.9.5 installed but no Herdr server for that home, against a running Herdr Core 0.1.20 in a scratch session named `probe1`:

```console
$ herdr-doctor
...
ok herdr on PATH
ok herdr 0.9.5
warn herdr server not running: the owner starts it (bots never do)
ok hc 0.1.20
ok Herdr Core answers (HC_SESSION probe1)
ok claude 2.1.322 reports its status (OSC 7501)
ok codex runs with --no-daemon
warn cursor-agent reports no OSC 7501 status on Herdr Core: a Core-native job runs it as a program (stampede start <job> <name> -- cursor-agent ...), a --core --relay job hands it to a Herdr TUI pane
ok backend core
...
```

With both usable the line is `ok backend tui,core`; `--core` or `--tui` checks one only, each gap a `PROBLEM`. On Herdr Core it also warns about an `hc` older than 0.1.20, old terminals on macOS and a core started from inside an agent ([Troubleshoot](#troubleshoot)). It never starts, stops or restarts a core.

### One Core job, start to finish

These commands ran against the test suite's fake `hc` in a scratch home (`<repo>` stands for the repo's path, `J` for the job folder). The front door starts the job from the repo, outside any Herdr pane, so `backend` `auto` picks Herdr Core. The job folder is in the jobs root, as on the TUI, with the repo in `<job>/workdir`. The lead starts as a root terminal labelled with the space's name (`--space`, by default the job's slug):

```console
$ cd ~/code/my-app && stampede new --file ask.md --name add-health
on Herdr Core (backend auto: not inside a Herdr pane), repo ~/code/my-app
hook pre-push installed in ~/code/my-app/.git/hooks/pre-push: a job's agent cannot push to the default branch without the gate
STARTED lead-add-health (t1)
lead-add-health ~/code/herdr-jobs/jobs/2026-11-14-local-add-health
```

The lead writes `plan.md` and starts its helpers, each as its own Core child. A helper's role, its name up to the first `-`, gives its kind, model and effort (the settings `roles.<role>`: `build-health` is a Claude builder at medium effort, `review-health` a Codex reviewer); `--kind`, `--model` and `--effort` override them. Any CLI runs as a program:

```console
$ J=~/code/herdr-jobs/jobs/2026-11-14-local-add-health
$ stampede start $J build-health --brief $J/briefs/build-health.md --report reports/build-health.md
STARTED build-health (t2) under lead-add-health
$ stampede start $J review-health --brief $J/briefs/review-health.md
STARTED review-health (t3) under lead-add-health
$ stampede start $J lint -- npm run lint
STARTED lint (t4) under lead-add-health
```

At most 12 helpers work at once in one lead's tree, at any depth (`--max-helpers <n>` at `new`, `<job>/max-helpers`, or `STAMPEDE_MAX_HELPERS`). With this job's cap set to 3, a fourth start waits in the queue, and the lead runs `stampede next` when a child's note says it is done:

```console
$ stampede start $J docs-health --brief $J/briefs/docs-health.md
QUEUED docs-health (3 running, cap 3)
$ stampede next $J
STARTED docs-health (t5) under lead-add-health
$ stampede next $J
NOTHING QUEUED
$ stampede tree $J
space add-health (hc-62876e54e3ce)
  lead-add-health (t1) lead claude idle tab main pane 1
    build-health (t2) helper claude done tab main pane 2
    review-health (t3) helper codex idle tab main pane 3
    lint (t4) helper program idle tab main pane 4
    docs-health (t5) helper claude idle tab main-2 pane 1
```

The layout is labels only. The lead is pane 1 of tab `main`, top left, and helpers fill `main`, `main-2` and so on, 4 live terminals to a tab (`STAMPEDE_TAB_PANES`), or a workstream tab named with `--tab <label>`, in a 2x2 by default (the setting `helpers.layout`: `grid`, `columns` or `rows`). The lead and every helper also carry `herdr.space` and `herdr.tab`, so the Herdr app can show the job as one space. Every label: [Layout labels](docs/CORE-NATIVE.md#layout-labels); `stampede tree --json` gives the same to a client.

The lead waits with Core, never with sleep or a poll. With nothing else to do it ends its turn: Core types each child's news and each message into its terminal, and that wakes it. To block inside a command it runs `hc wait --children any --timeout <seconds>`. A helper reports with `hc send <parent address> "build-health: done reports/build-health.md"`: one line and the path of its result file, which the lead then reads ([Messages](docs/CORE-NATIVE.md#messages)). The owner's words reach the lead through `tell`:

```console
$ stampede tell $J lead "The owner says: keep the route at /health"
SUBMITTED lead-add-health (t1)
```

A question for the owner, or a gate, goes out with `stampede ask`; on a Core job the answer comes back through Core, typed into the lead's terminal (the phone here):

```console
$ stampede ask $J "Keep the route at /health?" --option Yes --option No
ASKED 188e888a8640 (Core types the answer into the lead's terminal; cancel with: stampede cancel $J 188e888a8640)
$ stampede ask $J --gate --kind merge --sha <commit> --pr 12 "merge PR #12"
ASKED 439e979b6d65 (Core types the answer into the lead's terminal; cancel with: stampede cancel $J 439e979b6d65)
GATE 8b6cf83c386c on the phone; act after stampede gate-ok $J 8b6cf83c386c --sha <the commit you act on> prints APPROVED
```

A message from an agent arrives in a terminal as `<hc from="t7 name">...</hc>`; one from a plain program arrives as bare text. Neither is ever the owner's approval.

A CI wait or a build is a plain child of the lead, `hc run --bg --name wait-ci-<pr> -- gh pr checks <pr> --watch`: it carries no stampede label, never counts against the cap, and its exit comes to the lead as Core's note.

Gates are as everywhere on Core: only the recorded yes counts ([Safety](#safety)). When the job is done the lead runs `stampede finish $J "<summary>"`, and on the owner's yes closes it. Here the owner closes the job before it is finished, so it can be reopened to work again:

```console
$ stampede close $J review-health
CLOSED review-health (t3)
$ stampede close $J
CLOSED build-health (t2)
CLOSED lint (t4)
CLOSED docs-health (t5)
CLOSED lead-add-health (t1)
```

`close` ends a subtree leaves first, politely when an agent is idle or done, else by killing its terminal. A helper closed by name stays closed at a reopen. With no agent `close` ends the whole job, the lead last, and writes `<job>/closed`, so the watchdog raises no alarm. Closing a whole job is always the owner's call, and it is refused from a terminal inside the subtree it would end.

**Reopen.** stampede keeps `tree.json`, the reopen record, at every step. After a crash, a reboot or a close of a job not yet finished, `stampede reopen $J` (or `bash $J/reopen.sh`) brings back what is not live, parents first, each in its recorded tab and pane, and removes `closed` (here `review-health` stays closed, as it was closed by name; the lead's and build-health's Claude sessions ran, docs-health's never did):

```console
$ stampede reopen $J
STARTED lead-add-health (t6)
STARTED build-health (t7) under lead-add-health
DONE review-health (closed)
SKIPPED lint (a program: --rerun-programs runs it again)
STARTED docs-health (t8) under lead-add-health
$ bash $J/reopen.sh
LIVE lead-add-health (t6)
LIVE build-health (t7)
DONE review-health (closed)
SKIPPED lint (a program: --rerun-programs runs it again)
LIVE docs-health (t8)
```

A reopen never hands out work by itself. The lead comes back first and gets one line saying it was reopened; a Claude helper whose session ran comes back resumed and idle and waits for the lead's word. What would start work again (a Claude helper whose session never ran, `--fresh`, `--rerun-programs`) goes through the queue and the cap. A Codex helper is `SKIPPED` without `--fresh`. The details: [Reopen and close](docs/CORE-NATIVE.md#reopen-and-close). A finished job reopens for reading only, so work that would start again is refused:

```console
$ stampede finish $J "added /health with a test"
FINISHED ~/code/herdr-jobs/jobs/2026-11-14-local-add-health
$ stampede reopen $J --fresh
stampede reopen: the job is finished, so it reopens for reading only: --fresh and --rerun-programs would start its work again
```

### The earlier path: `--core --relay`

`stampede new --core --relay` starts a Core job the earlier way: a follower terminal per job, inbox files and hooks. It is deprecated and goes in the next minor release; until then it is the one way to hand Cursor, Hermes or Kimi workers to Herdr TUI panes. Its reference: [references/core-relay.md](skills/herdr-fleet/references/core-relay.md).

## Front doors

Every front door writes the ask and runs `stampede new`; none plans or runs the job itself.

| front door | how you ask | where answers arrive | guide |
|---|---|---|---|
| a chat in Herdr | type the ask in a Claude pane | the lead's pane, plus a Moshi card | [walkthrough](#use-one-job-start-to-finish) |
| Claude desktop or the Claude app | Remote Control into a session on the machine | the lead's row in the Claude app, plus Moshi | [remote/claude-code.md](remote/claude-code.md) |
| Codex desktop or the ChatGPT app | Codex on the connected machine | Moshi | [remote/codex.md](remote/codex.md) |
| Cursor | a Cursor chat on the machine runs the same two commands | Moshi | [remote/other.md](remote/other.md) |
| **Grok Bot** (preferred bot) | the bot reaches your Mac over SSH and Tailscale | the Grok chat, woken by a webhook | [remote/grokbot/](remote/grokbot/README.md), [grokbot-herdr](skills/grokbot-herdr/SKILL.md) |
| any other bot | the same as Grok Bot | its webhook | [remote/other.md](remote/other.md) |
| a whole remote computer | Herdr, the CLIs and stampede on one box | any of the above | [remote/any-machine/](remote/any-machine/README.md) |

Any of them can run the job on Herdr Core instead: outside a Herdr pane that is the default, or it passes `--core --cwd <repo>` ([Herdr Core](#herdr-core)). It then hears a question, a gate, a post and done from the lead's own commands, and blocked, error, dead or stale for the lead from the machine's watchdog within about 5 minutes.

Moshi, the phone side of every front door: [remote/moshi.md](remote/moshi.md).

## Safety

- **Your own yes, every time:** a merge to main, a push to main or another shared branch, a deploy, publishing, sending email or messages, resubmitting a sitemap, any spend, and closing panes, tabs, a workspace or a Core job (`stampede close`). Pushing the job's own work branch and opening a draft PR need no ask. The one list, and what never counts as a yes: [gates.md](skills/herdr-fleet/references/gates.md).
- **Gates go back to whoever started the job.** `stampede new` records the bot that started it (`HERDR_EVENTS_OWNER`, else the workspace's owner tag) in `<job>/owner`. The lead asks each gate with `stampede ask <job> --gate [--kind merge|push_default_branch] --sha <commit> [--pr <n>] "<the exact action>"` (`--kind merge` for a merge, `--kind push_default_branch` for a push to the default branch; a gate for anything else has no kind):
  - **started by a bot:** a `gate` event goes to that bot ([remote/events.md](remote/events.md)). The bot asks you in chat and, on your yes, runs `stampede approve-gate <job> <gate> --sha <commit> --by "owner in <bot> chat"` over SSH, which records it in `<job>/gates/`.
  - **started locally:** your phone, through `FLEET_ASK_CMD` (Moshi), records your tap the same way; or the lead's own question card.
  - **started by a front door** (`--front-door`, on the Herdr TUI or on Herdr Core): a post in `<job>/outbox/`. The front door shows you the exact action and, on your yes in its chat, runs `stampede approve-gate ... --by "owner in <chat>: '<your words>'"`. An explicit order you already gave there for that exact action counts, quoted; anything vaguer goes back to you.
  - **either way, on the Herdr TUI,** a yes typed in a Claude lead's Herdr pane works.
- **The lead acts on your yes typed in its pane for that exact action (a Claude lead on the Herdr TUI only), or on a recorded yes for one gate at one commit:** `stampede gate-ok <job> <gate> --sha <the commit it acts on>` prints `APPROVED` only when the record names that gate and that commit. A merge and a push to the default branch take only the recorded yes, since the code checks them (below). `approve-gate` refuses inside Herdr, for a job started locally and for another commit: an agent's own say-so never counts, and nor does a plan, a brief or a yes passed on in a message.
- **A yes covers the gate as you were asked it.** The record holds a digest of the gate's action, PR, commit and route: a gate changed after your yes makes `gate-ok` refuse, and the bot's `approve` command carries the same digest (`--digest`), so a gate changed between the question and your yes takes none. `stampede finish` cancels every question of the job still waiting on your phone.
- **A Codex lead counts only the recorded yes.** stampede types its inbox into its pane, marked as from stampede, so text there proves nothing: it acts only after `gate-ok` prints `APPROVED`.
- **On Herdr Core only the recorded yes counts.** The lead acts only after `gate-ok` prints `APPROVED`: a yes typed into the lead, an answer to its own question card, and any message never count, because on Core another program can type into any terminal (`hc send`, `hc keys`). To a typed yes the lead replies: "A typed yes does not count on Core; answer in the chat or on the phone that started this job." Your tap on a phone card and a bot's `approve-gate` are recorded and count.
- **`approve-gate` refuses inside Herdr Core too:** in a Core terminal (`HC_TERMINAL_ID`, `HC_TERMINAL_SOCKET` or `HC_SCOPE` set) and under a `herdr-core` or `hc` process, so `hc exec` cannot run it: a bot runs it over plain ssh. Core's own `blocked` state is never a gate.
- **Three gates are held by code, not only by the lead's brief:**
  - **merge:** the lead merges only with `stampede merge <job> <pr> --sha <sha> --review <report> --gate <id>`. Whatever the settings, the review report's header must say exactly `Status: PASS` and `Reviewed: <sha>` ([Troubleshoot](#troubleshoot) has its format), and the PR must be open with that sha as its head.
    With `gates.merge` on, the gate must be one asked with `--kind merge` for that PR and approved at that sha. Every new head, a rebase too, needs a review report that names it. Then it marks a draft ready and runs `gh pr merge <pr> --squash --match-head-commit <sha>` (`merge.method`), so a push after the review or the yes means reviewing and asking again.
  - **push to the default branch:** `stampede new` installs a `pre-push` hook (marked `# stampede-hook`) in the repo's own hooks folder, only when there is no `pre-push` and `core.hooksPath` is unset; a repo with a hook of its own gets no push gate from a hook (`new` says so).
    A push from your own shell outside a job (neither `STAMPEDE_JOB_KEY` nor `HERDR_WORKSPACE_ID` set) is never touched. A job's agent pushing to the default branch needs a gate asked with `--kind push_default_branch` and approved at the pushed commit. The default branch is the one `stampede new` found for each remote (its HEAD), else `refs/remotes/<remote>/HEAD`, else `main` and `master`.
    Only `stampede prepush`'s own refusal (exit 9) stops a push: a missing, old or failing stampede lets it through with one warning line.
  - **close:** a whole job never closes from one of its own terminals, and `stampede close` never ends a terminal that carries another job's key: it skips that terminal, its branch and the terminals above it (`SKIPPED ...`), and exits 1.
  - These guard against a forgetful agent, not a hostile one: an agent runs as your user and could edit the record or skip a hook with `git push --no-verify`.
- **Opting out is allowed, and logged.** Every gate is on by default (`[gates]` in [Configure](#configure)). Switch one off for one job with `stampede new --no-gate merge` (repeatable, the same as `--set gates.merge=false`), or for every job in your own `config.toml`; a repo's `.stampede.toml` can never switch a gate off.
  - `stampede new` records the job's gates and each remote's default branch outside the job folder, in `$HERDR_EVENTS_DIR/gates/<job key>.json`, where `stampede merge`, the hook, the lead's brief and `finish` read them (a job with no record has every gate on).
  - Each gate off is a line `<UTC time> OFF <name> (<layer>)` in `<job>/gates.log`, the lead's brief names it, `stampede config show --job` shows it, and `stampede finish` prints `gates off: <names>` and sends it with the done event.
  - Two rules have no switch: never close what the job did not create, and merge only the reviewed commit.
- **Auto mode, never no-checks mode, by default:** Claude `--permission-mode auto`, Codex `--approve-for-me`, Cursor `--auto-review`, Hermes its default (a dangerous command asks), Kimi `-y` (a risky action asks). `stampede start --yolo-in <worktree>` runs a worker in its CLI's no-checks mode only when its pane's shell sits in its own linked git worktree, and never the lead.
- **Plan approval** (only when you asked to see the plan) lets the lead work inside the job's own folder and branch; it is not a gate and covers no merge or spend.
- **Nothing closes by itself.** The last step is always the question whether to close; no answer is a no.
- **Never touched:** panes, tabs and workspaces the lead did not create; the pane you have focused; credentials and `.env` files.

## Configure

Nothing needs setting: every setting has a default. Each one is resolved from layers, and the last layer that sets it wins:

1. the defaults, in [defaults.toml](skills/herdr-fleet/scripts/stampede/defaults.toml), the list of every key;
2. yours: `~/.config/stampede/config.toml` (`$XDG_CONFIG_HOME/stampede/config.toml` when that is set);
3. the project's: `.stampede.toml` at the repo root, which a repo can commit;
4. the environment: the variable names stampede has always read, which keep working;
5. the command's own flags (`--lead`, `--lead-model`, `--lead-effort`, `--max-helpers`, and `start`'s `--kind`, `--model`, `--effort`), then `--set key=value` (repeatable, on `new` and `start`; the value is read as TOML, and a bare word is a string).

[config.example](config.example) is every key with its default: copy it to `~/.config/stampede/config.toml` and keep only what you change.

```bash
mkdir -p ~/.config/stampede && cp config.example ~/.config/stampede/config.toml
stampede config show                     # every setting and the layer that set it; exit 1 when the config has problems
stampede config show --json              # {values, sources, files, environment, problems}
stampede config show --job <job>         # what that job saved at new
stampede new --file ask.md --set helpers.max=6 --set lead.kind=codex
```

`stampede new` saves what it resolved in `<job>/settings.json`, with the layer of each value, and every later command of that job reads it there: a job remembers what was set when it started, and anything not set then follows your current config. A later command's own `--set` still wins for that command, and `<job>/max-helpers` for its job.

**User only.** `jobs_root`, `trust_root`, `ask.command`, `lead.forbid` and every `gates.` key run a command, widen what is trusted or lower a rule, so they are read from your file, the environment or a flag, never from a repo's `.stampede.toml` (there each is skipped with a problem line), and never saved in `settings.json`, which the job's agents can write. `lead.forbid` matches exact model names. A job's gates are fixed at `stampede new`, in the owner-side record ([Safety](#safety)); the other four follow your live config at every command.

**Problems.** An unknown key, a value of the wrong type or not one of the key's choices, or a file that does not parse is skipped and named in one line by `stampede config show`. `stampede new` refuses to start a job while there is one (exit 2); no other command fails on them.

<details>
<summary><b>Every key, with its default</b></summary>

| key | default | environment | what it does |
|---|---|---|---|
| `backend` | `auto` | | where `stampede new` runs a job given no `--core`, `--pane` or `--workspace`: `auto` (the Herdr TUI inside a Herdr pane, Herdr Core everywhere else), `tui` or `core` |
| `jobs_root` | `~/code/herdr-jobs` | `FLEET_JOBS_ROOT` | every job folder, on every backend, is `<root>/jobs/<date>-<owner or local>-<slug>`, never in a repo (user only) |
| `trust_root` | `~/code` | `FLEET_TRUST_ROOT` | a Core job's repo must sit under it (user only). `herdr-trust` and `herdr-doctor` read only `FLEET_TRUST_ROOT`: if you move the root, export that too |
| `lead.kind` | `claude` | `FLEET_LEAD_KIND` | the lead's CLI when `stampede new` has no `--lead`: `claude` or `codex`, on the Herdr TUI and on Herdr Core. `--fork` takes `claude` only |
| `lead.forbid` | `[]` | `FLEET_LEAD_FORBID` (comma-separated) | models that may not lead a job: `stampede new` refuses, before it makes anything, a lead whose model is on the list, whether it came from `--lead-model`, a setting or the default, with one line naming the model and `lead.forbid` (user only). Workers are not checked |
| `lead.claude.model`, `lead.claude.effort` | Claude Opus 5.5 (its id is in config.example), `xhigh` | `FLEET_LEAD_MODEL`, `FLEET_LEAD_EFFORT` | a Claude lead's model and effort |
| `lead.codex.model`, `lead.codex.effort` | GPT-6 Astra (its id is in config.example), `ultra` | `FLEET_LEAD_MODEL`, `FLEET_LEAD_EFFORT` | a Codex lead's model and effort. `FLEET_LEAD_MODEL` and `FLEET_LEAD_EFFORT` set a pair: a `gpt-...` model sets the Codex pair, any other (or none) the Claude pair. `new --lead-model` and `--lead-effort` set the pair of the lead's own CLI |
| `roles.<role>.kind`, `.model`, `.effort` | `build`, `default`: Claude Opus 5.5 `medium`; `research`: Claude Opus 5.5 `xhigh`; `copy`: Claude Opus 5.5 `high`; `test`: Claude Sonnet 5.5 `medium`; `review`, `qa`, `design`: Codex GPT-6 Astra `ultra` (the ids are in config.example) | | what `stampede start <job> <role>-<scope>` gives a helper when it names no `--kind`, `--model` or `--effort` (the role is the name up to its first `-`; any other role takes `roles.default`). A flag always wins; a role's model and effort go only with its own kind, so `--kind codex` on a Claude role leaves the model to Codex. Add a role of your own as `[roles.<name>]`. Not for a program after `--` |
| `review.step` | `end` | | the review step the lead's brief asks for, with its reviewer from `roles.review`: `end` (one pass at the end, by another model than the builder's), `each` (one per pull request or step) or `none` (no review step: the brief says the owner switched it off). Guidance only, nothing enforces it |
| `ask.command` | `moshi-hook ask --require-remote --source herdr-fleet --timeout 24h` | `FLEET_ASK_CMD` | what `stampede ask` runs, for a question or a gate, in a job started locally (a bot-started job asks its bot); the options and question are appended (user only) |
| `brief.sections` | the seven headings of the [hand-off template](skills/herdr-fleet/references/brief.md) | | the sections every worker's brief must fill |
| `helpers.max` | `12` | `STAMPEDE_MAX_HELPERS` | a Core job: how many helpers may work at once in the lead's tree, at any depth; a start over it is queued (`--max-helpers` or `<job>/max-helpers` per job) |
| `helpers.layout` | `grid` | | a Core job: the split labels of a tab's terminals: `grid` (2 right of 1, 3 below 2, 4 below 1), `columns` (each right of the one before) or `rows` (each below the one before) |
| `helpers.tab_panes` | `4` | `STAMPEDE_TAB_PANES` | a Core job: live terminals per layout tab label (`main`, `main-2`, ...) before a helper goes to the next |
| `timeouts.wait` | `3600` | | seconds `stampede wait` waits before exit 3 (`--timeout` per call) |
| `timeouts.hc_call` | `60` | | seconds one `hc` call may take on top of what the command itself waits for |
| `timeouts.leave` | `15` | | seconds an idle agent has to leave after `/exit` or `/quit` at `stampede close` |
| `timeouts.hold_settle` | `5` | | seconds a `--relay` terminal must have been at rest before its turn count can start a hold |
| `gates.merge` | `true` | | `stampede merge` needs a gate approved at the reviewed commit; `false` merges a passing review without one, logged (user only) |
| `gates.push_default_branch` | `true` | | the `pre-push` hook stops a job's agent pushing to the default branch without a gate; `false` lets it, logged (user only) |
| `gates.deploy`, `gates.publish`, `gates.send`, `gates.spend` | `true` | | the lead asks before a deploy, publishing, sending or any spend; `false` tells it that one needs no yes (user only) |
| `gates.close` | `true` | | the lead asks before closing a helper's terminals; a whole job never closes from inside it (user only) |
| `merge.method` | `squash` | | how `stampede merge` merges: `squash`, `merge` or `rebase` |
</details>

<details>
<summary><b>Environment only, with defaults</b></summary>

Other programs read these, so they stay environment variables. Export them in your shell profile, or in the shell file `~/.config/stampede/config` (`$XDG_CONFIG_HOME/stampede/config` when that is set) sourced from it. The relay scripts read that file themselves, so the hooks and the timers see it with no profile line. They read only its plain lines, `NAME=value` or `export NAME=value` (the value bare or quoted, with `$HOME` or a leading `~/` at most), and run nothing in it: a value worked out by a command belongs in your shell profile, and `herdr-doctor --relay` names the lines they skip. A file over 4 KB or 100 lines is not read at all, and `herdr-doctor --relay` says so. A value the environment already holds wins over the file. The Herdr plugin event is the exception: as before, it sources the file as shell, and there the file's value wins. `stampede config show` lists them with their current values. A Core job passes them, and the environment names above, to every terminal it starts.

| variable | default | what it does |
|---|---|---|
| `FLEET_WATCH_INTERVAL` | `30` | seconds between `fleet-watch.sh` passes (a bot outside Herdr) |
| `FLEET_WATCH_PASSES` | `0` | stop the watch after this many passes; 0 runs until stopped |
| `FLEET_WATCH_NOTIFY` | `1` | `0` turns off the watch's phone push. A `--core --relay` job's follower pushes stalls and ended terminals to the phone (`moshi-hook notify`) only when it is `1`; unset, it does not |
| `HERDR_EVENTS_MACHINE` | short hostname (`hostname -s`, else the name before the first dot) | the machine label sent with every event |
| `HERDR_EVENTS_HOME` | `~/.herdr-events` | the event queue and dead letters |
| `HERDR_EVENTS_ROUTES_DIR` | `$HERDR_EVENTS_DIR/routes` | one file per route, `URL=` and `KEY=` |
| `HERDR_EVENTS_STALE_MINUTES` | `30` | the watchdog's sweep of a Core job's lead, and a `--core --relay` job's follower: minutes a working terminal's screen may stay unchanged, with no status or turn change, before one `stale` (the TUI watchdog's fixed 30) |
| `HERDR_EVENTS_DIR` | `~/.config/herdr-events` | owner tags (`owners/`), job markers (`jobs/`), handed panes' marks (`handed/`), and the routes when `HERDR_EVENTS_ROUTES_DIR` is unset |
| `HERDR_EVENTS_FLUSH_LOG` | `~/.herdr-events/flush.log` | the flusher's log |
| `HERDR_EVENTS_FALLBACK_ROUTE` | unset | a route's name, a file in the routes folder: an owner with no route file of its own goes there instead of `default`, and a Codex turn with no Herdr pane and no Core terminal (the Codex desktop app) is sent there as source `codex-desktop`, with no workspace or owner, instead of skipped. It must be the name of a route in the routes folder; any other value is ignored (logged), and events go as when it is unset. A question or a gate never uses it |
| `HERDR_EVENTS_LAUNCHD` | `local` | macOS: the label prefix of the two launchd jobs `herdr-doctor` checks, `<prefix>.herdr-event-watchdog` and `<prefix>.herdr-events-flush` |
| `HERDR_DOCTOR_EXTRA` | unset | an absolute path to an executable of your own that `herdr-doctor` runs last, never through a shell, with empty stdin: its lines print with control bytes removed, each line that starts `PROBLEM` counts toward exit 1, and a missing or failing one, or one not done in 30 seconds (it and its process group are ended), is one `warn` |
| `HERDR_EVENTS_OWNER` | unset | set per command by a bot, never in a config file: at `stampede new`, the bot that started the job (else the workspace's owner tag), so its gates go back to it |
| `HC` | `hc` | the Herdr Core binary, 0.1.13 or later |
| `HC_SESSION` | `default` | Herdr Core's own: which core; each name is a separate core with its own terminals and state. A Core job keeps the one it was made with (`<job>/endpoint`) and passes it to every terminal; a command from a shell set to another is refused |
| `HC_SOCKET` | Core's default path for the session | Herdr Core's own: that core's socket; passed on like `HC_SESSION`. Set to the default socket's own path, it is the default core |
| `STAMPEDE_APP_SPACE` | `0` | `1`: every `stampede new --core --relay` job labels its lead and workers for the Herdr app, as `--app-space` does ([core-relay.md](skills/herdr-fleet/references/core-relay.md#in-the-herdr-app)); a Core job always carries the app's labels |
| `STAMPEDE_NO_UPDATE_CHECK` | `0` | `1` turns off the daily check for a newer release ([Updating](#updating)) |
| `STAMPEDE_UPDATE_URL` | `https://api.github.com/repos/vib-z/stampede/releases/latest` | where the check reads the latest release; the tests point it at a local file |
</details>

## Troubleshoot

| what you see | fix |
|---|---|
| `refused: a workspace labelled <label> is already open` from `reopen.sh`, with `none of this job's agents runs there` | after a Herdr server restart, Herdr restores the job's workspace with plain shells: close that workspace (your yes, as for any close), then run `reopen.sh` again |
| `reopen.sh: workspace <id> is open but not tagged for <bot>` (exit 5) | `herdr-events-owner` failed, so the bot would not hear that workspace: run the command it prints, then carry on |
| `stampede merge: no review report <file>`, `... says Status: FINDINGS, not PASS` or `... names no Reviewed: <full sha>` | the reviewer writes `Status: PASS` and `Reviewed: <full sha>` in its report's first 10 lines; fix any findings and review again, then merge |
| `stampede merge: the review report <file> has 2 Status: lines ...`, `line <n> ... comes before or inside its header` or `says Reviewed: <text>: it takes one full sha and nothing else` | the header is a title line, then one `Status:` line and one `Reviewed: <40-hex sha>` line, before any code block, quote, comment or indented line: the reviewer fixes it |
| `stampede merge: the review report passes <a>, not <b>`, or `... but the PR head is <b>: review the new commit` | merge only the reviewed commit: review the new head, then ask the gate at it |
| `stampede merge: the merge gate is on ...`, `gate <id> is not a merge gate for PR <n> ...`, `gate <id> has no recorded yes` or `... was approved for <a>, not <b>` | run the `stampede ask ... --kind merge` line it prints for this PR at this commit, wait for the owner's yes, then merge with `--gate <id>` |
| `stampede merge: PR <n> is merged, not open` (or closed) | nothing to merge: check the PR number |
| `stampede merge: gh pr merge failed: <gh's line>` (exit 1), or `<job>/merges.log cannot be written (...): nothing was merged` | fix what gh names (auth, a protected branch, a head that moved), or make `merges.log` writable, then merge again |
| `stampede gate-ok: gate <id> changed after the yes`, or `stampede approve-gate: gate <id> changed while the owner was asked` | the gate's action, PR or route changed after you were asked, so your yes was for something else: the lead asks again |
| `stampede gate-ok: gate ... was approved for <sha>, not <sha>` | a push came after the yes: ask the gate again at the new commit |
| `stampede approve-gate: approve-gate needs --digest` | a bot built the command itself: run the gate event's `approve` line as given, which carries the digest |
| `stampede approve-gate: approve-gate runs only outside Herdr` | it is the starting bot's command, over plain ssh, never `hc exec`. On the Herdr TUI, type yes in a Claude lead's pane instead, except for a merge or a push to the default branch ([Safety](#safety)) |
| `stampede prepush: a push of <sha> to main needs the owner's yes. Ask it with the next line ...` | a job's agent pushed to the default branch: run the `stampede ask ... --kind push_default_branch` line it prints, then push again once `gate-ok` prints `APPROVED`; or push the work branch instead |
| `stampede-hook: stampede is not on PATH, so this job's push gate was not checked` (or `stampede prepush failed (exit <n>)`) | the push went through unchecked: put stampede on PATH (`./install.sh`) or run `stampede update` |
| `stampede new: the push gate is not enforced by a hook in this repo, because it has its own (...)` | the repo has its own `pre-push` or `core.hooksPath`: a push to the default branch is the lead's to ask; `stampede merge` still holds the merge gate |
| `stampede new: --no-gate <name> is no gate` | use one of the names it lists: `merge`, `push_default_branch`, `deploy`, `publish`, `send`, `spend`, `close` |
| `SKIPPED <name> (<address>): it carries another job's key ...` from `stampede close` | another job's terminal runs under this job's: close it from its own job; this one stays open around it |
| `stampede start: the owner asked to see this plan` | a `--review` job: approve the plan as it stands with `stampede approve <job> --by <who>` |
| `stampede approve: the owner has not been shown this plan` | a `--front-door` job: the lead posts `plan.md` (`stampede post <job> "PLAN READY" --file <job>/plan.md`), the front door sends that file to you, and only your yes to it is approved; post again after any change |
| `stampede approve: the front door has not received this plan.md yet` | the front door has not run `stampede wait` since the lead posted the plan: run it, send the owner the file it names, and approve only their yes to that file |
| `BLOCKED <lead>: <kind>` from `stampede wait` on a Core job | the lead waits at a dialog (a permission, a trust prompt): show the owner the screen `wait` printed, clear it only as they say (`hc keys <address> <keys>`), then run `wait` again |
| `BLOCKED_ON_CARD <agent>` from `stampede tell` or `stampede wait` | the agent waits at a question card in its pane and reads nothing else until it is answered; your message is queued. Answer the card in its pane. In a `--front-door` job the lead's own cards become posts, so this is rare |
| `BLOCKED <agent>: clear the startup dialog` | read the screen (`herdr agent read <agent> --source visible --lines 30`), clear the dialog, then send the printed `stampede tell` line |
| the lead's pane shows Claude's sign-in or first-run screen, though `stampede new` printed `DELIVERED` | sign in to Claude Code once in a plain terminal (`claude`) before your first ask. Then finish the screen in the lead's pane and send `stampede tell <job> lead "Read <job>/briefs/<lead>.md"` |
| a Codex lead does not react to a worker's report or your `tell` | its lines are typed only while it is idle or done, unfocused, with nothing typed in its prompt: leave its pane, clear a draft, and see `<job>/hooks/deliver.log` (`GAVE UP` after 4 h, `CANNOT REACH HERDR`); `stampede _wake <job>` starts the deliverer again |
| `stampede new: --fork forks a Claude chat, so it takes a Claude lead` (exit 2) | a Codex lead never starts as a fork: drop `--lead codex` (or unset `FLEET_LEAD_KIND`), or start it without `--fork`; nothing was made |
| `<file>: helpers.maxx is not a setting (did you mean helpers.max?); skipped`, then `stampede new: fix it or remove the key: stampede config show` (exit 2) | a config file, the environment or a `--set` holds an unknown key, a value of the wrong type, a file that is not TOML, or a user-only key in a repo's `.stampede.toml`: fix or remove what the line names, check with `stampede config show` (exit 0 when clean), then run `new` again; nothing was made |
| `stampede new: new needs --workspace or --pane, or run it inside Herdr (the setting backend is tui) ...` | your config says `backend = "tui"` and you ran `new` outside Herdr with no target: pass `--workspace <id>` or `--pane <id>`, run the printed line for Herdr Core, or drop the key |
| `on Herdr Core (backend auto: not inside a Herdr pane), repo <path>` then `stampede new: Herdr Core did not answer ...` (or `is not installed`, or `needs --cwd`) | `new` chose Herdr Core, which is not running: start it (`hc server start`), pass `--cwd <repo>` outside a git repo, or for the Herdr TUI run `new` inside a Herdr pane or pass `--workspace` or `--pane`; nothing was made |
| `stampede new: ...; Herdr Core answers here, so this job can run on it: new --core ...` | the Herdr TUI could not take the job and a Herdr Core is running: start Herdr, or run the job on Core with `--core`; nothing was made |
| `stampede new: the ask file <path> does not exist` | write what the job is for in that file, then run `new` again |
| `stampede <command>: job folder not found: <path>`, or `not a job folder, it has no lead or ask.md file: <path>` | pass the folder `stampede new` printed (`<jobs_root>/jobs/<date>-<owner>-<name>`, or `<repo>/.herdr-<name>` for an older job) |
| `stampede tell: agent <name> is not in this job (it has: ...)` | use one of the names it lists, or `lead` |
| `stampede start: brief ... is missing: ...` or `brief ... does not exist` | write the brief on the [hand-off template](skills/herdr-fleet/references/brief.md), fill every missing or empty section, then start again |
| `stampede start: fleet-job starts claude, codex or cursor ...`, or `hermes runs only as a handed agent of a Herdr Core job ...` (or kimi) | stampede starts only those kinds: in a Core job run any other CLI as a program (`stampede start <job> <name> -- <cli> ...`), or start it by hand and record it with `herdr-reopen-snapshot` |
| `stampede start: <agent> is already running in pane <pane>`, `... not as the launch this job recorded`, or `pane <pane> is handed to <agent> of <job>` | that pane runs an agent: tell it instead, or pick another pane; for a replacement the job did not start, read it with `herdr agent get <pane>`, then end it or use another name |
| `stampede start: pane ...'s shell is in ..., not ...` | `--yolo-in` needs the pane's shell in that worktree; use auto mode or `cd` the pane first |
| `refused: ... is outside ~/code` from `herdr-trust`, or `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | `herdr-trust` trusts repos only under `FLEET_TRUST_ROOT`: move the repo, create the folder, or set the key |
| `POSTED <n> to the outbox only ...: no bot or front door hears it` | a local job's post is in `<job>/outbox` and nobody is told: a bot sets `HERDR_EVENTS_OWNER=<bot>` when it runs `new`, and a chat outside Herdr starts the job with `--front-door` |
| `QUEUED <name> (...)` from `stampede start` on a Core job, and the helper never starts | the cap was full and nobody started the queue since: run `stampede next <job>` (the lead runs it on each child's note) |
| `UNKNOWN <name>: ...; run stampede next once Herdr Core answers` from `stampede next` (exit 1) | Core stopped answering after a failed start, so the request stays queued: once `hc ls` answers, run `stampede next <job>` again; it never starts a helper twice |
| a helper of a Core job cannot reach its parent after a reopen | the parent has a new address: the helper reads it with `hc get $HC_TERMINAL_ID` (its `parent`) and sends there |
| a Core job's lead is dead (a `dead` event from the watchdog, or no lead in `stampede tree <job>`) | `bash <job>/reopen.sh` (or `stampede reopen <job>`) starts it again with its session resumed, then its helpers under it |
| `... runs on Herdr Core HC_SESSION=<a>, but HC_SESSION here is <b>` | the job lives on another core: unset `HC_SESSION` (or `HC_SOCKET`), or set it to the job's, and run the command again |
| from a `--core --relay` job: `BLOCKED <lead>: <kind>` or `NOT READY <lead>: ...`, `FAILED <lead> (...): nothing of <job> runs`, `terminals of an earlier job at this path still run`, `UNKNOWN <agent>: ... Nothing was taken back`, `stampede start: <agent> is already running at <address>`, `is being started by another caller (pid <n>)`, `Cursor reports no OSC 7501 status ...`, `Kimi reports its status on Herdr Core, but stampede has no turn hook ...`, `FAILED <agent> (Herdr Core cancelled the send ...)`, `(hc send: no answer in <N> s ...)`, `GONE <agent> ... (a shell is in its place at <address> ...)`, `its program was lost and Herdr Core put a shell in its place`, `NOT RUNNING <agent> (pane <pane>): ...`, `NOT BRIEFED <agent> (pane <pane>): ...`, `Herdr did not see <kind> start in pane <pane>`, `UNKNOWN <agent>: Herdr did not show it in pane <pane> ...`, `RELAY DOWN <reason>` | each line and its recovery: [core-relay.md](skills/herdr-fleet/references/core-relay.md); never run `new` again for that folder |
| `NOT ACKNOWLEDGED <file>` from a `--relay` job's `reopen.sh` (exit 3) | the restarted lead has not read that file yet: once it is up, run the printed `echo` line |
| `stampede new: --front-door on Herdr Core is for a native job: drop --relay` (exit 2) | a `--core --relay` job has no front door: start it with `stampede new --core --front-door`; nothing was made |
| `stampede new: a Codex lead on Herdr Core gets its inbox typed into its terminal, and ...` (exit 2), or `HELD: a send to <lead> got no answer ...` in `<job>/hooks/deliver.log` | a Codex lead on a `--relay` job needs Herdr Core 0.1.20 or later with `draft_wait` at 30 or more, or use `--lead claude`. A held line most often means text sits typed in its prompt: send or clear it; if you cleared it without sending, remove `<job>/hooks/deliver-held.json` |
| `lock-not-taken` in the relay log | another relay held the de-dupe lock past 5 s, or there is no `lockf` (macOS) or `flock` (Linux, util-linux): the event still went out |
| a bot gets no events | `herdr-doctor --relay` names the broken part; see [remote/events.md](remote/events.md) |
| `stampede ask: the relay did not queue this for <bot>` | a job that bot started asks it by its own route only: add `~/.config/herdr-events/routes/<bot>` with a `URL=` (the same webhook as `default` is fine) and check with `herdr-doctor --relay`; meanwhile answer in the lead's pane |
| `UNDELIVERED gate <id> for <bot> held: route <bot> has no URL` in `inbox.log` (or `UNDELIVERED post outbox <NNN> ...`) | put the `URL=` back in `~/.config/herdr-events/routes/<bot>` and the flusher sends it within 2 minutes; do not post a held post again. After 24 h it moves to `dead/`: ask or post again |
| relay `PROBLEM` lines on a Mac without a bot | a routes folder, a relay launch agent or a relay hook is left over: finish its setup ([remote/events.md](remote/events.md)) or remove what you no longer use |
| `stampede needs Python 3.9 or later (this is <version>)` | put a newer `python3` first on PATH: stampede runs the first one there |
| `PROBLEM not on PATH: ...` from `stampede doctor` | run this checkout's `install.sh` and put `~/.local/bin` first on PATH |
| `PROBLEM on PATH from another checkout: ...` from `stampede doctor`, or `skip ...: something else is there; left as is` from `install.sh` | an older copy or a link into another checkout is in the way: run this checkout's `install.sh --replace`, which backs each one up first and prints its `rollback.sh` ([Install](#install)), and put `~/.local/bin` first on PATH |
| `PROBLEM` from `stampede doctor` or `herdr-doctor` | the line names the broken part and its fix. A backend's gaps are a `warn` while the other one is usable; `--tui` or `--core` checks one strictly; the relay's checks run when it is installed, or with `--relay` |
| `PROBLEM herdr <version> is older than 0.9.4` or `herdr --version printed no version` | upgrade Herdr, then the owner restarts the server |
| `PROBLEM herdr server not running` (a `warn` while Herdr Core is usable) | start Herdr (run `herdr` in a terminal), then run `herdr-doctor` again |
| `PROBLEM Herdr Core not running` from `herdr-doctor --core` | start the core yourself (`hc server start`), then check again; the doctor and stampede never start one |
| `PROBLEM no usable backend` | neither the Herdr TUI nor Herdr Core can run a job: fix the lines above it for one of them |
| `PROBLEM` lines for stampede on PATH, linked skills or the relay's timers from `herdr-doctor --core` in a checkout that is not installed | expected until `install.sh` runs; the Core checks are the `ok hc`, `ok Herdr Core answers`, `ok claude` and `ok codex` lines |
| `warn hc <version> is older than 0.1.20` | `hc update`; then reopen each open Core job's terminals once (end each, then `bash <job>/reopen.sh`), since terminals opened before the update keep the old behaviour |
| `warn <N> terminal(s) were opened before the Herdr Core bundle here was installed` (macOS) | those terminals keep their old holder (local network and microphone access, and later fixes): reopen each once, a job's with its `reopen.sh` |
| `warn Herdr Core was started from inside an agent or a pane` | every new terminal inherits that environment: from a terminal outside Herdr, run `hc server restart --fresh` yourself (running programs keep running) |
| `PROBLEM event loop not running` or `systemd ... not enabled` from `herdr-doctor --relay` | on Linux, re-run `install.sh`; on macOS, load the launchd jobs in [watchdogs](remote/watchdogs.md) |
| on Linux the systemd timers stop when you log out, or the flock loop is gone after a reboot | on a machine nobody logs in to, run `loginctl enable-linger $USER` once; after a reboot, run `install.sh` again for the flock loop ([watchdogs](remote/watchdogs.md)) |
| `PROBLEM ... not in the plugin checkout ...`, or `stampede: command not found` after a Herdr restart | the links point at an old plugin checkout, which Herdr deletes at its next start: rerun the current checkout's installer ([docs/SETUP.md, Update](docs/SETUP.md#update)) |
| `stampede` still works after `herdr plugin uninstall stampede` | Herdr keeps its checkout until its server next starts and never removes the links: [docs/SETUP.md, Uninstall](docs/SETUP.md#uninstall) |
| `refused: ... has local changes or untracked files`, `... is on <branch>, not main` or `... the update adds <path>, already in ...` from `stampede update` | commit, stash or move the files it names, or `git switch main`, then rerun; it never overwrites a file of yours |
| no update line, though a release is out | the check runs at most once a day and is silent offline: delete `~/.cache/stampede/latest-release` to check now, and see that `STAMPEDE_NO_UPDATE_CHECK` is not `1` |

Every known failure with its fix: [failure-modes.md](skills/herdr-fleet/references/failure-modes.md) (at a start) and [failure-modes-run.md](skills/herdr-fleet/references/failure-modes-run.md) (while running, in git, at close). Error format and examples: [docs/CLI.md](docs/CLI.md#errors). Startup dialogs: [unattended-setup.md](skills/herdr-fleet/references/unattended-setup.md). Setup problems: [docs/SETUP.md](docs/SETUP.md#setup-problems).

**FAQ**
- *Do I need stampede for this?* Only for a big job: hours long, more than one agent family, anything that leaves the machine (merge, push, send, spend, publish, deploy), or work that must survive a restart. A small job runs as one agent session with its built-in subagents, still inside Herdr in a single tagged pane of its own, so its finish arrives as an event. That is also the answer to "why not subagents": for small jobs, use them. The rule: [Size the job first](skills/herdr-fleet/SKILL.md#size-the-job-first-small-or-big).
- *Why two names?* `stampede` is the public name of `fleet-job`, its first name; both run the same command.
- *Can Codex or Cursor lead?* Codex can, on the Herdr TUI and on Herdr Core: `stampede new --lead codex` ([Pick the lead](#use-one-job-start-to-finish)). Cursor not yet ([roadmap](#status-and-roadmap)).
- *Can workers run on Gemini, Kimi or the other agents Herdr knows?* In a Core job any CLI runs as a program (`stampede start <job> <name> -- <cli> ...`); Hermes and Kimi are handed to Herdr TUI panes in a `--core --relay` job; as first-class kinds, not yet ([roadmap](#status-and-roadmap)).
- *Can a job run without the Herdr TUI?* Yes, on Herdr Core ([Herdr Core](#herdr-core)).

## Reference

<details>
<summary><b><code>stampede</code> commands and exit codes</b></summary>

Every command with its flags, the status words it prints (`STARTED`, `QUEUED`, `DELIVERED`, `SUBMITTED`, `BLOCKED`, `APPROVED`, `TIMEOUT`, `LEAD_GONE` and the rest) and one table of exit codes: [docs/CLI.md](docs/CLI.md).

Every command an agent runs takes `--json` and prints one JSON object instead (`ok`, `command`, `status` and the facts the line names, or `error` and `retry` for a refusal), with the same exit code: [docs/CLI-JSON.md](docs/CLI-JSON.md).

The command lists itself too: `stampede --help`, and `stampede <command> --help` for each one's flags and an example. `stampede` and `fleet-job` are the same command ([fleet_job.py](skills/herdr-fleet/scripts/fleet_job.py), the entry; the [stampede package](skills/herdr-fleet/scripts/stampede/) holds the commands, `stampede merge` and the hidden `stampede prepush` among them). In short: 0 done, 1 Herdr, Herdr Core or a program failed (or `doctor` found a `PROBLEM`), 2 a usage error or a refusal with its reason on one line, 3 `tell` queued behind a question card or `wait` timed out.
</details>

<details>
<summary><b>Helper scripts</b></summary>

In [skills/grokbot-herdr/scripts/](skills/grokbot-herdr/scripts/):

| script | does | exit |
|---|---|---|
| `herdr-trust <dir>` | pre-trusts a repo for Claude and Codex | 0, or 2 refused |
| `herdr-send <agent> <text>` | prompts an agent and confirms it started: `SUBMITTED` or `FAILED`; refuses a pane you have focused before any key | 0, 1 failed, 2 usage |
| `herdr-reopen-snapshot <ws> <job dir>` | reads the live workspace (read only) and writes `REOPEN.md` and `reopen.sh` in the job folder: the tabs holding the job's agents (from `agents.tsv`), never another's agent. Given a `--relay` job's `<hc-key>`, it writes that job's record from `agents.tsv` and `core.json` | 0, or 1 with the reason |
| `<job>/reopen.sh` | recreates the workspace and resumes each agent's session; `--fresh` new sessions, `--prompt` re-sends the briefs, `--into <ws>` adds to an open workspace | 0, 2 a workspace with that label is open, 3 a pane's folder is gone, 4 a tab did not open, 5 the new workspace could not be tagged for its bot, 64 usage |
| `<job>/reopen.sh` (a Core job) | the same as `stampede reopen <job>`: brings back what is not live from `tree.json`, parents first, under the cap | as `stampede reopen` |
| `<job>/reopen.sh` (a `--relay` job) | starts only what is not live, each once: the follower, the lead, then each worker; `--lead`, `--prompt` and `--fresh` as in [core-relay.md](skills/herdr-fleet/references/core-relay.md#reopen) | 0, 1 a restart was not `STARTED`, 2 another caller is starting one or a folder is gone, 3 the lead did not acknowledge a file |
| `herdr-doctor [--relay] [--tui\|--core]` | read-only health check: `ok`, `warn`, `PROBLEM` lines; `-h` prints usage. It checks the stampede install and each backend that is installed (the Herdr TUI when `herdr` is on PATH, Herdr Core when `hc` is); one usable backend is enough, and `ok backend tui,core` (or `tui`, or `core`) names where a job can run. `--tui` or `--core` checks that one only, each gap a `PROBLEM`. The event relay is checked when installed, or with `--relay`. It never starts a core | 0 ok, 1 a PROBLEM, 2 usage |
| `herdr-events-owner <ws> [<bot>\|--clear]` | tags a workspace, or an open Herdr Core job's key `hc-<12 hex>`, with the bot its events go to; `-h` prints usage | 0, or 2 refused |
| `herdr-event-sweep` | run by the watchdog timer every 5 minutes: one look at the lead of each open Core job, and one `source` `hc` event per episode (`blocked`, `error`, `stale`, `dead`) ([remote/events-core.md](remote/events-core.md#a-core-native-job-the-sweep)). `--alive` asks the selected core's socket for `hello`, never starting one; `--core-version` prints the running core's version; `--socket` prints its path | 0; `--alive` and `--core-version`: 0 up, 1 down; 2 usage |
| `herdr-event-core <job dir>` | the follower of a `--relay` job, started by `stampede new --core --relay`: follows the job's terminals, writes their lines to the lead's inbox and posts `source` `hc` events for the bot ([remote/events-core.md](remote/events-core.md)) | 0 the job finished or never started, 1 relay down, 2 usage |
| `herdr-event-post`, `herdr-event-flush`, `herdr-event-watchdog`, `herdr-event-claude-hook`, `herdr-event-codex-notify` | the event relay to a bot, with every exit code: [remote/events.md](remote/events.md). While a job marker is present, a plain turn end in that workspace is not sent | 0; `herdr-event-post --strict`: 3 no route of its own, 4 not queued, 6 a malformed `workspace`; 5 a follower's event not queued |
</details>

<details>
<summary><b>Repo layout</b></summary>

```text
README.md  CHANGELOG.md  CONTRIBUTING.md  RELEASING.md  SECURITY.md  LICENSE  VERSION
AGENTS.md  CLAUDE.md  SKILL.md  USING.md  config.example  install.sh  herdr-plugin.toml
.github/                issue and pull request templates, workflows/ci.yml (macOS and Linux CI)
skills/herdr-fleet/     the job: SKILL.md, references/ (core.md: a Core job; core-relay.md: the --relay path),
                        scripts/fleet-job, fleet_job.py (the entry), fleet-watch.sh, and scripts/stampede/,
                        the commands, one module per concern: base, job (the job folder), hcapi (Herdr Core),
                        herdrapi (Herdr), agents (per CLI), owner (questions, gates, tell, finish), hooks, tui,
                        native (a Core job), relay and handed (the --relay path), cli (the parser and help),
                        doctor and check (stampede doctor and stampede check), gates (stampede merge, the
                        pre-push hook and each job's gate record), out (--json),
                        settings (the layered config) with defaults.toml (every key and its default);
                        core_native.py re-exports native
skills/grokbot-herdr/   the bot front door: SKILL.md, scripts/ (herdr-send, herdr-trust, herdr-doctor,
                        the relay, herdr-event-sweep: the Core sweep and probes,
                        herdr-event-core: a --relay job's follower)
skills/share-plan/      the plan review, on request
skills/stampede/        the front door: "use stampede" in any chat starts a lead
scripts/stampede        the command (also linked as fleet-job); answers --version and update
scripts/stampede_update.py   the daily release check and stampede update
scripts/herdr-plugin-event   the Herdr plugin's event hook
remote/                 front-door guides
docs/                   SETUP.md, LINUX.md, RUNS.md, CLIENTS.md, CLI.md (every command), CLI-JSON.md (--json),
                        CORE-NATIVE.md (a Core job's shape), superpowers/specs/ (the design), images/
assets/                 the poster, the teaser and the demo GIF
site/                   the hero site: index.html, assets/
site/brand/             the identity assets and the brand guide
tests/                  python3 -m unittest discover tests; fake_hc.py (a fake Herdr Core),
                        fake_herdr.py (a fake Herdr TUI, for mixed jobs), core_smoke.py (CI, a real one)
                        test_clients.py and clients_run.py: the cross-client suite (docs/CLIENTS.md)
tests/evals/            the evals: cases.json, run.py, record.py, live/, linux/, runs/ (tests/evals/README.md)
```
</details>

## Docs

| doc | for |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | the full setup: installer, unattended agents, the event relay, uninstall |
| [docs/LINUX.md](docs/LINUX.md) | stampede on Linux: what was verified and how, the install, the timers, what differs from macOS, the gaps |
| [USING.md](USING.md) | the one page an agent reads first to run a job: start it, the commands that follow, the job folder, the gates |
| [SKILL.md](SKILL.md) | the skill entry point, routing each role to its skill |
| [skills/herdr-fleet](skills/herdr-fleet/SKILL.md) | the lead's playbook, with [failure modes](skills/herdr-fleet/references/failure-modes.md) [a job on Herdr Core](skills/herdr-fleet/references/core.md) and [the earlier `--core --relay` path](skills/herdr-fleet/references/core-relay.md) |
| [docs/CLI.md](docs/CLI.md) | every command: its flags, the status words it prints, and the exit codes |
| [docs/CLI-JSON.md](docs/CLI-JSON.md) | `--json`: the one object each command prints, its status values and facts |
| [docs/CORE-NATIVE.md](docs/CORE-NATIVE.md) | the shape of a Core job: the tree, labels, messages, events, the job folder and the commands, for a client that draws one |
| [remote/](remote/README.md) | one guide per front door, Moshi and the event relay |
| [docs/RUNS.md](docs/RUNS.md) | real runs, with timelines and what changed because of them |
| [docs/CLIENTS.md](docs/CLIENTS.md) | the cross-client suite: every client stampede claims reaching the same outcomes on the Herdr TUI and on Herdr Core, the matrix, the live runbook, and which client does worse |
| [tests/evals/README.md](tests/evals/README.md) | the evals: the dataset, how a run is recorded, the baseline and after runs |
| [the lean design](docs/superpowers/specs/2026-10-21-stampede-lean-design.md) | why stampede is shaped this way |
| [site/](site/README.md) | the hero site, and its [brand kit](site/brand/README.md) |
| [CHANGELOG.md](CHANGELOG.md) | what each version shipped |
| [RELEASING.md](RELEASING.md) | how a maintainer cuts a release: VERSION, the changelog, the tag, the GitHub Release |
| [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) | how to help, and how to report a security problem privately |

## Contribute

How to open an issue or a pull request: [CONTRIBUTING.md](CONTRIBUTING.md). The rules every change follows: [AGENTS.md](AGENTS.md).

- **Tests:** `stampede check` runs the fast part (shape, versions, the hc contract, layers and the pure-unit classes) in a few seconds; `stampede check --full`, or `python3 -m unittest discover tests`, runs them all (Python 3.9 or later). All run with fakes, and nothing touches a live Herdr or Herdr Core: a fake `herdr` through `HERDR`, and [tests/fake_hc.py](tests/fake_hc.py) through `HC`. A test marked as an expected failure is a part not built yet.
  - [CI](.github/workflows/ci.yml) runs them on macOS, on Linux and on Python 3.9 on every push and pull request. The macOS job then does a real install and `herdr-doctor` against Homebrew Herdr, the relay sample payloads ([test-relay.sh](skills/grokbot-herdr/scripts/test-relay.sh)), and [tests/core_smoke.py](tests/core_smoke.py) on Herdr Core 0.1.20 (checked against its pinned checksum) in a scratch `HC_SESSION`. The Linux job runs the same unit suite, relay samples and Core smoke run, and `install.sh` with the timers left off.
  - [test_native.py](tests/test_native.py) and [test_native_events.py](tests/test_native_events.py) state a Core job's contract ([docs/CORE-NATIVE.md](docs/CORE-NATIVE.md)) and the watchdog's sweep. `python3 tests/evals/live/native_fleet.py` (about 60 s; `--only tree,fanout`, `--keep`) runs a Core job's sandbox fleet test on a real Herdr Core in a scratch session of its own, with stand-in agents.
  - The `--relay` path's tests ([test_core.py](tests/test_core.py), [test_core_relay.py](tests/test_core_relay.py), and [test_mixed.py](tests/test_mixed.py) with [tests/fake_herdr.py](tests/fake_herdr.py) for handed agents) state its contract, and [test_core_releases.py](tests/test_core_releases.py) what Herdr Core 0.1.18 to 0.1.20 changed.
- **Herdr Core's API, pinned:** [tests/fixtures/hc-schema-0.1.20.json](tests/fixtures/hc-schema-0.1.20.json) is `hc schema` as that release prints it. [tests/hc_contract.py](tests/hc_contract.py) names what stampede uses of it (each `hc` command's method, parameters, error kinds and result fields, and the event types), and [tests/test_hc_contract.py](tests/test_hc_contract.py) holds the product code, the fake `hc` and the follower's decision on every event type to it.
  When Herdr Core moves on: save `hc schema` as a new fixture, point `SNAPSHOT` at it, and run the unit suite and the live eval V03, which compares the snapshot with `hc schema` on the machine.
- **The cross-client suite:** `python3 -m unittest tests.test_clients` (about 25 s) plays one job per client (a Herdr chat, Claude, Codex, Cursor, Hermes, a bot over SSH) and backend against the fakes and checks each outcome's command contract, O1 to O9, for each; the agents' own work is left to the live runs. A client is one row in `CLIENTS` in [tests/test_clients.py](tests/test_clients.py) plus one in [docs/CLIENTS.md](docs/CLIENTS.md), which also holds the live runbook and the clients that do worse; a worker kind is one entry in `WORKERS` there, which every client's job then starts.
- **The evals:** `python3 tests/evals/run.py --label <name>` runs every fixture case (about 90 s on macOS, 40 s on Linux) and records the run in `tests/evals/runs/`; the live runners (`python3 tests/evals/live/core_e2e.py --label <name>` on a real Herdr Core in a scratch session, `tests/evals/live/tui_scratch.sh --label <name>` on a real Herdr TUI in a scratch home, both with stand-in agents) and the Linux container are in [tests/evals/README.md](tests/evals/README.md). CI runs the fixture cases on macOS and on Linux.
- **This repo is the source** of the four skills and their scripts: every machine runs them from a checkout through `install.sh` (`--replace` takes over an older install). A pull request that changes `skills/` is welcome. Behaviour only some setups want is a setting with a default in [config.example](config.example), never a private edit of the code.
- **A front door:** a guide in `remote/` that writes the ask and runs `stampede new`, linked from [Front doors](#front-doors).
- **An agent CLI:** its auto and no-checks flags in `AUTO` and `YOLO`, and its hooks in `cli_args`, in [agents.py](skills/herdr-fleet/scripts/stampede/agents.py), with a test in `tests/test_fleet_job.py`. In a Core job any CLI already runs as a program (`stampede start <job> <name> -- <cli>`).
  On the `--relay` path it must also report OSC 7501 status and have a turn hook and a known empty prompt: its Core flags go in `start_core` ([relay.py](skills/herdr-fleet/scripts/stampede/relay.py)), with a test in `tests/test_core.py`; one that path does not start on Core goes in `HANDED` ([handed.py](skills/herdr-fleet/scripts/stampede/handed.py)) and in `TURNS` in `herdr-event-core`, with a test in `tests/test_mixed.py`.

## Status and roadmap

**0.2.1, 14 Nov 2026, and early:** commands and files may still change. What each release shipped, and how it was tested: [CHANGELOG.md](CHANGELOG.md). Real jobs, with timelines: [docs/RUNS.md](docs/RUNS.md).

**Works and tested.** Every command in this README was run against a scratch job with the fakes, or against `--help`.
- **A job on the Herdr TUI:** the job folder, the lead's start with its hooks, Claude, Codex and Cursor workers, complete worker briefs, plan approval, background questions and cancel, gates that go back to whoever started the job, quieter events while a job is open, a lead forked from the planning chat, a Codex lead, a front door outside Herdr, and reopen.
  - Tested with fakes. Live on macOS (21 Oct 2026): a hooked Claude lead woken by its inbox file, a Codex reviewer's turn through Codex's notify hook, a Cursor worker under auto-review, and a question on the owner's phone that did not block the lead and was cancelled cleanly. A Codex lead on Codex 0.167.1 was checked live on Linux in a Herdr 0.9.5 pane; no whole job has run live with a real Codex lead yet.
  - The lead's reply to a typed gate approval on Core has not been checked with a live agent.
- **A Core job, run the way Core works:** the tree, the cap and queue, the layout labels, `tell`, `snapshot`, `reopen`, `close`, the watchdog sweep and the native front door.
  - Tested with the fake `hc` ([test_native.py](tests/test_native.py), [test_native_events.py](tests/test_native_events.py)) and every command in [One Core job, start to finish](#one-core-job-start-to-finish).
  - Live on a real Herdr Core 0.1.21 on macOS with stand-in programs: the ten-check fleet test ([docs/RUNS.md](docs/RUNS.md#core-native-sandbox-fleet-test-13-nov-2026)). CI's real-Core smoke run covers the native part on Herdr Core 0.1.20, on macOS and Linux.
  - One job with real agents ran on it (a Claude lead with a Codex reviewer and a Claude tester as its Core children). Not run: the fleet test on Linux, and the native path or its front door from a live client.
- **The earlier `--core --relay` path:** tested with the fake `hc` and a fake `herdr`; live on real cores (`hc` 0.1.13 to 0.1.20) with a Claude lead and Claude and Codex workers, every bot route replaced by a local stand-in, and a handed Cursor on Herdr 0.9.5; later runs used stand-in agents.
  - Not run live: Kimi, the follower's `TURN` for Hermes and Kimi, a signed-in Codex as a Core lead, and the Herdr app looking at a job.
  - Not run live for a handed worker: `STALE`, `BLOCKED`, and a `tell` refused while it works or is focused.
- **Gates:** only the recorded yes opens a merge, a push to the default branch, or any gate on Core; a yes covers the gate as asked (its digest). Tested with the unit suite, the evals and the cross-client suite on every client. One documented ceiling: an agent that detaches to pid 1 as the same user can still run `approve-gate` (eval case G15).
- **Install, updating and plugin installs:** both install routes from a throwaway home (the quick start ran up to the lead's first turn, with no signed-in Claude there), `stampede update` and the daily check (a local reply file, a fake rate-limited server, scratch git repos, and once the live GitHub API), and the plugin lifecycle; the `herdr plugin` commands themselves ran only in a sandboxed test.
- **Linux:** the install, a whole TUI job and a whole Core job, live on Ubuntu 24.04 arm64 with Herdr 0.9.5, Herdr Core 0.1.19 and stand-in agents; CI runs the unit suite, the relay samples and the evals there ([docs/LINUX.md](docs/LINUX.md)). The systemd timers were checked only against a fake `systemctl`; not run on Linux: a signed-in agent, Moshi paired, a real systemd user manager, or a bot over SSH.
- **The cross-client suite:** every client drives one job per backend through the real `stampede` command against the fakes; live runs on one Mac covered a Herdr chat, Claude, Codex, Hermes and a test bot over SSH (a real Grok Bot and Cursor were not run; Claude on Core, Codex and Hermes passed all but O4, O5 and O7, which wait on the owner's tap). The matrix, and which client does worse: [docs/CLIENTS.md](docs/CLIENTS.md).
- **Posts to a bot:** in a job a bot started, `stampede post` also sends that bot a `post` event; tested with the unit tests and the cross-client suite, not yet with a live bot.
- **The evals:** the fixture cases run in CI on macOS and Linux; the live runners and the before and after runs: [tests/evals/README.md](tests/evals/README.md).
- **The command:** layered config with `stampede config show`, `--help` for every command, `stampede doctor` and `stampede check`, and `--json` on every command an agent runs (tested on all three backends, on Python 3.9 too, and on a real scratch core).
- **The site** is live at https://vib-z.github.io/stampede/ and mirrored on Vercel at https://stampede-xi.vercel.app/.

**Next:**
- On Herdr Core: Cursor, Hermes and Kimi as first-class kinds in a Core job (today they run as programs), then removing the `--core --relay` path.
- On Linux: the systemd user timers on a real user manager, x86_64 live (CI covers it with fakes and a Core smoke run), a signed-in Claude and Codex, Moshi paired, and a bot over SSH.
- A Herdr server restart: `reopen.sh` into the workspace Herdr restores, starting the agents in its plain shells, instead of asking to close it first.
- The open cross-client finding in [docs/CLIENTS.md](docs/CLIENTS.md#doing-worse): a TUI job whose bot is named by `HERDR_EVENTS_OWNER` tagging its workspace.
- On Herdr Core, planned:
  - opt-in alerts to the owner for helpers (blocked, error, stale, dead), as the watchdog sends for the lead today;
  - workers on a second machine (`hc run --on`; a job is local to one machine today);
  - a look at an `--app-space` job in the Herdr app, and a name for its space set through the app;
  - Kimi as a Core agent (Kimi 2.5.3 reports its status on Herdr Core 0.1.20) once a signed-in run shows its turns and its empty prompt;
  - Hermes and Kimi workers on a TUI-only job, and Hermes's empty prompt, so a handed one is briefed and told without a hand.
- Starting workers on the other agents Herdr detects, beyond Claude, Codex, Cursor, Hermes and Kimi.
- Workers on a second machine over Tailscale.
- Cursor as the lead, and a signed-in Codex leading a live Herdr Core job.
- ChatGPT Dots as a front door, once it can be woken by a webhook.
- Report to Herdr that the panes of a reopened workspace sent the plugin no status events in the live Linux runs (needs the owner's yes).
- Report to Herdr that Codex's "Implement this plan?" and Cursor's "Ready to build?" dialogs read as `idle` and `done`, not `blocked` (needs the owner's yes).

## Credits and license

Built on [Herdr](https://herdr.dev) and its agent automation, with [Moshi](https://getmoshi.app/docs/herdr) for the phone. A stream of many small, independent coding tasks fits [herdr-projects](https://github.com/eliasstravik/herdr-projects) better. [tests/fixtures/hc-schema-0.1.20.json](tests/fixtures/hc-schema-0.1.20.json) is the output of `hc schema` from Herdr Core 0.1.20, which names its licence as Apache-2.0; it is kept unchanged, for the tests only.

Product marks: [docs/images/logos/SOURCES.md](docs/images/logos/SOURCES.md). The brand kit, in [site/brand](site/brand/README.md) with its [visual guide](site/brand/guide.html), holds the Open gate logo, the Star link, the painterly grounds and the brand guide.

[MIT](LICENSE), copyright 2026 stampede contributors. The code licence does not grant rights to the stampede name or marks. See [site/brand/CREDITS.md](site/brand/CREDITS.md).
