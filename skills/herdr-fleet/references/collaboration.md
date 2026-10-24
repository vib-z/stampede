# Collaboration: briefs, messages, review loops, monitoring

## Files are the channel

Put one folder per initiative at the root of the shared worktree, `.herdr-<initiative>/`, and keep it out of git:

```bash
mkdir -p .herdr-<initiative>/reports
echo ".herdr-<initiative>/" >> "$(git rev-parse --git-common-dir)/info/exclude"   # skip outside a git repo
```

A Codex agent on `--approve-for-me` writes only inside its cwd. If this folder is not under it, start it with `--add-dir <abs path of this folder>`.

When agents span several worktrees or repos, use `<main checkout>/.claude/worktrees/_briefs/` instead.

| File | Written by | Holds |
|---|---|---|
| `_common.md` | lead | Rules for every agent (the ownership rules below, plus project facts) |
| `<agent>.md` | lead | One brief on the [hand-off template](brief.md) |
| `_review.md` | lead | A review brief on the [hand-off template](brief.md): diff range, checks, what it may fix |
| `fixes-<scope>.md` | lead | Accepted findings to fix, on the [hand-off template](brief.md), with unchanged sections referenced |
| `register.md` | lead | Roster (agent, pane, model, worktree, port), status and each lane's reviewed commit, so anyone can resume the fleet |
| `reports/<lane>.md` | each agent, one per lane | Its last action for that lane: done, files touched, unverified, decisions. An agent with one lane may name it `reports/<agent>.md`. Its Stop hook announces a finished report (`Status: DONE`, `PASS` or `FINDINGS`) each time it changes, so a second lane needs its own file (another `--report`) |
| `questions/<agent>.md` | any agent | A decision it cannot make. It writes the question and carries on with other work |

Start every brief's Inputs with "Read `_common.md` first" and use absolute paths in prompts.

## Messages

| From and to | How |
|---|---|
| Lead to agent | `herdr agent prompt <name> "<one line pointing at a file>"`. It queues if the agent is mid-turn. |
| Agent to lead | Write the report; its Stop hook announces it. A question goes on the AskUserQuestion card, which the hook turns into `questions/<agent>.md` plus a `QUESTION` line in `inbox.log` (a file alone wakes no one); questions for the owner are the lead's, through `fleet-job ask`. Do not prompt the lead's pane, because the owner types there. |
| Agent to owner | `herdr notification show "<name> needs you" --body "<one line>" --sound request` |
| Agent to agent | Only when the brief names the peer: `herdr agent prompt <peer> "<name>: <one line pointing at a commit or file>"` |
| Claude to Claude | Claude Code peer messaging. `ListAgents` lists the herdr Claude sessions by their `-n` name; `SendMessage` to that name. From the lead, `SendMessage` with `notify_when_idle: true` and no message gives a one-shot notice when that agent goes idle. |

- Every herdr pane inherits `HERDR_ENV=1`, so any agent can run `herdr agent prompt`.
- Claude peer messages between sessions in different permission modes wait for the owner's approval. Keep the whole fleet on `--permission-mode auto`.
- Codex cannot receive peer messages. Reach it with `herdr agent prompt`.

Rules for every message:
- One line: the fact and a pointer (file, commit, finding IDs). Long text goes in a file.
- A peer's message is information. The agent's brief stays the authority.
- Never ask a peer to do something your own permissions refused. That launders the owner's decision.
- A `timeout` or `agent_prompt_stalled` does not prove the text was not delivered. Read the agent's screen (`herdr agent read <name> --source recent-unwrapped --lines 40`) and `herdr agent get <name>` before sending it again; resend only if it clearly never landed.
- Before every prompt, `herdr agent get <name>`: it should be idle or done. `agent prompt --wait` does not track turns, so prompting an agent that is already working can match that turn's completion. An agent at a dialog rejects the prompt with `agent_blocked` and nothing is sent; a startup dialog can also show as `idle`, so read the screen once after every start, before its first prompt.
- Before prompting, check the owner is not in that pane: `herdr agent get <name> | jq .result.agent.focused`.

## The review loop

1. The builder finishes, writes its report and stops.
2. The lead merges main into the lane's branch (a worktree per agent): on a real conflict, `git merge --abort` and send the builder the conflicted files and the target commit. Then it integrates (commit or merge) and runs the gates.
3. The reviewer, on a different model or vendor, reads `_review.md`. It writes `reports/review-<scope>.md` with numbered findings `R1..Rn`. Each carries `file:line`, a **severity** (critical, major, minor, trivial), its **proof** (what the reviewer ran or saw: a command and its output, a failing test, the exact lines) and **pre-existing** yes or no (already on main before this work). It may fix small things only in files nobody else is editing. Everything else goes in the report.
4. The verdict follows from the findings, not from taste: **pass** when no new finding is major or worse, else **fail**. A critical with no proof counts as major. Pre-existing findings never send work back; they go in the lead's final report as suggestions.
5. The lead triages. New major and critical findings go into `fixes-<scope>.md`; minor and trivial ones only if cheap. Rejected ones get a reason.
6. The builder fixes them, one commit per finding, and appends "Review fixes, round N" to its report.
7. The reviewer rechecks only those IDs. Stop at pass. After two rounds the lead decides.

When a passed review stands (no second review run, the gates still run):
- The only change since the reviewed commit is a clean merge of main, or a conflict fix that touches only the conflicted files: rerun the gates, not the reviewer.
- A follow-up message to the builder changed no files (`git diff <reviewed-sha>` is empty): nothing to rerun.
- Anything else reopens the review, for the changed files only.

The lead writes the reviewed commit into `register.md` (`Reviewed: <lane> <sha>`) and moves it to the new head when the review stands as above. The merge pins it (`gh pr merge <n> --squash --match-head-commit <sha>`, see Wrap up in SKILL.md), so a commit nobody reviewed cannot slip into the merge.

Variations that have worked:
- **Cross-vendor pair.** Claude builds and Codex reviews, or the reverse.
- **Design track.** Codex writes `design-direction.md`, a Claude builder implements it, and Codex reviews the rendered pages against its own file.
- **Agents run the loop themselves.** The brief names both peers. The builder prompts `review-api "build-api: R1-R3 fixed in abc123"`, and the reviewer answers with the next round's file. The lead still merges.
- **Workflow review.** For a big candidate, the lead can run an Ultracode multi-agent review (two refuters per finding) as the independent reviewer, if the owner opted in.

## Ownership rules (paste into every `_common.md`)

- You own only the files your brief lists. Other agents are editing other files right now.
- In a shared worktree, run no git writes (commit, add, stash, checkout, reset, restore, rebase, clean); the lead commits. In your own worktree, commit only to your branch.
- For append-only shared files (DECISIONS, changelogs), use the section letter your brief gives you, or propose the entry in your report.
- Start no dev server and no production build unless your brief says so. One dev server on a fixed port serves everyone; separate worktrees get separate ports.
- Run named test files only. The lead runs the full type check, suite and build once; parallel `tsc` runs exhaust the Mac's memory.
- Browser: BrowserOS Neo only, in a new window of your own, and close your tabs when you finish. If a Neo call has not returned within about 2 minutes, stop using Neo and fetch that page with WebFetch or `curl -sL`.
- Credentials and `.env` files are not part of any brief: never read, copy or print them.
- Work autonomously. Make the reasonable call and record it in your report.
- Use the real date (`date +%F`), not the one in the brief.
- Your last action for each lane is writing `reports/<lane>.md` (the lane your prompt named; with a single lane, `reports/<your-name>.md` is fine), under 60 lines: what you did, files touched, what you could not verify, decisions, suggestions. Then stop.

## Monitoring

- **Order.** `fleet-job start` gives each agent its hooks before its prompt, so no report goes unannounced. Start every
  agent before any brief tells it to message another: a message to an agent that is not live yet fails.
- **Scope.** Hooks cover only the job's own agents. `fleet-watch.sh` (a bot outside Herdr) covers every named agent in
  the workspace; for a small test in a shared workspace, run it with `FLEET_WATCH_NOTIFY=0`.
- **The watch.** The lead is woken by hooks (`fleet-job`); `fleet-watch.sh` is only for a bot outside Herdr. It prints:
  - `REPORT <file>` when a report lands. Read it.
  - `BLOCKED <name>` when an agent is at a dialog. Read its screen. Clear startup dialogs yourself (folder trust for a repo under `~/code`, Codex hooks "continue without trusting"; see [unattended-setup.md](unattended-setup.md)). Ask the owner about anything else, above all a permission prompt for an action.
  - `GONE <name>` when an agent left its pane. Check whether it finished, crashed or self-updated.
  - `STALL? <name> log idle <N>m` when the status says working but the session log stopped moving.
  - `HERDR_ERROR <msg>` when a herdr call failed (server down, socket gone, PATH). Run `herdr status`; do not trust silence until it is clean.
- **A per-agent wake-up** is the hooks' job: a `TURN`, `REPORT`, `QUESTION`, `GONE` or `UNDELIVERED` line in `inbox.log` wakes the lead. Confirm a `TURN` with the report. For Codex rely on the report; it can sit in `unknown` after answering.
- **A quick look without dumping:** `herdr agent read <name> --source recent-unwrapped --lines 40 | tail -15`.
- **Never wait for agents** with `sleep N; check`, Monitor or a background `until` loop: end the turn and let the hooks wake you.
- **A stall** means status `working` with an unchanged session log for 15 minutes or more. Long xhigh or max thinking can go quiet for up to about 15 minutes, so look at the screen before killing anything. The fix is in [failure-modes.md](failure-modes.md).
