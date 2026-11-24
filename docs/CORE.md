# Herdr Core

This page shows how a job runs on Herdr Core, the second place a job can run.
A job runs here only when you ask for it. The default is the Herdr TUI.

- [When a job runs on Herdr Core](#when-a-job-runs-on-herdr-core)
- [The parts of a Core job](#the-parts-of-a-core-job)
- [Check the computer first](#check-the-computer-first)
- [One Core job, start to finish](#one-core-job-start-to-finish)
- [The earlier path](#the-earlier-path---core---relay)

[Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later; checked against 0.1.20) is Herdr's terminal runtime: a server (a program that keeps running in the background) that runs programs in terminals that stay open.
- An agent reports its own status (OSC 7501, a code it prints to its terminal); a plain program reports none.
- Core gives each terminal a parent link and labels, and sends a stream of events.
- It has no workspaces, tabs or panes.

On top of Core, stampede adds only the space's name, the owner tag, the reopen record, your gates (steps that need your yes), a cap on helpers and the layout labels.
The shape a client reads (labels, parent links, events): [docs/CORE-NATIVE.md](CORE-NATIVE.md). The lead's playbook: [references/core.md](../skills/herdr-fleet/references/core.md). For Core's own basics, read `hc --skill`.

## When a job runs on Herdr Core

A job runs on the Herdr TUI (Herdr's window, with tabs and panes) by default. It runs on Herdr Core only when you ask:
- with `--core` on `stampede new`, for one job;
- with the setting `backend`, which is `tui` by default. `core` makes Core your standing choice. `auto`, if you set it, runs a job on the TUI inside a Herdr pane and on Core anywhere else, and says so on the first line.

`--pane` or `--workspace` always means the TUI. With the default setting, `new` refuses outside a Herdr pane when it has no `--core`, `--pane` or `--workspace`, and makes nothing.

## The parts of a Core job

- **You, the owner,** ask, answer questions and give every gate's yes.
- **The front door** is the chat or bot you talk to. It writes the ask, runs `stampede new --core`, passes your words to the lead with `stampede tell <job> lead "..."` and records a gate's yes with `approve-gate`. It reads the lead or a helper with `hc read <address>`, and never types into one. A chat outside Herdr adds `--front-door`, as on the TUI ([Front door](CORE-NATIVE.md#front-door)).
- **The lead** is the root of the tree: one Core terminal with no parent, one per job. The space has no terminal of its own: its name is the lead's `stampede.space` label.
- **Helpers** are the lead's real Core children, started with `stampede start`: Claude, Codex or any program. A helper may start its own helpers, at any depth.
- Core ends a branch of the tree when its parent ends, unless a helper was started with `--outlive-parent`.
  Core sets a parent only once, so such a helper still names its old parent after a lead is reopened. `stampede tree` shows it at depth 1 as `outlived <its old parent>`. The cap counts it, and closing the whole job ends it with the rest.
- **The reviewer** is one helper on another model: a `review-<scope>` helper gets the setting `roles.review` (Codex by default). The setting `review.step` says when the lead's brief asks for a review: at the `end` by default ([Configure](CONFIGURE.md#every-key-with-its-default)).

**What lives where.**
- Core holds the tree and each terminal's status. Read it with `stampede tree <job>`.
- The job folder holds the ask, the plan, the briefs, the reports, your gates and `tree.json`, the reopen record.
- Messages go only through Core. A Core job has no follower terminal, inbox files or hooks ([Messages](CORE-NATIVE.md#messages)).

## Check the computer first

Check the computer once with `herdr-doctor`, then start the job from the repo. The last backend line says where a job can run.
This run was on a Mac with Herdr 0.9.5 installed but no Herdr server for that home, against Herdr Core 0.1.20 running in a scratch session named `probe1`:

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
With both usable, the line is `ok backend tui,core`. Everything it checks: [SETUP, Health check](SETUP.md#health-check) and [Herdr Core](SETUP.md#herdr-core).

## One Core job, start to finish

These commands ran against the test suite's fake `hc` in a scratch home. `J` stands for the job folder.

**Start.** The front door starts the job from the repo with `--core`. The job folder is in the jobs root, as on the TUI, with the repo in `<job>/workdir`.
The lead starts as a root terminal labelled with the space's name (`--space`, by default the job's slug):

```console
$ cd ~/code/my-app && stampede new --core --file ask.md --name add-health
on Herdr Core (--core), repo ~/code/my-app
hook pre-push installed in ~/code/my-app/.git/hooks/pre-push: a job's agent cannot push to the default branch without the gate
STARTED lead-add-health (t1)
lead-add-health ~/code/herdr-jobs/jobs/2026-11-14-local-add-health
```
**Helpers.** The lead writes `plan.md` and starts its helpers. A helper's role is its name up to the first `-`. The role gives its kind, model and effort, from the settings `roles.<role>`.
Here `build-health` is a Claude builder at medium effort, and `review-health` a Codex reviewer, also at medium (every worker's default). `--kind`, `--model` and `--effort` override them. Any CLI runs as a program:

```console
$ J=~/code/herdr-jobs/jobs/2026-11-14-local-add-health
$ stampede start $J build-health --brief $J/briefs/build-health.md --report reports/build-health.md
STARTED build-health (t2) under lead-add-health
$ stampede start $J review-health --brief $J/briefs/review-health.md
STARTED review-health (t3) under lead-add-health
$ stampede start $J lint -- npm run lint
STARTED lint (t4) under lead-add-health
```
**The cap.** At most 12 helpers work at once in one lead's tree, at any depth (the setting [helpers.max](CONFIGURE.md#every-key-with-its-default)).
This job's cap is 3, so a fourth start waits in the queue. The lead runs `stampede next` when a child's note says it is done:

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
**The layout** is labels only: Core itself has no tabs. The lead is pane 1 of tab `main`, top left. Helpers fill `main`, `main-2` and so on, 4 live terminals to a tab (`STAMPEDE_TAB_PANES`), or a workstream tab named with `--tab <label>`.
A tab is a 2x2 grid by default (the setting `helpers.layout`: `grid`, `columns` or `rows`). The lead and every helper also carry `herdr.space` and `herdr.tab`, so the Herdr app can show the job as one space.
Every label: [Layout labels](CORE-NATIVE.md#layout-labels); `stampede tree --json` gives the same to a client.

**Waiting and messages.** The lead waits with Core, never with sleep or a poll (checking again and again). With nothing else to do, it ends its turn. Core types each child's news and each message into its terminal, and that wakes it.
To wait inside a command, it runs `hc wait --children any --timeout <seconds>`. A helper reports with `hc send <parent address> "build-health: done reports/build-health.md"`: one line and the path of its result file, which the lead then reads ([Messages](CORE-NATIVE.md#messages)). Your words reach the lead through `tell`:

```console
$ stampede tell $J lead "The owner says: keep the route at /health"
SUBMITTED lead-add-health (t1)
```
**Questions and gates.** A question for you, or a gate, goes out with `stampede ask`. On a Core job the answer comes back through Core, typed into the lead's terminal (the phone here):

```console
$ stampede ask $J "Keep the route at /health?" --option Yes --option No
ASKED 188e888a8640 (Core types the answer into the lead's terminal; cancel with: stampede cancel $J 188e888a8640)
$ stampede ask $J --gate --kind merge --sha <commit> --pr 12 "merge PR #12"
ASKED 439e979b6d65 (Core types the answer into the lead's terminal; cancel with: stampede cancel $J 439e979b6d65)
GATE 8b6cf83c386c on the phone; act after stampede gate-ok $J 8b6cf83c386c --sha <the commit you act on> prints APPROVED
```
A message from an agent arrives in a terminal as `<hc from="t7 name">...</hc>`. A plain program's arrives as bare text. Neither is ever your approval.

A CI wait (waiting for the online tests of a PR) or a build is a plain child of the lead, started with a bare `hc run`: `hc run --bg --name wait-ci-<pr> -- gh pr checks <pr> --watch`.
It is in the tree by its parent link alone, carries no stampede label and never counts against the cap. When it exits, Core's note tells the lead.

**Close.** Only your recorded yes counts for a gate ([Safety](SAFETY.md)). When the job is done, the lead runs `stampede finish $J "<summary>"`, and closes the job on your yes.
Here the owner closes the job before it is finished, so it can be reopened to work again:

```console
$ stampede close $J review-health
CLOSED review-health (t3)
$ stampede close $J
CLOSED build-health (t2)
CLOSED lint (t4)
CLOSED docs-health (t5)
CLOSED lead-add-health (t1)
```
- `close` ends a subtree leaves first: politely when an agent is idle or done, else by killing its terminal.
- A helper closed by name stays closed at a reopen.
- With no agent named, `close` ends the whole job, the lead last. It writes `<job>/closed`, so the watchdog raises no alarm.
- Closing a whole job is always your call. It is refused from a terminal inside the subtree it would end.

**Reopen.** stampede keeps `tree.json` up to date at every step. After a crash, a reboot or a close of a job not yet finished, `stampede reopen $J` (or `bash $J/reopen.sh`) brings back what is not live.
It starts parents first, each in its recorded tab and pane, and removes `closed`. Here `review-health` stays closed, since it was closed by name. The lead's and build-health's Claude sessions had run; docs-health's never did:

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
- A reopen never hands out work by itself. The lead comes back first, with one line saying it was reopened.
- A Claude helper whose session ran comes back resumed and idle, and waits for the lead's word.
- What would start work again goes through the queue and the cap: a Claude helper whose session never ran, `--fresh`, `--rerun-programs`.
- A Codex helper is `SKIPPED` without `--fresh`. The details: [Reopen and close](CORE-NATIVE.md#reopen-and-close).

A finished job reopens for reading only, so work that would start again is refused:

```console
$ stampede finish $J "added /health with a test"
FINISHED ~/code/herdr-jobs/jobs/2026-11-14-local-add-health
$ stampede reopen $J --fresh
stampede reopen: the job is finished, so it reopens for reading only: --fresh and --rerun-programs would start its work again
```
## The earlier path: `--core --relay`

`stampede new --core --relay` starts a Core job the earlier way: a follower terminal per job, inbox files and hooks. It is deprecated (on its way out) and goes in the next minor release.
Until then, it is the one way to hand Cursor, Hermes or Kimi workers to Herdr TUI panes. Its reference: [references/core-relay.md](../skills/herdr-fleet/references/core-relay.md).
