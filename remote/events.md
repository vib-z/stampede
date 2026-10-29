# Events: how a bot hears back without polling

When an agent finishes a turn, gets stuck or needs an answer, one short JSON message goes to the bot's webhook. The bot waits for it instead of asking again and again. A lead inside Herdr does not need this: its own hooks wake it.

## Do
- Give each bot a route: a webhook URL and secret, in a file only you can read.
- Tag each workspace with its bot before its agents start.
- An untagged workspace, or a bot with no route file, uses the default route for its turn events; no route file at all means logged only. A question or a gate (below), and `stampede finish` in a job a bot started, go only through that bot's own route, with `herdr-event-post --strict`: no route of its own (exit 3) or no queue (exit 4) is a refusal the lead sees, and a queued one waits out a route with no URL instead of being dropped. Its lead hears it as one `UNDELIVERED` line in `inbox.log` when it is held, and another if it is still undelivered after 24 h.
- One message per turn end, in a workspace with no open job: the same pane and state inside 120 seconds is sent once. While a job is open, plain turn ends in that workspace stay on the machine (below). Every gate is its own message. Blocked and permission prompts for one pane are one message for 120 seconds.
- A send that fails waits in a queue; after an outage only each pane's newest event goes.
- On an event, read that pane once. Never poll.

## Run
| source | state | sent by |
|---|---|---|
| herdr | done, blocked, idle right after working | the stampede Herdr plugin (`scripts/herdr-plugin-event`) |
| claude | Stop, StopFailure, Notification | `herdr-event-claude-hook`, a Claude Code hook |
| codex | agent-turn-complete | `herdr-event-codex-notify`, the Codex `notify` command |
| herdr-watchdog | stale, dead | `herdr-event-watchdog` ([watchdogs.md](watchdogs.md)) |
| stampede | question, gate, done | `stampede ask`, `stampede ask --gate`, and `stampede finish` |
| hc | blocked, error, done, idle, dead, relay_down | `herdr-event-core`, the follower of a Herdr Core job ([below](#a-herdr-core-job)) |

```bash
mkdir -p ~/.config/herdr-events/routes
printf 'URL=%s\nKEY=%s\n' '<webhook url>' '<secret>' > ~/.config/herdr-events/routes/<bot>
chmod 600 ~/.config/herdr-events/routes/<bot>        # and the same for a route named default
herdr-events-owner <workspace id> <bot>              # tag; --clear removes it; no second argument shows it
herdr-event-post source=test state=done pane=<pane id>   # a test event
herdr-event-flush                                    # send what is queued, oldest first
```

- **Payload:** `source`, `state`, `pane`, `workspace`, `owner`, `route`, `machine` (`HERDR_EVENTS_MACHINE`), `timestamp`; from Herdr also `workspace_label`, `tab`, `agent`, `previous_state` and `output_tail` (the pane's last 40 lines); from Claude and Codex `cwd`, `session_id` or `thread_id`, and `last_assistant_message` (first 2000 characters).
- **A question:** `job`, `agent` (the lead), `lead_pane`, `ask`, `question`, `options`, and `answer` (`stampede tell <job> lead "<the owner's words>"`): ask the owner in chat, then run it with their words.
- **A gate:** `job`, `agent` (the lead), `lead_pane`, `gate`, `action` (the exact action), `pr`, `sha`, `options` (`yes`, `no`), and the two answers as commands: `approve` (`stampede approve-gate <job> <gate> --sha <sha> --by "owner in <bot> chat"`) and `deny` (`stampede tell <job> lead "<the owner's words>"`). Ask the owner in chat with the action, PR and commit; run `approve` over plain SSH (never `hc exec`) only on their yes to that gate, else `deny` with their words. Never type a yes into a pane.
- **Delivery:** an HTTP POST of the JSON to `URL`, with `Authorization: Bearer <KEY>` when `KEY` is set. URL and KEY are never logged. Queue and dead letters: `HERDR_EVENTS_HOME` (default `~/.herdr-events`). Log: `~/Library/Logs/herdr-events.log`.

## While a job is open

`stampede new` (the same command as `fleet-job new`) writes `~/.config/herdr-events/jobs/<workspace>`, holding the job folder's path. The lead's brief tells it to run `stampede finish <job> "<one line on where it ended>"` once when the job is done or stopped for good. Until that removes the marker, these stay on the machine (logged, not sent):

- Herdr `done` and `idle`
- Claude `Stop`
- Claude's `idle_prompt` notification
- Codex `agent-turn-complete`

These still go out: `blocked`, a permission prompt, Claude `StopFailure`, the watchdog's `stale` and `dead`, and a `question` or `gate`. `finish` sends one event, `source` stampede, `state` done, plus `summary`. In a job a bot started, that uses the same strict route as a question (exit 3 with no route of its own, exit 4 if it is not queued). In a job started locally, it uses the ordinary relay and still clears the marker. A second `finish` does not send again.

A Codex turn with no Herdr pane (`HERDR_PANE_ID` empty), including the Codex desktop app, is not sent. After the marker is gone, that workspace behaves as before.

## A Herdr Core job

A job started with `stampede new --core` has no Herdr workspace: its key, `hc-<12 hex>` (in `<job>/workspace`), stands in for the workspace id in its marker (`jobs/<key>`), its owner tag (`owners/<key>`) and every event's `workspace`. A Core terminal is named `hc:<key>/<address>` in `pane`. Plain turn ends (`hc` done and idle) stay on the machine while its marker is there, as for a workspace.

- **The follower:** `herdr-event-core <job>` runs as the job's `relay-<12 hex>` terminal. It follows `hc events --label stampede.job=<key>` and posts, with `agent` and `output_tail`: `blocked` (with `kind` and `msg`) and `error`, once per new episode; `done` and `idle` turn ends; `dead` when a terminal finishes while working or blocked, or fails with no status ever, or its record is gone (`reason` lost); and `relay_down` when Core stays unreachable for 10 minutes. It skips its own terminal and the job's wait terminals. Each event carries an `event_id` (`<key>/<address>|<state>|<episode>`), and `herdr-event-post` adds it to its de-dupe key: two blocked or error episodes on one terminal are two messages, the same one sent twice is one.
- **The relay hooks** inside a Core terminal stampede started (`STAMPEDE_JOB_KEY` and `HC_TERMINAL_ID` set, no `HERDR_PANE_ID`) send `pane` `hc:<key>/<address>` and `workspace` `<key>`, so a Codex turn there is no longer dropped. In any other Core terminal they behave as before.
- **Owner tags:** `herdr-events-owner <key> <bot>` works only while the job is open; it never calls `herdr`. The watchdog, with or without the Herdr TUI, keeps a key's tag while the job is open or Core still runs one of its terminals, keeps it when Core cannot be reached, and removes it a day after Core confirmed neither.

## Hooks

These change the agents' own settings, so you add them yourself. `herdr-doctor --relay` checks both.

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
