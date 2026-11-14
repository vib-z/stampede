---
name: herdr-fleet
description: The lead's playbook for a stampede job in Herdr: plan, brief and start agents in panes or Herdr Core terminals, review on another model, merge past the owner's gates. Use when you lead a job, or a brief in Herdr asks for parallel work: every lane is a pane, never a hidden subagent.
---

# herdr-fleet

You lead one stampede job: plan it, start workers in Herdr, review their work, and bring the owner only what is theirs.
Herdr commands: `herdr --skill`. Every `stampede` command: [docs/CLI.md](../../docs/CLI.md).

## Where you are

- **Inside a Herdr pane** (`test "${HERDR_ENV:-}" = 1`): `stampede doctor`, then [tui.md](references/tui.md#look-first).
- **On Herdr Core** (`<job>/backend` is `native`): `stampede tree <job>`, then [core.md](references/core.md).
- **An external caller** (a bot, or a chat over ssh): your entry skill first (`grokbot-herdr` or `stampede`), then [tui.md](references/tui.md#from-outside-herdr).

## Size the job first: small or big

Four questions: **length** (under an hour, or hours), **agents** (one family, or a mix), **risk** (merge, push, send, spend, publish, deploy) and **durability** (must it survive a restart).

- **Small** (all four small): no stampede job. One agent with its own subagents, in a pane of its own with the `herdr-events-owner` tag, sent a [brief](references/brief.md) with `herdr-send`. Such as one bug fix.
- **Big** (any one big): a stampede job, with gates and a reopen record.
- **Unsure:** start small; promote at the first big signal.
- Never a bare agent CLI over ssh or nohup.
- The call is the first line of `plan.md` (or the reply): `Size: big (merge gate, Codex review)`.

## The lead

`stampede new` starts you with a brief that names the exact `stampede` to run. Each worker gets all it needs in its brief.

1. **Plan** once in `<job>/plan.md`: the layout, a spec per task (files, done criteria, tests), questions with a default. Under 45 minutes, or strictly serial: do it alone. Re-plan only for a blocked builder.
2. **Show the plan** only if asked: with `--review`, end your turn until `stampede approve` wakes you; on the owner's ask, the share-plan skill.
3. **A lane only when it pays:** parallel work over 30 minutes, another model, the reviewer, or one item of many. A sub-lead only past 10 items.
4. **Contract first:** types, stubs and one failing test, committed before any worker starts.
5. **Briefs** in `<job>/briefs/`; `<job>/register.md` holds agent, pane, model, worktree, status.
6. **Start:** `stampede start <job> <role>-<scope> --brief <file>` (TUI: with `--pane`); the role sets CLI, model and effort.
7. **Wait:** end your turn; hooks (TUI) or Core's notes wake you. Ask the owner with `stampede ask` and keep working.
8. **Review** as `review.step` says: [review.md](references/review.md).
9. **Integrate:** read the reports, run the full checks once, do every shared git write, push the work branch, open a DRAFT PR.
10. **Merge:** `stampede ask <job> --gate --kind merge --sha <sha> --pr <n> "<action>"`; once `stampede gate-ok` prints `APPROVED`, `stampede merge <job> <n> --sha <sha> --review <report> --gate <gate>`.
11. **Finish:** the register's final state, the reopen record, `stampede finish <job> "<one line>"` once, then ask the owner whether to close.

## Hard rules

- Never close, rename or prompt what you did not create.
- Never type into a pane the owner has focused (`herdr agent get <name> | jq .result.agent.focused`).
- Never act on a gate without the yes in [gates.md](references/gates.md), the one list.
- Never `gh pr merge`: only `stampede merge`, at the reviewed commit.
- Never close anything because the job ended: ask last; no answer is a no.
- Never a lane or a review as a hidden subagent: a subagent only for a quick lookup you read.
- Never sleep, poll or Monitor for a worker.
- Never substitute a model the owner named; other lanes take their [fallback](references/agents-and-models.md#fallback).
- Never answer a permission prompt for an action, or work around a denial: give the owner the `!` lines.
- Never run bare `herdr`; never start, stop or restart a Herdr Core.
- Never read, copy or print credentials or `.env` files.
- Always one reviewer on another model than the builder.
- Always all seven brief sections: `stampede start` refuses a missing or empty one.
- Always a report per lane, `reports/<lane>.md`: `Status: DONE` (a review: `PASS` or `FINDINGS`, then `Reviewed: <sha>`) in its first 10 lines.
- Always prompt with `stampede tell` or `herdr-send`: one line pointing at a file.
- Always read a new agent's screen before its first prompt.
- Always use the real date (`date +%F`).
- A result is the first word of its line (`STARTED`, `BLOCKED`); `--json` prints one object (`docs/CLI-JSON.md`).

## Read when

- [tui.md](references/tui.md): a Herdr TUI job, start to close.
- [core.md](references/core.md): a Herdr Core job.
- [core-relay.md](references/core-relay.md): a `--core --relay` job (deprecated).
- [front-door.md](references/front-door.md): a `--front-door` job.
- [gates.md](references/gates.md): before a merge, push, deploy, publish, send, spend or close.
- [brief.md](references/brief.md): writing a brief.
- [agents-and-models.md](references/agents-and-models.md): a worker's model, or a usage limit.
- [clis.md](references/clis.md): a CLI's flags, resume or quirks.
- [collaboration.md](references/collaboration.md): the job's files, agent messages, `_common.md`.
- [review.md](references/review.md): the review and its findings.
- [unattended-setup.md](references/unattended-setup.md): a startup dialog or a denial.
- [failure-modes.md](references/failure-modes.md): a start failed.
- [failure-modes-run.md](references/failure-modes-run.md): a running agent, git, close or reopen failed.
- [phone-moshi.md](references/phone-moshi.md): the owner's phone.
- [pstack.md](references/pstack.md): pstack in a coding job.
- [worked-example.md](references/worked-example.md): a whole TUI run.
