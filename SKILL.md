---
name: stampede
description: One ask starts a Herdr job run by a lead agent that opens panes only when it's worth it. Use when asked to use stampede, run a job with agents in Herdr, start a lead for an ask, or show the plan before a job starts.
---

# stampede

The owner texts a task to a Grok Bot, which reaches the owner's Mac over Tailscale, and every update and question goes back through it (it works without a bot too). One ask, one lead, and a pane only when it's worth it. The lead plans in `plan.md`, works, and brings the owner only the questions and gates that are theirs.

- **Running the job** (the lead, or a chat that will open panes): read [skills/herdr-fleet/SKILL.md](skills/herdr-fleet/SKILL.md).
- **A bot front door** (outside Herdr, over SSH): read [skills/grokbot-herdr/SKILL.md](skills/grokbot-herdr/SKILL.md).
- **The owner asks to see the plan first:** read [skills/share-plan/SKILL.md](skills/share-plan/SKILL.md).

## Front door

First size the job ([herdr-fleet, "Size the job first"](skills/herdr-fleet/SKILL.md#size-the-job-first-small-or-big)). A small job needs no stampede job: run it as one agent session with built-in subagents in a single tagged Herdr pane, never as a bare agent CLI call outside Herdr. Only a big job goes on:

Write the owner's ask, word for word, to a file, then start the lead and step back:

```bash
stampede new --file <ask.md>             # add --review when the owner asks to see the plan first
```

Inside Herdr the lead gets a tab in the current workspace. A front door outside Herdr (a bot, a desktop app) passes `--workspace <id>` or `--pane <id>`: it creates a workspace for the job and passes its root pane:

```bash
P=$(herdr workspace create --cwd <repo> --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file <ask.md> --pane "$P"
```

When you are a Claude chat in which the owner already worked out the plan with you, add `--fork "$CLAUDE_CODE_SESSION_ID"`: the lead starts as a fork of this chat and keeps the whole conversation. Put the agreed plan in the ask file as well.

It prints `<lead name> <job dir>`. Tell the owner the lead's name; never run the job yourself. `stampede` is the same command as `fleet-job`.
