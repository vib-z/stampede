# The Linux evals

One command runs stampede on a real Linux, with the real Herdr TUI 0.9.5 and the real Herdr Core 0.1.19, in a disposable container, and records every case as an eval run:

```bash
tests/evals/linux/run.sh                      # this checkout; runs land in tests/evals/runs/<stamp>-baseline-linux-{install,tui,core}
tests/evals/linux/run.sh --src <checkout> --label after-linux   # another checkout, another label
tests/evals/linux/run.sh --keep               # leave the container for a look: docker exec -it stampede-eval-<stamp> bash
tests/evals/linux/run.sh --only tui           # one runner (install, tui or core); install.sh and the plugin link still happen
```

It needs Docker (colima is fine) and the network once, for the pinned downloads. It exits 1 when a case failed or broke. Nothing is signed in, paired or sent anywhere: the bot's webhook is a stand-in on 127.0.0.1 inside the container.

## What it does

| step | where | what |
|---|---|---|
| image | [Dockerfile](Dockerfile) | Ubuntu 24.04 with git, jq, python3, ps, flock and curl; one unprivileged user; [install-pinned.sh](install-pinned.sh) installs the releases in [pins.txt](pins.txt) into that user's `~/.local/bin`, each download checked by sha256 before it is installed. No systemd: `install.sh` takes its flock path. |
| copy | [run.sh](run.sh) | the checkout under test (tracked and untracked files git does not ignore, never `.git`) into the container; the host commit goes along as `STAMPEDE_EVAL_COMMIT` |
| setup | [inside.sh](inside.sh) | the owner's one-time setup from [remote/events.md](../../../remote/events.md) (Claude's relay hooks, Codex's notify line, a route for the bot), the stand-ins on PATH as `claude` and `codex`, a scratch repo, the stand-in route ([route_server.py](route_server.py)), a real `herdr server` and a real `hc` core in the scratch session `evals` |
| I01 to I06 | [install_checks.py](install_checks.py) | the pinned installs, `install.sh` twice, the plugin link and its event hook, `herdr-doctor` plain, `--relay` and `--core`, the unit suite, moshi-hook unpaired behind `stampede ask` |
| T01 to T10 | [../live/tui_e2e.py](../live/tui_e2e.py) | one job on the real Herdr: a bot's front door from outside Herdr, the lead's commands inside a real pane of the job's workspace, two stand-in workers (Claude and Codex), tell and reply, the report's wake, a gate with the outside yes, close and reopen, a server restart, finish, the plugin event, Codex screen detection |
| C01 to C12 | `../live/core_e2e.py` | when that file is in the checkout, or given with `--core-script`, or found on the branch `qa/core-live` |

## What is real and what is a stand-in

Real: Ubuntu 24.04 (arm64 under colima here; the amd64 pins are in [pins.txt](pins.txt) but have not been run), Herdr 0.9.5 and its server, panes, agent detection, prompts and plugin events, Herdr Core 0.1.19, moshi-hook 0.4.50, every stampede command and relay script, `install.sh`.

Stand-ins: the agents and the bot. [standin.py](standin.py) is a small program Herdr sees as Claude or Codex: it draws the agent's prompt screen (Herdr's detection manifests read it), goes working while it acts, and keeps the agent's hook contract (a Claude stand-in runs the hooks of its `--settings` file as Claude does, with Claude's JSON on stdin; a Codex stand-in runs the notify command from `-c notify=[...]` and writes a rollout file). It reads its brief and does what the brief's `stand-in:` lines say; a worker echoes every later prompt to the lead. A pass proves Herdr, Herdr Core and stampede work together on Linux; it does not prove a signed-in Claude or Codex does.

## Known limits

- No systemd user manager in the container, so `install.sh` is verified on its flock path only; the systemd timers stay a gap here.
- The container runs its own Docker-provided init, not a login session: `XDG_RUNTIME_DIR` is a folder under the user's home.
- Herdr's remote detection manifests are fetched by the server at start (the container has network); without network the bundled manifests apply.
