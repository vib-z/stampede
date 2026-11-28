# Grok Bot: the preferred remote

A Grok Bot is an agent with a computer of its own. It reaches your machine over SSH on a private Tailscale network, starts a stampede job's lead in Herdr there, and waits for a webhook to tell it what happened. You talk to the bot from your phone; the fleet runs on your machine.

## Do
- Set up once, in this order:
  - [tailscale.md](tailscale.md): one private network for the bot and the machine.
  - [ssh.md](ssh.md): the bot logs in with a key, no password.
  - [herdr.md](herdr.md): Herdr and stampede on the machine, checked from the bot.
  - [webhook.md](webhook.md): events reach the bot, so it never polls.
  - [send.md](send.md): how the bot prompts an agent.
- Then, once per owner, ask their default preferences and save them ([below](#the-owners-preferences)).
- Then, for every job, follow the [grokbot-herdr](../../skills/grokbot-herdr/SKILL.md) skill exactly: connect, health check, own workspace, tag, start the lead, end the turn, act on events.
- Questions for the owner go to the owner in chat, never into a pane.
- Touch only the workspaces, tabs and panes the bot made.
- When the job ends, leave it open and ask before closing anything.

## The owner's preferences
Ask these in chat, each with its recommended answer, then save them on the machine in one command. Skip a question the owner does not care about: its answer stays as it is.

| ask | recommended | flag |
|---|---|---|
| Use pstack, working rules for a coding agent, on coding jobs? | yes | `--pstack yes\|no` |
| Which agent leads a job? | claude | `--lead claude\|codex` |
| The lead's model? | the default of that agent | `--lead-model <model>` |
| The lead's effort? | xhigh | `--lead-effort <level>` |
| Every worker's effort? | medium | `--worker-effort <level>` |
| Where do jobs run: the Herdr TUI or Herdr Core? | tui | `--backend tui\|core\|auto` |
| When is the work reviewed: once at the end, each step, or never? | end | `--review end\|each\|none` |

```bash
ssh <host> 'stampede setup --json --pstack yes --review each'        # only the answers the owner gave
ssh <host> 'stampede setup --json --pstack yes --review each --yes'  # after the owner saw the change and said yes
```

- With no terminal it asks nothing. A new settings file is written at once.
- A settings file the owner already has is never changed without `--yes`: the first line then exits 2 and prints the change, under `notes` with `--json`. Show the owner that change, and add `--yes` only on their yes.
- When the result says pstack is not installed, give the owner the install line it prints. A job runs without pstack ([Setup](../../docs/SETUP.md#pstack)).
- One job that is not coding work: add `--set dev.pstack=false` to its `stampede new`.

## Run
Give the bot the skill: [skills/grokbot-herdr/SKILL.md](../../skills/grokbot-herdr/SKILL.md) (its Steps are the per-job steps), with [herdr-fleet](../../skills/herdr-fleet/SKILL.md) beside it for the rules after the hand-off.

`<host>` is the SSH alias from [ssh.md](ssh.md). The rules every front door follows: [README.md](../README.md). The gates: [Safety](../../docs/SAFETY.md).
