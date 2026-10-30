# Cross-client suite

This suite shows that stampede works when each client it supports drives it, on the Herdr TUI and on Herdr Core. Every client should reach the same outcomes; the features they use may differ. Any client that does worse is flagged here, under [Doing worse](#doing-worse).

It has two halves. The automated half ([tests/test_clients.py](../tests/test_clients.py)) runs in CI on every push: one job per client and backend against the repo's fakes, through the real `stampede` command. The live half is a maintainer running the same small job from each real client ([Live runbook](#live-runbook)).

## Outcomes

- **O1 health**: the client runs the health check (`herdr-doctor`, with `--core` or `--relay`) and reads the result.
- **O2 start**: `stampede new` from the client starts a lead. The lead writes `plan.md` and works.
- **O3 workers**: the lead starts each worker kind the backend allows (claude, codex, and cursor on the TUI only). On Core, a cursor worker is refused with the documented message.
- **O4 question**: a question from the lead reaches the client's channel (a bot's route, or `FLEET_ASK_CMD`), and the answer gets back to the lead.
- **O5 gate**: a gate reaches the client. The lead acts only on a yes, recorded or typed, for that commit. `approve-gate` is refused inside Herdr or Core, and for another commit.
- **O6 tell**: the client tells an agent something. A Claude agent, the lead included, gets it in its inbox file at any time. Another CLI is prompted: on Core, an idle agent through `hc send --if idle` (so it goes in only while it is still idle), an agent whose turn is done at once, and a working one is refused.
- **O7 finish**: one finish event reaches the client, and the job marker is cleared.
- **O8 reopen-safe**: `reopen.sh` on a live job starts nothing. On the TUI it refuses while the workspace is open.
- **O9 no-poll**: a bot waits for events and does not poll.

## Clients

Automated: the suite's result against the fakes, 30 Oct 2026. Live: a run from the real client on one Mac.

| client | stands for | where it runs | its jobs belong to | automated | live, TUI | live, Core |
|---|---|---|---|---|---|---|
| `herdr-chat` | a Claude chat in a Herdr pane | inside Herdr | the machine (local) | O1 to O8 pass | pending | pending |
| `claude-code` | Claude desktop or the Claude app, on the machine | outside Herdr | local | O1 to O8 pass | pending | pending |
| `codex` | Codex desktop or the ChatGPT app, on the machine | outside Herdr | local | O1 to O8 pass | pending | pending |
| `cursor` | a Cursor chat on the machine | outside Herdr | local | O1 to O8 pass | pending | pending |
| `hermes` | a Hermes chat on the machine | outside Herdr | local | O1 to O8 pass | pending | pending |
| `grokbot` | Grok Bot, over SSH from its own computer | over SSH | the bot, by the workspace's owner tag | O1 to O9 pass | pending | pending |
| `other-bot` | any other bot with a computer of its own | over SSH | the bot, by `HERDR_EVENTS_OWNER` | O1 to O9 pass; TUI O9 partial ([F2](#doing-worse)) | pending | pending |
| `remote-computer` | Herdr, the CLIs and stampede on one remote box | inside Herdr | local | O1 to O8 pass | pending | pending |

O9 is for bots only: a local client hears from its own pane, the lead's card or the phone.

## What differs between clients

In code, the clients differ in their environment and flags, not in the commands they run. The lead's side is the same for all of them.

| | inside Herdr | outside Herdr | over SSH (a bot) |
|---|---|---|---|
| environment | `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID` set | no Herdr ids, no Herdr process above it | no Herdr ids; its parent is `sshd` |
| start on the TUI | `stampede new --file <ask.md>` (this workspace) | `herdr workspace create`, then `stampede new --file <ask.md> --pane <its root pane>` | the same, after `herdr-events-owner <workspace> <bot>`, or with `HERDR_EVENTS_OWNER=<bot>` |
| start on Core | `stampede new --core --file <ask.md> --cwd <repo>` | the same | `HERDR_EVENTS_OWNER=<bot> stampede new --core ...` (no workspace to tag) |
| questions and gates | the phone (`FLEET_ASK_CMD`), or the lead's own card | the phone | `question` and `gate` events on the bot's route |
| `approve-gate` | refused: an agent's command | refused: a local job's gate is the phone's | allowed over plain SSH, for that commit only |
| finish | the ordinary relay (logged, or the default route) | the same | one `done` event on the bot's route |

## What the automated suite asserts

For every client and backend, as a subtest named `<client>/<backend> <outcome>`, for example `cursor/core O3`:

- **O1:** `herdr-doctor` run with the client's environment (`--relay` for a bot, `--core` on Core) prints the same lines and exit code as a run with none: the doctor reads the machine, not the client. On Core it reads the fake `hc` (`ok hc 0.1.13`), never a real core.
- **O2:** `stampede new` exits 0 and prints `<lead> <job dir>`; the job is marked open; `<job>/owner` names the bot, or is absent for a local client; the lead got its brief pointer (its inbox on the TUI, its first prompt on Core).
- **O3:** the lead starts one worker of each kind in `WORKERS`, the one worker registry: claude, codex and cursor on the TUI, claude and codex on Core. A kind the backend does not take exits 2 with its reason from `REFUSED` (on Core, cursor: `Cursor reports no OSC 7501 status`), and no terminal starts.
- **O4:** a bot gets one `question` event on its own route and runs the answer command it carries; a local client's phone card (a recorder in place of Moshi) gets the question and options. Either way the answer lands in the lead's inbox, and nothing goes to the other channel.
- **O5:** `approve-gate` exits 2 when run inside Herdr, in a Core terminal (`HC_TERMINAL_ID` set), or for another commit. A bot's `approve-gate` over SSH records the yes; a local job's yes is the phone card's, and the client's own `approve-gate` is refused. Then `gate-ok` prints `APPROVED` for that commit and refuses another.
- **O6:** `stampede tell <job> lead` lands in the lead's inbox (a Claude agent's inbox file, with no status check); an idle codex worker gets `SUBMITTED` (on the TUI through `herdr-send`). On Core that send is `hc send --if idle`; a working worker gets `FAILED ... (working: tell it after its turn)` with nothing sent; a worker whose turn is `done` gets `SUBMITTED`, sent without `--if`.
- **O7:** two `stampede finish` calls give one `done` event on the bot's route (a local job: one line logged by the relay, nothing queued), the `finished` stamp, and no marker.
- **O8:** on the TUI, after `herdr-reopen-snapshot`, `reopen.sh` refuses (exit 2) while the workspace is open and makes no workspace, tab or agent; on Core it prints `LIVE <key>: no agent to restart` and starts no terminal.
- **O9 (bots):** a plain turn end of the open job is not queued; the `question`, `gate` and `done` events each carry the command the bot runs next; the lead's `blocked` reaches the bot's route.

## Run it

```bash
python3 -m unittest tests.test_clients        # about 15 s; part of python3 -m unittest discover tests
```

Expected: `OK (skipped=12, expected failures=2)`. The 12 skips are O9 for the six local clients on two backends; the 2 expected failures are the findings below. A failure names the client, backend and outcome, as in `FAIL: test_o5_gate (...) [grokbot/core O5]`.

How it runs: [tests/clients_run.py](../tests/clients_run.py) plays one job per client and backend, 8 at a time, each in a scratch folder with its own `HOME`, a fake Herdr (`HERDR`, and first on `PATH`), the fake Herdr Core [tests/fake_hc.py](../tests/fake_hc.py) (`HC`), fake `claude` and `codex`, a route for a bot that is never flushed, and a recorder as `FLEET_ASK_CMD`. A client outside Herdr runs its commands with pid 1 as their parent's parent, so no Herdr process sits above them wherever the suite runs; a bot's run under a process named `sshd`. Nothing reaches a real Herdr, Herdr Core, agent CLI or the network.

## Add a client

1. One row in `CLIENTS` in [tests/test_clients.py](../tests/test_clients.py): its README front-door row (or `None`), `where` (`inside`, `outside` or `ssh`), its `backends`, and for a bot its slug (`bot`) and `owner_from` (`tag` or `env`).
2. One row in the [Clients](#clients) table above, with its automated result once the suite passes.
3. A live run from the real client ([Live runbook](#live-runbook)), and its row's live cells.

`ClientsInSync` fails until README's front doors, `CLIENTS` and this table agree. A client that behaves differently in code (a new environment, flag or channel) needs that difference in `tests/clients_run.py`, and the matching line in [What differs](#what-differs-between-clients).

**A worker kind** is not a client: add it to `WORKERS` under each backend that takes it, and for a backend that does not, the refusal `stampede start` gives in `REFUSED`. Every client's job then starts it on every backend (O3); `test_every_kind_a_backend_does_not_take_says_why` fails until `REFUSED` names it.

## Live runbook

One small job per client and backend, on one Mac, by a maintainer. The commands below are the ones the automated suite runs against the fakes.

1. **Scratch repo:** `git init` a folder under `FLEET_TRUST_ROOT`, commit a README, run `herdr-trust <repo>`.
2. **No phone cards:** set `FLEET_ASK_CMD` to a recorder that logs the question and prints the first option, or `yes` for a gate.
3. **The ask:** one worker writes `hello-<client>-<backend>.txt`; the lead asks one question with two options, asks a gate for committing the file at `HEAD`, commits only after `gate-ok` prints `APPROVED`, then runs `stampede finish` once.
4. **Start, from the client** (`--name xc-<client>-<backend>`):
   - inside Herdr: `stampede new --file <ask.md> --name <name>`;
   - outside Herdr: `herdr workspace create --cwd <repo> --label <name> --no-focus`, then `stampede new --file <ask.md> --pane <root pane> --name <name>`;
   - a bot over SSH: the same, after `herdr-events-owner <workspace> <bot>`;
   - on Core, any client: `stampede new --core --file <ask.md> --cwd <repo> --name <name>`, a bot with `HERDR_EVENTS_OWNER=<bot>` in front.
5. **Check each outcome:** `herdr-doctor` (O1); `plan.md` and the worker (O2, O3); the recorder log or the bot's `question` event, then the answer in `<job>/inbox/` (O4); `approve-gate` from the bot over SSH, refused from a Herdr pane, then `gate-ok` (O5); `stampede tell <job> <agent> "<text>"` (O6); `bash <job>/reopen.sh` on the live job, after `herdr-reopen-snapshot <workspace> <job>` on the TUI (O8); the finish line and the marker gone from `~/.config/herdr-events/jobs/` (O7). A bot waits for its webhook between steps (O9).
6. **Record** PASS, FAIL with proof, or N/A with why, in the [Clients](#clients) table, dated, with personal details removed.

Leave the test workspaces open; the owner closes them.

## Doing worse

- **F1, a bot on Core, from its own guide.** Over SSH a bot has no workspace on Core, so only `HERDR_EVENTS_OWNER` makes a job its own. [remote/grokbot/herdr.md](../remote/grokbot/herdr.md) and [remote/other.md](../remote/other.md) give the Core start without it: run as written, the job is local, its questions and gates go to the phone, its finish to the default route, and the bot never hears them. Fix: put `HERDR_EVENTS_OWNER=<bot>` in front of those commands (the skills' source first). Test: `test_f1_a_bots_core_start_names_its_owner`.
- **F2, a bot that names itself by `HERDR_EVENTS_OWNER` on the TUI.** `stampede new` records it in `<job>/owner`, so questions, gates and finish reach it, but it does not tag the workspace, so the panes' own `blocked`, permission, `stale` and `dead` events go to the default route. On Core, `new` tags the job's key, so the follower's events do reach it. Fix: `new` on the TUI tags the workspace as `new --core` tags the key, or the guides say to tag first. Test: `test_f2_an_owner_set_by_env_hears_its_panes`.
- **Hermes has no front-door guide.** It is in `CLIENTS` and passes like the other local clients, but README's front doors and `remote/` do not name it.
