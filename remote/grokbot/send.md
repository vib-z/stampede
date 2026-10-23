# Grok Bot, part 5: prompting an agent

Every message to an agent goes through one helper that makes sure it landed.

## Do
- Prompt only through the send helper; never paste and press Enter.
- Go on only when it says submitted.
- On a failure, read the screen once before any resend.
- Never send an interrupt to an idle Codex: on an empty prompt it quits.
- Prompt only agents in the bot's own workspace, never the focused pane.
- Never type a gate's yes into a pane; the owner's answer to a gate goes only through `stampede approve-gate` ([events.md](../events.md)).

## Run
```bash
herdr-send <agent or pane id> "<text>"
herdr agent read <agent> --source visible --lines 30     # after a FAILED line, before any resend
stampede tell <job dir> <agent> "<text>"                 # inside a job: a Claude agent's inbox file, never typed
herdr-send <agent> "/exit"                               # Claude and Hermes; Codex takes /quit
```

| output | meaning |
|---|---|
| `SUBMITTED <agent>` | the agent took the prompt and started working |
| `SUBMITTED <agent> (pressed Enter again: the first was dropped)` | Claude kept the text but lost the Enter while drawing its screen; it was pressed once more |
| `SUBMITTED <agent> (the agent exited)` | `/exit` or `/quit` ended the agent, as asked |
| `FAILED <agent> (not a live agent)` | no agent by that name or pane; exit 1 |
| `FAILED <agent> focused: the owner is in that pane; retry later` | the owner has that pane selected; no key or prompt was sent; exit 1 |
| `FAILED <agent> (blocked at a dialog; read the screen)` | the agent waits at a dialog; exit 1 |
| `FAILED <agent> (status before: ..., now: ...)` | the prompt did not start a turn; read the screen; exit 1 |

`SUBMITTED` means the agent admitted the message, not that it has acted on it; wait for its report. Usage errors exit 2. How each CLI behaves: [agents-and-models.md](../../skills/herdr-fleet/references/agents-and-models.md).
