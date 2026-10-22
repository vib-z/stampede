---
name: share-plan
description: Use only when the owner explicitly asks to see or approve the plan before work starts ("share the plan first", "show me the plan", "let me approve it"). Shows the fleet plan as text where the owner asked, takes Approve or a change, records the approval with fleet-job approve, and only then lets the lead open panes. Without that ask, herdr-fleet plans and goes.
---

# Share the plan

1. Mark the job as one to review before any pane opens: start it with `fleet-job new --file <ask.md> --review`, or, when the lead already runs, `touch <job>/review` before it starts a worker. `fleet-job start` then refuses until step 5.
2. Once the lead has written `<job>/plan.md` (the layout, then the tasks with their pane, then questions), show it where the owner asked: pasted in the chat, or as the md file. A bot posts it in its chat.
3. Ask one question: Approve, or say what to change. Inside Herdr, the lead's own question card (it reaches the phone); a bot asks in its chat.
4. A change: the lead puts it into `plan.md` in the owner's words; show the new version, ask again.
5. Approve: `fleet-job approve <job> --by <who carried the yes>`. It records the plan's fingerprint and wakes the lead. Any later change to `plan.md` needs a new approve.
6. Cancel, or no answer: nothing starts. Ask once more, when the owner next writes.
7. Approval covers the panes, agents and models in the plan. Merges, pushes to main, deploys, sending, spending and closing stay gates, each asked when reached.
