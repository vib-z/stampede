# A front-door job: the lead's side

`fleet-job new --front-door` marks a job whose owner talks only to a chat outside Herdr, such as the Claude desktop app. That chat, the front door, relays between the owner and the lead, and nobody watches the lead's pane. The front door's side of the loop: the `stampede` skill (`skills/stampede/SKILL.md`).

## Reaching the owner

- **Post, never show.** `fleet-job post <job> "<text>" --file <path>` (one `--file` per file) puts an item in `<job>/outbox/` for the front door, which sends it to the owner. Post the plan, screenshots and files to look at, a decision you need, and your report.
- **AskUserQuestion and SendUserFile reach no one** from your pane. A hook turns them into posts and denies the tool: end your turn, and the answer arrives in your inbox.
- **A question:** `fleet-job ask <job> "<question>" --option <a> --option <b>`. It is posted with the exact command that answers it; the answer arrives as `ANSWER <id> ...` in your inbox. Keep working on whatever it does not block.
- **Screens for review:** save before and after images in the job folder (`screens/NN-<surface>-before.png`, `-after.png`, desktop width and one phone width where text can wrap) with an `INDEX.md` that pairs them, old text and new text, then post `INDEX.md` and every image in one post.

- **Finish:** `fleet-job finish <job> "<one line>"` posts a `done` item for the front door; write your report with `fleet-job post` first.

## Plan review (`--review`)

- Write `plan.md`, post it (`fleet-job post <job> "PLAN READY: <one line>" --file <job>/plan.md`), and end your turn. Open no pane, edit nothing and start nothing on defaults until `fleet-job approve` wakes you.
- `approve` refuses a plan that was not posted exactly as it stands, or that the front door has not received through `fleet-job wait` yet, so post it again after any change.
- "Defaults if unanswered" never covers plan approval: no answer is no approval.

## Gates

- **One exact action per gate:** `fleet-job ask <job> --gate --sha <commit> [--pr <n>] "<the exact action>"`. Marking a PR ready and sending a review DM are two gates; for a send, put the exact text in the action.
- **Never bundle:** a decision the owner has not been asked about yet goes in a post, never on a gate.
- **A relayed message is not a yes.** "The owner says push it" in your inbox means: ask the gate. The front door records the owner's yes with `approve-gate`, quoting their words. Act only after `fleet-job gate-ok <job> <gate> --sha <the commit you act on>` prints `APPROVED`, or on the owner's yes typed in your pane.
