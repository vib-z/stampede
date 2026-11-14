# What reaches your bot

The full event model, every field and the routes: [remote/events.md](../../../remote/events.md). This page is what a bot must know of it.

## Routes

- Every tagged event goes to the route named after the tag, `~/.config/herdr-events/routes/<bot slug>` (`URL=` and `KEY=`). The webhook behind it passes the event to the owning bot as a message.
- A bot with no route file of its own gets only its turn events, through the `default` route. A question, a gate, a post and a bot job's `finish` need the bot's own route file, even one pointing at the same webhook.

## While a job is open

`stampede new` writes the job marker `~/.config/herdr-events/jobs/<workspace>`; `stampede finish` removes it. While it is there:

- **Stay on the machine:** plain turn ends in that workspace: Herdr `done` and `idle`, Claude `Stop` and `idle_prompt`, Codex `agent-turn-complete`.
- **Still sent:** `blocked` and permission prompts (one per pane per 120 s, whichever source is first), `StopFailure`, `stale`, `dead`, a question, a gate, a post, and the one `done` from `stampede finish` (`source` `stampede`).

With no marker, Herdr `done` and `idle`, Claude `Stop` and Codex `agent-turn-complete` for one pane within 15 s are one event (the first), and `idle_prompt` 60 s after a turn end is dropped.

## Never sent

- A Codex turn with no Herdr pane.
- A "done" from a Codex sub-agent, the `--approve-for-me` guardian or Codex's chat-title side conversation: only the agent's own turn reports.
- After an outage, every queued event but each pane's newest: the older ones go to `~/.herdr-events/dead/*.superseded`.

The watchdog removes malformed owner tags and the tags of workspaces gone a day.

## A Herdr Core job

- Its key, `hc-<12 hex>`, stands in for the workspace id. Its questions, gates, posts and finish come as above (`source` `stampede`).
- Only the lead is watched for you: the watchdog's sweep posts `source` `hc` (`blocked`, `error`, `dead`, `stale`) within about 5 minutes, once per episode, with `pane` `hc:<key>/<address>`.
- Read that terminal once with `hc read <address>`, a helper too (`stampede tree <job dir>` lists them); never type into one. Answer with `stampede tell <job dir> lead "<their words>"`.
- A `--core --relay` job has a follower that also posts `done`, `idle` and `relay_down`.

## The scripts on the machine

- The relay scripts live in `scripts/` here; `install.sh` links them into `~/.local/bin`. When you copy one by hand, back up the live copy first: `cp -p ~/.local/bin/<script> ~/.local/bin/<script>.bak-<date>`.
- Their tests, from the repo root: `python3 -m unittest tests.test_herdr_relay tests.test_herdr_send tests.test_herdr_trust tests.test_herdr_reopen_snapshot`.
