# Grok Bot, part 4: the event webhook

The machine tells the bot when an agent is done, stuck or waiting. A webhook turns each event into a message for the bot, so the bot never polls.

## Do
- In Grok Bot, make a routine that a webhook starts and that hands the request body to the bot.
- Copy the routine's webhook URL and secret.
- On the machine, save them as a route file only the owner can read.
- Send one test event; check the bot got it.
- Tag every workspace the bot makes, before its agents start.

## Run
```bash
mkdir -p ~/.config/herdr-events/routes
printf 'URL=%s\nKEY=%s\n' '<webhook url>' '<secret>' > ~/.config/herdr-events/routes/<route>
chmod 600 ~/.config/herdr-events/routes/<route>
herdr-events-owner <workspace id> <route>
herdr-event-post source=test state=done pane=<pane id>
```

- **One routine for many bots:** save it as the route named `default` and have the routine pass each message to the bot named in its `owner` field. A tagged workspace whose bot has no route file of its own uses `default`.
- **What the bot does with a message:** read that pane once, report to the owner in plain words, then wait again. `state` is done, blocked, Stop, StopFailure, agent-turn-complete, stale or dead.
- **Nothing arrives:** `herdr-doctor` names the broken part. With no route file for the tag and none named `default`, an event is logged only.
- **The full event model:** [events.md](../events.md). **Never** paste the URL or secret into a chat, a brief or the repo.
