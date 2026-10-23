---
name: grokbot-herdr
description: "FIRST skill to read whenever a Grok Bot needs Herdr on the owner's Mac: handles the remote entry from the box (SSH over Tailscale, health check, workspace lookup, safe agent start), then hands off to herdr, herdr-fleet and moshi-best-practices for the actual work."
---

> **STRICT, every bot:** tag the Herdr workspace with your bot slug before agents start, launch and exit, never poll or wait on a job (no `herdr agent wait` for its result, sleep loops, repeated reads or watcher executors). Act only when the relayed event arrives. Bounded startup checks are fine: `agent start`, `herdr-send` and `agent wait <name> --until idle --timeout 30000` after clearing a startup dialog.
# grokbot-herdr: remote entry to Herdr on the owner's Mac

## First look here
You are a Grok Bot on the box, OUTSIDE Herdr. Before any Herdr work:
1. Read this skill and do steps 1-4 below (connect, health check, workspace, start agent).
2. Then hand off: use `herdr` for ground rules and commands, `herdr-fleet` for fleet shape, roles, model routing and failure-modes.md, and `moshi-best-practices` for the phone side, as written.
3. herdr-fleet's **Where are you?** section covers external callers; keep the **After hand-off** lines at the bottom in force.

## Running from Grok Bot

- Grok Bot runs on a Linux box. Anything that touches the owner's repos, herdr or the Mac runs on the Mac through `ssh <host>` (the SSH alias of the owner's Mac, over Tailscale). If ssh times out, bring Tailscale back up on the box, then retry.
- herdr on the Mac is `~/.local/bin/herdr` (0.9.4 on both machines when written). Run `herdr --version` on the Mac first and treat the Mac's binary as the authority. Run herdr ON the Mac over ssh, never `herdr --remote` or `--machine` from the box: the Mac has no saved machine profiles.
- Never use a work machine. Only the owner's own machines.
- Questions for the owner go to the owner in chat, never into a herdr pane.
- Credentials and env files are not part of this skill: never read, copy or print them, on either machine.
- Approval gate: herdr-fleet's list applies (merge, push to main or another shared branch, publish, deploy, sitemap resubmission, email or messages, spend, and closing panes, tabs or a workspace or clearing an owner tag to close one, 17 Oct 2026). Ask in chat and wait for an explicit yes. A plan, a brief or a skill is not approval. Allowed without asking (owner, 2026-10-16): pushing the job's own work branch and opening a DRAFT PR from it. On a yes to merge, merge only the reviewed commit: `gh pr merge <n> --squash --match-head-commit <reviewed-sha>`. A push after the review withdraws the yes; ask again.
- Then follow herdr-fleet's "Where are you?" external-caller rules: literal ids, never set `HERDR_ENV`, read the screen after every start, report in chat.

## Hard rules
- Target ONLY the ssh alias `<host>`: the owner's own Mac with the owner's own Claude, Codex and Cursor subscriptions. Never a machine on work subscriptions unless the owner asks in chat for that job.
- Run herdr ON the Mac via ssh (0.9.4 on both). Never `herdr --remote`/`--machine` from the box. Never start/stop `herdr server` or the TUI.
- Never touch workspaces, tabs or panes you didn't create (the owner's own project workspaces above all).
- Never poll a running job. After the first prompt and one screen check, end your turn and wait for the webhook event (source herdr, claude, codex or herdr-watchdog; state done, blocked, Stop, StopFailure, agent-turn-complete, stale or dead). Only then read the pane, once.
- Always prompt agents with `herdr-send <name-or-pane> "<text>"` (grokbot-herdr/scripts/herdr-send, installed at `~/.local/bin/herdr-send`) or `herdr agent prompt`, never `pane send-text` plus Enter (Codex leaves it unsubmitted). Never send `ctrl+c` to an idle Codex yourself: on an empty prompt it quits Codex (herdr-send clears only typed leftovers). Continue only on `SUBMITTED`; on `FAILED` read the screen before any resend. If Claude kept the text but dropped the Enter (it can while still drawing its screen), herdr-send presses Enter once and says so; it never does that for a slash command.

## Size the job first
Before creating any workspace, size the job (herdr-fleet, "Size the job first: small or big"). A small job needs no stampede job: do it as one session with built-in subagents in a single Herdr pane of its own, tagged with `herdr-events-owner` and prompted with `herdr-send`, never as a bare agent CLI call over SSH or nohup outside Herdr. Only a big job goes through `fleet-job new`.

## Setup note
Every tagged event goes to the route named after the tag (`~/.config/herdr-events/routes/<bot-slug>`, holding `URL=` and `KEY=`), or to the `default` route when the bot has none (turn events only: a job's questions and gates need the bot's own route file, even when it points at the same webhook); the webhook behind it passes the event to the owning bot as a message. When that message arrives, read the pane once and finish your job.

The relay scripts live in `scripts/` here and are copied to `~/.local/bin` on the Mac (back up the live copy first: `cp -p ~/.local/bin/<s> ~/.local/bin/<s>.bak-<date>`). `herdr-reopen-snapshot` (the reopen record, Step 4 and After hand-off) is copied the same way. Tests: `python3 -m unittest tests.test_herdr_relay tests.test_herdr_send tests.test_herdr_trust tests.test_herdr_reopen_snapshot` from the repo root. What reaches your bot (2026-10-16):
- One event per turn: Herdr `done`/`idle`, Claude `Stop` and Codex `agent-turn-complete` for one pane within 15 s are one event (the first). Claude's "waiting for your input" notice (`idle_prompt`), 60 s after a turn end, is dropped. Permission notices, `blocked`, `StopFailure`, `stale` and `dead` always pass.
- Codex sub-agents, the `--approve-for-me` guardian and Codex's chat-title side conversation never report "done"; only the agent's own turn does.
- After an outage only each pane's newest queued event is delivered; older ones go to `~/.herdr-events/dead/*.superseded`.
- Owner tags for workspaces gone a day, and malformed tags, are removed by the watchdog.

## Step 1. Connect
Every call: `ssh -o BatchMode=yes -o ConnectTimeout=10 <host> '<herdr command>'`. If herdr isn't found, prefix `export PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH;`.

## Step 2. Health check
`ssh -o BatchMode=yes -o ConnectTimeout=10 <host> '~/.local/bin/herdr-doctor --relay'` (read only; checks the herdr server and client, the relay plugin, hooks and launchd jobs, the event queue, owner tags, leftover worktrees and disk; one `ok`, `warn` or `PROBLEM` line each, exit 1 on a PROBLEM).
- Exit 0: go on. Mention any `warn` line in your report; never fix it yourself unless it is yours (your own stale tag or worktree).
- Exit 1: stop and tell the owner the PROBLEM lines (a broken relay means your job's events would never reach you).
- ssh fails -> bring Tailscale back up on the box, then retry once. Still failing -> stop and tell the owner (usually the Mac is asleep/offline).
- herdr server not running or erroring (a `PROBLEM herdr` line) -> stop and tell the owner; don't start it.

## Step 3. Workspace (by name, never env vars)
- Existing project workspace id: `ssh -o BatchMode=yes <host> 'herdr workspace list' | jq -r '.result.workspaces[]|select(.label=="<project>").workspace_id'`
- Bot work: create your own: `herdr workspace create --cwd <repo dir> --label bot-<task> --no-focus`. Record the returned literal ids (`.result.workspace.workspace_id`, `.result.tab.tab_id`, `.result.root_pane.pane_id`, e.g. `wK`, `wK:t1`, `wK:p1`). **First tab rule:** `workspace create` already makes tab 1 with a root pane. Never leave it empty: use it for the first workstream (`herdr tab rename <tab> <label>` on the returned `.result.tab.tab_id`, and put the lead or first agent in `.result.root_pane.pane_id`), and only `tab create` for further workstreams. Before creating tabs in an existing workspace, list its tabs; rename a leftover empty default tab and use it. When the owner says yes to closing (After hand-off) and you created the workspace, close the whole workspace (`herdr workspace close <ws>`), not tab by tab, so no stray tab 1 is left.
- Tag the owner right away: `~/.local/bin/herdr-events-owner <wK> <your-bot-slug>` (lowercase bot name, e.g. `alpha`). `<wK>` is the literal `.result.workspace.workspace_id` (e.g. `w1K`), never the `.result.workspace` object; the script refuses anything that is not a live workspace id. It also shows your slug as `$owner` in Herdr's sidebar, once the owner's Herdr config lists that token. For one-off commands in a pane, also set `HERDR_EVENTS_OWNER=<your-bot-slug>`. Finish, blocked, stale and dead events from the Herdr plugin, Claude and Codex hooks and the watchdog then POST to your route (or the default route), which relays them to your bot. Untagged workspaces are only logged, never sent.

## Step 4. Start an agent safely
Write the owner's words to `ask.md` on the box and copy it to the Mac (`ssh -o BatchMode=yes <host> 'cat > /tmp/ask-<task>.md' < ask.md`), then run `fleet-job new --file /tmp/ask-<task>.md --pane <wK root pane>` there, after the owner tag (Step 3); in an existing project workspace use `--workspace wK` instead. It makes the job folder `<repo>/.herdr-<slug>/`, starts the lead `lead-<slug>` on Claude with its hooks in that empty root pane (its tab becomes `lead`, per the first tab rule) or in a new `lead` tab, and prints the lead's name and the job folder; tell the owner the lead's name. When the owner asked to see the plan first, add `--review` and use the share-plan skill.
- `agent_not_ready` = blocked at a dialog. Some dialogs report `idle` instead, so after every start read the screen once: `herdr agent read <name> --source visible --lines 30`.
- Codex "Update available" (start returns `agent_not_ready`): the highlighted default is "Update now", which runs npm. Press `herdr agent send-keys <name> esc` to skip it; never Enter.
- Claude "New MCP server found in this project": `herdr agent send-keys <name> enter` on the default, "Continue without using this MCP server". Prevent it in a folder `herdr-trust` refuses (not a git repo) by writing `{"disabledMcpjsonServers": ["<server>"]}` to `<cwd>/.claude/settings.local.json` before the start (failure-modes.md).
- Folder trust: before starting agents in a repo under the trust root (`FLEET_TRUST_ROOT`, default `~/code`), run `~/.local/bin/herdr-trust <repo dir>` (owner-approved 2026-10-16). It marks the repo trusted in `~/.claude.json` and `~/.codex/config.toml`, so neither CLI asks. If a trust dialog still shows (a new folder that is not a repo, or the write was refused), Claude: `agent send-keys <name> down`, read to confirm "Yes, I trust this folder" is selected, then `agent send-keys <name> enter` as a separate call; Codex: `agent send-keys <name> enter` on "Trust and continue".
- After clearing a dialog: `herdr agent wait <name> --until idle --timeout 30000` (a stale `blocked` clears within seconds), then read the screen once more before the first prompt.
- Login, payment, account switch, trust for a folder outside the trust root, or anything unfamiliar -> stop and ask the owner.
- Reopen record (17 Oct 2026): `fleet-job new` records the lead's start in `<job dir>/agents.tsv`; once it runs, `herdr-reopen-snapshot wK <job dir>` writes `REOPEN.md` and `reopen.sh` there. Refresh it after every later start and before any close (herdr-fleet, "Reopen record").

Then end your turn: events arrive by webhook as today. On an event, read the new lines of `<job dir>/inbox.log` once. A `QUESTION` line or a `question` event (source `stampede`) for the owner: ask in chat, then `fleet-job tell <job dir> lead "<their words>"`. A gate comes back to you as a `gate` event (source `stampede`: job, gate, exact action, PR, commit): ask the owner in chat with those, and only on their yes to that gate run its `approve` command on the Mac, `fleet-job approve-gate <job dir> <gate> --sha <commit> --by "owner in <bot> chat"`; on a no or anything else, `fleet-job tell` the lead their words. Never type a yes into a pane, approve a gate the owner did not answer, or change its commit; a push after the yes withdraws it. Hand off to `herdr` / `herdr-fleet` / `moshi-best-practices` for anything else.

## After hand-off
herdr-fleet now handles external callers; follow its **Where are you?** section (literal ids, scoped fleet-watch, agent get before prompt, read before resend). Also keep:
- The ask you write for `fleet-job new` names every parallel step as a pane (`research-web` in tab `research`, `review-claude`), never leaving one unassigned, or the lead runs it as a hidden built-in subagent (herdr-fleet, "Panes, not built-in subagents"). The lead it starts is woken by hooks: it neither polls nor watches, so do not add rules about waiting.
- Moshi: read-only from bots; if the box's pairing (moshi-hook serve) is dead, report, never re-pair.
- Done: never close anything, or clear the owner tag, by yourself when the job ends (the owner's rule, 17 Oct 2026). Refresh the reopen record, leave the workspace open, and end your report or done event with the question: "Close workspace <label>? Reopen with <job dir>/reopen.sh." No answer is a no. Only after the owner's explicit yes, as the last step: exit the agents gracefully (`/exit`, `/quit` for Codex), `herdr-reopen-snapshot wK <job dir>`, `~/.local/bin/herdr-events-owner wK --clear`, then `herdr workspace close wK`, only for workspaces you created. Never close project workspaces. Never delete receipts or invoices.
- Hard rules above stay in force (`<host>` only, herdr on the Mac, never touch what you didn't create).

## Official docs
- https://herdr.dev/docs/cli-reference/
- https://herdr.dev/docs/agent-automation/

Re-check both, and `herdr <cmd> --help` on the Mac, after Herdr is upgraded or when a command fails. Where they differ the installed binary wins (2026-10-16: the docs track 0.9.5, the Mac runs 0.9.4).
