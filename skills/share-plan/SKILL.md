---
name: share-plan
description: Use only when the owner explicitly asks to see or approve the plan before work starts ("share the plan first", "show me the plan", "let me approve it"). Shows the plan where the owner asked, takes Approve or a change, records the yes with stampede approve, and only then lets the lead start helpers. Without that ask, herdr-fleet plans and goes.
---

# Share the plan

For: a job whose owner asked to see the plan before any helper starts.
Use only on that ask; otherwise the lead plans and goes.

## Steps

1. **Mark the job for review** before any helper starts: `stampede new --file <ask.md> --review`, or, when the lead already runs, `touch <job>/review` before its first `start`. `stampede start` then refuses (exit 2) until step 5.
2. **Show the plan** once the lead has written `<job>/plan.md` (the layout, then the tasks with their pane or helper, then the questions), where the owner asked: pasted in the chat, or as the file. A front door gets it as a `PLAN READY` post and sends the file itself; a bot reads `plan.md` and posts it in its chat.
3. **Ask one question:** Approve, or say what to change. Inside Herdr, the lead's own question card (it reaches the phone), or `stampede ask` for a Codex lead, which has no card; a bot or a front door asks in its chat.
4. **A change:** pass it with `stampede tell <job> lead "<their words>"`; the lead puts it into `plan.md` in the owner's words. Show the new version and ask again.
5. **Approve:** `stampede approve <job> --by "<who carried the yes, and their words>"`. It records the plan's fingerprint and wakes the lead. Any later change to `plan.md` needs a new approve.
6. **Cancel, or no answer:** nothing starts. Ask once more when the owner next writes.

## Hard rules

- Only the owner's yes to the plan they saw approves it: never "ok", "go", or a yes to a summary.
- In a front-door job, `approve` refuses a plan the lead did not post as it stands, or one `stampede wait` has not handed on, and refuses to run inside Herdr.
- Approval covers the helpers, agents and models in the plan. Every gate is still asked when reached: [gates.md](../herdr-fleet/references/gates.md).

## Read when

- The lead's side of a review job: [front-door.md](../herdr-fleet/references/front-door.md).
- The command's output and exit codes: [docs/CLI.md](../../docs/CLI.md).
