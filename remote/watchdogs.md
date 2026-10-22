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
| `herdr-doctor` | read only: tools on PATH, the Herdr server and client, the event plugin, the Claude and Codex hooks, the helpers, the two timers below, the route files, the queue, owner tags, leftover worktrees under `FLEET_TRUST_ROOT`, free disk; one `ok`, `warn` or `PROBLEM` line each, exit 1 on a PROBLEM | by hand or by the bot, before a job |
| `herdr-event-watchdog` | sends `stale` (working, no output change for 30 minutes) and `dead` (pane gone without a done); removes malformed tags and tags of workspaces gone a day | launchd, every 5 minutes |
| `herdr-event-flush` | sends the queued events, oldest first; after 24 hours undelivered, an event moves to `dead/` | launchd, every 2 minutes |
| `fleet-watch.sh` | for a bot outside Herdr: `REPORT`, `BLOCKED`, `GONE` and `STALL?` lines for one job, with a phone push (`FLEET_WATCH_*`) | by the bot, as a background command |

The two timers, as macOS launch agents with the labels `herdr-doctor` checks:

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
herdr-doctor
```

Never test a network watchdog with a live `tailscale down` over SSH: it cuts your own connection.
