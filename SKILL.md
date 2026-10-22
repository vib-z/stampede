---
name: stampede
description: One ask starts a Herdr job run by a lead agent that opens panes only when they pay. Use when asked to use stampede, run a job with agents in Herdr, start a lead for an ask, or show the plan before a job starts.
---

# stampede

One ask, one lead, and only the panes that pay. The lead plans in `plan.md`, works, and brings the owner only the questions and gates that are theirs.

- **Running the job** (the lead, or a chat that will open panes): read [skills/herdr-fleet/SKILL.md](skills/herdr-fleet/SKILL.md).
- **A bot front door** (outside Herdr, over SSH): read [skills/grokbot-herdr/SKILL.md](skills/grokbot-herdr/SKILL.md).
- **The owner asks to see the plan first:** read [skills/share-plan/SKILL.md](skills/share-plan/SKILL.md).

## Front door

Write the owner's ask, word for word, to a file, then start the lead and step back:

```bash
stampede new --file <ask.md>             # add --review when the owner asks to see the plan first
```

Inside Herdr the lead gets a tab in the current workspace. A front door outside Herdr (a bot, a desktop app) passes `--workspace <id>` or `--pane <id>`: it creates a workspace for the job and passes its root pane:

```bash
P=$(herdr workspace create --cwd <repo> --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file <ask.md> --pane "$P"
```

It prints `<lead name> <job dir>`. Tell the owner the lead's name; never plan or run the job yourself. `stampede` is the same command as `fleet-job`.
