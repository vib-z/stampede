# Events: how a bot hears back without polling

When an agent finishes a turn, gets stuck or needs an answer, one short JSON message goes to the bot's webhook. The bot waits for it instead of asking again and again. A lead inside Herdr does not need this: its own hooks wake it. A Herdr Core job's events: [events-core.md](events-core.md).

## Do
- Give each bot a route: a webhook URL and secret, in a file only you can read.
- Tag each workspace with its bot before its agents start.
- On an event, read that pane once. Never poll.

## Run
| source | state | sent by |
|---|---|---|
| herdr | done, blocked, idle right after working | the stampede Herdr plugin (`scripts/herdr-plugin-event`) |
| claude | Stop, StopFailure, Notification | `herdr-event-claude-hook`, a Claude Code hook |
| codex | agent-turn-complete | `herdr-event-codex-notify`, the Codex `notify` command |
| herdr-watchdog | stale, dead | `herdr-event-watchdog` ([watchdogs.md](watchdogs.md)) |
| stampede | question, gate, post, done | `stampede ask`, `stampede ask --gate`, `stampede post`, `stampede finish` |
| hc | blocked, error, stale, dead, and more | a Core job's watchers ([events-core.md](events-core.md)) |

```bash
mkdir -p ~/.config/herdr-events/routes
printf 'URL=%s\nKEY=%s\n' '<webhook url>' '<secret>' > ~/.config/herdr-events/routes/<bot>
chmod 600 ~/.config/herdr-events/routes/<bot>        # and the same for a route named default
herdr-events-owner <workspace id> <bot>              # tag; --clear removes it; no second argument shows it
herdr-event-post source=test state=done pane=<pane id>   # a test event
herdr-event-flush                                    # send what is queued, oldest first
```

## Routes
- A tagged workspace's events go to the route named after its tag. An untagged workspace, or a bot with no route file, uses the `default` route for its turn events; with `HERDR_EVENTS_FALLBACK_ROUTE` set to a route's name, a bot with no route file uses that one instead. With neither, an event is logged only.
- A Codex turn with no Herdr pane and no Core terminal (the Codex desktop app) is skipped. With `HERDR_EVENTS_FALLBACK_ROUTE` set, it goes to that route as source `codex-desktop`, with no workspace or owner; each thread and turn is its own event.
- A question, a gate or a post, and `stampede finish` in a job a bot started, go only through that bot's own route, with `herdr-event-post --strict`.
  - No route of its own: exit 3. Not queued: exit 4. Either is a refusal the lead sees.
  - A route with no URL holds it instead of dropping it. The lead hears one `UNDELIVERED` line when it is held, and another if it is still undelivered after 24 h (in `inbox.log`; in a Core job, through `stampede tell <job> lead`).
- **Delivery:** an HTTP POST of the JSON to `URL`, with `Authorization: Bearer <KEY>` when `KEY` is set. URL and KEY are never logged.
- **A failed send** waits in the queue, `HERDR_EVENTS_HOME` (default `~/.herdr-events`). After an outage only each pane's newest event goes; after 24 h undelivered an event moves to `dead/`.
- **Log:** `~/Library/Logs/herdr-events.log` on macOS, `${XDG_STATE_HOME:-~/.local/state}/herdr-events.log` on Linux.

## What a message holds
- **Every event:** `source`, `state`, `pane`, `workspace`, `owner`, `route`, `machine` (`HERDR_EVENTS_MACHINE`), `timestamp`; a `codex-desktop` event (a Codex turn outside Herdr) has no `pane` and no `workspace`.
- **From Herdr** also `workspace_label`, `tab`, `agent`, `previous_state` and `output_tail` (the pane's last 40 lines). **From Claude and Codex** `cwd`, `session_id` or `thread_id`, and `last_assistant_message` (its first 2000 characters).
- **A question:** `job`, `agent` (the lead), `lead_pane`, `ask`, `question`, `options`, and `answer` (`stampede tell <job> lead "<the owner's words>"`). Ask the owner in chat, then run `answer` with their words.
- **A gate:** `job`, `agent`, `lead_pane`, `gate`, `action` (the exact action), `pr`, `sha`, `options` (`yes`, `no`), and two commands:
  - `approve`: `stampede approve-gate <job> <gate> --sha <sha> --digest <d> --by "owner in <bot> chat"`. Run it as given, over plain SSH (never `hc exec`), only on the owner's yes to that gate. The digest is the gate as it was asked, so a gate changed since takes no yes.
  - `deny`: `stampede tell <job> lead "<the owner's words>"`, for a no or anything else.
  - Ask the owner in chat with the action, PR and commit. Never type a yes into a pane.
- **A post:** `job`, `agent`, `lead_pane`, `text`, `outbox` (its number), `item` (`<job>/outbox/NNN.md`) and `files` (the copies under `outbox/NNN/`, on the machine): the lead's plan, files to look at, a decision or its report. Show the owner the text and send the files; there is nothing to answer.
  - A post held for a route with no URL goes out by itself once the route has one: the lead's `UNDELIVERED ... held` line says not to post it again. After 24 h in `dead/`, the second line says to post again.
- **Done:** `source` stampede, `state` done, and `summary`, the lead's one line. A second `finish` sends nothing.

## How often
- In a workspace with no open job, one message per turn end: the same pane and state inside 120 seconds is sent once.
- Blocked and permission prompts for one pane are one message for 120 seconds. Every question and every gate is its own message.

## While a job is open

`stampede new` writes `~/.config/herdr-events/jobs/<workspace>`, holding the job folder's path. The lead runs `stampede finish <job> "<one line on where it ended>"` once, when the job is done or stopped for good, and that removes it. Until then these stay on the machine (logged, not sent):

- Herdr `done` and `idle`, Claude `Stop` and its `idle_prompt` notification, Codex `agent-turn-complete`.

These still go out: `blocked`, a permission prompt, Claude `StopFailure`, the watchdog's `stale` and `dead`, and a `question`, `gate` or `post` in a job a bot started. `finish` sends one `done`: in a job a bot started on the strict route as a question does; in a job started locally on the ordinary relay, and it still clears the marker.

A Codex turn with no Herdr pane (`HERDR_PANE_ID` empty), the Codex desktop app included, is never sent. Once the marker is gone, the workspace behaves as before.

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
