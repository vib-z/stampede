# Events from a Herdr Core job

A job started with `stampede new --core` has no Herdr workspace. The rest of the event model is [events.md](events.md); this page is what differs on Core.

## The key
- The job's key, `hc-<12 hex>` (in `<job>/workspace`), stands in for the workspace id: in its marker (`jobs/<key>`), its owner tag (`owners/<key>`) and every event's `workspace`.
- A Core terminal is named `hc:<key>/<address>` in `pane`.
- An explicit `workspace` must be well formed: `hc-` and 12 lowercase hex, or only letters, digits, `_` and `-`. `herdr-event-post --strict` refuses another (exit 6), and an ordinary event drops it, so it never picks an owner tag.
- Plain turn ends (`hc` done and idle) stay on the machine while its marker is there, as for a workspace.

## A Core-native job: the sweep

A `stampede new --core` job (`<job>/backend` holds `native`) has no follower. Its questions, gates, posts and `finish` go out from the lead's own `stampede` commands, and a helper's news reaches its parent as Core's own note. Only the lead, the root, needs a watcher.

- Each watchdog run (every 5 minutes) calls `herdr-event-sweep` once.
- It looks at each open marker whose job folder says `native` and has neither a `finished` nor a `closed` file. A whole-job `stampede close` writes `closed` and `stampede reopen` removes it: a job closed on purpose is no alarm, and nothing it still owes is retried.
- It asks that job's own core (its `endpoint`) for the terminal labelled `stampede.job=<key>` and `stampede.role=lead`. A core that does not answer is no news, and none is ever started.
- It posts, once each:
  - `blocked` (with `kind` and `msg`) and `error`, per new episode;
  - `stale` (with `minutes_unchanged`), per stall: the lead is `working` and its screen has not changed for `HERDR_EVENTS_STALE_MINUTES` (30);
  - `dead` (with `reason`, `exit_code`, `last_state`) when no live terminal carries those labels, or the one that does is the shell Core put in a lost program's place (`reason` lost), or Core has no row for it while `<job>/tree.json` names the lead's address. With no address yet it is still starting: no news. Never for its own exit 0.
- Each event has `source` `hc`, `pane` `hc:<key>/<address>`, `workspace` `<key>`, `agent` the lead's name, `job`, `owner`, `output_tail` (its last 40 lines) and an `event_id`.
- `<job>/sweep-state.json` keeps what it saw and sent: a later pass never sends one thing twice, and an event `herdr-event-post` did not take goes out on the next pass. Two blocks, or a block and a stall, inside one 5 minute window can be one message.

## A `--core --relay` job: the follower

`herdr-event-core <job>` runs as the job's `relay-<12 hex>` terminal. It follows `hc events --label stampede.job=<key>` and posts, with `agent` and `output_tail`:

- `blocked` (with `kind` and `msg`) and `error`, once per new episode; `done` and `idle` turn ends.
- `stale` (with `minutes_unchanged`), once per stall: a working terminal's screen and status unchanged for `HERDR_EVENTS_STALE_MINUTES` (30).
- `dead` when a terminal finishes while working or blocked, fails with no status ever, or its record is gone (`reason` lost); never for its own exit 0 (a graceful `/exit`: the lead still gets `GONE`). A kept terminal whose program is lost (Core's `lost` event, `reason` such as `signaled`) is `dead` once, and the shell Core then puts at its address is never reported as an agent.
- `relay_down` when Core stays unreachable for 10 minutes.
- For a Codex lead, `blocked` with `kind` `held` (from the lead's deliverer, once per hold): a line for the lead got no answer, so text may be left in its prompt and nothing more is typed there until it takes a turn.

It skips its own terminal and the job's wait terminals. Each event carries an `event_id`, `<key>/<address>|<state>|<episode>`, which `herdr-event-post` adds to its de-dupe key: two episodes on one terminal are two messages, the same one sent twice is one. A permission prompt the agent's own Claude hook also reports is one message, whichever arrives first.

`herdr-event-post` records an event for a Core pane (`hc:`), the agents' own hooks' included, as sent only once it is queued, so a failed queue write suppresses no later copy; a follower event exits 5 when it cannot be queued. An event it did not take is kept in `<job>/relay-state.json` and sent again every 30 s, after a reconnect or a restart too, until it is queued.

## Handed panes (`--core --relay`)

- Such a job hands Cursor, Hermes and Kimi to Herdr TUI panes (`stampede start --pane`). The follower looks at them every 5 s with `herdr agent list` and `get`, and posts the same events, `source` `hc`, with `pane` the Herdr pane id and `event_id` `<key>/tui:<pane>|<launch>|...`.
- A turn end is Herdr's `completion_seq` rising (`...|completion|<seq>`, its `turn` that value). A `blocked` event's `kind` is `dialog`. `output_tail` is a screen read only while the agent's name and session still matched (none on a `dead` for a replaced or departed agent).
- While the job is open, `$HERDR_EVENTS_DIR/handed/<pane>` (the job and launch) makes `herdr-event-post` keep every other event about that pane on the machine (Herdr's plugin, the watchdog, a hook), and the watchdog skips the pane. `stampede finish` removes the job's marks.

## Hooks and owner tags on Core
- **The relay hooks** inside a Core terminal stampede started (`STAMPEDE_JOB_KEY` and `HC_TERMINAL_ID` set, no `HERDR_PANE_ID`) send `pane` `hc:<key>/<address>` and `workspace` `<key>`, so a Codex turn there is sent. In any other Core terminal they behave as on the TUI.
- **Owner tags:** `herdr-events-owner <key> <bot>` works only while the job is open; it never calls `herdr`. The tag also names the job's core when it is not the default (`session=`, `socket=` lines), and the watchdog asks that core.
- The watchdog, with or without the Herdr TUI, keeps a key's tag while the job is open or its core still runs one of its terminals, keeps it when Core cannot be reached, and removes it a day after Core confirmed neither.
