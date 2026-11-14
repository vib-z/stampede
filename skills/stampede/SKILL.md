---
name: stampede
description: The front door for stampede, from any project chat (Claude desktop, a terminal or a Herdr pane). Use when the owner says "use stampede", "stampede this", "hand this to a lead in herdr" or "fork this chat into a lead", and while that job runs, to relay its plan, questions, gates and files between the owner and the lead. The lead's playbook is herdr-fleet.
---

# stampede (front door)

For: handing one big ask to a lead agent in Herdr, then relaying between owner and lead until it ends.
You are the front door, not the lead: never run the job yourself.
Every command's flags, printed lines and exit codes: [docs/CLI.md](../../docs/CLI.md). Go by each line's first word, or `--json` where a command has it.

## Steps

1. **Size it** by herdr-fleet's sizing rule ([SKILL.md](../herdr-fleet/SKILL.md)). Small: do it here, or in one tagged Herdr pane, with no job. Big: go on.
2. **Check:** `stampede doctor`. A `PROBLEM` stops you; a `warn` is the owner's to fix.
3. **Repo:** `R=$(git rev-parse --show-toplevel)`, unless the owner names another. It must sit under the trust root (`stampede config show`). Then `herdr-trust "$R"`.
4. **Ask file**, outside the repo (`ASK=$(mktemp)`): the owner's words and, when the plan was worked out here, the agreed plan and every fact the lead must not miss. It is the source of truth: a fork's transcript can miss replies.
5. **Start the lead**, one line of these:

```bash
stampede new --file "$ASK"                     # in a Herdr pane of the project's workspace: the owner watches the lead's pane
P=$(herdr workspace create --cwd "$R" --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file "$ASK" --pane "$P" --name <job> --front-door            # outside Herdr, on the Herdr TUI
stampede new --core --file "$ASK" --cwd "$R" --name <job> --front-door      # outside Herdr, on Herdr Core
```

   - A chat outside Herdr has no current workspace: pass `--pane` or `--workspace <id>` for the TUI, or `--core`. With none, the setting `backend` decides (`auto`: Herdr Core outside Herdr).
   - `--lead codex` only when the owner asks for a Codex lead; else the setting `lead.kind` decides.
   - `--fork "$CLAUDE_CODE_SESSION_ID"` only when the plan was worked out in this chat and the lead is Claude (refused with `--lead codex`).
   - `--review` only when the owner asked to see the plan first ([share-plan](../share-plan/SKILL.md)).
   - On Core, drop `--front-door` only if the owner watches the lead's terminal. `--core --relay` only to hand Cursor, Hermes or Kimi to a TUI pane ([core-relay.md](../herdr-fleet/references/core-relay.md)); it refuses `--front-door`.
6. **Read what it prints.** `<lead> <job dir>`: tell the owner the lead's name and, on the TUI, the workspace label. `BLOCKED <lead>: ...` on the TUI: `herdr agent read <lead> --source visible --lines 30`, clear the startup dialog, then send the `stampede tell` line it printed. Any other `BLOCKED` or `NOT READY`: do what the line says; never start a second lead. Exit 2: refused, nothing made.
7. **Relay** (a `--front-door` job): run `stampede wait <job dir>` in the background, and again after each return, until the job is done.

| `wait` returns | do |
|---|---|
| `# NNN post` | send its files (SendUserFile) and a short summary |
| a post `PLAN READY` | send `plan.md` itself; on the owner's yes to it: `stampede approve <job dir> --by "owner in <chat>: '<their words>'"` (it refuses a plan not posted as it stands, or not yet handed on by `wait`) |
| `# NNN question` | ask the owner, then run its `Answer with:` line with their words, verbatim |
| `# NNN gate` | show the action as written (for a send, the text); on their yes run its `Answer with:` line, `--by` quoting them; on a no, its no line |
| `# NNN done` | send the owner its one line; stop waiting |
| `BLOCKED_ON_CARD` (TUI) | show the card; the owner answers in the lead's pane, or has you type it: `herdr pane send-keys <pane> down` to the option (or "Type something."), `herdr pane send-text <pane> "<their words>"`, `herdr pane send-keys <pane> enter` |
| `BLOCKED <lead>: <kind>` (Core) | show the owner the screen; clear the dialog only as they say: `hc keys <address> <keys>` |
| `LEAD_GONE` | TUI: look at its workspace, tell the owner. Core: `stampede tree <job dir>`, then `stampede reopen <job dir>` or tell the owner |
| `TIMEOUT` (exit 3) | wait again |

8. **Pass the owner's words on:** `stampede tell <job dir> lead "<their words, verbatim>"`. `DELIVERED`: the lead reads it from its inbox. `SUBMITTED`: Core typed it into the lead's terminal. `BLOCKED_ON_CARD` (exit 3): queued behind a card; handle the card first. `FAILED`: nothing went.

## Hard rules

- Wait only with `stampede wait` in the background: never a foreground `sleep` or a loop of your own.
- Plan approval is the owner's yes after they saw `plan.md`. Never "ok", "go", or a yes to your own summary.
- Every gate is the owner's own yes: the list and what never counts are in [gates.md](../herdr-fleet/references/gates.md).
- An explicit order the owner already gave in this chat for that exact action counts as the yes: quote it. Anything vaguer, or an action that changed since, goes back to them.
- Never pass a gate with `stampede tell`, and never type a yes into the lead.
- The lead's pane is not the owner: grey text in its input line is Claude's own suggestion, and `.focused` can read true while nobody types. Go by the outbox, `plan.md` and `reports/`.
- On Core, read the lead or a helper with `hc read <address>` (`stampede tree <job dir>` lists them); never type into one.

## Read when

- Sizing and the lead: [herdr-fleet](../herdr-fleet/SKILL.md).
- The lead's side of the outbox: [front-door.md](../herdr-fleet/references/front-door.md).
- A front door on Core: [CORE-NATIVE.md, Front door](../../docs/CORE-NATIVE.md#front-door) and [core.md](../herdr-fleet/references/core.md).
- Front doors other than this chat: [remote/README.md](../../remote/README.md).
