# Failure modes and fixes

Seen in the owner's fleets between 2026-09-30 and 2026-10-14 (the smoke test of every installed CLI on 2026-10-14 included). Each was hit for real; recheck the fix against the installed binary before relying on it.

## Permissions and the auto-mode classifier

| Symptom | Fix |
|---|---|
| `agent start ... --permission-mode auto` (or a Codex start with `--approve-for-me`) denied as "Create Unsafe Agents" | Do not work around it with other flags or sub-agents. Finish every other setup step (contract, briefs, panes, worktrees, register), then give the owner the exact start lines to run as `!` commands in the lead pane. Or ask the owner to add a Bash permission rule for `herdr agent start:*`. On 2026-10-11, after the owner said "Can you do that for me?", the same start was allowed. Try once and hand over on denial. |
| Claude in a repo it has never opened shows "trust this folder". The start returns `agent_not_ready` | Prevent it: `~/.local/bin/herdr-trust <repo dir>` before the first start (owner-approved 2026-10-16). If it still shows: with [unattended-setup.md](unattended-setup.md) applied and the repo under `~/code`: `herdr agent send-keys <name> down`, read the screen to confirm "Yes, I trust this folder" is selected, then `herdr agent send-keys <name> enter` as a separate call. Then `herdr agent wait <name> --until idle --timeout 30000` (a stale `blocked` clears within seconds) and prompt. Otherwise the owner presses Down and Enter in that pane. Worktrees of a trusted repo never ask. |
| "Teach auto mode about your environment?" at the end of a turn | Turned off by `skillOverrides["auto-mode-setup"] = "off"` ([unattended-setup.md](unattended-setup.md)). |
| Editing `~/.claude/settings.json` (or writing a script that does) refused as "Self-Modification", even after the owner explicitly asks | Expected and correct. Give the owner the exact command to run with `!`. |
| `herdr agent list` occasionally denied as "Credential Exploration" (its JSON carries session ids and paths) | Filter it to names and states with jq, as in the SKILL.md quick look. |
| The classifier refuses writes to shared resources (a shared database, `gh pr merge`) | Report the exact command and why, and let the owner run it. Never route it through another agent. |
| `agent start` for Hermes with `--yolo` or Kimi with `-y` denied by a safety check or classifier (seen 2026-10-14) | These are the owner-approved start flags (2026-10-14). Retry the same command through the caller's approval path (approval card) so the owner approves it once; inside Claude, extend `autoMode.allow` to Hermes and Kimi. Never retry with a different bypass flag or a reshaped command. |

## Starting agents

| Symptom | Fix |
|---|---|
| `agent start` returns `timeout` but the agent is working (a positional prompt, or an already trusted folder) | `herdr pane read <pane> --source visible --lines 20` to confirm, then `herdr agent rename <pane> <name>`. Never start a second agent in that pane. |
| Claude start returns `agent_not_ready` at "New MCP server found in this project" (an `.mcp.json` in the folder or a parent, e.g. `~/code`) | Prevent it: before the first start, write `{"disabledMcpjsonServers": ["<server>"]}` (the server names in that `.mcp.json`) to `<agent cwd>/.claude/settings.local.json`; this works in a pack folder that is not a git repo, where `herdr-trust` refuses. If it still shows: `herdr agent send-keys <name> enter` on the highlighted default, "Continue without using this MCP server". It grants nothing. Then `herdr agent wait <name> --until idle --timeout 30000` (a stale `blocked` clears within seconds) and prompt. |
| An agent's `herdr agent prompt <other>` fails with "not an active named agent" | The other agent had not started yet (live test 2026-10-11: Claude reached its message step 9s after its prompt). Start every agent before prompting any whose brief messages another; or tell the sender to retry once the target is live. |
| Codex in a folder it has never opened: "Folder access, Trust this folder?"; the start returns `agent_not_ready`, status `blocked` | Prevent it with `herdr-trust <repo dir>` (above). If it still shows, for a repo under `~/code`: `herdr agent send-keys <name> enter` (the default is "Trust and continue"). Expect the hooks dialog next. |
| Codex "Hooks need review" (after folder trust, and again in a fresh worktree); the start times out, or returns with the dialog still up and status `idle` | `herdr agent rename <pane> <name>` if the name is missing, then `herdr agent send-keys <name> down down enter` (continue without trusting the hooks). Use `agent send-keys`, not `pane send-keys`: only the former is on the allow list. |
| A startup dialog is up (Codex hooks, Kimi or Gemini folder trust, Gemini's sign-in picker) but the start succeeded and `agent get` says `idle` | Herdr marks only some dialogs `blocked`. After every start, `herdr agent read <name> --source visible --lines 30` before the first prompt. Clear a known startup dialog; hand anything else to the owner. |
| Text sent with `agent prompt` to an agent at a dialog that shows as `idle` goes into the dialog as keystrokes (seen: `/quit` at Gemini's sign-in picker pressed Enter on "Sign in with Google") | Read the screen before every prompt and before every exit. Leave a dialog with `esc` (`ctrl+c` can quit Codex), or close the pane you created. Never type credentials or codes. |
| `agent prompt` returns `agent_blocked` | The agent is at a dialog herdr recognised; nothing was sent. Read the screen, clear a startup dialog yourself, ask the owner about an action prompt. |
| A CLI needs a login (Kimi: "stored token rejected"; Gemini: sign-in picker; Cursor: "login keychain is locked") | Blocked on an owner prerequisite (`kimi login`, Google sign-in, `security unlock-keychain`). Exit it and tell the owner, who logs in or unlocks the keychain in a session of their own. Never enter credentials, codes or an account switch for it. |
| `agent start` returns `timeout` after the full wait and the pane shows the CLI's error above a shell prompt (seen: `cursor-agent` with the keychain locked) | The CLI exited at once. Fix the cause; do not retry blindly. |
| `agent start` or `pane run` rejects a long command on macOS | The terminal's line-input limit (about 1 KB). Keep the start line short and send the prompt with `agent prompt`, which pastes. |
| Codex "Update available" at start (start returns `agent_not_ready`, status `blocked`); the highlighted default is "Update now" | `herdr agent send-keys <name> esc` skips it, then `herdr agent wait <name> --until idle --timeout 30000`. Never Enter: that runs npm and Codex exits (next row). |
| Codex self-updates (`npm install -g @openai/codex`), prints "Please restart Codex" and exits; Gemini updates itself on start too | `herdr pane read <pane>` shows a bare shell. Start it again once. Never issue a second start while the owner has a restart queued in the lead pane. |
| `agent start` refuses the pane | The pane must sit at a shell prompt with nothing in the foreground. Read it, and press `ctrl+c` with `herdr pane send-keys <pane> ctrl+c` if a half-typed line is there. |
| Flags vanish in `-- $ARGS` | zsh does not word-split. Write the flags literally or use an array. |
| A plan cell like `opus, xhigh` became `--model opus,` | Models and efforts are separate flags: `--model opus --effort xhigh`. |
| Herdr reads Codex's "Implement this plan?" as `idle` and Cursor's "Ready to build?" as `done`, not `blocked` | Read the screen after a plan-mode turn; `idle` or `done` there is a waiting dialog, not finished work. |

## Running agents

| Symptom | Fix |
|---|---|
| An agent hangs for hours inside a BrowserOS Neo call (hidden tabs never paint). The spinner keeps going | The truth is the session log's mtime (`ls -l ~/.claude/projects/*/<session-id>.jsonl`; the id is in `agent get` as `agent_session.value`). The watch script reports it as `STALL?`. If it is stale, kill and resume (below). Prevent it in `_common.md`: own new Neo window, ~2 minute limit, then WebFetch or curl. |
| Text sent to a hung agent with `agent prompt`, `send-keys` or `pane run` queues silently and spills into the shell after the kill | Do not prompt an agent you think is hung. After a kill, read the pane and clear the line with `ctrl+c` before restarting. |
| The Mac freezes (load 400+, swap full) and Neo drops with ECONNRESET | Dozens of leftover Neo renderer tabs are spinning. Count the `BrowserOS neo Helper (Renderer)` processes in `ps -Ao %cpu,command`. A force quit (`pkill -9 -f "BrowserOS neo"`) fixes it, but it kills every session's tabs, so ask the owner first. Logins survive. |
| Several panes run full `npx tsc --noEmit` or builds at once and the Mac runs out of memory | Agents run named test files only. The lead runs the full gates once. |
| With 6+ agents in Neo, extra screenshots fail ("Unable to capture") | Leave visual QA to one agent. |
| Stall alerts at 12 minutes fire during long xhigh thinking | Use 15 minutes (the watch script's default). |
| Codex sits in `unknown` after a reply and `agent wait` for `idle` times out | Seen with 0.9.3; 0.9.4 reported `done`. Either way the report file is the signal. |
| Kimi stays `working` after an error turn and `agent wait` times out | Read the screen. `STALL?` covers Claude and Codex only (the script knows their session log paths); check Hermes, Kimi and Gemini by screen. |
| Codex turn ends with "Selected model is at capacity" | Read the screen to confirm nothing changed, then send the prompt again with "Retry:" in front. If it happens again, or any agent reports a usage limit, restart the lane on its fallback (SKILL.md, Pick the agent and model), unless the owner named the model. |
| A prompt sits unsent in Claude's box and the agent stays `idle` (typed before Claude drew its screen; the Enter is lost) | `herdr-send` presses Enter once and prints `SUBMITTED <name> (pressed Enter again: ...)`. After a raw `agent prompt`, read the screen and, if the text is in the box, `herdr agent send-keys <name> enter` once. |
| A CLI times out inside agents but works for the lead (for example `npx shadcn search`) | The lead runs it, or uses the matching MCP tool, and writes the result into a brief. |
| The date rolls over mid-run and agents keep stamping yesterday | Tell them to use `date +%F`. That rule belongs in `_common.md`. |
| A lead runs parallel lanes (research, ideas) as built-in subagents (Claude's Agent tool): the owner cannot see them, Moshi and the watch miss them, and reviews cannot check them (seen 2026-10-17, when the brief named a pane for every step except research) | Open a pane per lane, as SKILL.md's "Panes, not built-in subagents" says. Briefs name every parallel step as a pane, e.g. `research-web` and `research-local` in a `research` tab. |
| An agent restarted in its own pane after `/exit` (a fresh reviewer per round) comes up unnamed: `agent list` shows `-` and `herdr-send <name>` prints "not a live agent" (seen 2026-10-17, round 4 of 5) | `herdr agent rename <pane> <name>`, then `herdr agent wait <name> --until idle --timeout 30000` and send. Check `agent list` after every restart. |
| `agent prompt` returns `agent_not_running` | The agent exited and its name was cleared. Read the pane before restarting. |
| A pane was moved with `pane move` and its old id fails | Use `.result.move_result.pane.pane_id` or the agent name. |
| A prompt typed into a pane the owner has focused lands in the middle of their typing | Check `herdr agent get <name> \| jq .result.agent.focused` first and wait while it is true. `fleet-job tell` to a Claude agent writes its inbox file and never types. |
| Claude's grey suggestion text in an idle prompt looks like typed input | It is not typing: `herdr agent read <name> --ansi` shows it dim. |
| A Claude agent that ran `cd` lost its file watch and missed its inbox | `fleet-job start` adds a `CwdChanged` hook that re-sends the watched paths. |
| Keys sent into another agent's dialog: one extra Enter approved a revised plan nobody saw | Answer dialogs with commands and files (`fleet-job tell`, a brief), not keys. |
| A killed question waiter left its card on the phone | `fleet-job cancel <job> <id>` stops the waiter and its card as one process group. |

## Kill and resume a hung Claude agent

```bash
P=<pane>; N=<name>
SID=$(herdr agent get "$N" | jq -r .result.agent.agent_session.value)   # null before the first turn for Codex, Hermes, Kimi: take it from the register
PID=$(herdr pane process-info --pane "$P" | jq -r '.result.process_info.foreground_processes[] | select(.argv0=="claude") | .pid')
kill -KILL "$PID"
herdr pane read "$P" --source visible --lines 10      # look for spilled text
herdr pane send-keys "$P" ctrl+c
herdr agent start "$N" --kind claude --pane "$P" --timeout 90000 -- \
  --resume "$SID" --model claude-opus-5-5 --effort xhigh --permission-mode auto
herdr agent prompt "$N" "You were restarted after a hang in a browser call. Re-read your brief and carry on; skip Neo for pages that hang."
```

## Git and worktrees

| Symptom | Fix |
|---|---|
| A parallel session flips the main checkout's branch mid-task | Do branch work in a worktree (`git worktree add ~/code/herdr-jobs/worktrees/<name> <branch>`), symlink `node_modules`, copy `.env.local`. |
| Copied helper scripts `cd` to another worktree's hard-coded path | Copies must `cd "$(dirname "$0")/.."`. |
| Two agents append to the same DECISIONS file and collide | Give each agent its own section letter. Resolve with a keep-both union. Renumber at merge if main took the letter. |
| `workspace close` (after the owner's yes) returns `workspace_group_close_required` | Linked worktree workspaces are still open. Close those you created, with the same yes; never add `--group` just to get past it (0.9.4 has no `--group`; the 0.9.5 docs add it). |

## Closing and reopening

| Symptom | Fix |
|---|---|
| A lead closed its workspace and cleared the owner tag by itself when the job ended (seen 2026-10-17: `nohup sh -c 'sleep 20; herdr workspace close w1R'`), so the owner never saw the final screens and nothing could be reopened | The owner's rule since 17 Oct 2026: ask before close (SKILL.md, Wrap up). Leave everything open, ask, and close only after an explicit yes, as the last step. |
| A closed workspace is needed again | `bash <job dir>/reopen.sh` recreates it from the reopen record and resumes each agent's session (`--fresh` for new sessions; `--into <ws>` adds the tabs to an open project workspace). No record: rebuild by hand from `register.md` and each CLI's resume form ([agents-and-models.md](agents-and-models.md)). |
| `reopen.sh` refuses: "a workspace labelled ... is already open" | It is still open: use it, or `--into <ws>` for missing tabs. Never close it just to reopen it. |
| `reopen.sh` refuses: "cwd ... is gone" | The worktree was removed. `git worktree add <cwd> <branch>` (the branch is in the register), then run it again. |
| `reopen.sh` starts an agent on CLI defaults, or fresh instead of resumed | Its start flags were never recorded, or the snapshot ran before Codex, Hermes or Kimi reported a session id (after the first turn). Record at every start (`herdr-reopen-snapshot record`) and refresh the snapshot after first turns and before any close. |
