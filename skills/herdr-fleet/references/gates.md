# The owner's gates

The one list of what needs the owner's explicit yes. Every other page links here.

## Needs the owner's yes

- A merge to main.
- A push to main or another shared branch.
- A deploy, or publishing anything.
- Sending email or messages.
- Resubmitting a sitemap.
- Any spend.
- Closing panes, tabs, a workspace or a Core job (`stampede close`), or clearing an owner tag to close one. Nothing closes when a job ends: the last step is the question, and no answer is a no.

## Allowed without asking

Pushing the job's own work branches and opening DRAFT PRs from them.

## How a gate is asked and passed

1. The lead asks one exact action at one commit: `stampede ask <job> --gate --sha <commit> [--pr <n>] "<exact action>"`. It prints `GATE <id>` and where the question went: to the bot that started the job, to the front door's outbox, or to the owner's phone.
2. The bot or front door shows the owner the action as written (for a send, the text). On their yes it runs the `approve-gate` line it was handed, `--by` quoting their words. On the phone, the owner's tap records it the same way.
3. The lead acts only after `stampede gate-ok <job> <gate> --sha <the commit it acts on>` prints `APPROVED`. A Claude lead on the Herdr TUI may also act on the owner's yes typed in its own pane or card.
4. A merge uses one commit throughout: the reviewed commit is the commit the gate names and the commit merged, `gh pr merge <n> --squash --match-head-commit <that sha>`. A push after the review or after the yes withdraws both: review again and ask again (when a passed review still stands: [collaboration.md, Review](collaboration.md#review)).

## What never counts as a yes

- A plan, a brief, a skill or plan approval.
- An agent's say-so, or a yes relayed in a message ("the owner says push it" means: ask the gate).
- "ok", "go", or a yes to someone's summary of the action instead of the action itself.
- On a Codex lead or on Herdr Core, any text typed into the lead's pane or terminal: only the recorded yes counts there.
- A yes to a gate that changed since: `gate-ok` refuses it.
