# The owner's phone (Moshi)

The owner watches and steers fleets from an iPhone with Moshi (Pro), paired to this Mac. Checked 2026-10-11
(rechecked 2026-10-14) with moshi-hook 0.4.28 and herdr 0.9.4. The binary is the authority: `moshi-hook <command> --help`.

## What already happens with no work from the lead

- `moshi-hook` runs as a Homebrew service and has hooks in both Claude (`~/.claude/settings.json`) and Codex
  (`~/.codex/hooks.json`), next to herdr's own state hooks. They coexist. `moshi-hook doctor` lists the other
  CLIs it hooks on this Mac (Gemini, Cursor, Kimi, Hermes and more), so those kinds reach the phone the same way.
- Every agent's questions (AskUserQuestion), plan approvals (ExitPlanMode), permission prompts and turn
  completions reach the phone's Inbox, tagged with the herdr session, workspace and tab. One tap reattaches
  that pane. So tab and agent names are what the owner reads on the phone: name them after the task.
- The phone shows herdr's tabs with each agent's status, and panes are reachable too (the owner uses them;
  no pane limit for the phone's sake).
- Keep **one herdr server session** (`default`) with a workspace per project. Moshi offers direct workspace
  attach only while a single session runs; a second named session turns it into a session list first.
- The auto-mode classifier's refusals are not prompts and never ping the phone; agents work around them.
- Claude Code's own phone notifications are also on. The owner keeps both (2026-10-11), so some events arrive
  twice. Do not change that.

## What the lead adds

- **Questions for the owner:** use AskUserQuestion. It already reaches the phone; the owner answers there.
  From a script, a watch loop or a Codex agent, gate on the phone directly:

  ```bash
  moshi-hook ask --require-remote --source herdr-fleet --label "<project> lead" --timeout 2h "Merge build-api into main?"
  choice=$(moshi-hook ask --require-remote --source herdr-fleet --options "Ship,Hold,Revert" --timeout 2h "Review found 2 issues. Next?")
  ```

  Exit codes: 0 approved or an option chosen, 1 denied or Cancel, 2 usage error, 3 timed out, 4 Moshi unreachable.
  The phone always offers Cancel, so never list it in `--options` (`"Approve,Change,Cancel"` exits 2 at once and
  the question is never asked). A failed ask returns within a second: read its exit before assuming it waits. Always pass
  `--require-remote` (an agent's shell has no terminal to fall back to).
- **One live progress row per fleet.** Start it when the agents start, keep its id in `register.md`:

  ```bash
  id=$(moshi-hook job start --source herdr-fleet "<initiative> fleet")
  moshi-hook job update "$id" --progress 40 --message "2 of 5 reports in"   # silent; updates <15s apart coalesce
  moshi-hook job end "$id"                                                   # notifies; add --error on failure
  ```

- **Alerts only for what Moshi cannot see.** `scripts/fleet-watch.sh` pushes `STALL?` (working, but the log
  stopped) and `GONE` (left its pane) with `moshi-hook notify`. It does not push `REPORT` or `BLOCKED`:
  completions and approval dialogs already reach the phone. A startup dialog the lead cannot clear is the
  exception: ask the owner with AskUserQuestion, naming the pane. `FLEET_WATCH_NOTIFY=0` silences the watch.
- **A one-off message** (end of a long run, a deploy finished): `moshi-hook notify --source herdr-fleet
  --title "<title>" "<message>"`. Add `--silent` to update the Inbox without a buzz, `--error` for failures.

## Settings to leave alone

- `suppress-nested-agent-push` stays **off**: it hides a nested agent's approvals too. herdr fleet agents are
  not nested anyway (each runs in its own pane, not as a child of the lead).
- `suppress-push-while-unlocked` is off by the owner's choice.
- After `herdr update` or a moshi-hook update, run `moshi-hook doctor` (it only reports without `-y`).
  Re-installing hooks (`moshi-hook install`, `herdr integration install claude|codex`) writes the agents'
  settings files, so the owner runs it. Its known warning for the `pi` agent is irrelevant here.

Moshi publishes its own skill, `moshi-best-practices` (host setup, Easy Pair, troubleshooting).
Sources: getmoshi.app/docs/herdr, /guides/fleet, /docs/hook-settings, /docs/moshi-cli, /docs/skill.
