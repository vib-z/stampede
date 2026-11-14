---
name: grokbot-herdr
description: "FIRST skill to read whenever a Grok Bot, or any bot outside Herdr, needs Herdr on the owner's machine: connect over SSH, health check, a tagged workspace, a safe stampede start, then act only on the events that come back. Hands off to herdr and herdr-fleet."
---

# grokbot-herdr: a bot's way into Herdr

For: a bot on its own computer, OUTSIDE Herdr, that starts and relays a stampede job on the owner's machine over SSH.
Use before any Herdr work; then herdr-fleet's external-caller rules ([SKILL.md](../herdr-fleet/SKILL.md)), `herdr` and moshi-best-practices.
Every `stampede` command and its output: [docs/CLI.md](../../docs/CLI.md). An event's line may say `fleet-job`: the same command.

## Steps

1. **Connect.** Every call: `ssh -o BatchMode=yes -o ConnectTimeout=10 <host> '<command>'`. Not found: prefix `export PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH;`. ssh fails: bring Tailscale up on the box, retry once, then tell the owner (the machine is likely asleep).
2. **Health check:** `stampede doctor --tui` (a Core job: `--core`), read only.
   - Exit 0: go on; report each `warn`, fix only your own (a stale tag or worktree).
   - Exit 1: stop and tell the owner the `PROBLEM` lines. A `PROBLEM herdr`: never start the server.
   - It says `event relay not installed`: run `herdr-doctor --tui --relay`; stop on its `PROBLEM` lines.
3. **Size the job** by herdr-fleet's sizing rule. Small: no job, one tagged pane of your own, `herdr-send` to a [brief](../herdr-fleet/references/brief.md); never a bare agent CLI over SSH or `nohup`.
4. **Workspace and tag** (a TUI job):
   - Make your own: `herdr workspace create --cwd <repo> --label bot-<task> --no-focus`, and keep its literal ids.
   - Tag it before any agent starts: `herdr-events-owner <workspace id> <bot slug>`. Untagged, your bot hears none of its questions or gates.
   - Ids, the first tab, a project workspace: [workspace.md](references/workspace.md).
5. **Start the lead.** Write the owner's words to `ask.md` and copy it over: `ssh -o BatchMode=yes <host> 'cat > /tmp/ask-<task>.md' < ask.md`. Then on the machine:

```bash
herdr-trust <repo>                                             # a repo under the trust root
stampede new --file /tmp/ask-<task>.md --pane <root pane id>   # or --workspace <id>
HERDR_EVENTS_OWNER=<bot slug> stampede new --core --file /tmp/ask-<task>.md --cwd <repo>   # on Herdr Core
```

   - `--lead codex` when the owner asks for a Codex lead; `--review` when they asked to see the plan first ([share-plan](../share-plan/SKILL.md)). Never `--front-door`: a bot relays its own jobs.
   - The ask names every parallel step as a pane (`research-web`), or the lead runs it as a hidden subagent.
   - It prints `<lead> <job dir>`: tell the owner its name. Read the screen once: `herdr agent read <lead> --source visible --lines 30` (Core: `hc read <address>`); a dialog: [workspace.md](references/workspace.md).
6. **End your turn.** The lead's own hooks wake it; nothing wakes you but an event.
7. **On an event,** read once, act, end your turn. A TUI job: first read the new lines of `<job dir>/inbox.log` once.

| event (`source` `state`) | do |
|---|---|
| `stampede question` | ask the owner in chat, then run its `answer` with their words |
| `stampede gate` | ask the owner in chat with its action, PR and commit; on their yes to that gate run its `approve` line over plain ssh (never `hc exec`); else its `deny` with their words |
| `stampede post` | show the owner the text and send its files; nothing to answer |
| `stampede done` | report its `summary`, then ask the close question (below) |
| `herdr`, `claude`, `herdr-watchdog`: blocked, a permission prompt, `StopFailure`, `stale`, `dead` | read that pane once, tell the owner |
| `hc`: blocked, error, stale, dead | `hc read <address>` once (`stampede tree <job dir>` lists them), never type into it; answer with `stampede tell <job dir> lead "..."` |
| a turn end, no open job | read the pane once and finish |

## Hard rules

- Target only `<host>`, the owner's own machine; a work machine only when the owner asks in chat for that job.
- Run herdr on the machine over ssh: never `herdr --remote` or `--machine` from the box, never start or stop `herdr server` or the TUI, never set `HERDR_ENV`.
- Never poll a job (no `herdr agent wait` for a result, sleep loops, repeated reads or watchers). Fine: `agent start`, `herdr-send`, `herdr agent wait <name> --until idle --timeout 30000` after clearing a dialog.
- Prompt only with `herdr-send <name or pane> "<text>"` or `herdr agent prompt`, never `pane send-text` and Enter. Go on only on `SUBMITTED`; on `FAILED` read the screen first ([send.md](../../remote/grokbot/send.md)). Never `ctrl+c` an idle Codex: it quits.
- Touch only the workspaces, tabs and panes you created; never the owner's project workspaces.
- Questions for the owner go to them in chat, never into a pane.
- Gates are the owner's yes in chat ([gates.md](../herdr-fleet/references/gates.md)). Never type a yes into a pane, approve a gate they did not answer, or change its commit: a push after the yes withdraws it.
- Never read, copy or print credentials or env files, on either machine.
- Login, payment, an account switch, trust for a folder outside the trust root, or anything unfamiliar: stop and ask the owner.
- Nothing closes when the job ends: refresh the reopen record and end with "Close workspace <label>? Reopen with <job dir>/reopen.sh." No answer is a no.
- Moshi is read-only for a bot: report a dead pairing, never re-pair. Never delete receipts or invoices.

## Read when

- The workspace, dialogs, trust, the reopen record, closing, Herdr's docs: [references/workspace.md](references/workspace.md).
- What reaches your bot and when, installing the relay scripts: [references/relay.md](references/relay.md).
- Every event field: [remote/events.md](../../remote/events.md). The one-time setup: [remote/grokbot/](../../remote/grokbot/README.md).
