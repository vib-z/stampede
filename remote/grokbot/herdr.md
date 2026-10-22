# Grok Bot, part 3: Herdr and stampede on the machine

Herdr runs on your machine and holds the agents in panes. stampede is a Herdr plugin. The bot drives both over SSH and treats the machine's Herdr as the authority.

## Do
- Install Herdr and stampede on the machine, not on the bot.
- Run the health check before every job; stop and tell the owner on a problem.
- Never start or stop the Herdr server or its screen from the bot.
- Make a workspace of its own and use the ids Herdr returns, never guesses.
- Read the screen after every agent start; clear only the dialogs below.
- Login, payment, account or anything unfamiliar: stop and ask the owner.

## Run
```bash
git clone https://github.com/vib-z/stampede.git ~/stampede && ~/stampede/install.sh   # on the machine, once
herdr-doctor                                    # exit 0 go on, exit 1 stop and report the PROBLEM lines
herdr workspace list                            # never bare herdr over SSH: it opens the screen and hangs
herdr workspace create --cwd <project dir> --label bot-<task> --no-focus
herdr-trust <project dir>                       # before agents start in a repo under FLEET_TRUST_ROOT; it writes the agents' own trust settings
herdr agent read <agent> --source visible --lines 30
herdr agent send-keys <agent> esc               # Codex "Update available": skip it, never Enter
```

- **Install:** [herdr.dev/docs](https://herdr.dev/docs/) for Herdr. stampede's own setup: [docs/SETUP.md](../../docs/SETUP.md).
- **Literal ids:** keep `.result.workspace.workspace_id`, `.result.tab.tab_id` and `.result.root_pane.pane_id` from the create. Use the first tab; do not leave it empty.
- **Never** set `HERDR_ENV` yourself, and never use `herdr --remote` from the bot.
- **Commands:** [CLI reference](https://herdr.dev/docs/cli-reference/), [agent automation](https://herdr.dev/docs/agent-automation/). Where they differ, the installed `herdr <command> --help` wins.
