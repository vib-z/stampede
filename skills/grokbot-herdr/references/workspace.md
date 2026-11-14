# A bot's workspace: make it, start in it, close it

Every command here runs on the machine over `ssh -o BatchMode=yes <host> '...'` ([SKILL.md](../SKILL.md), step 1).

## The workspace

- **Your own:** `herdr workspace create --cwd <repo dir> --label bot-<task> --no-focus`. Keep the literal ids it returns: `.result.workspace.workspace_id`, `.result.tab.tab_id`, `.result.root_pane.pane_id`. Never guess an id, never read one from an environment variable.
- **First tab rule:** `workspace create` already makes tab 1 with a root pane. Use it for the first workstream: `herdr tab rename <tab id> <label>`, and the lead goes in its root pane (`stampede new --pane` makes that tab `lead`). Only `tab create` for further workstreams.
- **An existing project workspace:** find it by label, `herdr workspace list | jq -r '.result.workspaces[]|select(.label=="<project>").workspace_id'`, then `stampede new --workspace <id>` (the lead gets a new `lead` tab). Before you make tabs there, list them; rename a leftover empty default tab and use it.
- **The tag:** `herdr-events-owner <workspace id> <bot slug>` (a lowercase bot name). The id is the literal `.result.workspace.workspace_id`, never the `.result.workspace` object: the script refuses anything that is not a live workspace id. `--clear` removes the tag; no second argument shows it. Once the owner's Herdr config lists that token, the sidebar shows your slug as `$owner`.
- **One-off commands in a pane:** also set `HERDR_EVENTS_OWNER=<bot slug>`.
- **The job folder** is `<jobs_root>/jobs/<date>-<bot>-<slug>` (`stampede config show` names the root); the repo stays the lead's cwd.

## Trust

- Before agents start in a repo under the trust root (`FLEET_TRUST_ROOT`), run `herdr-trust <repo dir>`. It marks the repo trusted for Claude and Codex, so neither asks.
- A trust dialog that still shows (a new folder that is not a repo, or the write was refused): Claude: `herdr agent send-keys <name> down`, read to confirm "Yes, I trust this folder" is selected, then `herdr agent send-keys <name> enter` as a separate call. Codex: `herdr agent send-keys <name> enter` on "Trust and continue".
- A folder outside the trust root: stop and ask the owner.

## Startup dialogs

After every start, read the screen once: `herdr agent read <name> --source visible --lines 30`. A start that returns `agent_not_ready` is blocked at a dialog, and some dialogs report `idle` instead.

| dialog | do |
|---|---|
| Codex "Update available" | `herdr agent send-keys <name> esc`. Never Enter: the default, "Update now", runs npm |
| Claude "New MCP server found in this project" | `herdr agent send-keys <name> enter` on the default, "Continue without using this MCP server" |
| login, payment, account switch, anything unfamiliar | stop and ask the owner |

- In a folder `herdr-trust` refuses (not a git repo), prevent the MCP dialog before the start: write `{"disabledMcpjsonServers": ["<server>"]}` to `<cwd>/.claude/settings.local.json`.
- After clearing a dialog: `herdr agent wait <name> --until idle --timeout 30000` (a stale `blocked` clears within seconds), read the screen once more, then, if `stampede new` printed `BLOCKED`, send the `stampede tell` line it printed.
- More dialogs and their fixes: [unattended-setup.md](../../herdr-fleet/references/unattended-setup.md) and [failure-modes.md](../../herdr-fleet/references/failure-modes.md).

## The reopen record

`stampede new` records the lead's start in `<job dir>/agents.tsv`. Once it runs, `herdr-reopen-snapshot <workspace id> <job dir>` writes `REOPEN.md` and `reopen.sh` there. Refresh it after every later start and before any close. A Core job keeps its own record (`stampede snapshot <job dir>`).

## Closing, only on the owner's yes

The job's end is a question, never an action: "Close workspace <label>? Reopen with <job dir>/reopen.sh." No answer is a no. Only after the owner's explicit yes, as the last step, and only for a workspace you created:

```bash
herdr-send <agent> "/exit"                     # each agent; Codex takes /quit
herdr-reopen-snapshot <workspace id> <job dir>
herdr-events-owner <workspace id> --clear
herdr workspace close <workspace id>           # the whole workspace, so no stray tab 1 is left
```

A Core job closes with `stampede close <job dir>`, on the same yes. Never close a project workspace.

## Herdr's own docs

Herdr on the machine is `~/.local/bin/herdr`; run `herdr --version` there first. Re-read the [CLI reference](https://herdr.dev/docs/cli-reference/) and [agent automation](https://herdr.dev/docs/agent-automation/), and `herdr <cmd> --help` on the machine, after an upgrade or when a command fails. Where they differ, the installed binary wins.
