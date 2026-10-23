# Moshi: the phone, with any remote

Moshi is a phone terminal for your own machine. It attaches to Herdr's tabs and panes over SSH or Mosh, and its hook sends every agent's questions, approvals and finished turns to the phone. Use it alone, or beside Grok Bot, Claude or Codex.

## Do
- Install Herdr and Moshi's hook on the machine; pair the phone.
- Keep one Herdr session, with a workspace per project.
- Name tabs and agents after the task: that is what the phone shows.
- Answer agents' questions from the phone Inbox; one tap opens the pane. In a job you started locally, the lead's questions and gates come as cards; a job a bot started asks in the bot's chat.
- Hook settings are the owner's to change.

## Run
```bash
moshi-hook doctor                         # read only; checks the hooks for each agent CLI
moshi-hook ask --require-remote --source herdr-fleet --timeout 24h --option "Keep all" --option "Trim to 5" -- "Trim the list?"   # what stampede ask runs
```

- **`moshi-hook ask` exits:** 0 yes or an option chosen, 1 no or Cancel, 2 usage error (2 to 6 options), 3 timed out, 4 Moshi unreachable. Always pass `--require-remote`. It is the default `FLEET_ASK_CMD`, which `stampede ask` runs for the lead in the background in a job started locally (a bot-started job asks its bot); the answer, or why it failed, lands in the lead's inbox. The phone always offers Cancel, so never list it in `--options`.
- **What the phone already gets:** questions, plan approvals, permission prompts and turn ends from every hooked CLI. `fleet-watch.sh`, for a bot outside Herdr, adds only `STALL?` and `GONE`; `FLEET_WATCH_NOTIFY=0` turns that off.
- **Detection fails:** `herdr` is missing from the non-interactive SSH PATH. Check with `ssh <host> 'command -v herdr'`.
- **More:** [phone-moshi.md](../skills/herdr-fleet/references/phone-moshi.md). **Docs:** [Moshi and Herdr](https://getmoshi.app/docs/herdr), [moshi CLI](https://getmoshi.app/docs/moshi-cli), [hook settings](https://getmoshi.app/docs/hook-settings).
