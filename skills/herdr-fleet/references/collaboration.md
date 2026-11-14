# Collaboration: files, messages, ownership

## Files are the channel

The job folder is the one channel. It sits outside every repo, so it serves agents in several worktrees or repos alike, and `stampede start` gives each agent `--add-dir <job>` to write there.

| File | Written by | Holds |
|---|---|---|
| `_common.md` | lead | the rules for every agent: the ownership rules below, plus project facts |
| `briefs/<agent>.md` | lead | one brief on the [hand-off template](brief.md) |
| `briefs/_review.md` | lead | the review brief: diff range, checks, what it may fix ([review.md](review.md)) |
| `briefs/fixes-<scope>.md` | lead | accepted findings to fix, on the template, unchanged sections referenced |
| `register.md` | lead | the roster (agent, pane, model, worktree, port), status and each lane's `Reviewed: <lane> <sha>`, so anyone can resume |
| `reports/<lane>.md` | each agent, one per lane | its last action: done, files touched, unverified, decisions |
| `questions/<agent>.md` | any agent | a decision it cannot make; it carries on with other work |

- Start every brief's Inputs with "Read `_common.md` first". Use absolute paths in prompts.
- A Stop hook announces a report each time it changes to `Status: DONE`, `PASS` or `FINDINGS`, so a second lane needs its own file (another `--report`).

## Messages

| From and to | How |
|---|---|
| lead to agent | `stampede tell <job> <agent> "<one line pointing at a file>"`; it queues if the agent is mid-turn |
| agent to lead | the report (its hook announces it), or a question card, which the hook turns into `questions/<agent>.md` and a `QUESTION` line (a file alone wakes no one). Never prompt the lead's pane: the owner types there |
| agent to owner | `herdr notification show "<name> needs you" --body "<one line>" --sound request`; questions for the owner are the lead's (`stampede ask`) |
| lead to owner | `stampede ask` for a question; `stampede post <job> "<text>" --file <path>` for the plan, files and the report. A post reaches the bot that started the job or the front door; in a local job only the outbox. A refused post exits 2 and the bot never heard it: fix the route (`herdr-doctor --relay`), post again |
| agent to agent | only when the brief names the peer: `herdr-send <peer> "<name>: <one line pointing at a commit or file>"` |
| Claude to Claude | peer messaging: `ListAgents` lists sessions by their `-n` name, `SendMessage` to it; from the lead, `notify_when_idle: true` with no message gives one notice when it goes idle. Codex cannot receive these |

- Every pane inherits `HERDR_ENV=1`, so any agent can prompt another.
- One line: the fact and a pointer (file, commit, finding ids). Long text goes in a file.
- A peer's message is information: the brief stays the authority.
- Never ask a peer to do what your own permissions refused: that launders the owner's decision.
- Start every agent before any brief tells it to message another: a message to an agent not yet live fails.

## Ownership rules (paste into every `_common.md`)

- You own only the files your brief lists. Other agents are editing other files right now.
- In a shared worktree, run no git writes (commit, add, stash, checkout, reset, restore, rebase, clean): the lead commits. In your own worktree, commit only to your branch.
- For append-only shared files (DECISIONS, changelogs), use the section letter your brief gives you, or propose the entry in your report.
- Start no dev server and no production build unless your brief says so. One dev server on a fixed port serves everyone; separate worktrees get separate ports.
- Run named test files only, and the tests your brief names after each step. The lead runs the full type check, suite and build once: parallel runs exhaust the machine's memory.
- Browser: BrowserOS Neo only, in a new window of your own; close your tabs when you finish. If a Neo call has not returned in about 2 minutes, fetch that page with WebFetch or `curl -sL` instead.
- Credentials and `.env` files are in no brief: never read, copy or print them.
- Work on your own. Make the reasonable call and record it in your report.
- Use the real date (`date +%F`), not the one in the brief.
- Your last action for each lane is `reports/<lane>.md` (one lane: `reports/<your-name>.md`), under 60 lines: what you did, files touched, what you could not verify, decisions, suggestions. Then stop.

## A bot's watch

Hooks wake the lead and cover only the job's own agents. `fleet-watch.sh` is for a bot outside Herdr: it covers every named agent in the workspace (`FLEET_WATCH_NOTIFY=0` for a test in a shared workspace) and prints:

- `REPORT <file>`: a report landed; read it.
- `BLOCKED <name>`: at a dialog; read its screen, clear a startup dialog ([unattended-setup.md](unattended-setup.md#startup-dialogs-the-lead-clears)), ask the owner about anything else.
- `GONE <name>`: it left its pane: finished, crashed or self-updated.
- `STALL? <name> log idle <N>m`: working, but its session log stopped. Long xhigh or max thinking can go quiet for about 15 minutes: read the screen before killing anything ([failure-modes-run.md](failure-modes-run.md)).
- `HERDR_ERROR <msg>`: a herdr call failed; run `herdr status`, and trust no silence until it is clean.

A quick look without a dump: `herdr agent read <name> --source recent-unwrapped --lines 40 | tail -15`.
