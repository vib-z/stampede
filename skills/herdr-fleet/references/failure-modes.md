# Failure modes at a start

Each was hit for real; recheck a fix against the installed binary before relying on it. Startup dialogs and how to clear them: [unattended-setup.md](unattended-setup.md#startup-dialogs-the-lead-clears). Failures while running, in git and at close: [failure-modes-run.md](failure-modes-run.md).

## Permissions and the auto-mode classifier

| Symptom | Fix |
|---|---|
| A start denied as "Create Unsafe Agents" | Never work around it with other flags or subagents. Finish every other step (contract, briefs, panes, worktrees, register), then give the owner the exact start lines to run as `!` commands, or ask them for a Bash rule for `herdr agent start:*`. Try once; hand over on a denial. |
| Editing `~/.claude/settings.json` (or a script that does) refused as "Self-Modification", even when the owner asks | Expected. Give the owner the exact command to run with `!`. |
| `herdr agent list` denied as "Credential Exploration" (its JSON holds session ids and paths) | Filter it to names and states with jq ([tui.md](tui.md#look-first)). |
| Writes to shared resources refused (a shared database, a merge) | Report the exact command and why, and let the owner run it. Never route it through another agent. |
| Hermes with `--yolo` or Kimi with `-y` denied by a safety check | These are the approved flags. Retry the same command through the caller's approval path, so the owner approves it once; inside Claude, extend `autoMode.allow` to them. Never a different bypass flag or a reshaped command. |

## Starting agents

| Symptom | Fix |
|---|---|
| A folder trust dialog; the start returns `agent_not_ready` | Prevent it: `herdr-trust <repo dir>` before the first start. If it still shows, clear it as in [unattended-setup.md](unattended-setup.md#startup-dialogs-the-lead-clears), or the owner presses Down and Enter. |
| Claude's "New MCP server found in this project" (an `.mcp.json` in the folder or a parent) | Prevent it: write `{"disabledMcpjsonServers": ["<server>"]}` to `<agent cwd>/.claude/settings.local.json` before the first start; this works in a folder that is not a git repo, where `herdr-trust` refuses. Else clear it. |
| A startup dialog is up but `agent get` says `idle` | Herdr marks only some dialogs `blocked`. Read the screen after every start, before the first prompt. Clear a known startup dialog; hand anything else to the owner. |
| `agent start` returns `timeout`, but the agent works | `herdr pane read <pane> --source visible --lines 20`, then `herdr agent rename <pane> <name>`. Never start a second agent in that pane. |
| `timeout` after the full wait, and the pane shows the CLI's error above a shell prompt | The CLI exited at once (such as `cursor-agent` with the keychain locked). Fix the cause; never retry blindly. |
| A CLI needs a login (Kimi "stored token rejected", Gemini's sign-in picker, Cursor "login keychain is locked") | An owner prerequisite. Exit it and tell the owner. Never type credentials, codes or an account switch. |
| `agent prompt` returns `agent_blocked` | At a dialog Herdr recognised; nothing was sent. Read the screen; clear a startup dialog, ask the owner about an action prompt. |
| Text sent to an agent at a dialog shown as `idle` goes in as keystrokes | Read the screen before every prompt and every exit. Leave a dialog with `esc`, or close the pane you made. |
| An agent's `herdr agent prompt <other>` fails: "not an active named agent" | The other had not started yet. Start every agent before prompting one whose brief messages another, or have the sender retry. |
| Codex prints "Please restart Codex" and exits after updating itself (Gemini updates on start too) | `herdr pane read <pane>` shows a shell. Start it again once; never while the owner has a restart queued in the lead's pane. |
| `agent start` refuses the pane | It must sit at a shell prompt with nothing in the foreground. Read it; clear a half-typed line with `herdr pane send-keys <pane> ctrl+c`. |
| A long `agent start` or `pane run` line is rejected on macOS | The line-input limit (about 1 KB). Keep the start short; send the prompt with `agent prompt`. |
| Flags vanish in `-- $ARGS`, or a plan cell `opus, xhigh` became `--model opus,` | zsh does not word-split; model and effort are separate flags ([clis.md](clis.md#zsh-and-herdr-flags)). |
| Herdr reads Codex's "Implement this plan?" as `idle` and Cursor's "Ready to build?" as `done` | After a plan-mode turn, read the screen: that is a waiting dialog, not finished work. |
