# Other front doors: Cursor, ChatGPT Dots, or any bot with a computer of its own

**Cursor** on the machine is a front door like a Herdr chat: ask it to read stampede's `SKILL.md` and start the job; it writes the ask to a file and runs `stampede new --file <ask.md>`. A Cursor chat runs outside Herdr, so it passes `--workspace` or `--pane`: it creates a workspace for the job and passes its root pane ([SKILL.md](../SKILL.md#front-door)). Cursor cannot be woken by another agent, so the lead's questions reach you through Moshi. Cursor works as a worker, not yet as the lead.

Any bot that has a computer of its own can drive stampede the way Grok Bot does: it reaches your machine over SSH on a private network, and a webhook brings events back. Planned, not yet tested.

## Do
- Check the bot can run SSH from its computer.
- Check the bot can join your tailnet, or reach the machine another private way.
- Check the bot has a webhook that turns a POST into a message to it.
- Then follow the Grok Bot guide, part by part.
- Give the bot the same rules: never poll, touch only its own panes, ask before closing.

## Run
```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 <host> 'herdr-doctor --relay'   # the bot reaches the machine
herdr-event-post source=test state=done pane=<pane id>    # on the machine: the bot gets a message
```

| bot | computer | way in | events | status |
|---|---|---|---|---|
| ChatGPT Dots | its own cloud computer | SSH, once it can join the tailnet | no public webhook announced; a chat app channel may stand in | planned, untested |
| any bot with a computer | its own | SSH | its webhook, if it takes the JSON as sent | follow [grokbot/](grokbot/README.md) |

- **The webhook body:** `herdr-event-post` sends the event JSON as is, with `Authorization: Bearer <KEY>`. A webhook that needs another shape (extra headers, the event wrapped in a text field) is planned.
- **On Herdr Core:** the health check is `herdr-doctor --core`, the start `stampede new --core --file <ask.md> --cwd <repo>`, and events carry `pane` `hc:<key>/<address>` ([core.md](../skills/herdr-fleet/references/core.md)).
- **Events and routes:** [events.md](events.md). The rules every front door follows: [README.md](README.md).
