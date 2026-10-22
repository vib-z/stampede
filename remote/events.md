# Events: how a bot hears back without polling

When an agent finishes a turn, gets stuck or needs an answer, one short JSON message goes to the bot's webhook. The bot waits for it instead of asking again and again. A lead inside Herdr does not need this: its own hooks wake it.

## Do
- Give each bot a route: a webhook URL and secret, in a file only you can read.
- Tag each workspace with its bot before its agents start.
- An untagged workspace, or a bot with no route file, uses the default route; no route file at all means logged only.
- One message per turn end: the same pane and state inside 120 seconds is sent once.
- A send that fails waits in a queue; after an outage only each pane's newest event goes.
- On an event, read that pane once. Never poll.

## Run
| source | state | sent by |
|---|---|---|
| herdr | done, blocked, idle right after working | the stampede Herdr plugin (`scripts/herdr-plugin-event`) |
| claude | Stop, StopFailure, Notification | `herdr-event-claude-hook`, a Claude Code hook |
| codex | agent-turn-complete | `herdr-event-codex-notify`, the Codex `notify` command |
| herdr-watchdog | stale, dead | `herdr-event-watchdog` ([watchdogs.md](watchdogs.md)) |

```bash
mkdir -p ~/.config/herdr-events/routes
printf 'URL=%s\nKEY=%s\n' '<webhook url>' '<secret>' > ~/.config/herdr-events/routes/<bot>
chmod 600 ~/.config/herdr-events/routes/<bot>        # and the same for a route named default
herdr-events-owner <workspace id> <bot>              # tag; --clear removes it; no second argument shows it
herdr-event-post source=test state=done pane=<pane id>   # a test event
herdr-event-flush                                    # send what is queued, oldest first
```

- **Payload:** `source`, `state`, `pane`, `workspace`, `owner`, `route`, `machine` (`HERDR_EVENTS_MACHINE`), `timestamp`; from Herdr also `workspace_label`, `tab`, `agent`, `previous_state` and `output_tail` (the pane's last 40 lines); from Claude and Codex `cwd`, `session_id` or `thread_id`, and `last_assistant_message` (first 2000 characters).
- **Delivery:** an HTTP POST of the JSON to `URL`, with `Authorization: Bearer <KEY>` when `KEY` is set. URL and KEY are never logged. Queue and dead letters: `HERDR_EVENTS_HOME` (default `~/.herdr-events`). Log: `~/Library/Logs/herdr-events.log`.

## Hooks

These change the agents' own settings, so you add them yourself. `herdr-doctor` checks both.

- **Claude Code,** in `~/.claude/settings.json`, the same command on `Stop`, `StopFailure` and `Notification`:

```json
{"hooks": {
  "Stop": [{"hooks": [{"type": "command", "command": "~/.local/bin/herdr-event-claude-hook"}]}],
  "StopFailure": [{"hooks": [{"type": "command", "command": "~/.local/bin/herdr-event-claude-hook"}]}],
  "Notification": [{"hooks": [{"type": "command", "command": "~/.local/bin/herdr-event-claude-hook"}]}]
}}
```

- **Codex,** in `~/.codex/config.toml`, one line at the top level (Codex appends the event JSON as the last argument):

```toml
notify = ["<home>/.local/bin/herdr-event-codex-notify"]
```

Docs: Claude Code [hooks](https://code.claude.com/docs/en/hooks), Codex [notify](https://developers.openai.com/codex/config-advanced).
