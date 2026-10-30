<h1 align="center">stampede</h1>

**You text a task to your Grok Bot. It reaches your Mac over Tailscale, where a Claude Code lead does the job in [Herdr](https://herdr.dev) and adds Codex or Cursor panes only when parallel work helps. Nothing is merged, pushed, sent or spent until you say yes.**

Grok Bot is the setup we recommend, but you don't need it: stampede also runs when you start it straight from Claude, Codex or any agent ([Without a bot](#without-a-bot)). Either way you can watch every agent in Herdr, and every question comes back to you.

**Let a Grok Bot set it up.** [Stompy](https://x.ai/bot/_mNMq-0M5aA02AQMNOHTy) is a Grok Bot that sets up stampede between your Grok Bot and your Mac, end to end, and keeps it healthy.

<p align="center">
  <a href="https://github.com/vib-z/stampede/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/vib-z/stampede/actions/workflows/ci.yml/badge.svg"></a>
  <a href="CHANGELOG.md"><img alt="Version 0.1.5" src="https://img.shields.io/badge/version-0.1.5-black"></a>
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
- **Your yes on every merge, push, send, spend or close.** The gate question goes back to whoever started the job, and a yes typed in a Herdr pane works too (on Herdr Core only the recorded yes counts). The lead keeps working while it waits.

## Quick start

On a Mac with [Herdr](https://herdr.dev/docs/install/) 0.9.4 or later, Claude Code signed in, Python 3.9 or later, git, jq and curl:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
export PATH="$HOME/.local/bin:$PATH"   # add this line to your shell profile too
herdr-doctor                           # exit 0, with Herdr running
```

**Your first ask.** Once per Mac, run the [unattended setup](skills/herdr-fleet/references/unattended-setup.md), so the lead can start workers with no visit to their panes. Run `herdr-trust ~/code/my-app` once for your repo, open it in Herdr, start Claude in a pane, and type:

> With stampede: add a /health endpoint with a test, have a reviewer on another model check it, then open a draft PR.

**Then from your phone (recommended).** Set up Grok Bot's SSH, Tailscale and webhook once ([remote/grokbot/](remote/grokbot/README.md)), and send the same ask in chat.

**On Herdr Core instead of the Herdr TUI.** With [Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later) installed and running, run `herdr-doctor --core`, then ask *"With stampede, on Herdr Core: ..."*. The front door runs `stampede new --core`, and each agent runs in a Core terminal of its own ([Herdr Core](#herdr-core)).

**Limits.**
- macOS only. No Linux run has been tried.
- The lead is Claude (any Claude model, set by `FLEET_LEAD_MODEL`). Workers can be Claude, Codex or Cursor (on Herdr Core, Claude or Codex).
- Version 0.1.x, and early: commands and files may still change.
- For big jobs. A small job runs as one agent session in a single tagged Herdr pane ([FAQ](#troubleshoot)).

The full install, with every prerequisite: [Install](#install). A whole job, command by command: [the walkthrough](#use-one-job-start-to-finish).

## What is stampede?

stampede is multi-agent orchestration for Claude Code and Codex in Herdr: four skills and one command, installed by script or as a Herdr plugin. You ask once, in plain words: in a Claude pane in Herdr, from Claude or Codex desktop or Cursor, or, as we recommend, from your phone through Grok Bot. stampede starts **one lead agent** for the job. The lead writes a short plan and starts working at once. It brings in Codex workers, or Claude Code or Cursor ones, each in its own Herdr pane, only when that agent earns its place: work that runs in parallel, a different model, one reviewer, or the same task many times over. Workers report through hooks, so nobody polls. Gate questions come back to wherever you asked, and nothing that matters happens without your own yes.

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

**Agents.** The lead runs on Claude Code. Workers run on Claude Code, Codex or Cursor, each started by `stampede start --kind claude|codex|cursor` with its own hooks and auto mode.

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
      <b>Codex</b><br><sub>workers and reviewers</sub>
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

Herdr itself detects many more agent CLIs (its `herdr agent start --help` lists 24, from Gemini and Kimi to OpenCode and Copilot). That is Herdr's support, not stampede's yet: `stampede start` refuses any other kind, and starting workers on them is [planned](#status-and-roadmap). The marks belong to their owners and imply no endorsement ([sources](docs/images/logos/SOURCES.md)).

## Works well with

**[pstack](https://github.com/michael-denyer/pstack-claude), optional.** For coding jobs, the lead picks up pstack if you have it: data shape first, a contract commit, proof on the real surface. The lead is a normal Claude Code session, so an installed pstack loads on its own, and stampede's rules keep pstack's fan-out as Herdr panes you can watch. Not required: without it nothing changes. The rules: [references/pstack.md](skills/herdr-fleet/references/pstack.md).

## See it

![The build tab of a fleet in Herdr: four panes side by side. build-steps-plan and build-steps-run are Claude Code agents that have just finished; build-scripts and build-app are Codex agents still working.](docs/images/fleet-build-tab.png)

<sub>Real, drawn: the <code>build</code> tab of the fleet that built stampede's first version, drawn from each pane's own screen text (<code>herdr agent read</code>), personal paths replaced with <code>~</code>, 18 Oct 2026. A lean job opens fewer panes; each looks the same.</sub>

## How it works

The flow is the [diagram at the top](#how-it-flows), step by step, for any front door:

1. **You ask once**, in plain words, in a [front door](#front-doors). It writes the ask to a file, runs `stampede new --file <ask.md>`, tells you the lead's name, and steps back.
2. **One lead plans and goes.** `lead-<slug>` starts on Claude (Opus 5.5 at `xhigh` effort by default) in auto mode, in a `lead` tab. It writes `plan.md` (the tasks, who does each, questions with a safe default, and the gates) and starts work.
3. **A pane only when it's worth it:** parallel pieces of about 30 minutes or more (at most 4), another model or tool, one reviewer on another model, or the same task many times (6 at once). Each worker gets its own Herdr pane.
4. **Hooks, not polling.** A worker's report, turn end, question or exit lands as a line in `<job>/inbox.log` (`REPORT`, `TURN`, `QUESTION`, `GONE`, and `UNDELIVERED` for a question or gate its bot has not heard), and Claude's file hook wakes the lead.
5. **Review only what ships**, on another model, at most two rounds.
6. **Questions and gates go back to whoever started the job**: a bot gets a `question` or `gate` event, asks you in chat and passes your answer back (a gate's yes recorded with `approve-gate`); a job you started locally asks on your phone through Moshi. A yes typed in the lead's pane always works. The lead keeps working while it waits, and an agent's own say-so never counts.
7. **The lead reports back once.** When the job is done or stopped for good it runs `stampede finish <job> "<summary>"`. That is the one done event a bot outside Herdr gets for the job. While the job is open, plain turn ends in its workspace stay on the machine. Blocked, permission prompts, StopFailure, a stale or dead pane, questions and gates still go out. Then the lead asks whether to close.
8. **Workers exit when their work is merged** or accepted. Nothing closes without your yes, and `reopen.sh` brings a closed job back.

**Stateful lead, stateless workers.** The lead holds your ask, the plan, the decisions and the judgement. A worker gets one brief and nothing else, so that brief carries the state: Goal, Why, Inputs, Constraints, Done when, Report back and If blocked, on the [hand-off template](skills/herdr-fleet/references/brief.md). A thin brief is the usual cause of weak worker output. `stampede start` refuses a worker brief with a missing or empty section before starting anything. Pick a strong planner for the lead and a fast, capable executor for workers; both are [settings](#configure), not code.

**What lives where.** Your Mac, always on, runs Herdr, the lead and the workers. A bot such as Grok Bot runs on its own computer and reaches the Mac over SSH and Tailscale. Or the whole thing runs on one remote computer. Either way, the lead and its workers share one machine; workers on a second machine are [planned](#status-and-roadmap).

**On Herdr Core** the same flow runs in Core terminals instead of panes: the brief pointer is each agent's first prompt, `tell` prompts Codex with `hc send` by its status, and the job's follower, `herdr-event-core`, adds `BLOCKED`, `ERROR`, `GONE`, `WAITED`, `LOST`, `STALE` and `RELAY DOWN` lines to `inbox.log` and posts `source` `hc` events for a bot ([Herdr Core](#herdr-core)).

<details>
<summary><b>The job folder</b></summary>

`stampede new` makes `<repo>/.herdr-<slug>/`, kept out of git through `.git/info/exclude`:

```text
ask.md        your ask, word for word
lead          the lead's name
plan.md       the lead's plan
briefs/       the generated lead brief, then worker briefs on the hand-off template
hooks/        each agent's hook settings and wake state
inbox.log     REPORT, TURN, QUESTION, GONE and UNDELIVERED lines that wake the lead
inbox/        messages to each agent, one file per agent
questions/    a worker's questions, as files for the lead
asks/         questions out to your phone, while they wait
owner         the bot that started the job, when one did: its gates go back to it
workspace     the Herdr workspace id, or a Herdr Core job's key hc-<12 hex>; while the job is open,
              ~/.config/herdr-events/jobs/<id> names this job
backend       core, for a Herdr Core job (no file: the Herdr TUI)
endpoint      the Herdr Core a Core job was made on (HC_SESSION, HC_SOCKET);
              every later command uses it
core.json     a Core job's terminals: state, address, name, role, cwd per agent,
              and whether each Claude session ran
locks/        a Core job's launch locks, one per agent
relay-state.json   what a Core job's follower saw and sent
start-failed  why a Core job's start never ran
reopen-pending  a restarted Core lead that has not acknowledged both inbox files yet
finished      the one-line summary written by stampede finish
gates/        each gate asked (action, PR, commit) and your recorded yes
agents.tsv    who was started, and how: the reopen record
approved      the plan's fingerprint, for a --review job
REOPEN.md, reopen.sh   written by herdr-reopen-snapshot before a close (a Core job: at every start)
```
</details>

## Install

**Prerequisites** (tested on macOS 27.2, 21 Oct 2026):

| tool | version tested | needed for |
|---|---|---|
| [Herdr](https://herdr.dev/docs/install/) | 0.9.4 (the plugin needs 0.9.4 or later) | the panes |
| [Herdr Core](https://herdr.dev/core/) `hc` | 0.1.13 | a job on Herdr Core, optional; a live test also ran on 0.1.14 |
| [Claude Code](https://code.claude.com/docs/en/setup) | 2.1.306 (2.1.295 or later on Herdr Core, for its status) | the lead, and workers |
| [Codex CLI](https://developers.openai.com/codex/cli) | 0.163.0 (0.165.0 checked for `--no-daemon` on Herdr Core) | workers, optional |
| [Cursor Agent](https://cursor.com/docs/cli/installation) | 2026.10.19 | workers, optional |
| Python 3, git, jq, curl | Python 3.9 (the tests need 3.11), git 2.56, jq 1.7 | the scripts |
| [Moshi](https://getmoshi.app/docs/herdr) `moshi-hook` | 0.4.33 | questions on your phone, optional |
| [Tailscale](https://tailscale.com/kb/1017/install) | 1.104.1 | a bot on another computer, optional |

**Step by step**, on a Mac with Herdr, Claude Code (signed in), Python 3 and git:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
cd ~/stampede
./install.sh --dry-run               # prints each link it would make, changes nothing
./install.sh                         # links the skills and the commands
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
stampede --version                   # 0.1.5
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

**Or as a Herdr plugin**, where Herdr keeps the checkout and runs the same `install.sh`, plus the event hook:

```bash
herdr plugin install vib-z/stampede  # shows a preview and asks y/N; add --yes over SSH or from a bot
export PATH="$HOME/.local/bin:$PATH" # add this line to your shell profile too
herdr-doctor                         # Herdr hides the installer's output; exit 0 on a clean install, with Herdr running
herdr-trust ~/code/my-app            # once per repo, before agents start there
```

Then open your repo in Herdr, start Claude in a pane, and ask: *"With stampede: ..."*. The [walkthrough](#use-one-job-start-to-finish) shows a whole job.

`install.sh` links the four skills into `~/.claude/skills/` and `~/.codex/skills/` (each only when `~/.claude` or `~/.codex` exists), and links `stampede`, `fleet-job` and the `herdr-*` helpers into `~/.local/bin`. It is safe to re-run (`ok` for a link already in place) and never replaces anything already there (`skip ... left as is`), except, in a Herdr plugin install, its own link to the same file in an older checkout of that same install, which it moves to the new one (`relinked`). A clone relinks nothing. `herdr-trust` marks a repo trusted for Claude, and for Codex when `~/.codex` exists, so agents start without the folder-trust dialog; it refuses a repo outside `FLEET_TRUST_ROOT` (default `~/code`), so keep your repos there or set the key.

**Then, once:** the settings that let agents start and run without a visit to their pane, which you run yourself: [unattended-setup.md](skills/herdr-fleet/references/unattended-setup.md). A remote bot also needs the event relay. Both: [docs/SETUP.md](docs/SETUP.md). To uninstall: [docs/SETUP.md, Uninstall](docs/SETUP.md#uninstall).

**Linux:** the lead, `stampede` and `herdr-trust` use only Python and git, but the event relay scripts use macOS tools (`launchd`, BSD `stat`, `md5`), and no Linux run has been tried.

## Updating

Once a day stampede tells you when a newer release is out; it never updates anything by itself. Then you update:

| installed with | update with |
|---|---|
| a clone and `./install.sh` | `stampede update` |
| `herdr plugin install vib-z/stampede` | `herdr plugin update stampede` (add `--yes` from a bot, a script or SSH) |

**The daily check.** At most once a day, `stampede --version`, `stampede update --check` and `herdr-doctor` ask GitHub for the latest release: one request without a token, given 3 s in all (DNS, connect and the reply), the answer cached for 24 h in `${XDG_CACHE_HOME:-~/.cache}/stampede/`. When a newer release is out they print one line:

```text
$ stampede --version
0.1.0
stampede 0.2.0 is out, this is 0.1.0: run stampede update
```

In a plugin install the line ends `run herdr plugin update stampede --yes`. `stampede --version` puts that line on stderr, after the version, and still exits 0; `herdr-doctor` prints it as a `warn` line, never a `PROBLEM`. Offline, rate-limited, a malformed reply or any other failure prints nothing and is cached too, so the next try is a day later. Turn the check off with `export STAMPEDE_NO_UPDATE_CHECK=1` in your shell profile or `~/.config/stampede/config` ([Configure](#configure)). To hear of a release on GitHub instead: on the repo page, **Watch**, then **Custom**, then **Releases**. How a release is cut: [RELEASING.md](RELEASING.md).

**`stampede update`** is the guided updater: it updates only a clean checkout on `main`, and never overwrites a file of yours. It runs `git fetch`, fast-forwards with `git merge --ff-only`, reruns `./install.sh` (which links any new skill or command), and ends with `stampede 0.1.0 -> 0.2.0`. It refuses with the reason, and changes no file, when the checkout has local changes or untracked files, is on another branch, or holds an ignored file at a path the update adds, which git would overwrite (`refused: the update adds local-settings.txt, already in <checkout> (ignored by git, so it would be overwritten): move it away, then rerun`). In a Herdr plugin install it changes nothing and prints `herdr plugin update stampede --yes` to run instead, though Herdr's checkout holds a `.git`.

**A plugin update moves the links.** Herdr gives each plugin install or update a new checkout folder and deletes the old one the next time its server starts. The installer it runs moves each stampede link that points at the same file in an older checkout of that same install to the new one, and leaves any other link alone (another plugin's, a backup's, one of yours); `herdr-doctor` reports a `PROBLEM` if `stampede` or a skill still resolves outside the checkout Herdr reports.

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
recorded lead-make-hello-txt-with-hi (claude) in <repo>/.herdr-make-hello-txt-with-hi/agents.tsv
DELIVERED lead-make-hello-txt-with-hi (inbox file)
lead-make-hello-txt-with-hi <repo>/.herdr-make-hello-txt-with-hi
```

Inside Herdr, `--workspace` defaults to the current workspace and the lead gets a new `lead` tab; `--pane <id>` puts it in an empty pane instead, and `--name <slug>` names the job. A front door outside Herdr (a bot, a desktop app) has no current workspace, so it passes `--workspace` or `--pane`: it creates a workspace for the job (`herdr workspace create`) and passes its root pane, as in [skills/stampede](skills/stampede/SKILL.md). The chat tells you `lead-make-hello-txt-with-hi` and stops.

**Plan in chat, then fork it into the lead.** A Claude chat where you and Claude already worked out the plan, in Herdr or the Claude desktop app, adds `--fork "$CLAUDE_CODE_SESSION_ID"`: the lead starts as a fork of that chat (`claude --resume <id> --fork-session`), so it keeps the whole conversation and writes the agreed plan into `plan.md` instead of planning again. Your chat stays as it was. Put the agreed plan in the ask file too: it stays the source of truth, since a chat's saved transcript can miss some of its messages. The reopen record leaves the fork out, so `reopen.sh` resumes the lead's own session. Guide: [remote/claude-code.md](remote/claude-code.md#plan-here-then-fork-the-lead).

The lead reads `ask.md`, writes `plan.md` and goes on at once. Here it writes `briefs/review-hello.md` on the [hand-off template](skills/herdr-fleet/references/brief.md), then starts one reviewer on another model:

```console
$ stampede start .herdr-make-hello-txt-with-hi review-hello --kind claude --pane <pane id> \
    --brief .herdr-make-hello-txt-with-hi/briefs/review-hello.md \
    --model <another model> --effort max --report reports/review-hello.md
recorded review-hello (claude) in .herdr-make-hello-txt-with-hi/agents.tsv
DELIVERED review-hello (inbox file)
```

When the reviewer writes `reports/review-hello.md` with `Status: PASS` in its first 10 lines and ends its turn, its hook adds `REPORT reports/review-hello.md` to `inbox.log`, which wakes the lead. A question for you, with the lead still working:

```console
$ stampede ask .herdr-make-hello-txt-with-hi "Keep the file in the repo root?" \
    --option Yes --option No
ASKED 1fecfa0be4dc (the answer goes to the lead inbox; cancel with: fleet-job cancel <job> 1fecfa0be4dc)
```

Your tap comes back as `ANSWER ...` in the lead's inbox. A gate (say, merging the draft PR) goes back to whoever started the job ([Safety](#safety)); you started this one in Herdr, so it is the lead's own question card or `stampede ask --gate`, on your phone. Then the lead writes a short report and asks whether to close the workspace; `<job>/reopen.sh` brings it back later.

### Share the plan first

Say "share the plan first" and the front door adds `--review`. The lead then writes `plan.md` and ends its turn, and no pane can open until you approve that exact plan:

```console
$ stampede new --file ask.md --name hello-review --review
recorded lead-hello-review (claude) in <repo>/.herdr-hello-review/agents.tsv
DELIVERED lead-hello-review (inbox file)
lead-hello-review <repo>/.herdr-hello-review
$ stampede start .herdr-hello-review review-hello --kind codex \
    --pane <pane id> --brief <brief>
fleet-job start: the owner asked to see this plan: run fleet-job approve after their yes, and again after any change to the plan
$ stampede approve .herdr-hello-review --by "owner in chat"
DELIVERED lead-hello-review (inbox file)
$ cat .herdr-hello-review/approved
Approved: 2026-10-21 21:35 by owner in chat, plan 6ef5e2effdb06d6adf70e17da8726c05dd2d057a4a7ba23c4fbe3836eed14ffa
```

The `start` refusal exits 2. The approval holds a fingerprint of `plan.md`; any later change locks `start` again until a new approve. A change you ask for goes to the lead with `stampede tell <job> lead "<your words>"`. The steps: [share-plan](skills/share-plan/SKILL.md).

## Herdr Core

[Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later) is Herdr's terminal runtime: programs in persistent terminals that report their own status (OSC 7501), with labels and an event stream, and no workspaces, tabs or panes. `stampede new --core` runs a whole job there instead of on the Herdr TUI. One job is all Core or all TUI; every TUI job and command works as before. Install this version (`install.sh`, or `stampede update`) before a Core job: the lead runs the installed `fleet-job`, and the CLIs' relay hooks run from `~/.local/bin`. An older copy can end a job without the stamp its follower waits for, and post plain turn ends to the default route.

What changes on Core, in short: each agent is its own terminal with no parent, so a worker never ends with the lead; its brief goes in with its start; its start, prompt and wake come from its own status, not its screen; one follower per job, `herdr-event-core`, reports every worker's block, error and exit to the lead (a hard kill included) and to a bot; a job outlives every window and comes back with `reopen.sh`; and only a recorded yes passes a gate. Cursor stays on the TUI (it reports no status). The lead's playbook: [references/core.md](skills/herdr-fleet/references/core.md).

Check the machine once (this ran against a Mac's running core), then start the job from the repo (the job commands here ran against the test suite's fake `hc`, which answers as a real core does):

```console
$ herdr-doctor --core
...
ok hc 0.1.13
ok Herdr Core answers (HC_SESSION default)
ok claude 2.1.312 reports its status (OSC 7501)
ok codex runs with --no-daemon
warn cursor-agent runs on the TUI only for stampede: it reports no OSC 7501 status on Herdr Core
...
$ stampede new --core --file ask.md --cwd ~/code/my-app
STARTED lead-add-health-endpoint-with (t2)
lead-add-health-endpoint-with <repo>/.herdr-add-health-endpoint-with
```

It wrote the job record first (`backend`, the key `hc-a941d115ee38` in `workspace`, `core.json`), then started the follower (`t1`) and the lead (`t2`), each labelled `stampede.job=<key>`. The lead starts a worker with `--cwd` (default: the repo) instead of `--pane`, and talks to it by its status:

```console
$ stampede start .herdr-add-health-endpoint-with review-health --kind codex \
    --brief .herdr-add-health-endpoint-with/briefs/review-health.md --report reports/review-health.md
STARTED review-health (t3)
$ stampede tell .herdr-add-health-endpoint-with review-health "Check the error path too"
SUBMITTED review-health (t3)
$ stampede tell .herdr-add-health-endpoint-with review-health "One more thing"
FAILED review-health (working: tell it after its turn)
$ stampede start .herdr-add-health-endpoint-with review-health --kind codex --brief <brief>
fleet-job start: review-health is already running at t3
```

The two `FAILED` and `already running` lines exit 2. When part of the job is gone (a reboot, a lost holder, the follower down), `reopen.sh` starts only what is missing:

```console
$ bash .herdr-add-health-endpoint-with/reopen.sh --lead
RESTARTED relay-a941d115ee38 (t4)
$ bash .herdr-add-health-endpoint-with/reopen.sh
LIVE hc-a941d115ee38: no agent to restart
```

A lead that needs CI runs the wait as a labelled terminal, `hc run --bg --no-parent --no-notify --name wait-ci-<pr> --label stampede.job=<key> --label stampede.role=wait -- gh pr checks <pr> --watch`, and wakes on `WAITED wait-ci-<pr> exit <code>`. `stampede finish` ends the job as on the TUI, and the follower exits with it.

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

Any of them can run the job on Herdr Core instead: it passes `--core --cwd <repo>` in place of `--pane` or `--workspace` ([Herdr Core](#herdr-core)).

Moshi, the phone side of every front door: [remote/moshi.md](remote/moshi.md).

## Safety

- **Your own yes, every time:** a merge to main, a push to main or another shared branch, a deploy, publishing, sending email or messages, any spend, and closing panes, tabs or a workspace. Pushing the job's own work branch and opening a draft PR need no ask.
- **Gates go back to whoever started the job.** `stampede new` records the bot that started it (`HERDR_EVENTS_OWNER`, else the workspace's owner tag) in `<job>/owner`. The lead asks each gate with `stampede ask <job> --gate --sha <commit> [--pr <n>] "<the exact action>"`:
  - **started by a bot:** a `gate` event goes to that bot ([remote/events.md](remote/events.md)). The bot asks you in chat and, on your yes, runs `stampede approve-gate <job> <gate> --sha <commit> --by "owner in <bot> chat"` over SSH, which records it in `<job>/gates/`.
  - **started locally:** your phone, through `FLEET_ASK_CMD` (Moshi), records your tap the same way; or the lead's own question card.
  - **either way, on the Herdr TUI,** a yes typed in the lead's Herdr pane works.
- **The lead acts on your yes typed in its pane for that exact action (Herdr TUI only), or on a recorded yes for one gate at one commit:** `stampede gate-ok <job> <gate> --sha <the commit it acts on>` prints `APPROVED` only when the record names that gate and that commit. A merge also passes `--match-head-commit` on that commit, so a push after your yes means asking again. `approve-gate` refuses inside Herdr, for a job started locally and for another commit: an agent's own say-so never counts, and nor does a plan, a brief or a yes passed on in a message.
- **On Herdr Core only the recorded yes counts.** In a job started with `stampede new --core` the lead acts only after `gate-ok` prints `APPROVED`: a yes typed into the lead, an answer to its own question card, and any message never count, because on Core another program can type into any terminal (`hc send`, `hc keys`). Your tap on a phone card (`FLEET_ASK_CMD`) and a bot's `approve-gate` are recorded and count. `approve-gate` also refuses inside a Herdr Core terminal (`HC_TERMINAL_ID`, `HC_TERMINAL_SOCKET` or `HC_SCOPE` set) and under a `herdr-core` or `hc` process, so `hc exec` cannot run it: a bot runs it over plain ssh. Core's own `blocked` state is never a gate.
- **Auto mode, never no-checks mode, by default:** Claude `--permission-mode auto`, Codex `--approve-for-me`, Cursor `--auto-review`. `stampede start --yolo-in <worktree>` runs a worker in its CLI's no-checks mode only when its pane's shell sits in its own linked git worktree, and never the lead.
- **Plan approval** (only when you asked to see the plan) lets the lead work inside the job's own folder and branch; it is not a gate and covers no merge or spend.
- **Nothing closes by itself.** The last step is always the question whether to close; no answer is a no.
- **Never touched:** panes, tabs and workspaces the lead did not create; the pane you have focused; credentials and `.env` files.

## Configure

Every key is an environment variable with a default; nothing needs setting. To change one, copy [config.example](config.example) to `~/.config/stampede/config`, edit it, and source it from your shell profile (`. ~/.config/stampede/config`). The Herdr plugin event reads the same file.

<details>
<summary><b>Every key, with its default</b></summary>

| key | default | what it does |
|---|---|---|
| `FLEET_LEAD_MODEL` | Claude Opus 5.5 (its id is in config.example) | the lead's Claude model; worker models and effort are chosen per start with `--model` and `--effort`, so lead and workers swap independently |
| `FLEET_LEAD_EFFORT` | `xhigh` | the lead's effort |
| `FLEET_ASK_CMD` | `moshi-hook ask --require-remote --source herdr-fleet --timeout 24h` | what `stampede ask` runs, for a question or a gate, in a job started locally (a bot-started job asks its bot); the options and question are appended |
| `FLEET_TRUST_ROOT` | `~/code` | `herdr-trust` trusts repos only under it; `herdr-doctor` checks worktrees there |
| `FLEET_WATCH_INTERVAL` | `30` | seconds between `fleet-watch.sh` passes (a bot outside Herdr) |
| `FLEET_WATCH_PASSES` | `0` | stop the watch after this many passes; 0 runs until stopped |
| `FLEET_WATCH_NOTIFY` | `1` | `0` turns off the watch's phone push. A Herdr Core job's follower pushes stalls and ended terminals to the phone (`moshi-hook notify`) only when it is `1`; unset, it does not |
| `HERDR_EVENTS_MACHINE` | `hostname -s` | the machine label sent with every event |
| `HERDR_EVENTS_HOME` | `~/.herdr-events` | the event queue and dead letters |
| `HERDR_EVENTS_ROUTES_DIR` | `$HERDR_EVENTS_DIR/routes` | one file per route, `URL=` and `KEY=` |
| `HERDR_EVENTS_STALE_MINUTES` | `30` | a Herdr Core job's follower: minutes a working terminal's screen may stay unchanged, with no status or turn change, before one `stale` (the TUI watchdog's fixed 30) |
| `HERDR_EVENTS_DIR` | `~/.config/herdr-events` | owner tags (`owners/`), job markers (`jobs/`), and the routes when `HERDR_EVENTS_ROUTES_DIR` is unset |
| `HERDR_EVENTS_FLUSH_LOG` | `~/.herdr-events/flush.log` | the flusher's log |
| `HERDR_EVENTS_OWNER` | unset | set per command by a bot, never in the config file: at `stampede new`, the bot that started the job (else the workspace's owner tag), so its gates go back to it |
| `HC` | `hc` | the Herdr Core binary, 0.1.13 or later |
| `HC_SESSION` | `default` | Herdr Core's own: which core; each name is a separate core with its own terminals and state. A Core job keeps the one it was made with (`<job>/endpoint`) and passes it to every terminal; a command from a shell set to another is refused |
| `HC_SOCKET` | Core's default path for the session | Herdr Core's own: that core's socket; passed on like `HC_SESSION`. Set to the default socket's own path, it is the default core |
| `STAMPEDE_NO_UPDATE_CHECK` | `0` | `1` turns off the daily check for a newer release ([Updating](#updating)) |
| `STAMPEDE_UPDATE_URL` | `https://api.github.com/repos/vib-z/stampede/releases/latest` | where the check reads the latest release; the tests point it at a local file |
</details>

## Troubleshoot

| what you see | fix |
|---|---|
| `fleet-job start: the owner asked to see this plan` | a `--review` job: approve the plan as it stands with `stampede approve <job> --by <who>` |
| `fleet-job start: brief ... is missing: ...` or `brief ... does not exist` | write the brief on the [hand-off template](skills/herdr-fleet/references/brief.md), fill every missing or empty section, then start again |
| `fleet-job start: fleet-job starts claude, codex or cursor; ...` | stampede starts only those three kinds; start another agent by hand and record it with `herdr-reopen-snapshot` |
| `BLOCKED <agent>: clear the startup dialog` | read the screen (`herdr agent read <agent> --source visible --lines 30`), clear the dialog, then send the printed `fleet-job tell` line |
| `refused: ... is outside ~/code` from `herdr-trust` | the repo is outside `FLEET_TRUST_ROOT`; move it or change the key |
| `fleet-job start: pane ...'s shell is in ..., not ...` | `--yolo-in` needs the pane's shell in that worktree; use auto mode or `cd` the pane first |
| `FileExistsError` from `stampede new` | a job of that name exists; pass `--name <new slug>` |
| `fleet-job new: new needs --workspace or --pane, or run it inside Herdr` | run outside Herdr with no target: pass `--workspace <id>` or `--pane <id>` ([skills/stampede](skills/stampede/SKILL.md)) |
| `PROBLEM` from `herdr-doctor` | the line names the broken part and its fix. Plain `herdr-doctor` checks the core install only; the event relay's checks run when the relay is installed, or with `--relay` |
| `PROBLEM herdr server not running` from `herdr-doctor` | start Herdr (run `herdr` in a terminal), then run `herdr-doctor` again |
| `PROBLEM` lines for stampede on PATH, linked skills or the relay's launchd jobs from `herdr-doctor --core` in a checkout that is not installed | expected until `install.sh` runs; the Core checks are the `ok hc`, `ok Herdr Core answers`, `ok claude` and `ok codex` lines |
| `PROBLEM Herdr Core not running` from `herdr-doctor --core` | start the core yourself (`hc server start`), then check again; the doctor and stampede never start one |
| `BLOCKED <lead>: <kind>` or `NOT READY <lead>: ...` from `stampede new --core` (exit 1) | the lead runs but is not ready: `hc read <address>`, clear a dialog with `hc keys <address> <keys>`, then send the printed `stampede tell` line; never run `new` again for that folder |
| `FAILED <lead> (...): nothing of <job> runs` | the start never ran, or the follower ended at once (`start-failed` in the folder says why): fix it, then start a new job with another `--name` |
| `... runs on Herdr Core HC_SESSION=<a>, but HC_SESSION here is <b>` | the job lives on another core: unset `HC_SESSION` (or `HC_SOCKET`), or set it to the job's, and run the command again |
| `terminals of an earlier job at this path still run` from `stampede new --core` | a job made at this path before (same `--name`, so the same key) still has live terminals: kill them (`hc ls --all --label stampede.job=<key>`) or pick another `--name` |
| `UNKNOWN <agent>: ... Nothing was taken back` | Herdr Core lost an answer during the start: once it answers, run the printed `reopen.sh`, which adopts the agent or starts it, never twice |
| `fleet-job start: <agent> is already running at <address>` or `... is being started by another caller (pid <n>)` | a Core job runs one terminal per agent: tell it instead, or wait for the other start |
| `fleet-job start: Cursor reports no OSC 7501 status ...` | Cursor workers run on the Herdr TUI only; start a Claude or Codex worker on Core |
| `RELAY DOWN <reason>` in a Core job's `inbox.log` | the follower lost Herdr Core for 10 minutes and exited: once Core is up, `bash <job>/reopen.sh --lead` |
| `NOT ACKNOWLEDGED <file>` from a Core job's `reopen.sh` (exit 3) | the restarted lead has not read that file yet: once it is up, run the printed `echo` line |
| the lead's pane shows Claude's sign-in or first-run screen, though `stampede new` printed `DELIVERED` | sign in to Claude Code once in a plain terminal (`claude`) before your first ask. Then finish the screen in the lead's pane and send `stampede tell <job> lead "Read <job>/briefs/<lead>.md"` |
| a bot gets no events | `herdr-doctor --relay` names the broken part; see [remote/events.md](remote/events.md) |
| `fleet-job ask: the relay did not queue this for <bot>` | a job that bot started asks it by its own route only, never the default route: add `~/.config/herdr-events/routes/<bot>` with a `URL=` (the same webhook as `default` is fine) and check the queue folder with `herdr-doctor --relay` ([remote/events.md](remote/events.md)); meanwhile answer in the lead's pane |
| `UNDELIVERED gate <id> for <bot> held: route <bot> has no URL` in `inbox.log` | the gate or question is queued, but its bot's route lost its URL: put the `URL=` back in `~/.config/herdr-events/routes/<bot>` and the flusher sends it within 2 minutes. After 24 h it moves to `dead/` (a second `UNDELIVERED` line says so): ask again, or ask the owner in the lead's pane |
| `fleet-job gate-ok: gate ... was approved for <sha>, not <sha>` | a push came after the yes: ask the gate again at the new commit |
| `fleet-job approve-gate: approve-gate runs only outside Herdr` | it is the starting bot's command, over SSH; inside Herdr, type yes in the lead's pane instead. For a Herdr Core job the message names Herdr Core too: run it over plain ssh, never `hc exec`, since a typed yes does not count there |
| relay `PROBLEM` lines on a Mac without a bot | a routes folder, a relay launch agent or a relay hook is left over, so the relay counts as installed: finish its setup ([remote/events.md](remote/events.md)) or remove what you no longer use |
| `PROBLEM ... not in the plugin checkout ...` from `herdr-doctor`, or `stampede: command not found` after a Herdr restart | the links point at an old plugin checkout, which Herdr deletes at its next start: rerun the current checkout's installer, which moves them ([docs/SETUP.md, Update](docs/SETUP.md#update)) |
| `stampede` still works after `herdr plugin uninstall stampede` | Herdr keeps its checkout until its server next starts and never removes the links: [docs/SETUP.md, Uninstall](docs/SETUP.md#uninstall) |
| `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | `herdr-trust` trusts repos only under that folder: create it, or set `FLEET_TRUST_ROOT` to where your repos are |
| `refused: ... has local changes or untracked files`, `... is on <branch>, not main` or `... the update adds <path>, already in ...` from `stampede update` | commit, stash or move the files it names, or `git switch main`, then rerun; it never overwrites a file of yours |
| no update line, though a release is out | the check runs at most once a day and is silent offline: delete `~/.cache/stampede/latest-release` to check now, and see that `STAMPEDE_NO_UPDATE_CHECK` is not `1` |

Every known failure with its fix: [failure-modes.md](skills/herdr-fleet/references/failure-modes.md). Startup dialogs: [unattended-setup.md](skills/herdr-fleet/references/unattended-setup.md). Setup problems: [docs/SETUP.md](docs/SETUP.md#setup-problems).

**FAQ**
- *Do I need stampede for this?* Only for a big job: hours long, more than one agent family, anything that leaves the machine (merge, push, send, spend, publish, deploy), or work that must survive a restart. A small job needs no stampede job: run it as one agent session with its built-in subagents, still inside Herdr in a single tagged pane of its own, so its finish arrives as an event. That is also the answer to "why not subagents": for small jobs, use them. The rule: [Size the job first](skills/herdr-fleet/SKILL.md#size-the-job-first-small-or-big).
- *Why two names?* `stampede` is the public name of `fleet-job`, its first name; both run the same command.
- *Can Codex or Cursor lead?* Not yet; the lead is Claude ([roadmap](#status-and-roadmap)).
- *Can workers run on Gemini, Kimi or the other agents Herdr knows?* Not through `stampede start` yet ([roadmap](#status-and-roadmap)).
- *Can a job run without the Herdr TUI?* Yes, on Herdr Core: `stampede new --core` ([Herdr Core](#herdr-core)).

## Reference

<details>
<summary><b><code>stampede</code> commands and exit codes</b></summary>

`stampede` is the same command as `fleet-job` ([fleet_job.py](skills/herdr-fleet/scripts/fleet_job.py)). `stampede --version` (or `-V`) prints the version from [VERSION](VERSION), then, on stderr, the update line when a newer release is out ([Updating](#updating)). `update` is in [stampede_update.py](scripts/stampede_update.py).

| command | flags | does |
|---|---|---|
| `new --file <ask.md>` | `--workspace <id>` (default `$HERDR_WORKSPACE_ID`), `--pane <id>`, `--name <slug>`, `--review`, `--fork <session id>` (the lead starts as a fork of that Claude chat; a value that is not a UUID exits 2) | makes the job folder, starts the lead with its hooks, marks the workspace so plain turn ends stay on the machine, prints `<lead> <job dir>` |
| `new --core --file <ask.md>` | `--cwd <repo>` (default: the git root of the current folder; it must sit under `FLEET_TRUST_ROOT`), `--name`, `--review`, `--fork <session id>`; `--pane` or `--workspace` exits 2 | a whole job on Herdr Core: writes the job record first (`backend`, the key `hc-<12 hex>` in `workspace`, the marker, the owner tag, the lead's row), starts the job's follower `relay-<12 hex>`, then the lead in its own terminal with its brief as the first prompt; prints `<lead> <job dir>`. A lead that is blocked, at an error or silent after 30 s stays the job's lead: `BLOCKED` or `NOT READY` with the recovery, exit 1. A start that never ran, or a follower that ended at start, is taken back: `FAILED`, `start-failed` in the folder, exit 1. When Core loses an answer, nothing is taken back: `UNKNOWN <agent>`, exit 1, and `reopen.sh` adopts or starts it later |
| `finish <job> <summary>` | | one `done` event (`source` stampede, with the summary). A job a bot started uses the same strict route as a question; a local job uses the ordinary relay. Then removes the job marker. A second run does not send again |
| `start <job> <agent> --kind claude\|codex\|cursor --pane <id> --brief <file>` | `--model`, `--effort`, `--report <path>` (repeatable), `--yolo-in <worktree>` | refuses a missing brief or a missing or empty section (exit 2); otherwise starts a worker with hooks and auto mode, records it and sends its brief pointer |
| `start <job> <agent> --kind claude\|codex --brief <file>` (a Core job) | `--cwd <dir>` (default: the repo), `--model`, `--effort`, `--report`, `--yolo-in <worktree>` (must equal `--cwd`); `--pane` or `--kind cursor` exits 2 | one live launch per agent: refuses while another caller starts it or a live terminal of the job runs it (`already running at <address>`); starts it with no parent and no notes, its brief pointer (made absolute) as the first prompt, Claude with `--session-id`, Codex with `--no-daemon`; `STARTED <agent> (<address>)` exit 0, else `BLOCKED`, `NOT READY` (still the job's agent) or `FAILED`, exit 1 |
| `tell <job> <agent> <text>` | `lead` names the lead | a Claude agent's inbox file; another CLI through `herdr-send`, or on Herdr Core only through `hc send` by status, never a key: `idle` sends only while idle, `done` sends at once; `working`, `blocked`, `error`, no status, another job's terminal, Core not answering, text already typed in the prompt, or a slash command (which needs keys Core cannot guard) is one `FAILED <agent> (<why>)` line with the step to do by hand, exit 2 |
| `ask <job> <question>` | `--option <a>` (repeatable) | asks you in the background: a `question` event to the bot that started the job, else your phone; prints `ASKED <id>` |
| `ask <job> --gate --sha <commit> <action>` | `--pr <n>`; no `--option`: a gate is yes or no | a gate: a `gate` event to the bot that started the job, else your phone; prints `GATE <id>` |
| `approve-gate <job> <gate> --sha <commit> --by <who>` | | the starting bot records your yes in chat, run outside Herdr; refuses inside Herdr or a Herdr Core terminal (or under a `herdr`, `herdr-core` or `hc` process), a local job's gate or another commit |
| `gate-ok <job> <gate> --sha <commit>` | | the lead's check before it acts: prints `APPROVED ...` only for your recorded yes at that commit |
| `cancel <job> <id>` | | stops an asked question and its phone card (a question sent to a bot has no card: refused) |
| `approve <job> --by <who>` | | records the plan's fingerprint and wakes the lead |
| `update` | | in a clean git checkout on `main`: `git fetch`, `git merge --ff-only`, then `./install.sh`; refuses local changes, untracked files, another branch, or an ignored file at a path the update adds; in a Herdr plugin install prints `herdr plugin update stampede --yes` |
| `update --check` | | one line: a newer release (exit 1) or the latest release (exit 0); nothing when offline, failed or turned off (exit 0) |
| `hook <action> <job> --agent <name>` | actions: `watch-paths`, `wake`, `claude-stop`, `ask-lead`, `codex-notify`, `cursor-stop`, `session-end` | run by the agents' hooks, never by hand |

**Exit codes:** 0 done; 2 a usage error or a refusal (an agent not in the job, a kind other than claude, codex or cursor (on Herdr Core, Cursor too), an agent already running or being started on Core, a Codex agent on Core that is not ready for `tell`, a start before approval, yolo outside a worktree, a gate with no recorded yes or another commit, no route for the bot that started the job, `approve-gate` inside Herdr or Herdr Core, `cancel` of a question that is no phone card), with the reason on stderr; 1 a Core start that did not end with a ready agent (`BLOCKED`, `NOT READY`, `UNKNOWN` or `FAILED <agent> (<reason>)` on stdout), or Herdr Core failed (one `fleet-job <command>: <reason>` line on stderr), or Herdr or the file system failed, with a Python traceback. The `wake` hook exits 2 on purpose: that wakes Claude. `update` exits 0 updated (or already the latest), 1 refused or failed with the reason, 2 a usage error; `update --check` exits 1 only when a newer release is out.
</details>

<details>
<summary><b>Helper scripts</b></summary>

In [skills/grokbot-herdr/scripts/](skills/grokbot-herdr/scripts/):

| script | does | exit |
|---|---|---|
| `herdr-trust <dir>` | pre-trusts a repo for Claude and Codex | 0, or 2 refused |
| `herdr-send <agent> <text>` | prompts an agent and confirms it started: `SUBMITTED` or `FAILED`; refuses a pane you have focused before any key | 0, 1 failed, 2 usage |
| `herdr-reopen-snapshot <ws> <job dir>` | reads the live workspace (read only) and writes `REOPEN.md` and `reopen.sh` in the job folder: the tabs holding the job's agents (from `agents.tsv`), never another's agent | 0, or 1 with the reason |
| `<job>/reopen.sh` | recreates the workspace and resumes each agent's session; `--fresh` new sessions, `--prompt` re-sends the briefs, `--into <ws>` adds to an open workspace | 0, 2 a workspace with that label is open, 3 a pane's folder is gone, 4 a tab did not open, 64 usage |
| `herdr-reopen-snapshot <hc-key> <job dir>` | a Herdr Core job's record, from `agents.tsv` and `core.json` with no `hc` call; `stampede` writes it at every Core start | 0, or 1 with the reason |
| `<job>/reopen.sh` (a Core job) | starts only what is not live, each once: for an open job its marker, owner tag and follower, then the lead (session resumed) and each worker (Claude resumed; Codex resumed by the session its notify recorded, with `--no-daemon`, else fresh); `--lead` only the follower and the lead; `--prompt` sends a restarted Codex worker its brief; `--fresh` starts each on a new session with its recorded flags and brief, nothing resumed. A Claude session is resumed only when it is known to have run (for good, whatever a later attempt does), started fresh when it never ran, and otherwise left alone with an `UNKNOWN` line. A restarted lead must take `REOPENED <lead> <attempt>` through its wake hook in both inbox files, retried every 5 s for 90 s; until both are acknowledged `<job>/reopen-pending` stays, and every later reopen asks again, even with the lead live | 0, 1 a restart was not `STARTED` (each is reported as `start` reports it: `BLOCKED` or `NOT READY` with its recovery, `FAILED`, `UNKNOWN`), 2 another caller is starting one of them, a folder is gone (each named, nothing started) or this shell names another core, 3 the lead did not acknowledge a file (printed, with the line to write by hand) |
| `herdr-doctor [--relay] [--core]` | read-only health check: `ok`, `warn`, `PROBLEM` lines; `-h` prints usage. `--core` checks Herdr Core in place of the Herdr TUI: `hc` 0.1.13 or later, the selected core answering on its socket (never started), Claude 2.1.295 or later (OSC 7501 status), Codex's `--no-daemon`, and warns that Cursor runs on the TUI only. The core install by default; the event relay too when it is installed, or with `--relay`. For a GitHub-managed plugin, `stampede` or a skill outside the checkout Herdr reports is a `PROBLEM`. A newer stampede release, or no `FLEET_TRUST_ROOT` folder, is a `warn` | 0 ok, 1 a PROBLEM, 2 usage |
| `herdr-events-owner <ws> [<bot>\|--clear]` | tags a workspace with the bot its events go to; also a Herdr Core job's key `hc-<12 hex>`, while that job is open | 0, or 2 refused |
| `herdr-event-core <job dir>` | the follower of a Herdr Core job, started by `stampede new --core` as `relay-<12 hex>`: follows the job's terminals, writes `BLOCKED`, `ERROR`, `GONE`, `WAITED`, `LOST`, `STALE` and `RELAY DOWN` lines for the lead and posts `source` `hc` events for the bot ([remote/events.md](remote/events.md#a-herdr-core-job)); `--alive` asks the selected core's socket for `hello`, never starting a core; `--socket` prints that socket's path | 0 the job finished or never started, 1 relay down; `--alive`: 0 up, 1 down; 2 usage |
| `herdr-event-post`, `herdr-event-flush`, `herdr-event-watchdog`, `herdr-event-claude-hook`, `herdr-event-codex-notify` | the event relay to a bot: [remote/events.md](remote/events.md). While a job marker is present, a plain turn end in that workspace exits 0 without sending | 0; `herdr-event-post --strict` (a job's questions, gates, and finish when a bot started the job): 3 no route of its own, 4 not queued, 6 a malformed `workspace` (a Core key not `hc-<12 hex>`, or any value with characters outside letters, digits, `_` and `-`; an ordinary event drops it instead and is routed as having none); an event from a Core job's follower (with `event_id`): 5 not queued, so the follower tries again; any event for a Core pane counts as sent only once queued |
</details>

<details>
<summary><b>Repo layout</b></summary>

```text
README.md  CHANGELOG.md  CONTRIBUTING.md  RELEASING.md  SECURITY.md  LICENSE  VERSION
AGENTS.md  CLAUDE.md  SKILL.md  config.example  install.sh  herdr-plugin.toml
.github/                issue and pull request templates, workflows/ci.yml (macOS CI)
skills/herdr-fleet/     the job: SKILL.md, references/, scripts/fleet-job, fleet_job.py, fleet-watch.sh
skills/grokbot-herdr/   the bot front door: SKILL.md, scripts/ (herdr-send, herdr-trust, herdr-doctor,
                        the relay, herdr-event-core: a Herdr Core job's follower)
skills/share-plan/      the plan review, on request
skills/stampede/        the front door: "use stampede" in any chat starts a lead
scripts/stampede        the command (also linked as fleet-job); answers --version and update
scripts/stampede_update.py   the daily release check and stampede update
scripts/herdr-plugin-event   the Herdr plugin's event hook
remote/                 front-door guides
docs/                   SETUP.md, RUNS.md, superpowers/specs/ (the design), images/ (screenshots, logos/)
assets/                 the poster, the teaser and the demo GIF
site/                   the hero site: index.html, assets/
site/brand/             the identity assets and the brand guide
tests/                  python3 -m unittest discover tests; fake_hc.py (a fake Herdr Core),
                        core_smoke.py (CI, a real one)
                        test_clients.py and clients_run.py: the cross-client suite (docs/CLIENTS.md)
```
</details>

## Docs

| doc | for |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | the full setup: installer, unattended agents, the event relay, uninstall |
| [SKILL.md](SKILL.md) | the entry point an agent reads to run a job |
| [skills/herdr-fleet](skills/herdr-fleet/SKILL.md) | the lead's playbook, with [failure modes](skills/herdr-fleet/references/failure-modes.md) and [a job on Herdr Core](skills/herdr-fleet/references/core.md) |
| [remote/](remote/README.md) | one guide per front door, Moshi and the event relay |
| [docs/RUNS.md](docs/RUNS.md) | real runs, with timelines and what changed because of them |
| [docs/CLIENTS.md](docs/CLIENTS.md) | the cross-client suite: every client stampede claims reaching the same outcomes on the Herdr TUI and on Herdr Core, the matrix, the live runbook, and which client does worse |
| [the lean design](docs/superpowers/specs/2026-10-21-stampede-lean-design.md) | why stampede is shaped this way |
| [site/](site/README.md) | the hero site, and its [brand kit](site/brand/README.md) |
| [CHANGELOG.md](CHANGELOG.md) | what each version shipped |
| [RELEASING.md](RELEASING.md) | how a maintainer cuts a release: VERSION, the changelog, the tag, the GitHub Release |
| [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) | how to help, and how to report a security problem privately |

## Contribute

How to open an issue or a pull request: [CONTRIBUTING.md](CONTRIBUTING.md). The rules every change follows: [AGENTS.md](AGENTS.md).

- **Tests:** `python3 -m unittest discover tests` (Python 3.11 or later; all with fakes, nothing touches a live Herdr or Herdr Core: a fake `herdr` through `HERDR`, and [tests/fake_hc.py](tests/fake_hc.py) through `HC`). [CI](.github/workflows/ci.yml) runs them on macOS on every push and pull request, then a real install and `herdr-doctor` against Homebrew Herdr, then [tests/core_smoke.py](tests/core_smoke.py) on Herdr Core 0.1.13 (downloaded and checked against its pinned checksum) in a scratch `HC_SESSION`, never a machine's own core. The Herdr Core tests ([test_core.py](tests/test_core.py), [test_core_relay.py](tests/test_core_relay.py)) state the Core contract; a test marked as an expected failure is a part not built yet.
- **The cross-client suite:** `python3 -m unittest tests.test_clients` (about 25 s) plays one job per client (a Herdr chat, Claude, Codex, Cursor, Hermes, a bot over SSH) and backend against the fakes and checks each outcome's command contract, O1 to O9, for each; the agents' own work is left to the live runs. A client is one row in `CLIENTS` in [tests/test_clients.py](tests/test_clients.py) plus one in [docs/CLIENTS.md](docs/CLIENTS.md), which also holds the live runbook and the clients that do worse; a worker kind is one entry in `WORKERS` there, which every client's job then starts.
- **The four skills are copies** of the maintainer's own skills, scrubbed of anything personal. A pull request that changes `skills/` is welcome; the maintainer carries it to the source first, then copies it back here.
- **A front door:** a guide in `remote/` that writes the ask and runs `stampede new`, linked from [Front doors](#front-doors).
- **An agent CLI:** its auto and no-checks flags in `AUTO` and `YOLO`, and its hooks in `cli_args`, in [fleet_job.py](skills/herdr-fleet/scripts/fleet_job.py), with a test in `tests/test_fleet_job.py`. On Herdr Core it must also report OSC 7501 status; its Core flags go in `start_core`, with a test in `tests/test_core.py`.

## Status and roadmap

**0.1.0, 22 Oct 2026. Works and tested:** the job folder, the lead's start with its hooks, starting workers on Claude, Codex or Cursor, the review lock and approval, background questions and cancel, the wake on every rewritten report, the yolo guard, the install, `--version` and the plugin event, all with fakes. Every command in this README was run against a scratch job.

**0.1.1, 23 Oct 2026. Updating:** `stampede update` and `stampede update --check`, the daily release check in `--version` and `herdr-doctor`, and a test that keeps `herdr-plugin.toml` at VERSION. Tested with a local reply file, a fake rate-limited server and scratch git repos, and run once against the live GitHub API.

**0.1.1, 23 Oct 2026. A clean first install:** plain `herdr-doctor` checks the core install, and the event relay only when it is installed or with `--relay`; the README opens with a short path; CI on macOS runs the tests, a real install and `herdr-doctor` against Homebrew Herdr on every push and pull request.

**0.1.2, 23 Oct 2026. Gates go back to whoever started the job:** a bot-started job's questions and gates go to that bot as events through `herdr-event-post --strict`, the bot records your yes with `approve-gate`, and the lead acts only once `gate-ok` matches it to the gate and the commit; a job started locally asks on your phone as before, and a yes typed in Herdr always works. Tested with fakes: a scratch relay route, scratch job folders, the refusal inside Herdr and for another commit, and a held or expired gate told to its lead. Small jobs stay in Herdr, in one tagged pane.

**0.1.2, 23 Oct 2026. Plugin installs:** from a sandboxed test of the whole plugin lifecycle. A plugin update or reinstall moves stampede's own links (the same file, in an older checkout of the same install) to Herdr's new checkout, so nothing dangles after Herdr deletes the old one; `herdr-doctor` reports links outside the plugin's checkout, and warns when `FLEET_TRUST_ROOT` is missing; `stampede update` and the daily check name `herdr plugin update stampede --yes` in a plugin install; the README shows the plugin install, and SETUP.md the full uninstall, comparing link targets as plain text. Tested with fake managed checkouts, another plugin named `stampede-helper-abc`, a backup tree, glob characters in a path, both uninstall recipes run from SETUP.md in bash and zsh, a fake `herdr` and scratch git repos; the `herdr plugin` commands themselves were run only in that sandbox test.

**0.1.3, 25 Oct 2026. Complete worker briefs:** `stampede start` refuses a brief that is missing a section of the hand-off template or leaves one empty, and each role's model is set on its own (`FLEET_LEAD_MODEL` for the lead, `--model` per worker). Tested with fake Herdr.

**0.1.4, 28 Oct 2026. Optional pstack, a README that opens with a demo, and a clean install rehearsal:** a lead started inside Herdr with the same Claude flags `stampede new` uses loaded pstack 0.9.102 (its skills and its session start note were present) and ran that change under [references/pstack.md](skills/herdr-fleet/references/pstack.md), with its todo list as `todo.md` and no hidden subagents. Both install routes were run from a throwaway home with its own Herdr server and no stampede: `herdr-doctor` exited 0 and `stampede --version` printed the version. The quick start ran up to the lead's first turn (that home had no signed-in Claude): the gate and the plan lock held, and the reopen script was written.

**Site and brand, 22 Oct 2026:** the hero (PR #16), the brand kit (PR #20) and the landing page around the film (PR #3) are done. The site is live at https://vib-z.github.io/stampede/ and mirrored on Vercel at https://stampede-xi.vercel.app/.

**Live, 21 Oct 2026:** the engine started a hooked Claude lead, which was woken by its inbox file; a Codex reviewer's turn reached it through Codex's notify hook; a Cursor worker committed under auto-review and its stop hook reached the lead; a question went to the owner's phone without blocking the lead and was cancelled cleanly. Real jobs, with timelines: [docs/RUNS.md](docs/RUNS.md).

**0.1.5, 29 Oct 2026. Quieter events while a job is open, and a lead forked from the planning chat:** `stampede new` writes `~/.config/herdr-events/jobs/<workspace>`. Plain turn ends in that workspace stay on the machine, and `stampede finish` sends one done and removes the marker. Blocked and permission prompts for one pane are one message for 120 seconds. A Codex turn with no Herdr pane is not sent. Tested with the relay sample payloads and fake Herdr: a mid-job worker Stop was dropped, finish posted once, blocked from two sources posted once, a done in a workspace with no job still posted, a Codex turn with no pane was dropped, and StopFailure still posted. A chat in the desktop app was forked into a lead in a fresh Herdr workspace on a scratch repo: the lead started with the conversation, started a reviewer on another model, and got its pass through the hook. A fresh install linked the new `stampede` skill, and a chat told "use stampede" loaded it first.

**Unreleased, 29 Oct 2026. Herdr Core:** a whole job on Herdr Core (`hc` 0.1.13), next to the Herdr TUI, which is unchanged: `stampede new --core`, `start` and `tell` on Core, the job's follower `herdr-event-core`, Core gates that count only the recorded yes, the relay for a Core key, `reopen.sh` on Core and `herdr-doctor --core`. Tested with a fake `hc` (`tests/fake_hc.py`): the launch lock and races between two starts and a reopen, adopted and reclaimed starts, a lead or worker blocked or silent at start, `tell` by status and by exit code, events replayed through the follower (episodes, reconnects, a death or a wait's end while away, `RELAY DOWN`), and a restarted lead that must acknowledge both inbox files. `herdr-doctor --core` ran against this Mac's running core. Every command in [Herdr Core](#herdr-core) was run against the fake. Not run yet: a live job with a real Claude lead and Codex worker on Core (the test lanes), and CI's smoke run on a real `hc`.

**Unreleased, 30 Oct 2026. The cross-client suite:** [docs/CLIENTS.md](docs/CLIENTS.md). Every client in `CLIENTS` (a Herdr chat, Claude, Codex, Cursor, Hermes, Grok Bot, any other bot, a whole remote computer) drives one job on the Herdr TUI and one on Herdr Core through the real `stampede` command, with its own environment and process tree (inside Herdr, outside it, or over SSH under `sshd`), against the fakes; each passes the command-contract checks of O1 to O8, and the bots O9. No agent runs in them: `plan.md`, the worker's file and the commit are for the live runs. Two gaps for bots (F1, F2) and four found by the live runs (F4 to F7) are expected failures. Live, on one Mac, 30 Oct 2026: a Herdr chat and Claude on the TUI pass O1 to O8; Claude on Core and Codex on both backends pass all but O4, O5 and O7, which wait on the owner's tap; Cursor was not run (headless Cursor needs `--force`, then a usage limit); Hermes and Grok Bot are still to come. The live runs found seven more gaps (F3 to F9).

**Next:**
- A live job on Herdr Core: a real Claude lead and Codex worker, `tell` both ways, a gate, a lead-only reopen.
- The cross-client findings in [docs/CLIENTS.md](docs/CLIENTS.md#doing-worse): a bot's Core start that names its owner, and a TUI job whose bot is named by `HERDR_EVENTS_OWNER` tagging its workspace.
- On Herdr Core, planned: workers on a second machine (`hc run --on`), a bot front door over `hc`, the job shown in the Herdr app (its `herdr.space` and `herdr.tab` labels), and Cursor workers once Cursor reports OSC 7501 status.
- One live job from Grok Bot.
- Starting workers on the other agents Herdr detects, not only Claude, Codex and Cursor.
- Workers on a second machine over Tailscale.
- Codex or Cursor as the lead.
- ChatGPT Dots as a front door, once it can be woken by a webhook.
- Report to Herdr that Codex's "Implement this plan?" and Cursor's "Ready to build?" dialogs read as `idle` and `done`, not `blocked` (needs the owner's yes).
- A Linux run.

## Credits and license

Built on [Herdr](https://herdr.dev) and its agent automation, with [Moshi](https://getmoshi.app/docs/herdr) for the phone. A stream of many small, independent coding tasks fits [herdr-projects](https://github.com/eliasstravik/herdr-projects) better. Product marks: [docs/images/logos/SOURCES.md](docs/images/logos/SOURCES.md). The brand kit, in [site/brand](site/brand/README.md) with its [visual guide](site/brand/guide.html), holds the Open gate logo, the Star link, the painterly grounds and the brand guide.

[MIT](LICENSE), copyright 2026 stampede contributors. The code licence does not grant rights to the stampede name or marks. See [site/brand/CREDITS.md](site/brand/CREDITS.md).
