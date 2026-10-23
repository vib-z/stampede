# Stampede, lean: one plan, one approval, then run

Date: 21 Oct 2026. Status: approved by the owner as a design; not built.

## Where it lives

The owner's decisions, 21 Oct 2026:
- **Home: the owner's private skills,** the ones the owner already uses every day and gives to Grok Bot: `herdr-fleet` runs the job and `grokbot-herdr` is the bot's front door. `fleet-plan`, with its HTML page and lanes table, was never used, so it is left out: the lead writes the plan itself as a short `plan.md`. The lean version folds into them: they gain the few pieces below that the runs proved (hook wakes, non-blocking questions, the handoff, the fixes), and a new small skill, `share-plan`, shows that `plan.md` only when the owner asks. (Naming these skills here is the owner's call of 21 Oct 2026, overriding the repo's no-private-skill-names rule for this design.)
- **Stampede becomes the public version** of those skills afterwards: the same content without anything personal, plus its README, install and config.
- **Plan and go by default.** The lead plans and then executes at once. It shares the plan and waits only when the owner explicitly asks to see it ("share the plan first"). That ask is its own small skill, `share-plan`, which the other skills name in one line; without the ask it never loads. Gates (merges, spending, sending, publishing, closing) still wait for the owner's own yes either way.

## Why

Three dogfood runs on real jobs (19 to 21 Oct 2026) showed where the time goes:
- **Stops between steps.** A gated job stopped the owner for the plan, then again for the team. A merge typed in the lead's pane waited 6 h 37 min while the owner looked for the pane.
- **Too many small agents.** Run 3 used 8 agents for 15 tasks; its shortlist went through 5 review rounds.
- **Rounds.** A round waited for the whole round before it, so free work sat behind a blocked lane, and a plan that tried to start it early was refused.
- **The lead's time.** Briefing, starting and checking many small lanes made the lead the slowest part of the job.

Models are now good enough to take bigger pieces of work with less hand-holding. The lean version keeps what worked (hooks that wake agents, one owner contact, gates on the owner's own tap) and cuts the rest.

## The shape

The owner asks at a front door. A lead runs the job. Panes report to the lead. The lead reports to the owner.

```
front door  ->  lead  ->  panes (only when it's worth it)
     ^            |
     +--- owner <-+   plan, questions, gates, report
```

## Front doors

A front door is anything that can run a command on the machine where Herdr runs:
- a chat in Herdr;
- Claude desktop, Codex desktop or Cursor;
- Grok Bot, over SSH and Tailscale; ChatGPT Dots the same way once it can be woken by a webhook.

Every front door does the same two things: write the ask to a file, and run `stampede new --file <ask.md> --name <slug>`, which starts the lead in its own Herdr pane, in auto mode, with its hooks. It then tells the owner the lead's name and steps back. It never plans or runs the job itself.

The machine is either the owner's own (setup A: the bot reaches it over SSH) or the bot's own computer (setup B: Herdr, the agent CLIs, their logins, keys and a signed-in browser live there). The flow is the same; only setup differs.

## The flow

1. **Plan.** The lead reads the ask, the repo and any context, and writes one file, `<job>/plan.md`:
   - a header: the job, the goal in one sentence, the number of agents, a time estimate, the stops;
   - **Layout:** workspace, then tabs, then panes, each pane with its agent CLI, model and effort;
   - **Plan:** the tasks in the lead's own words, each with the pane that does it and what it waits for (`after 3`);
   - **Questions:** only what the owner alone can answer, each with a safe default;
   - **Gates:** the actions that will need the owner's yes.
2. **Go, by default.** Unless the owner asked to see the plan, the lead goes straight on to step 5. The plan stays in `plan.md`, so the owner can read it at any time, and the front door says in one line that the job has started and where its plan is.
3. **Review, only when asked.** When the owner's ask says to share the plan first, the front door starts the job with `stampede new --review`. The lead then ends its turn after writing `plan.md`, opening no pane and starting no agent. The new file reaches the front door, which sends it to the owner (Grok Bot posts it in the chat; a desktop app or Herdr chat opens it; Moshi pings the phone).
4. **Approve or change** (review jobs only).
   - A change goes to the lead in the owner's words (`stampede tell`); the lead rewrites `plan.md` and the loop repeats.
   - Approve runs `stampede approve <job>`: it writes `Approved: <when> by <front door>, plan <sha256 of plan.md>` and wakes the lead. If the lead changes the plan after approval, it asks again.
5. **Run.** The lead opens the panes the layout names and runs the job.
6. **Deliver.** One review on another model for what ships, each gate on the owner's own yes, a short report, then the close question.

In a review job, opening panes and starting agents is locked: stampede's own start command refuses until the approval line exists and its fingerprint matches `plan.md`. This holds for every agent CLI. Work done before approval stays on the job's own branch, where git can undo it.

Plan mode was tested and dropped (21 Oct 2026, Claude Code 2.1.306, Codex 0.163, Cursor 2026.10.19). Each CLI's plan mode works, but each needs its own start, its own way to get the plan out and its own keys at its approval dialog, and Herdr flags only Claude's dialog as `blocked`. Keys sent into another agent's dialog also proved risky: one extra Enter approved a revised plan nobody saw. A plan file, a recorded approval and a locked start do the same job the same way for all three.

## Auto mode per CLI

Every lead and worker runs in its CLI's automatic-review mode, never in a mode that skips checks:

| CLI | Auto mode | Never (no checks) |
|---|---|---|
| Claude | `--permission-mode auto` | `--dangerously-skip-permissions` |
| Codex | `--approve-for-me` | `--yolo` |
| Cursor | `--auto-review` | `--yolo`, `--force` |

The automatic reviewer, with the gate check under Reaching the owner, is what keeps an agent's own yes from merging or spending.

**Yolo, case by case (the owner's call, 21 Oct 2026):** a worker that runs in its own git worktree may start in its CLI's no-checks mode (`--yolo` on Codex and Cursor, `--dangerously-skip-permissions` on Claude), because the worktree confines its files to its own branch. `fleet-job start --yolo` refuses unless the pane's folder is a linked worktree, and it never applies to the lead. The worktree does not wall off the network or the owner's logins, so the worker's brief still forbids pushing to a shared branch, merging, spending and publishing. Cursor's auto mode still asks about anything it is unsure of, so Cursor is a worker on its own branch with an allowlist, not a lead. The lead is Claude by default, Codex when the owner asks.

## When the lead opens a pane

The lead does the work itself by default. It opens a pane only when the pane pays for itself:
- **Parallel pieces:** two or more pieces of different work that can run at the same time, each over about 30 minutes. At most 4 such panes per lead.
- **Another model or tool:** for example Codex for images.
- **One reviewer** on a model other than the builder's (see Review).
- **The same task many times** (10 forms, 10 quotes, 10 sites): one pane per item, all with the same short brief and the item filled in, on a cheaper model. They run 6 at a time by default (`STAMPEDE_FANOUT_LIVE=6`); the next starts as one finishes. Panes go in tabs of up to 6. In the layout they show as one line: `10 x quote-<insurer>, tab quotes`.
- **A sub-lead, rarely:** for more than 10 items, or a workstream with 3 or more parallel pieces of its own. It gets its own tab, runs it the same way, and gives the lead one summary.

Every pane reports to the lead by its report file and hook, never by polling. A worker exits once its work is merged or accepted, so its row in the Claude app archives itself; its session stays resumable.

## Review

- One review on another model, of what ships or reaches the owner: code before a merge, site changes, anything sent or published, reports the owner will act on.
- At most 2 rounds. After that the lead fixes what is left itself, or brings it to the owner with the reviewer's notes.
- Notes passed from one agent to another are not reviewed on their own; the review of the result covers them.
- Anything touching terms of service, money or law is checked as it happens, not only at the end.

## Reaching the owner

Answers come back where the owner asked:

| Asked from | Plan, questions, gates and report arrive in |
|---|---|
| a chat in Herdr | the lead's pane, plus a Moshi ping |
| Claude desktop | the lead's row in the Claude app (Remote Control), plus a Moshi ping |
| Codex desktop or Cursor | Moshi, since those apps cannot be woken by another agent |
| Grok Bot | the Grok chat: the webhook wakes the bot, it asks, and it passes the answer back with `stampede tell`, or a gate's yes with `stampede approve-gate` |

Moshi works with every front door, so nothing waits on an app the owner closed.

Gates go back to whoever started the job (the owner, 23 Oct 2026: "If any Grok Bot starts the job, then [gate questions] go back to the Grok Bot, otherwise Moshi is fine"). Herdr is the core; Moshi is the optional extra.
- `stampede new` records the starting bot in `<job>/owner`: `HERDR_EVENTS_OWNER`, else the workspace's owner tag. No bot means a job started locally.
- The lead asks each gate with `stampede ask <job> --gate --sha <commit> [--pr <n>] "<exact action>"`: one action at one commit, yes or no. It writes `<job>/gates/<id>.json` and does not block.
- **Started by a bot:** a `gate` event (job, gate id, exact action, PR, commit, options yes and no) goes to that bot through the event relay. The bot asks the owner in chat and, on a yes, runs `stampede approve-gate <job> <id> --sha <commit> --by "owner in <bot> chat"` over SSH. That refuses inside Herdr (a pane's environment or a process under the Herdr server), for a local job's gate and for another commit, and records the yes in `<job>/gates/<id>.approved`.
- **Ordinary questions follow the same route:** in a bot-started job, `stampede ask` without `--gate` is a `question` event to that bot, answered with `stampede tell`; in a local job, a Moshi card as before. Both go only through that bot's own route, or the lead sees a refusal; one queued while the route has no URL waits up to 24 h, and the lead hears `UNDELIVERED` when it is held and if it expires.
- **Started locally:** the question goes to `FLEET_ASK_CMD` (Moshi), and fleet-job records the owner's tap the same way; or the lead's own question card.
- **Either way,** a yes the owner types in the lead's Herdr pane counts.
- The lead acts on a recorded yes only after `stampede gate-ok <job> <id> --sha <the commit it acts on>` prints `APPROVED`, and merges with `--match-head-commit` on that commit. A push after the yes withdraws it: the gate is asked again.
- An agent's own say-so never counts, nor a yes passed on with `stampede tell` or typed into a pane by a bot. The job folder belongs to the same user as the agents, so the record stops mistakes, not a determined forger; auto mode is the boundary. A signed approval from the bot's own computer is the upgrade.

Plan approval is not a gate: it lets the lead work inside the job's own folder and branch, with nothing leaving the machine and nothing spent, so the front door may carry it.

## What goes

- Steps 3 (roles), 4 (orchestrate) and 5 (review app) as steps: the lead's one plan replaces them. The roles library stays as reference the lead may read.
- Rounds, checker badges, cards and per-task checks.
- The review app as a step. It stays as an optional page for dragging a plan around.

## Fixes carried over

- **Wake on every change.** A report rewritten after a review wakes the lead again, not only its first version (3 misses in run 3).
- **Cancel stops the whole ask.** Cancelling a question stops its waiter and its `moshi-hook` child, so no answered card stays on the phone.
- **One workspace per job**, so one job's reopen snapshot cannot overwrite another's.

## Not in this round

- Reporting to Herdr that Codex's "Implement this plan?" and Cursor's "Ready to build?" dialogs read as `idle` and `done`, not `blocked`. Posting it needs the owner's yes.
- ChatGPT Dots, until it has a webhook.
- Codex and Cursor as leads beyond the basic flow.

## Testing

- Plan and go: a job started without `--review` writes `plan.md` and starts its panes with no stop.
- The review loop end to end with fakes: with `--review`, a new `plan.md` reaches a fake front door, `stampede approve` records the fingerprint, the start command refuses without it and refuses a changed plan.
- The fan-out cap: 10 items with a cap of 6 never run more than 6 at once.
- The wake on a rewritten report.
- Cancel stops the whole ask process tree.
- Gate routing: a bot-started gate posts a `gate` event; `approve-gate` records the yes for that commit; a stale commit, a call from inside Herdr and a local job's gate are refused; a local gate asks `FLEET_ASK_CMD`.
- One live gated job from Grok Bot and one from a Herdr chat before release.
