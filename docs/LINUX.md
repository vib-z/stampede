# stampede on Linux

stampede runs on Linux as on macOS: the same command, the same skills, both backends (the Herdr TUI and Herdr Core), with the event relay's timers run by systemd or one flock-guarded loop instead of launchd. This page says what was verified, how, and what was not.

## What was verified

| platform | backend and versions | how | result | date |
|---|---|---|---|---|
| Ubuntu 24.04 arm64, a container under colima | install, `herdr-doctor`, the Herdr plugin, moshi-hook unpaired, the unit suite | [tests/evals/linux](../tests/evals/linux/README.md), cases I01 to I06 | 6 of 6 pass | 8 Nov 2026 |
| the same | a whole job on the real Herdr TUI 0.9.5 server | [tui_e2e.py](../tests/evals/live/tui_e2e.py), cases T01 to T10 | 10 of 10 pass | 8 Nov 2026 |
| the same | a whole job on the real Herdr Core 0.1.19 | [core_e2e.py](../tests/evals/live/core_e2e.py), cases C01 to C12 | 11 of 12 before the fixes (C08 failed: a phone question outlived `finish`) | 8 Nov 2026 |
| the same | the fixture evals, through the real `stampede` command against the fakes | [run.py](../tests/evals/run.py), 56 cases | 40 pass, 12 fail before the fixes; 54 pass after | 8 Nov 2026 |
| GitHub's `ubuntu-latest`, x86_64 | the unit suite, the relay samples, `install.sh`, Herdr 0.9.5 with `herdr-doctor`, the Herdr Core 0.1.19 smoke run, the fixture evals | [CI](../.github/workflows/ci.yml), every push and pull request | see the latest run | |

"Real" here means the real Ubuntu, Herdr server, panes, agent detection, plugin events, Herdr Core, moshi-hook binary, `install.sh`, relay scripts and `stampede` commands. The agents and the bot are stand-ins: small programs that look to Herdr and Herdr Core exactly like Claude or Codex at their prompt (their screen, their status, their hook calls), and a webhook on 127.0.0.1. A pass proves that Herdr, Herdr Core and stampede work together on Linux; it does not prove a signed-in Claude or Codex does. The run records, with every command, expected and actual, are in [tests/evals/runs](../tests/evals/runs).

## Install on Linux

You need Python 3.9 or later, git, jq, curl, `flock` (util-linux) and `ps` (procps), plus Herdr or Herdr Core and Claude Code. On Ubuntu: `sudo apt-get install -y python3 git jq curl util-linux procps`.

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede && cd ~/stampede
./install.sh                          # the skills, the commands in ~/.local/bin, and the event timers
export PATH="$HOME/.local/bin:$PATH"  # Ubuntu adds ~/.local/bin at login only if it existed then: add this to ~/.profile
herdr-doctor                          # or herdr-doctor --core for a Herdr Core job
```

Herdr and Herdr Core publish Linux builds for x86_64 and arm64: [Herdr](https://herdr.dev/docs/install/) (or the release binary from GitHub) and [Herdr Core](https://herdr.dev/core/) (`curl -fsSL https://releases.herdr.dev/core/install.sh | sh`). Moshi's `moshi-hook` has Linux builds too (Homebrew on Linux, or the tarball its formula names).

## The event timers

`install.sh` enables two systemd user timers, `herdr-event-watchdog.timer` (every 5 minutes) and `herdr-events-flush.timer` (every 2 minutes), when `systemctl --user` answers. Otherwise it starts one `herdr-event-supervise` loop held with `flock`. `herdr-doctor --relay` checks whichever this machine uses.

- systemd runs user timers only while your user manager runs: on a machine nobody logs in to, run `loginctl enable-linger $USER` once.
- The flock loop does not survive a reboot: run `install.sh` again after one.
- `--no-supervise` skips both; a `HOME` that is not the login home is skipped, so a throwaway home never touches a real user manager.

## What differs from macOS

| | macOS | Linux |
|---|---|---|
| relay timers | two launchd jobs you load ([watchdogs](../remote/watchdogs.md)) | systemd user timers, or the flock loop, started by `install.sh` |
| relay log | `~/Library/Logs/herdr-events.log` | `${XDG_STATE_HOME:-~/.local/state}/herdr-events.log` |
| de-dupe lock | `lockf` | `flock` |
| tools on a bare PATH (timers, the plugin hook) | `~/.local/bin`, `/opt/homebrew/bin` | `~/.local/bin`, `/usr/local/bin`, `/home/linuxbrew/.linuxbrew/bin` (both lists are searched on both) |
| who started a command (`approve-gate`) | `ps` | `ps` from procps; a command whose own row `ps` does not show is refused |

Herdr Core 0.1.17 and later start a terminal at once on a Linux machine without polkit (before, after 25 seconds); C12 measured the first status 0.1 s after start.

## Known gaps

- **systemd user timers** are not verified live: an unprivileged container has no user manager, so the live runs cover the flock loop only.
- **x86_64** runs only in CI (unit suite, install, doctor, the Core smoke run, the fixture evals); the live TUI and Core jobs ran on arm64.
- **No signed-in Claude or Codex** ran on Linux, no paired Moshi (only the unpaired `moshi-hook`, which makes `stampede ask` fail loudly), and no bot over SSH to a Linux machine.
- **Other distributions** than Ubuntu 24.04 were not run. Herdr Core's own changelog covers RHEL, Rocky and AlmaLinux 8 and Ubuntu 22.04.
- **After a Herdr server restart** Herdr restores the job's workspace with plain shells. `reopen.sh` refuses while it is open and says so: close that workspace, then run `reopen.sh` again.

Run it yourself: `tests/evals/linux/run.sh` (needs Docker; [tests/evals/linux](../tests/evals/linux/README.md)).
