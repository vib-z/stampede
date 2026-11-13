# Watchdogs: what speaks up when nothing else can

Events cover a turn that ends. Watchdogs cover the rest: an agent that hangs, a pane that vanishes, a queue that cannot send, a check before work starts. A bot outside Herdr needs them; a lead inside Herdr hears `GONE` through its own hooks.

## Do
- Check health before every remote job; stop on a problem.
- Let a timer flag agents stuck with no output, and panes that vanished.
- Let a timer retry the event queue, so an outage loses nothing.
- Keep the machine reachable: awake, online, on the tailnet.
- Watchdogs report. They never fix your setup by themselves.

## Run
| helper | what it does | how it runs |
|---|---|---|
| `herdr-doctor --relay` | read only: tools on PATH, the Herdr server and client, the event plugin, the Claude and Codex hooks, the helpers, the two timers below, the route files, the queue, owner tags, leftover worktrees under `FLEET_TRUST_ROOT`, a newer stampede release (a `warn`, once a day), free disk; one `ok`, `warn` or `PROBLEM` line each, exit 1 on a PROBLEM | by hand or by the bot, before a job |
| `herdr-event-watchdog` | sends `stale` (working, no output change for 30 minutes) and `dead` (pane gone without a done); skips a pane a Herdr Core job handed an agent to (its follower watches it); removes malformed tags and tags of workspaces gone a day; before its Herdr TUI part, so with or without the Herdr TUI, runs `herdr-event-sweep` once and goes on whatever it returns | every 5 minutes |
| `herdr-event-flush` | sends the queued events, oldest first; after 24 hours undelivered, an event moves to `dead/`; a stampede question, gate or post it holds for a route with no URL, or moves to `dead/`, is told to its lead as an `UNDELIVERED` line (in a Core-native job, with `stampede tell <job> lead`) | every 2 minutes |
| `herdr-event-sweep` | one look at the lead of each open Core-native job, on its own core: `blocked`, `error`, `stale` (`HERDR_EVENTS_STALE_MINUTES`, 30) and `dead`, once each, kept in `<job>/sweep-state.json` ([events.md](events.md#a-herdr-core-job)) | by `herdr-event-watchdog` |
| `herdr-event-core <job>` | a `--core --relay` job's follower, in place of the TUI watchdog and `fleet-watch.sh` for that job, its handed TUI panes included: `stale` once per stall (`HERDR_EVENTS_STALE_MINUTES`, 30), `dead`, `RELAY DOWN`, and with `FLEET_WATCH_NOTIFY=1` a phone push ([core.md](../skills/herdr-fleet/references/core.md)) | started by `stampede new --core --relay` |
| `fleet-watch.sh` | for a bot outside Herdr: `REPORT`, `BLOCKED`, `GONE` and `STALL?` lines for one job, with a phone push (`FLEET_WATCH_*`) | by the bot, as a background command |

The two timers. On macOS, launch agents with the labels `herdr-doctor --relay` checks:

```bash
plist() {  # plist <label> <helper> <seconds>
  cat > ~/Library/LaunchAgents/$1.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$HOME/.local/bin/$2</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>$3</integer>
</dict></plist>
EOF
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/$1.plist
}
plist local.herdr-event-watchdog herdr-event-watchdog 300
plist local.herdr-events-flush herdr-event-flush 120
herdr-doctor --relay
```

On Linux, `install.sh` starts the same two timers. When `systemctl --user` answers, it enables `herdr-event-watchdog.timer` (5 minutes) and `herdr-events-flush.timer` (2 minutes). When it does not, it starts one `herdr-event-supervise` process under `flock`, which runs both. `--no-supervise` skips this; `--dry-run` only prints it. A home that is not the login home is skipped too, so a throwaway `HOME` never enables the real user manager; `--supervise` forces it. `herdr-doctor --relay` checks whichever timer is in use. The timers alone do not mark the relay installed: plain `herdr-doctor` stays a core check until a route, a hook or a launchd plist is there.

systemd runs user timers only while your user manager runs. On a machine nobody logs in to (a server a bot reaches over SSH), run `loginctl enable-linger $USER` once, or the timers stop when the last session ends. The flock loop is a plain background process: it does not come back after a reboot, so run `install.sh` again after one.

The relay log is `~/Library/Logs/herdr-events.log` on macOS and `${XDG_STATE_HOME:-~/.local/state}/herdr-events.log` on Linux.

To stop the Linux timers:

```bash
systemctl --user disable --now herdr-event-watchdog.timer herdr-events-flush.timer 2>/dev/null || true
pkill -u "$USER" -f herdr-event-supervise || true
```

Never test a network watchdog with a live `tailscale down` over SSH: it cuts your own connection.
