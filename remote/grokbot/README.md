# Grok Bot: the preferred remote

A Grok Bot is an agent with a computer of its own. It reaches your machine over SSH on a private Tailscale network, starts a stampede job's lead in Herdr there, and waits for a webhook to tell it what happened. You talk to the bot from your phone; the fleet runs on your machine.

## Do
- Set up once, in this order:
  - [tailscale.md](tailscale.md): one private network for the bot and the machine.
  - [ssh.md](ssh.md): the bot logs in with a key, no password.
  - [herdr.md](herdr.md): Herdr and stampede on the machine, checked from the bot.
  - [webhook.md](webhook.md): events reach the bot, so it never polls.
  - [send.md](send.md): how the bot prompts an agent.
- Then, for every job, follow the [grokbot-herdr](../../skills/grokbot-herdr/SKILL.md) skill exactly: connect, health check, own workspace, tag, start the lead, end the turn.
- Questions for the owner go to the owner in chat, never into a pane.
- Touch only the workspaces, tabs and panes the bot made.
- When the job ends, leave it open and ask before closing anything.

## Run
Give the bot the skill: [skills/grokbot-herdr/SKILL.md](../../skills/grokbot-herdr/SKILL.md) (its Steps 1 to 4 are the per-job steps), with [herdr-fleet](../../skills/herdr-fleet/SKILL.md) beside it for the rules after the hand-off. Its commands call `fleet-job`, the same command as `stampede`.

`<host>` is the SSH alias from [ssh.md](ssh.md). The rules every front door follows: [README.md](../README.md). The gates: [README, Safety](../../README.md#safety).
