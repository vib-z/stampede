---
name: herdr-fleet
description: The owner's playbook for running a multi-agent fleet in herdr. One workspace per project, a tab per workstream and a pane per agent, so the owner can watch everything. A lead agent writes briefs, starts Claude or Codex agents on models matched to each task, monitors them, runs review loops and integrates the result. Use when asked to run agents in parallel in herdr, spin up a fleet or team of agents, delegate work to Claude or Codex agents in panes, act as the lead or orchestrator of a workspace, get agents to review or talk to each other, or pick agents and models for a multi-agent job. Also use whenever a brief inside a Herdr pane asks for work in parallel (research, ideas, builds, reviews): every lane runs as a Herdr pane, not a built-in subagent. Builds on the built-in herdr skill (`herdr --skill`), which covers single commands and pane control.
---

> **Name:** Rancher is the official name of this skill. Herder Fleet (`herdr-fleet`) is the legacy alias; the folder and all references stay `herdr-fleet` so existing callers keep working.

# herdr fleet

The built-in skill (`herdr --skill`) is the command reference. This is how the owner runs teams on top of it. The installed binary is the authority (herdr 0.9.4 when written, 2026-10-14): check syntax with `herdr agent`, `herdr pane`, `herdr tab`, `herdr workspace`. Never run bare `herdr` (it attaches the TUI).

> **Strict rule for bots launching jobs from outside Herdr (Grok Bots, executors):** tag the workspace with `herdr-events-owner <ws> <bot-slug>` before any agent starts, then launch and exit. Never poll or wait on a job: no `herdr agent wait` for its result, sleep loops, repeated pane reads or monitoring executors (bounded startup checks, as in grokbot-herdr Step 4, are fine). The done or stuck event is relayed to the owning bot, which reads the result once. See grokbot-herdr. This rule is for bots only; a lead inside Herdr is woken by hooks instead (The lead, item 6).

## Where are you?

- **Inside a Herdr pane** (`test "${HERDR_ENV:-}" = 1` succeeds): use `$HERDR_WORKSPACE_ID`, `$HERDR_PANE_ID` and `--current` as written below.
- **External caller** (a bot or a session on another machine, reaching the Mac over ssh): first run your entry skill (connect, health check, workspace by label, safe start; for the bots that is `grokbot-herdr`). Skip the `HERDR_ENV` check and never set it. Everywhere below, replace `$HERDR_WORKSPACE_ID`, `$HERDR_PANE_ID` and `--current` with literal ids (e.g. `w1`, `w1:p1`). Variables inside single-quoted ssh commands expand on the Mac, where they are empty. Run herdr ON the Mac over ssh, never `herdr --remote` or `--machine` from the other machine (this Mac has no saved machine profiles). Only the owner's own machines, never a work machine. Report in your own chat, not in a lead pane.

Read live state before changing anything (`<ws>` is `$HERDR_WORKSPACE_ID` inside Herdr, the literal id outside):

```bash
herdr workspace list
herdr tab list --workspace <ws>
herdr agent list | jq -r '.result.agents[] | "\(.pane_id) \(.name // "-") \(.agent) \(.agent_status)"'
```

## Size the job first: small or big

Before opening any Herdr workspace, size the job on four questions: **length** (one sitting of under about an hour, or hours or overnight), **agents** (one agent family, or a mix such as Claude plus Codex, Cursor or another model), **risk** (does anything leave the machine: merge, push, send, spend, publish, deploy) and **durability** (must it survive a restart, or would the owner want to look in halfway).

- **Small** (all four small): no stampede job. Run it as one agent session with its built-in subagents, but still inside Herdr: its own pane (in the project's workspace, or a new workspace) with the `herdr-events-owner` tag, prompted with `herdr-send`, so the work stays organised and its finish arrives as an event. No extra panes and no reopen record. Never run a job as a bare agent CLI call over SSH or nohup outside Herdr. This is the answer to "why not subagents": for a small job, use them. Examples: find where a feature lives and explain it; review one PR from a few angles; fix one bug with its test; compare three pricing pages; a rename or docs tidy.
- **Big** (any one big): run it as a stampede job under the rules below, with gates and a reopen record (and an owner tag when a bot starts it). Examples: a research, writing and review run for a long document; a feature to PR with a cross-model review and a merge gate; a batch of images or videos with review; an overnight or multi-repo job; anything that sends, spends, publishes or deploys.
- **Unsure:** start small, and promote to big the moment a big signal appears (a merge or send is needed, it runs long, a second agent family is needed).
- Write the decision and the reason as one line at the top of `plan.md` (or in the reply when small), e.g. `Size: big (merge gate, Codex review)`.

Inside a big job, "Panes, not built-in subagents" still applies: subagents there are only for quick lookups the lead reads itself.

## The shape

- **Workspace = project or initiative**, one label per repo or initiative. Reuse the project's workspace if it exists. Otherwise: `herdr workspace create --cwd <repo> --label <project> --no-focus`.
- **Tab = workstream** (`billing`, `compare`, `research`, `review`). The lead sits in the workspace's first tab. `herdr tab create --workspace <ws> --cwd <dir> --label <workstream> --no-focus`.
- **First tab rule:** `workspace create` already makes tab 1 with a root pane. Never leave it empty: use it for the first workstream (`herdr tab rename <tab> <label>` on the returned `.result.tab.tab_id`, and put the lead or first agent in `.result.root_pane.pane_id`), and only `tab create` for further workstreams. Before creating tabs in an existing workspace, list its tabs; rename a leftover empty default tab and use it. When the owner says yes to closing (Wrap up) and you created the workspace, close the whole workspace (`herdr workspace close <ws>`), not tab by tab, so no stray tab 1 is left.
- **Pane = one agent**, labelled with its name (`herdr pane rename <pane> <name>`). At most 4 panes per tab on the laptop, 6 on a big monitor. Open another tab rather than shrink panes.
- **Agent names** are `<role>-<scope>`. Roles: `lead`, `build`, `research`, `review`, `design`, `qa`, `copy`. Examples: `build-api`, `review-api`, `research-pricing`. Must match `[a-z][a-z0-9_-]{0,31}` and be unique. Give Claude the same name with `-n <name>` so its session name matches.
- **Geometry**: read the pane's own rect, `herdr pane layout --pane <id> | jq '.result.layout.panes[] | select(.pane_id=="<id>") | .rect'` (`.result.layout.area` is the whole tab). Split right while both halves keep at least 80 columns, else split down while both keep at least 15 rows. Always pass `--no-focus` and an explicit `--cwd`.
- **Never close, rename or prompt what you did not create**, and never type into the pane the owner has focused (`herdr agent get <name> | jq .result.agent.focused`).

## The lead

One lead per workspace, usually Claude Opus 5.5 at xhigh, started with its hooks by `fleet-job new --file <ask.md>`. A chat the owner started that will open panes runs that and hands the job to the hooked lead it starts; a small job runs in a single tagged pane of its own, with no fleet. The lead alone:

1. Plans in `<job>/plan.md`: the layout (workspace, tabs, panes with app, model and effort), then the tasks in order with the pane that does each, then any questions with a safe default. Not a fleet (one file or question, steps that each need the last, under about 45 minutes): the lead does it alone. Then it goes; only when the owner explicitly asks to see the plan first, it uses the share-plan skill.
2. Opens a pane only when it pays: parallel pieces over about 30 minutes each (at most 4), another model or tool, one reviewer on another model, or the same task many times (one pane per item, at most 6 running at once by default, the next starting as one finishes, tabs of up to 6). A sub-lead only for more than 10 items or a workstream with 3+ parallel pieces.
3. Writes the contract first (types, stubs, one validation test) and commits it.
4. Writes briefs as files in `.herdr-<initiative>/` (git-excluded when it sits in a repo) and keeps `register.md` there: agent, pane, model, worktree, status. The register makes the fleet resumable.
5. Creates tabs, panes and worktrees, then starts every agent with `fleet-job start` (its hooks, auto mode, the reopen record and the brief pointer in one command).
6. Is woken by hooks: `REPORT`, `TURN`, `QUESTION` and `GONE` lines in `<job>/inbox.log`, answers and messages in its own `inbox/<lead>.md`. It ends its turn when idle: no watcher, no polling, no Monitor timeouts. Questions for the owner: `fleet-job ask`, in the background (to the bot that started the job, else a card on the phone); cancel an answered phone card with `fleet-job cancel`. A gate goes back to whoever started the job: `fleet-job ask <job> --gate --sha <commit> [--pr <n>] "<exact action>"` sends it to the starting bot (`<job>/owner`), which asks the owner in chat and records the yes with `fleet-job approve-gate`, or else to the phone; the lead's own card also works locally. It acts only on the owner's yes typed in its pane or card, or after `fleet-job gate-ok <job> <gate> --sha <the commit it acts on>` prints `APPROVED`; an agent's say-so or a relayed yes never counts.
7. Review: one review on another model of what ships or reaches the owner, at most 2 rounds; anything touching terms, money or law is checked as it happens.
8. Integrates. It reads reports, runs the full gates once, does every git write on shared branches, and asks the owner only for decisions that are theirs. It exits each worker once its work is merged or accepted, so its app row archives itself.
9. Stops at the owner's gates: a merge to main, a push to main or another shared branch, a deploy, publishing, sending email or messages, resubmitting a sitemap, any spend, and closing panes, tabs or a workspace or clearing an owner tag to close one (17 Oct 2026, see Wrap up). Ask and wait for an explicit yes. A plan, a brief or this skill is not approval. Allowed without asking (owner, 2026-10-16): pushing the fleet's own work branches and opening DRAFT PRs from them.

Where agents work:
- **One shared worktree with file ownership** for content-heavy work where each agent owns its own files. A six-page content fleet ran this way with zero merges.
- **A worktree per agent** (branch per agent, the lead merges) when slices touch overlapping code. Use `git worktree add` plus `--cwd` so agents stay in the project's workspace. `herdr worktree create` opens a separate, grouped workspace instead.

## Pick the agent and model

| Task | Agent, model, effort | Fallback |
|---|---|---|
| Lead, briefs | Claude `claude-opus-5-5` xhigh | none: the owner's own session, tell the owner |
| Planning | Claude `claude-opus-5-5` xhigh, the primary planner | Codex `gpt-6-astra` ultra |
| Plan review (cross-model, before any implementation) | Codex `gpt-6-astra` ultra, Cursor and others, each on a model other than the planner's; then the planner hardens the plan | Codex `gpt-6.1-sol` xhigh or Cursor, never the planner's model |
| Architecture, hard trade-offs | Claude `claude-fable-5-1` max, with a Codex `gpt-6-astra` ultra second opinion | Codex `gpt-6-astra` ultra alone |
| Implementation (against the hardened plan) | Claude `claude-opus-5-5` xhigh, or `claude-sonnet-5-5` for heavy coding the plan fully specifies. Codex `gpt-6.1-sol` xhigh for a parallel slice, `gpt-6-astra` ultra for the hardest one | The other vendor: a Claude lane goes to Codex `gpt-6.1-sol` xhigh, a Codex lane to Claude `claude-opus-5-5` xhigh |
| Independent review, QA | Claude `claude-fable-5-1` max (never the builder's model). Codex `gpt-6-astra` ultra for a cross-vendor pass | The other vendor's reviewer, still never the builder's model |
| Research with the browser | Claude `claude-opus-5-5` xhigh (Neo, treg, MCP tools) | Codex `gpt-6.1-sol` xhigh with `--search` (no Neo) |
| Design direction, design review | Codex `gpt-6-astra` ultra writes or reviews; a Claude builder implements | Claude `claude-fable-5-1` max |
| Image generation, layered HTML images | Codex. Grok only sparingly, for videos and the occasional photo (e.g. a painterly background) | none: wait or ask |
| Docs and copy | Claude `claude-opus-5-5` high | Codex `gpt-6.1-sol` high |
| Quick mechanical edits | The lead itself if under 10 minutes. Else Claude `claude-sonnet-5-5` medium or Codex `gpt-6.1-sol` medium | The other of those two |

Routing as of 2026-10 (the owner's call): Opus 5.5 plans; reviews follow The lead, items 1 and 7; Opus 5.5, Sonnet 5.5 or Codex `gpt-6.1-sol` implement; Codex makes images. Mix and match within the table. Where older notes disagree, this table wins. Other skills point here when they run inside a fleet.

Never substitute a model the owner named. **Fallback:** when a lane's agent hits a usage limit, or "at capacity" again after one retry, and the owner named no model for that lane, the lead restarts the lane on its Fallback (the plan's `fallback` column if it has one, else the table): exit the agent, start the fallback in the same pane under the same name, and prompt it with its brief plus one line saying it takes over from the stopped agent, whose work so far is on disk (`git status`) and in any partial report. A Claude usage limit covers every Claude model, so Claude lanes fall back to Codex. Note the switch in `register.md` and the report. Where the owner named the model, say so and wait or ask. Reasoning, both CLIs' flags and their gotchas: [references/agents-and-models.md](references/agents-and-models.md).

## Panes, not built-in subagents

Every lane is a Herdr pane with its own agent, so the owner sees it, Moshi reaches it, and the register, watch and review loop cover it. Open a pane for:
- parallel independent work (research, ideas, builds, asset generation) that pays a pane (The lead, item 2), even when the brief does not name a pane for it;
- work on another model family (Codex, Cursor, Hermes) or another Claude model;
- every review: a reviewer is never a subagent of the agent it reviews.

A built-in subagent (Claude's Agent or Task tool, a Codex sub-agent) is only for a quick lookup the lead reads itself: find a file, check a flag, skim one page. A brief that says "in parallel" without naming panes still means panes: name them `<role>-<scope>` (`research-web`, `research-local`) in a tab of their own. Seen 2026-10-17: a promo lead ran both research lanes as hidden subagents because its brief named a pane for every step except research.

## Start an agent

```bash
W=<abs work dir>; B=<abs job folder>
# a new workstream gets a tab; its root pane takes the first agent ...
P=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$W" --label research --no-focus | jq -r .result.root_pane.pane_id)
# ... further agents in that tab split beside it
P=$(herdr pane split --pane <id> --direction right --cwd "$W" --no-focus | jq -r .result.pane.pane_id)
fleet-job start "$B" research-web --kind claude --pane "$P" --brief "$B/briefs/research-web.md" --model claude-opus-5-5 --effort xhigh --report reports/research-web.md   # names the pane; hooks, auto mode, reopen record, brief pointer
herdr agent read research-web --source visible --lines 30   # on BLOCKED: clear the startup dialog (below), then fleet-job tell "$B" research-web "Read <brief>"
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"   # once the launch's agents run, and after every later start: REOPEN.md, reopen.sh
```

For Codex use `--kind codex --model gpt-6-astra --effort ultra`. `fleet-job start` adds `--approve-for-me`, which lets Codex write only inside its cwd, and `--add-dir <job folder>`, so its report lands even from a worktree or another folder.

Agents must start and run with no visit to their pane. That needs the one-time machine setup in [references/unattended-setup.md](references/unattended-setup.md), which the owner runs (agents cannot edit their own permissions). Before starting agents in a repo under `~/code`, pre-trust it with `~/.local/bin/herdr-trust <repo dir>` (owner-approved 2026-10-16; writes the repo's trust into `~/.claude.json` and `~/.codex/config.toml`, so Claude and Codex skip the trust dialog; its worktrees are covered). With that and the setup in place the lead clears the remaining startup dialogs itself: folder trust when one still shows (Kimi and Gemini always ask once), Codex "Update available" (`esc` skips it; the default, Enter, runs npm), Codex "Hooks need review" (continue without trusting) and Claude's "New MCP server found" (continue without). After clearing one, `herdr agent wait <name> --until idle --timeout 30000`, not a sleep. Herdr reports most of these dialogs as `idle`, not `blocked`, so after every start read the screen (`herdr agent read <name> --source visible --lines 30`) before the first prompt. It never answers a permission prompt for an action. Without the setup, or if the classifier still denies a start, do not work around it: finish every other step, then give the owner the exact lines to run as `!` commands.

## Reopen record

Every Herdr job keeps `REOPEN.md` and an executable `reopen.sh` in its job folder (owner's rule, 17 Oct 2026), written by `herdr-reopen-snapshot <ws> <job dir>` (grokbot-herdr/scripts, installed at `~/.local/bin`). They hold the workspace label and owner tag, the job's own tabs (those holding its agents in `agents.tsv`), every pane in them with label and cwd, and each agent's CLI, model, effort, session id, brief and exact start command. `bash <job dir>/reopen.sh` recreates the whole workspace after a close and resumes every agent's session (`--fresh` starts new sessions with the same flags, `--prompt` also re-sends each brief pointer); it refuses while a workspace with that label is open, or when a pane's cwd is gone (a removed worktree: add it back first). Herdr does not know start flags or briefs, so the recipe above records them at every start in `<job dir>/agents.tsv`. Refresh the snapshot after every start or restart and before any close; it keeps agents that already exited.

## Talk, watch, review

- A prompt is one line pointing at a file. The substance lives in briefs and reports. Agent-to-agent messages, Claude peer messaging, the review loop and the ownership rules every brief carries: [references/collaboration.md](references/collaboration.md).
- Before every prompt, `herdr agent get <name>` (idle or done, not focused; an agent at a dialog rejects the prompt with `agent_blocked`). After a `timeout`, `agent_prompt_stalled` or ssh drop, read the screen (`agent read <name> --source recent-unwrapped --lines 40`) before any resend; resend only if the prompt clearly never landed.
- Always prompt agents with `herdr-send <name-or-pane> "<text>"` (grokbot-herdr/scripts/herdr-send, installed at `~/.local/bin/herdr-send`) or `herdr agent prompt`, never `pane send-text` plus Enter (Codex leaves it unsubmitted), and never `ctrl+c` an idle Codex (on an empty prompt it quits). Continue only on `SUBMITTED`; on `FAILED` read the screen before any resend.
- The report file is the completion signal: one per lane, `reports/<lane>.md` with `Status: DONE` (a review: `PASS` or `FINDINGS`) in its first 10 lines, named with `fleet-job start --report`. The lead is woken by hooks (`fleet-job`); `fleet-watch.sh` is only for a bot outside Herdr.
- Known failures and their fixes: [references/failure-modes.md](references/failure-modes.md). A full run with exact commands: [references/worked-example.md](references/worked-example.md).

## The owner's phone (Moshi)

Every agent's questions, approvals and completions already reach the owner's iPhone through Moshi, tagged with the herdr workspace and tab, so name tabs and agents after the task. In a job started locally the lead adds three things: questions through AskUserQuestion (or `moshi-hook ask --require-remote` from a script), one live progress row per fleet (`moshi-hook job start/update/end`, id in `register.md`), and nothing else. For a bot outside Herdr, `fleet-watch.sh` pushes stalls and vanished agents; a lead hears `GONE` through its hooks. Commands and the settings to leave alone: [references/phone-moshi.md](references/phone-moshi.md).

## Wrap up

Integrate, run the gates once, push the work branch and open a DRAFT PR (no need to ask), then ask before any merge (the gates above). Record the reviewed commit in `register.md` (`Reviewed: <sha>`); on the owner's yes (or `gate-ok` for that commit), merge exactly that commit with `gh pr merge <n> --squash --match-head-commit <sha>`. A commit pushed after the review withdraws the yes: rerun the gates (and the review, unless the review rules in collaboration.md say it stands) and ask again. Write the register's final state, refresh the reopen record and tell the owner what is left for them.

**Ask before close (owner's rule, 17 Oct 2026).** Never close a pane, tab or workspace, and never clear the owner tag to close one, automatically when a job ends. Leave everything open; the very last step is a question to the owner: AskUserQuestion inside Herdr in a job started locally (it reaches the phone), or, in a job a bot started, the end of the lead's report and so the bot's chat or done event ("Close workspace <label>? Reopen with <job dir>/reopen.sh"). No answer is a no. Only after the owner's explicit yes, in this order: exit each agent gracefully so its session stays resumable (`/exit` for Claude, Hermes and Kimi, `/quit` for Codex), refresh the reopen record (`herdr-reopen-snapshot <ws> <job dir>`), clear the owner tag (`herdr-events-owner <ws> --clear`), then close only what you created: the whole workspace (`herdr workspace close <id>`) if the fleet created it, else only your own panes and tabs, never one of the owner's project workspaces. Remove only your worktrees, after their panes are closed (keep the branches, so `reopen.sh` can come back to them).

## Official docs
- https://herdr.dev/docs/cli-reference/
- https://herdr.dev/docs/agent-automation/

Re-check both, and `herdr <cmd> --help`, after Herdr is upgraded or when a command fails. Where they differ the installed binary wins (2026-10-16: the docs track 0.9.5, the Mac runs 0.9.4).
