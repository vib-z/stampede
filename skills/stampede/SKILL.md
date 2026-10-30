---
name: stampede
description: The front door for stampede, from any project chat (Claude desktop or a Herdr pane). Use when the owner says "use stampede", "with stampede", "stampede this", "hand this to a lead in herdr" or "fork this chat into a lead", and while such a job runs, to relay its plan, questions, gates and files between the owner and the lead. Sizes the job, writes the ask, opens a Herdr workspace for the project and starts a hooked Claude lead with `stampede new`, forked from this chat when the plan was worked out here. The lead's own playbook is herdr-fleet.
---

# stampede (front door)

You are the front door, not the lead: hand the job over, then relay between the owner and the lead until it ends. Never run the job yourself.

1. **Size it** ([herdr-fleet, "Size the job first"](../herdr-fleet/SKILL.md#size-the-job-first-small-or-big)). Small: do it here, or in one tagged Herdr pane; no stampede job. Big: go on.
2. **Project folder:** the git root of this chat's folder (`git rev-parse --show-toplevel`), unless the owner names another repo. It must sit under `FLEET_TRUST_ROOT` (default `~/code`). The job folder itself goes under `FLEET_JOBS_ROOT` (default `~/code/herdr-jobs`), never in the repo.
3. **Write the ask** to a file outside the repo (`mktemp`): the owner's words and, when the plan was worked out in this chat, the agreed plan plus every fact the lead must not miss. The ask file is the source of truth; a forked chat's saved transcript can miss some replies.
4. **Start the lead.** A chat outside Herdr (the Claude desktop app, a terminal) has no current workspace, so `stampede new` needs `--pane` (below) or `--workspace <id>`, and `--front-door`, because the owner talks to you, not to the lead's pane:

```bash
R=<project folder>
herdr-trust "$R"                      # pre-trusts it for Claude and Codex; safe to repeat
P=$(herdr workspace create --cwd "$R" --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file <ask.md> --pane "$P" --name <job> --front-door   # add --fork / --review as below
```

- Already in a Herdr pane in that project's workspace (`$HERDR_WORKSPACE_ID` is set): run `stampede new --file <ask.md>` without `--front-door`; the owner watches the lead's pane and answers its cards.
- `--fork "$CLAUDE_CODE_SESSION_ID"`: only when the owner worked the plan out with you in this chat. The lead starts with this conversation.
- `--review`: only when the owner asked to see the plan first ([share-plan](../share-plan/SKILL.md)).
- `--core`: only when the owner asks for Herdr Core. Then no workspace, no `--pane` and no `--front-door` (a Core job has no pane to relay from; it is refused): `stampede new --core --file <ask.md> --cwd "$R" --name <job>` after `herdr-trust "$R"`. A `BLOCKED` or `NOT READY` line names the lead's terminal: read it with `hc read <address>` ([core.md](../herdr-fleet/references/core.md)).

5. It prints `<lead> <job dir>`. On `BLOCKED ...`, read the lead's pane (`herdr agent read <lead> --source visible --lines 30`), clear the startup dialog, then send the `stampede tell` line it printed. Tell the owner the lead's name and the workspace label.

## Relay (a `--front-door` job)

Everything the lead has for the owner lands in `<job dir>/outbox/`. Wait for it in the background, never with a foreground `sleep` or a loop of your own:

```bash
stampede wait <job dir>      # background: returns with each new item, or BLOCKED_ON_CARD; exit 3 after an hour with nothing
```

Start it again after each return until the job is finished. Each item is `<job dir>/outbox/NNN.md`, its files in `outbox/NNN/`:

- **`done`:** the lead finished (`fleet-job finish`): send the owner its one-line result, and stop waiting. **`LEAD_GONE`** from `wait`: the lead's agent is gone from Herdr; look at its workspace and tell the owner.
- **A post:** the plan, screenshots, a decision, the report. Send its files to the owner (SendUserFile) with a short summary of the text.
- **The plan** (`PLAN READY`, a review job): send `plan.md` itself and wait for the owner's answer to it. Only a yes they gave after seeing it approves: `stampede approve <job dir> --by "owner in <chat>: '<their words>'"`. Never pass on "ok", "go" or a yes to your own summary as approval; `approve` refuses a plan the lead did not post as it stands, or one `stampede wait` has not handed you yet, and refuses to run from inside Herdr.
- **A question:** ask the owner, then run the item's "Answer with" line with their words, verbatim.
- **A gate:** one exact action at one commit. Show it as written (for a send, the text being sent). On the owner's yes, run the item's `approve-gate` line, `--by` quoting their words. An explicit order they already gave in this chat for that exact action ("mark the PR ready and DM the reviewer", with the DM text seen) counts: quote it. Anything vaguer, or an action that changed since, goes back to the owner. On a no, run the item's no line.
- **BLOCKED_ON_CARD:** the lead sits at a question card in its pane and reads nothing else until it is answered. Show the owner the card. They answer in the lead's pane, or tell you to type it: `herdr pane send-keys <pane> down` to the option (or "Type something."), `herdr pane send-text <pane> "<their words>"`, then `herdr pane send-keys <pane> enter`.

**Passing something on:** `stampede tell <job dir> lead "<the owner's words, verbatim>"`. `DELIVERED` means the lead will read it; `BLOCKED_ON_CARD` (exit 3) means it is queued behind a card: handle the card first.

**The lead's pane is not the owner.** In `herdr agent read`, the grey text in its input line is Claude's own prompt suggestion, not the owner typing, and `.focused` can read true while nobody types. Go by the outbox, `plan.md` and `reports/`.

**Gates** (merge, push to main, deploy, send, spend, close) are always the owner's own yes: in this chat (recorded with `approve-gate` as above), in the lead's pane, or on their phone (on Herdr Core only the recorded yes, never a typed one); never your decision.
