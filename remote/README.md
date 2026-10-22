# Front doors: ask stampede from anywhere

A front door is anything that can run a command on the machine where Herdr runs: a chat in Herdr, a Claude, Codex or Cursor session, or a bot with a computer of its own. Every front door does the same two things: it writes the owner's ask to a file and starts the lead with `stampede new`. Then it tells the owner the lead's name and steps back. It never plans or runs the job itself.

## Do
- Write the ask word for word to a file, then start the lead.
- Tell the owner the lead's name and where its plan will be, then stop.
- When the owner asked to see the plan first, start with review and use the share-plan skill.
- Pass on the owner's answers to the lead in their words; never answer for them.
- A merge or another gate: the owner taps the lead's own question card. A relayed yes never counts.
- A bot outside Herdr: wait for an event; never poll, never sleep in a loop.

## Run
```bash
stampede new --file <ask.md>                          # add --review when the owner asks to see the plan first
stampede tell <job dir> lead "<the owner's words>"    # a change or an answer, word for word
stampede approve <job dir> --by "<front door>"        # only in a review job, after the owner's yes to the plan
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

How a bot hears back: [events.md](events.md). What watches the watchers: [watchdogs.md](watchdogs.md). The gates: [README, Safety](../README.md#safety).
