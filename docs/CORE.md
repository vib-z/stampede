# Herdr Core

[Herdr Core](https://herdr.dev/core/) (`hc` 0.1.13 or later; checked against 0.1.20) is Herdr's terminal runtime: programs in persistent terminals that report their own status (OSC 7501), with parent links, labels and an event stream, and no workspaces, tabs or panes. `stampede new` runs a job there the way Core itself works: Core holds the tree of terminals, and stampede adds only the space's name, the owner tag, the reopen record, the owner's gates, a cap on helpers and the layout labels.

A job runs on the Herdr TUI by default, and on Herdr Core only when asked: `--core` on `stampede new`, or the setting `backend`. `backend` is `tui` by default; `core` makes Core the standing choice, and `auto`, if you set it, runs a job on the TUI inside a Herdr pane and on Core anywhere else, saying so on the first line. `--pane` or `--workspace` is always the TUI. With the default, `new` outside a Herdr pane with no `--core`, `--pane` or `--workspace` is refused and makes nothing. The shape a client reads (labels, parent links, events): [docs/CORE-NATIVE.md](CORE-NATIVE.md). The lead's playbook: [references/core.md](../skills/herdr-fleet/references/core.md). For Core's own basics read `hc --skill`.

**The tree and the roles.**
- **The owner** asks, answers questions and gives every gate's yes.
- **The front door** writes the ask, runs `stampede new --core`, passes the owner's words to the lead with `stampede tell <job> lead "..."` and records a gate's yes with `approve-gate`. It reads the lead or a helper with `hc read <address>` and never types into one. A chat outside Herdr adds `--front-door`, as on the TUI ([Front door](CORE-NATIVE.md#front-door)).
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

With both usable the line is `ok backend tui,core`; `--core` or `--tui` checks one only, each gap a `PROBLEM`. On Herdr Core it also warns about an `hc` older than 0.1.20, old terminals on macOS and a core started from inside an agent ([Troubleshoot](TROUBLESHOOT.md)). It never starts, stops or restarts a core.

## One Core job, start to finish

These commands ran against the test suite's fake `hc` in a scratch home (`<repo>` stands for the repo's path, `J` for the job folder). The front door starts the job from the repo with `--core`. The job folder is in the jobs root, as on the TUI, with the repo in `<job>/workdir`. The lead starts as a root terminal labelled with the space's name (`--space`, by default the job's slug):

```console
$ cd ~/code/my-app && stampede new --core --file ask.md --name add-health
on Herdr Core (--core), repo ~/code/my-app
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

The layout is labels only. The lead is pane 1 of tab `main`, top left, and helpers fill `main`, `main-2` and so on, 4 live terminals to a tab (`STAMPEDE_TAB_PANES`), or a workstream tab named with `--tab <label>`, in a 2x2 by default (the setting `helpers.layout`: `grid`, `columns` or `rows`). The lead and every helper also carry `herdr.space` and `herdr.tab`, so the Herdr app can show the job as one space. Every label: [Layout labels](CORE-NATIVE.md#layout-labels); `stampede tree --json` gives the same to a client.

The lead waits with Core, never with sleep or a poll. With nothing else to do it ends its turn: Core types each child's news and each message into its terminal, and that wakes it. To block inside a command it runs `hc wait --children any --timeout <seconds>`. A helper reports with `hc send <parent address> "build-health: done reports/build-health.md"`: one line and the path of its result file, which the lead then reads ([Messages](CORE-NATIVE.md#messages)). The owner's words reach the lead through `tell`:

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

Gates are as everywhere on Core: only the recorded yes counts ([Safety](SAFETY.md)). When the job is done the lead runs `stampede finish $J "<summary>"`, and on the owner's yes closes it. Here the owner closes the job before it is finished, so it can be reopened to work again:

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

A reopen never hands out work by itself. The lead comes back first and gets one line saying it was reopened; a Claude helper whose session ran comes back resumed and idle and waits for the lead's word. What would start work again (a Claude helper whose session never ran, `--fresh`, `--rerun-programs`) goes through the queue and the cap. A Codex helper is `SKIPPED` without `--fresh`. The details: [Reopen and close](CORE-NATIVE.md#reopen-and-close). A finished job reopens for reading only, so work that would start again is refused:

```console
$ stampede finish $J "added /health with a test"
FINISHED ~/code/herdr-jobs/jobs/2026-11-14-local-add-health
$ stampede reopen $J --fresh
stampede reopen: the job is finished, so it reopens for reading only: --fresh and --rerun-programs would start its work again
```

## The earlier path: `--core --relay`

`stampede new --core --relay` starts a Core job the earlier way: a follower terminal per job, inbox files and hooks. It is deprecated and goes in the next minor release; until then it is the one way to hand Cursor, Hermes or Kimi workers to Herdr TUI panes. Its reference: [references/core-relay.md](../skills/herdr-fleet/references/core-relay.md).
