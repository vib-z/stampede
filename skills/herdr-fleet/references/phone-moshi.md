# The owner's phone (Moshi)

The owner can watch and steer jobs from an iPhone with Moshi, paired to the machine. The binary is the authority: `moshi-hook <command> --help`. Moshi's own skill, `moshi-best-practices`, covers host setup and troubleshooting.

## What already happens, with no work from the lead

- `moshi-hook` runs as a service with hooks in Claude (`~/.claude/settings.json`) and Codex (`~/.codex/hooks.json`), beside herdr's own state hooks. `moshi-hook doctor` lists the other CLIs it hooks.
- Every agent's questions (AskUserQuestion), plan approvals, permission prompts and turn ends reach the phone's Inbox, tagged with the herdr workspace and tab; one tap reattaches the pane. So name tabs and agents after the task.
- The phone shows herdr's tabs with each agent's status, and panes are reachable too: no pane limit for the phone's sake.
- Keep **one herdr server session** (`default`): Moshi attaches to a workspace directly only while a single session runs.
- The classifier's refusals are not prompts and never reach the phone.
- Claude Code's own phone notifications stay on too, so some events arrive twice. Leave that.

## What the lead adds

- **Questions:** `stampede ask` (it runs the setting `ask.command`, `moshi-hook ask` by default, in a local job; in a bot's job it goes to that bot). AskUserQuestion also reaches the phone in a local job. From a script, a watch loop or a Codex agent:

  ```bash
  moshi-hook ask --require-remote --source herdr-fleet --label "<project> lead" --timeout 2h "Merge build-api into main?"
  choice=$(moshi-hook ask --require-remote --source herdr-fleet --options "Ship,Hold,Revert" --timeout 2h "Review found 2 issues. Next?")
  ```

  Exit 0 approved or an option chosen, 1 denied or Cancel, 2 usage error, 3 timed out, 4 Moshi unreachable. The phone always offers Cancel: never list it in `--options` (that exits 2 at once). A failed ask returns within a second: read its exit. Always `--require-remote` (an agent's shell has no terminal).
- **One live progress row per job,** its id in `register.md`:

  ```bash
  id=$(moshi-hook job start --source herdr-fleet "<initiative> fleet")
  moshi-hook job update "$id" --progress 40 --message "2 of 5 reports in"   # silent; updates under 15 s apart coalesce
  moshi-hook job end "$id"                                                   # notifies; --error on failure
  ```

- **Alerts only for what Moshi cannot see.** `fleet-watch.sh` (a bot's watch) pushes `STALL?` and `GONE` with `moshi-hook notify`, never `REPORT` or `BLOCKED`: those already reach the phone. A startup dialog the lead cannot clear is the exception: ask the owner, naming the pane. `FLEET_WATCH_NOTIFY=0` silences the watch.
- **A one-off message:** `moshi-hook notify --source herdr-fleet --title "<title>" "<message>"`; `--silent` updates the Inbox without a buzz, `--error` marks a failure.

## Settings to leave alone

- `suppress-nested-agent-push` stays **off**: it hides a nested agent's approvals too. Fleet agents are not nested anyway.
- `suppress-push-while-unlocked` stays off: the owner's choice.
- After a herdr or moshi-hook update, `moshi-hook doctor` (it only reports without `-y`). Reinstalling hooks (`moshi-hook install`, `herdr integration install claude|codex`) writes the agents' settings, so the owner runs it. Its warning for the `pi` agent does not apply.

Sources: getmoshi.app/docs/herdr, /guides/fleet, /docs/hook-settings, /docs/moshi-cli, /docs/skill.
