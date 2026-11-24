# The stampede guide

This page explains how a job runs and what stampede works with, then walks through one job, command by command.
To install stampede, see [Setup](SETUP.md). The short version is the [README](../README.md).

- [Words on this page](#words-on-this-page), [What is stampede](#what-is-stampede), [How it flows](#how-it-flows), [Quick start](#quick-start)
- [Works with](#works-with), [See it](#see-it), [How it works](#how-it-works), with [the job folder](#the-job-folder)
- [Use: one job, start to finish](#use-one-job-start-to-finish), [Share the plan first](#share-the-plan-first), [A front door outside Herdr](#a-front-door-outside-herdr-the-claude-desktop-app)
- [Front doors](#front-doors), [New releases](#new-releases)

## Words on this page

- **Agent:** an AI program that reads, writes and runs code for you, such as Claude Code or Codex.
- **Lead:** the one agent that plans the job and does it. **Worker:** an extra agent the lead brings in. On Herdr Core a worker is called a helper.
- **Herdr:** an app that shows each agent in its own **pane**, a box in its window. A **tab** holds a group of panes. The app, with its tabs and panes, is the **Herdr TUI** (an app drawn in text inside a terminal).
- **Herdr Core:** a second way to run a job, in plain terminals with no tabs or panes ([Herdr Core](CORE.md)).
- **Terminal:** the app where you type commands. **CLI:** a program you run in a terminal.
- **Repo:** your project's folder, kept with **git**, a tool that saves the history of your files.
- **Commit:** one saved change. **Branch:** a separate line of changes beside the main code. **Push:** sending commits to GitHub.
- **Pull request (PR):** a proposed change, waiting to be accepted. A **draft** PR is not ready to accept yet. **Merge:** accepting it into the main code.
- **Front door:** the chat or bot you talk to. It starts the job for you.
- **Gate:** a step that needs your yes, such as a merge ([Safety](SAFETY.md)).
- **Brief:** a worker's written task. **Hook:** a command an agent program runs by itself at a set moment, such as the end of a turn.
- **Auto mode:** the agent does small steps without asking you, with its own safety checks still on.
- **SSH:** a safe way to run commands on another computer. **Tailscale:** an app that joins your computers in a private network.
- **Grok Bot:** an agent with a computer of its own, which you text from your phone. It logs in to your computer over SSH, through Tailscale.
- **Moshi:** a phone app that shows agents' questions so you can answer them. **Webhook:** a web address one program calls to tell another what happened.

## What is stampede

stampede runs a team of AI agents in Herdr. You ask once, in plain words, from a [front door](#front-doors).
One lead plans the job and does it. It brings in workers only when they help ([How it works](#how-it-works)).

**Why.** Running many agents by hand goes wrong in four ways:

- agents stop and wait between steps;
- too many small agents start;
- rounds of work wait on each other;
- the lead spends its day writing briefs.

Real jobs showed all four ([docs/RUNS.md](RUNS.md)). So in stampede the lead plans and goes, works alone by default, wakes when a hook tells it something happened, and asks you only what is yours to decide.

**Who it is for.** Anyone who uses Claude Code, Codex or Cursor and wants a whole job done from one ask, watched in Herdr and answered from a phone.

**What it is made of.** Four skills and one command. A skill is a set of written steps an agent follows. You install them with a script, or as a Herdr plugin (an add-on that Herdr manages).

| part | what it does |
|---|---|
| [`stampede`](../skills/stampede/SKILL.md) (skill) | the front door: say "use stampede" in any project chat. It writes your ask to a file, opens a Herdr workspace for the project and starts the lead |
| [`herdr-fleet`](../skills/herdr-fleet/SKILL.md) | the steps the lead follows: plan, panes, hooks, review, gates, report, reopen |
| [`grokbot-herdr`](../skills/grokbot-herdr/SKILL.md) | the front door for a bot that reaches your computer over SSH |
| [`share-plan`](../skills/share-plan/SKILL.md) | shows you the plan before any agent starts, only when you ask |
| [`stampede`](../scripts/stampede) (command) | the command itself: `new`, `start`, `tell`, `ask`, `cancel`, `approve` and more ([docs/CLI.md](CLI.md)) |

## How it flows

The setup we recommend: you text a task to your Grok Bot, and it reaches your Mac over Tailscale.
A Claude Code lead does the job there, in [Herdr](https://herdr.dev). It adds Codex or Cursor panes only when parallel work helps.
No agent merges, pushes, sends or spends until you say yes.

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

**Let a Grok Bot set it up.** [Stompy](https://x.ai/bot/_mNMq-0M5aA02AQMNOHTy) is a Grok Bot that sets up stampede between your Grok Bot and your Mac, from start to end, and keeps the setup healthy.

### Without a bot

You do not need a bot. stampede works with only Herdr, Claude Code and this repo.
Start a job from Claude, Codex, Cursor or any agent, or from a Claude pane in Herdr ([Front doors](#front-doors)).
Gate questions then reach your phone through Moshi, if you use it. Otherwise you answer in Herdr.

## Quick start

**An agent told to run a job with stampede** starts at [USING.md](../USING.md), one short page.

**Your first ask, from a chat in Herdr.**

1. Install stampede and do steps 1 and 2 of [your first job](../README.md#your-first-job): the [one-time settings](SETUP.md#unattended-agents), and `herdr-trust` for your repo.
2. Open your repo in Herdr, start Claude in a pane, and type:

> With stampede: add a /health endpoint with a test, have a reviewer on another model check it, then open a draft PR.

**Then from your phone (recommended).** Set up Grok Bot's SSH, Tailscale and webhook once ([remote/grokbot/](../remote/grokbot/README.md)). Then send the same ask in the Grok chat.

**On Herdr Core instead of the Herdr TUI.** Set up and check [Herdr Core](CORE.md) first. Then ask *"With stampede, on Herdr Core: ..."*.
The front door then runs `stampede new` with `--core`. A job runs on Herdr Core only when you ask for it.

**Limits.**

- It runs on macOS and Linux. What differs on Linux: [docs/LINUX.md](LINUX.md).
- stampede is early: commands and files may still change.
- It is for big jobs. A small job runs as one agent session in a single tagged Herdr pane ([FAQ](TROUBLESHOOT.md#faq)).

The full install, with everything you need: [Install](SETUP.md#install). A whole job, command by command: [the walkthrough](#use-one-job-start-to-finish).

## Works with

**Agents.** The lead runs on Claude Code, or on Codex if you pick it, on the Herdr TUI or on Herdr Core ([Pick the lead](#use-one-job-start-to-finish)).
Workers run on Claude Code, Codex or Cursor. `stampede start --kind claude|codex|cursor` starts each one with its own hooks and auto mode.
A [Herdr Core](CORE.md) job can run any other CLI as a plain program. The earlier `--core --relay` path hands Cursor, Hermes and Kimi workers to Herdr TUI panes.

<table>
  <tr>
    <td align="center" width="150">
      <img src="images/logos/claude.svg" width="44" height="44" alt="Claude Code logo"><br>
      <b>Claude Code</b><br><sub>the lead, and workers</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/logos/codex-dark.svg">
        <img src="images/logos/codex.svg" width="44" height="44" alt="Codex logo">
      </picture><br>
      <b>Codex</b><br><sub>the lead if you pick it, workers and reviewers</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/logos/cursor-dark.svg">
        <img src="images/logos/cursor.svg" width="44" height="44" alt="Cursor logo">
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
        <source media="(prefers-color-scheme: dark)" srcset="images/logos/herdr-dark.svg">
        <img src="images/logos/herdr.svg" width="44" height="44" alt="Herdr logo">
      </picture><br>
      <b>Herdr</b><br><sub>the panes you watch</sub>
    </td>
    <td align="center" width="150">
      <img src="images/logos/moshi.svg" width="44" height="44" alt="Moshi logo"><br>
      <b>Moshi</b><br><sub>questions on your phone</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/logos/grokbot-dark.svg">
        <img src="images/logos/grokbot.svg" width="44" height="44" alt="Grok Bot logo">
      </picture><br>
      <b>Grok Bot</b><br><sub>the preferred bot</sub>
    </td>
    <td align="center" width="150">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/logos/tailscale-dark.svg">
        <img src="images/logos/tailscale.svg" width="44" height="44" alt="Tailscale logo">
      </picture><br>
      <b>Tailscale</b><br><sub>a bot's private link</sub>
    </td>
  </tr>
</table>

Herdr itself knows many more agent CLIs: its `herdr agent start --help` lists 24, from Gemini and Kimi to OpenCode and Copilot.
That is Herdr's support, not stampede's yet. `stampede start --kind` takes `claude`, `codex` and `cursor` on the Herdr TUI, and `hermes` and `kimi` only as handed workers of a `--core --relay` job. A Herdr Core job runs any other CLI as a program after `--`. Starting workers on the others as kinds is [planned](STATUS.md).
The logos belong to their owners and imply no endorsement ([sources](images/logos/SOURCES.md)).

### Works well with

**[pstack](https://github.com/michael-denyer/pstack-claude), optional.** For a coding job, the lead uses pstack if you have it. pstack settles how the data looks first, commits a skeleton of the code with one failing test, then proves the work on the real program.
The lead is a normal Claude Code session, so an installed pstack loads by itself. stampede's rules keep the extra agents pstack starts as Herdr panes you can watch.
Without pstack, nothing changes. The rules: [references/pstack.md](../skills/herdr-fleet/references/pstack.md).

## See it

![The build tab of a fleet in Herdr: four panes side by side. build-steps-plan and build-steps-run are Claude Code agents that have just finished; build-scripts and build-app are Codex agents still working.](images/fleet-build-tab.png)

<sub>Real, drawn: the <code>build</code> tab of the fleet that built stampede's first version, drawn from each pane's own screen text (<code>herdr agent read</code>), personal paths replaced with <code>~</code>, 18 Oct 2026. A lean job opens fewer panes; each looks the same.</sub>

## How it works

These are the steps of the [diagram above](#how-it-flows). They are the same for every front door.

1. **You ask once,** in plain words, in a [front door](#front-doors). It writes your ask to a file and runs `stampede new --file <ask.md>`. Then it tells you the lead's name and steps back.
2. **One lead plans, then goes.** The lead, named `lead-<slug>`, starts in auto mode in a tab named `lead`.
   - By default it runs on Claude (Opus 5.5) at extra high effort (`xhigh`). With `--lead codex` it runs on Codex (GPT-6.2 Sol), also at `xhigh`.
   - Every worker's role defaults to `medium` effort, whatever its model. A worker started on another CLI than its role's gets that CLI's own default unless you give `--effort`, and Cursor takes no effort setting.
   - You can change both, for one job, one worker or every job: [Configure](CONFIGURE.md#effort-the-default-and-how-to-change-it).
   - It writes `plan.md`: the tasks, who does each, questions with a safe default, and the gates. Then it starts work.
3. **A worker only when it pays.** The lead starts a worker for one of these, each in its own Herdr pane:
   - parallel pieces of about 30 minutes or more (at most 4);
   - another model or tool;
   - one reviewer on another model;
   - the same task many times (6 at once).
4. **Hooks wake the lead, so it never keeps checking.** When a worker reports, ends a turn, asks a question or exits, a line lands in `<job>/inbox.log`.
   The lines are `REPORT`, `TURN`, `QUESTION` and `GONE`, and `UNDELIVERED` for a question, gate or post its bot has not heard.
   A Claude lead's file hook then wakes it, and stampede types in any line the hook missed. A Codex lead has no file hook, so stampede types the lines into its pane ([Pick the lead](#use-one-job-start-to-finish)).
5. **Review only what ships,** on another model, in at most two rounds.
6. **Questions and gates go back to whoever started the job.**
   - A bot gets a `question` or `gate` event. It asks you in chat, passes your answer back, and records a gate's yes with `approve-gate`.
   - A job you started on your own computer asks on your phone through Moshi.
   - The lead keeps working while it waits. An agent's own say-so never counts. Which yes counts where: [Safety](SAFETY.md).
7. **The lead reports back once.** When the job is done, or stopped for good, the lead runs `stampede finish <job> "<summary>"`. That is the one done event a bot outside Herdr gets for the job.
   - While the job is open, plain turn ends stay on the computer. These still go out: blocked, permission prompts, StopFailure, a stale or dead pane, questions, gates and the lead's posts (`stampede post`).
   - By default, the lead then asks whether to close. With `finish.auto_close` on, a Herdr TUI job's own workspace closes by itself once nothing is left to lose or answer ([Configure](CONFIGURE.md#every-key-with-its-default)).
8. **Workers exit once their work is merged** or accepted. By default nothing closes without your yes, and `reopen.sh` brings a closed job back.

**The lead keeps the state; a worker gets a brief.** The lead holds your ask, the plan, the decisions and the judgement. A worker gets only its brief, so the brief must carry everything it needs.
A brief has seven sections: Goal, Why, Inputs, Constraints, Done when, Report back and If blocked, as in the [hand-off template](../skills/herdr-fleet/references/brief.md).
A thin brief is the usual cause of weak work. `stampede start` refuses a brief with a missing or empty section, before it starts anything.
Pick a strong planner for the lead, and a fast, capable model for the workers. Both are [settings](CONFIGURE.md), not code.

**What lives where.** Your Mac, always on, runs Herdr, the lead and the workers. A bot such as Grok Bot runs on its own computer and reaches the Mac over SSH and Tailscale.
Or everything runs on one remote computer. Either way, the lead and its workers share one machine. Workers on a second machine are [planned](STATUS.md).

**On Herdr Core** the steps stay the same, but Core holds the tree of agents. The lead is a root terminal, and each helper is its child, or the child of another helper, at any depth. By default at most 12 helpers work at once (the setting `helpers.max`); more starts wait in a queue.
Core's notes about the children, and messages sent with `hc send`, wake the lead. Hooks and inbox files are not used. Questions, gates, posts and finish reach you as above.
If the lead is blocked, failed, dead or stalled, the machine's watchdog tells you within about 5 minutes ([Herdr Core](CORE.md)).

### The job folder

`stampede new` makes a folder for each job, on every backend: `~/code/herdr-jobs/jobs/<date>-<bot or local>-<slug>/`. The setting `jobs_root` moves the root.
The folder is never inside your repo, so nothing in it lands in git. A job an older stampede made in `<repo>/.herdr-<slug>` keeps working.
The agents still work in the repo, and `--add-dir <job>` lets each one write here. The folder holds:

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

## Use: one job, start to finish

In a Herdr pane in your repo, ask your Claude chat: *"With stampede: make hello.txt with hi, then have a reviewer on another model confirm it."*
The chat is your front door. It writes the ask and starts the lead:

```console
$ printf 'Make hello.txt with hi.\nThen have a reviewer on another model confirm it.\n' > ask.md
$ stampede new --file ask.md
recorded lead-make-hello-txt-with-hi (claude) in ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi/agents.tsv
DELIVERED lead-make-hello-txt-with-hi (inbox file)
lead-make-hello-txt-with-hi ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi
```

Inside Herdr, `--workspace` defaults to the current workspace, and the lead gets a new `lead` tab. `--pane <id>` puts it in an empty pane instead, and `--name <slug>` names the job.
A front door outside Herdr has no current workspace: for the Herdr TUI it passes `--workspace` or `--pane`, and for Herdr Core `--core`.
With none of them, `new` refuses and makes nothing ([skills/stampede](../skills/stampede/SKILL.md)). Here the chat tells you `lead-make-hello-txt-with-hi` and stops.

**Plan in chat, then fork it into the lead.** Say you and a Claude chat already worked out the plan. The chat then adds `--fork "$CLAUDE_CODE_SESSION_ID"`.
The lead starts as a fork (a copy) of that chat, with `claude --resume <id> --fork-session`. It keeps the whole conversation and writes the agreed plan into `plan.md`. Your chat stays as it was.
Put the agreed plan in the ask file too: the ask file stays the source of truth. Guide: [remote/claude-code.md](../remote/claude-code.md#plan-here-then-fork-the-lead).

**Pick the lead.** The lead is Claude unless you ask for Codex. Then the front door adds `--lead codex`. To make Codex your standing choice, set `FLEET_LEAD_KIND=codex`.
A Codex lead defaults to GPT-6.2 Sol at `xhigh`, with its hooks and `--approve-for-me` (Codex's auto mode). stampede types its brief pointer into its pane at once. `--fork` takes only a Claude lead:

```console
$ stampede new --file ask.md --lead codex
recorded lead-make-hello-txt-with-hi (codex) in ~/code/herdr-jobs/jobs/2026-11-03-local-make-hello-txt-with-hi/agents.tsv
SUBMITTED lead-make-hello-txt-with-hi
lead-make-hello-txt-with-hi ~/code/herdr-jobs/jobs/2026-11-03-local-make-hello-txt-with-hi
$ stampede new --file ask.md --lead codex --fork "$CLAUDE_CODE_SESSION_ID"
stampede new: --fork forks a Claude chat, so it takes a Claude lead: drop --lead codex, or start without --fork
```

**How the lead gets news.** A Codex lead has no file hook. Instead, a short-lived deliverer types its new inbox lines into its pane, marked `[fleet-job inbox for <lead>, not typed by the owner]`.
It types only once the pane is idle, not focused, and has nothing typed in its prompt. On Herdr Core, Core delivers them.
A Claude lead on the Herdr TUI has the same deliverer as a backup. Claude Code's file watcher can miss a change, so after 30 seconds the deliverer types any line the hook did not take, once the lead is idle with an empty prompt.
If a lead's lines stay unread for 4 hours, the deliverer sends one `blocked` event (`kind` `undelivered`).
Since this text is typed in, a Codex lead acts on a gate only after `stampede gate-ok` prints `APPROVED`.

**The lead plans and starts a reviewer.** The lead reads `ask.md`, writes `plan.md` and goes on at once. Here it writes `briefs/review-hello.md` on the [hand-off template](../skills/herdr-fleet/references/brief.md), then starts one reviewer on another model:

```console
$ J=~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi
$ stampede start $J review-hello --kind claude --pane <pane id> \
    --brief $J/briefs/review-hello.md \
    --model <another model> --effort max --report reports/review-hello.md
recorded review-hello (claude) in ~/code/herdr-jobs/jobs/2026-10-29-local-make-hello-txt-with-hi/agents.tsv
DELIVERED review-hello (inbox file)
```

The reviewer writes `reports/review-hello.md`, with `Status: PASS` and `Reviewed: <sha>` in its first 10 lines. The sha is the full id of the commit it reviewed. Then it ends its turn, and its hook adds `REPORT reports/review-hello.md` to `inbox.log`, which wakes the lead.

**The lead asks you a question,** and keeps working:

```console
$ stampede ask $J "Keep the file in the repo root?" \
    --option Yes --option No
ASKED 1fecfa0be4dc (the answer goes to the lead inbox; cancel with: stampede cancel <job> 1fecfa0be4dc)
```

Your tap comes back as `ANSWER ...` in the lead's inbox.

**The merge gate.** A gate, such as merging the draft PR, goes back to whoever started the job ([Safety](SAFETY.md)). You started this one in Herdr, so it goes to your phone.
The lead merges only with `stampede merge`. It first checks the review report and the PR's newest commit (its head), and names the gate it needs:

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

`stampede merge` marked the draft ready and merged with `--match-head-commit $sha`. It wrote `<job>/merges.log`: a `MERGING` line before it touched GitHub, then `MERGED`.
Only your recorded yes opens a merge gate ([Safety](SAFETY.md)). Then the lead writes a short report and asks whether to close the workspace. `<job>/reopen.sh` brings it back later.

### Share the plan first

Say "share the plan first", and the front door adds `--review`. The lead then writes `plan.md` and ends its turn. No worker can start until you approve that exact plan:

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

The `start` refusal exits 2. The approval holds a fingerprint of `plan.md`, and any later change locks `start` again until a new approve.
A change you ask for goes to the lead with `stampede tell <job> lead "<your words>"`. The steps: [share-plan](../skills/share-plan/SKILL.md).

### A front door outside Herdr (the Claude desktop app)

When you talk to a chat outside Herdr, nobody watches the lead's pane. So the front door starts the job with `--front-door`. Then:

- the lead posts everything that is for you to `<job>/outbox/`: the plan, questions, gates, files and its report;
- a hook turns the lead's own question cards and SendUserFile into posts;
- the front door waits on the outbox in the background and passes each item on to you.

Here is a job with plan review:

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
$ stampede approve-gate $J 83307febaa1a --sha <commit> --digest <digest> --by "owner in desktop chat: 'mark it ready'"
DELIVERED lead-seller-copy (inbox file)
APPROVED 83307febaa1a at <commit>
```

- The front door shows you the plan file itself. A yes to its own summary is never an approval.
- A gate's item carries the exact `approve-gate` line, and the front door runs it with your words quoted.
- If the lead is held at a card anyway, `stampede wait` and `stampede tell` say `BLOCKED_ON_CARD`.
- The lead's `finish` posts a `done` item, and `stampede wait` says `LEAD_GONE` when Herdr no longer has the lead.

The front door's loop: [skills/stampede](../skills/stampede/SKILL.md#steps). The lead's side: [front-door.md](../skills/herdr-fleet/references/front-door.md).

**On Herdr Core** the same loop runs with `--core --front-door` on `stampede new`, from a chat outside Herdr. Here is one run against the test suite's fake `hc` (a stand-in for Herdr Core), every command from outside Herdr:

```console
$ stampede new --core --file ask.md --name login --front-door --review
on Herdr Core (--core), repo <repo>
hook pre-push installed in <repo>/.git/hooks/pre-push: a job's agent cannot push to the default branch without the gate
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

`SUBMITTED` means Core typed the line into the lead's terminal: there is no inbox file.
The lead has no hooks there, so its brief tells it never to use a question card or a file-send tool. The whole contract: [Front door](CORE-NATIVE.md#front-door).

## Front doors

A front door is the chat or bot you ask. Every front door writes the ask and runs `stampede new`. None of them plans or runs the job itself.

| front door | how you ask | where answers arrive | guide |
|---|---|---|---|
| a chat in Herdr | type the ask in a Claude pane | the lead's pane, plus a Moshi card | [walkthrough](#use-one-job-start-to-finish) |
| Claude desktop or the Claude app | Remote Control into a session on the machine | the lead's row in the Claude app, plus Moshi | [remote/claude-code.md](../remote/claude-code.md) |
| Codex desktop or the ChatGPT app | Codex on the connected machine | Moshi | [remote/codex.md](../remote/codex.md) |
| Cursor | a Cursor chat on the machine runs the same two commands | Moshi | [remote/other.md](../remote/other.md) |
| **Grok Bot** (preferred bot) | the bot reaches your Mac over SSH and Tailscale | the Grok chat, woken by a webhook | [remote/grokbot/](../remote/grokbot/README.md), [grokbot-herdr](../skills/grokbot-herdr/SKILL.md) |
| any other bot | the same as Grok Bot | its webhook | [remote/other.md](../remote/other.md) |
| a whole remote computer | Herdr, the CLIs and stampede on one computer | any of the above | [remote/any-machine/](../remote/any-machine/README.md) |

Any front door can run the job on Herdr Core instead, when you ask: it passes `--core --cwd <repo>`. What it then hears: [How it works](#how-it-works), and [Herdr Core](CORE.md).

Moshi is the phone side of every front door: [remote/moshi.md](../remote/moshi.md).

## New releases

To hear about new releases, open stampede on [GitHub](https://github.com/vib-z/stampede) and pick **Watch**, then **Custom**, then **Releases**.
The site: [vib-z.github.io/stampede](https://vib-z.github.io/stampede/).
