---
name: stampede
description: The front door for stampede, from any project chat (Claude desktop or a Herdr pane). Use when the owner says "use stampede", "with stampede", "stampede this", "hand this to a lead in herdr" or "fork this chat into a lead". Sizes the job, writes the ask, opens a Herdr workspace for the current project and starts a hooked Claude lead with `stampede new`, forked from this chat when the plan was worked out here. The lead's own playbook is herdr-fleet.
---

# stampede (front door)

You are the front door, not the lead: hand the job over, tell the owner, step back.

1. **Size it** ([herdr-fleet, "Size the job first"](../herdr-fleet/SKILL.md#size-the-job-first-small-or-big)). Small: do it here, or in one tagged Herdr pane; no stampede job. Big: go on.
2. **Project folder:** the git root of this chat's folder (`git rev-parse --show-toplevel`), unless the owner names another repo. It must sit under `FLEET_TRUST_ROOT` (default `~/code`).
3. **Write the ask** to a file outside the repo (`mktemp`): the owner's words and, when the plan was worked out in this chat, the agreed plan plus every fact the lead must not miss. The ask file is the source of truth; a forked chat's saved transcript can miss some replies.
4. **Start the lead.** A chat outside Herdr (the Claude desktop app, a terminal) has no current workspace, so `stampede new` needs `--pane` (below) or `--workspace <id>`:

```bash
R=<project folder>
herdr-trust "$R"                      # pre-trusts it for Claude and Codex; safe to repeat
P=$(herdr workspace create --cwd "$R" --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file <ask.md> --pane "$P" --name <job>   # add --fork / --review as below
```

- Already in a Herdr pane in that project's workspace (`$HERDR_WORKSPACE_ID` is set): skip the workspace and run `stampede new --file <ask.md>`; the lead gets a `lead` tab there.
- `--fork "$CLAUDE_CODE_SESSION_ID"`: only when the owner worked the plan out with you in this chat. The lead starts with this conversation.
- `--review`: only when the owner asked to see the plan first ([share-plan](../share-plan/SKILL.md)).
- `--core`: only when the owner asks for Herdr Core. Then no workspace and no `--pane`: `stampede new --core --file <ask.md> --cwd "$R" --name <job>` after `herdr-trust "$R"`. A `BLOCKED` or `NOT READY` line names the lead's terminal: read it with `hc read <address>` ([core.md](../herdr-fleet/references/core.md)).

5. It prints `<lead> <job dir>`. On `BLOCKED ...`, read the lead's pane (`herdr agent read <lead> --source visible --lines 30`), clear the startup dialog, then send the `stampede tell` line it printed. Tell the owner the lead's name and the workspace label. Never run the job yourself.

**Afterwards:** `stampede tell <job dir> lead "<text>"` passes on an answer or a change; status comes from `<job dir>/plan.md` and `<job dir>/reports/`. Gates (merge, push to main, deploy, send, spend, close) are the owner's own yes in the lead's pane or phone card (on Herdr Core only the recorded yes, never a typed one), never relayed by you.
