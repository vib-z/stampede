# Cross-client suite

This suite shows that stampede works when each client it supports drives it, on the Herdr TUI and on Herdr Core. Every client should reach the same outcomes; the features they use may differ. Any client that does worse is flagged here.

## Outcomes

- **O1 health**: the client runs the health check (`herdr-doctor`, with `--core` or `--relay`) and reads the result.
- **O2 start**: `stampede new` from the client starts a lead. The lead writes `plan.md` and works.
- **O3 workers**: the lead starts each worker kind the backend allows (claude, codex, and cursor on the TUI only). On Core, a cursor worker is refused with the documented message.
- **O4 question**: a question from the lead reaches the client's channel (a bot's route, or `FLEET_ASK_CMD`), and the answer gets back to the lead.
- **O5 gate**: a gate reaches the client. The lead acts only on a yes, recorded or typed, for that commit. `approve-gate` is refused inside Herdr or Core, and for another commit.
- **O6 tell**: the client tells an agent something. On Core, the message goes in only while the agent is idle.
- **O7 finish**: one finish event reaches the client, and the job marker is cleared.
- **O8 reopen-safe**: `reopen.sh` on a live job starts nothing. On the TUI it refuses while the workspace is open.
- **O9 no-poll**: a bot waits for events and does not poll.

## Clients

| client | stands for | where it runs | automated | live, TUI | live, Core |
|---|---|---|---|---|---|
| `herdr-chat` | a Claude chat in a Herdr pane | inside Herdr | planned | planned | planned |
| `claude-code` | Claude desktop or the Claude app, on the machine | outside Herdr | planned | planned | planned |
| `codex` | Codex desktop or the ChatGPT app, on the machine | outside Herdr | planned | planned | planned |
| `cursor` | a Cursor chat on the machine | outside Herdr | planned | planned | planned |
| `hermes` | a Hermes chat on the machine | outside Herdr | planned | planned | planned |
| `grokbot` | Grok Bot, over SSH from its own computer | over SSH | planned | planned | planned |
| `other-bot` | any other bot with a computer of its own | over SSH | planned | planned | planned |
| `remote-computer` | Herdr, the CLIs and stampede on one remote box | inside Herdr | planned | planned | planned |

## Run it

```bash
python3 -m unittest tests.test_clients
```
