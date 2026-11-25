# Grok Bot, part 5: prompting an agent

Every message to an agent goes through one helper that makes sure it landed.

## Do
- Prompt only through the send helper; never paste and press Enter.
- Go on only when it says submitted.
- On a failure, read the screen once before any resend.
- Never send an interrupt to an idle Codex: on an empty prompt it quits.
- Prompt only agents in the bot's own workspace, never the focused pane.
- Never type a gate's yes into a pane; the owner's answer to a gate goes only through `stampede approve-gate` ([events.md](../events.md)), run over plain ssh, never through `hc exec` (it refuses inside Herdr and Herdr Core).

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
| `SUBMITTED <agent> (it started late)` or `(the text left its prompt)` | Herdr saw no turn start in 5 seconds, but a turn started later, or the text left the prompt |
| `SUBMITTED <agent> (pressed Enter again: the first was dropped)` | the agent kept the text, or its paste placeholder, and lost the Enter; Enter was pressed again, up to 3 times, until it went in |
| `SUBMITTED <agent> (the agent exited)` | `/exit` or `/quit` ended the agent, as asked |
| `FAILED <agent> (not a live agent)` | no agent by that name or pane; exit 1 |
| `FAILED <agent> focused: the owner is in that pane; retry later` | the owner has that pane selected; no key or prompt was sent; exit 1 |
| `FAILED <agent> focused: the owner came into that pane ...` | the prompt was typed, and the owner came in before `herdr-send` could confirm it went in (`its prompt still holds the text` when the screen shows it); no key was pressed after that; read the screen before any resend; exit 1 |
| `FAILED <agent> (blocked at a dialog; read the screen)` | the agent waits at a dialog; exit 1 |
| `FAILED <agent> (the text stayed in its prompt through 3 Enter; cleared it with ctrl+c, ...)` | the text never went in, so it was cleared; send it again; exit 1 |
| `FAILED <agent> (...: read it with herdr agent read <agent> before any resend)` or `(status before: ..., now: ...; ...)` | it cannot tell whether the prompt went in, or another text is in the prompt; read the screen before any resend; exit 1 |

On Herdr Core there is no `herdr-send`: pass the owner's words with `stampede tell <job dir> lead "..."` (it runs `hc send` to the lead), and read the lead or a helper with `hc read <address>`; never type into a helper ([core.md](../../skills/herdr-fleet/references/core.md)).

`SUBMITTED` means the agent admitted the message, not that it has acted on it; wait for its report. Usage errors exit 2. How each CLI behaves: [clis.md](../../skills/herdr-fleet/references/clis.md).
