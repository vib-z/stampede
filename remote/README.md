# Front doors: ask stampede from anywhere

A front door is anything that can run a command on the machine where Herdr runs: a chat in Herdr, a Claude, Codex or Cursor session, or a bot with a computer of its own. Every front door does the same two things: it writes the owner's ask to a file and starts the lead with `stampede new`. Then it tells the owner the lead's name and steps back. It never plans or runs the job itself.

## Do
- Write the ask word for word to a file, then start the lead.
- Tell the owner the lead's name and where its plan will be, then stop.
- When the owner asked to see the plan first, start with review and use the share-plan skill.
- Pass on the owner's answers to the lead in their words; never answer for them.
- A gate goes back to whoever started the job ([gates.md](../skills/herdr-fleet/references/gates.md)):
  - A bot gets a `gate` event, asks the owner in chat and records the yes with `stampede approve-gate`.
  - A front door gets a gate item from `stampede wait` and does the same.
  - A job started locally asks on the phone or on the lead's own card.
  - On the Herdr TUI a yes typed in a Claude lead's pane also works, except for a merge or a push to the default branch. For a Codex lead and on Herdr Core only the recorded yes counts; a gate approval typed there gets a short notice to answer in the chat or on the phone that started the job.
- Never pass a gate on with `stampede tell` or by typing into a pane.
- A bot outside Herdr: wait for an event; never poll, never sleep in a loop.
- On Herdr Core the owner hears a question, a gate, a post and done from the lead's own commands, and blocked, error, dead or stale for the lead from the machine's watchdog within about 5 minutes ([events-core.md](events-core.md)).
  - Answer with `stampede tell <job dir> lead "..."` or `approve-gate`.
  - Read the lead or a helper with `hc read <address>` (`stampede tree <job dir>` lists them); never type into one ([core.md](../skills/herdr-fleet/references/core.md)).

## Run
```bash
stampede doctor                                       # first: a PROBLEM line stops the job
stampede new --file <ask.md>                          # add --review when the owner asks to see the plan first
stampede new --file <ask.md> --lead codex             # a Codex lead; the setting lead.kind is the default
stampede new --core --file <ask.md> --cwd <repo>      # the whole job on Herdr Core; outside Herdr the setting backend may pick it
stampede new --core --relay --file <ask.md> --cwd <repo>      # only when the owner asks to hand Cursor, Hermes or Kimi to a TUI pane
stampede tell <job dir> lead "<the owner's words>"    # a change or an answer, word for word
stampede approve <job dir> --by "<front door>"        # only in a review job, after the owner's yes to the plan
stampede approve-gate <job dir> <gate> --sha <commit> --digest <d> --by "owner in <bot> chat"   # a bot, outside Herdr: the gate event's approve line, after the owner's yes
```

| front door | what it is | guide |
|---|---|---|
| a chat in Herdr | a Claude pane on the machine | [README, Use](../README.md#use-one-job-start-to-finish) |
| Grok Bot (preferred bot) | setup A: a bot with its own computer drives your machine by SSH over Tailscale | [grokbot/](grokbot/README.md) |
| any machine | setup B: everything on one remote computer | [any-machine/](any-machine/README.md) |
| Claude | a Claude Code session on the machine, from the Claude app | [claude-code.md](claude-code.md) |
| Codex | Codex on the connected machine, from the ChatGPT app | [codex.md](codex.md) |
| Cursor, ChatGPT Dots, other bots | a Cursor chat on the machine, or any bot with SSH and a webhook | [other.md](other.md) |
| Moshi | the phone; pairs with every front door above | [moshi.md](moshi.md) |
| phone apps | other people's Herdr apps for a phone, linked | [phone-clients.md](phone-clients.md) |

How a bot hears back: [events.md](events.md), on Core [events-core.md](events-core.md). What watches the watchers: [watchdogs.md](watchdogs.md). Every command's output: [docs/CLI.md](../docs/CLI.md). The gates: [README, Safety](../README.md#safety).
