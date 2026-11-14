---
name: stampede
description: One ask starts a Herdr job run by a lead agent that opens panes only when it's worth it. Use when asked to use stampede, run a job with agents in Herdr, start a lead for an ask, or show the plan before a job starts.
---

# stampede

Start at [USING.md](USING.md): one short page with the command that starts a job, the commands that follow, where the job folder is and the gates.

The owner texts a task to a Grok Bot, which reaches the owner's Mac over Tailscale, and every update and question goes back through it (it works without a bot too). One ask, one lead, and a pane only when it's worth it. The lead plans in `plan.md`, works, and brings the owner only the questions and gates that are theirs.

- **Starting a job** (any chat the owner asks to use stampede): read [skills/stampede/SKILL.md](skills/stampede/SKILL.md).
- **Running the job** (the lead, or a chat that will open panes): read [skills/herdr-fleet/SKILL.md](skills/herdr-fleet/SKILL.md).
- **A bot front door** (outside Herdr, over SSH): read [skills/grokbot-herdr/SKILL.md](skills/grokbot-herdr/SKILL.md).
- **The owner asks to see the plan first:** read [skills/share-plan/SKILL.md](skills/share-plan/SKILL.md).
