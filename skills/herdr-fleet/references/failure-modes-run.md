# Failure modes while running, in git, at close

Each was hit for real; recheck a fix against the installed binary before relying on it. Failures at a start: [failure-modes.md](failure-modes.md).

## Running agents

| Symptom | Fix |
|---|---|
| An agent hangs for hours in a BrowserOS Neo call (hidden tabs never paint); the spinner keeps going | The truth is the session log's mtime (`ls -l ~/.claude/projects/*/<session id>.jsonl`), which the watch reports as `STALL?`. If it is stale, kill and resume (below). Prevent it in `_common.md` ([collaboration.md](collaboration.md#ownership-rules-paste-into-every-commonmd)). |
| Text sent to a hung agent queues silently and spills into the shell after the kill | Never prompt an agent you think is hung. After a kill, read the pane and clear the line with `ctrl+c` before the restart. |
| The machine freezes (load 400+, swap full) and Neo drops with ECONNRESET | Dozens of leftover Neo renderer tabs spin: count `BrowserOS neo Helper (Renderer)` in `ps -Ao %cpu,command`. A force quit (`pkill -9 -f "BrowserOS neo"`) fixes it but kills every session's tabs: ask the owner first. Logins survive. |
| Several panes run full type checks or builds at once and memory runs out | Agents run named test files only; the lead runs the full checks once. |
| With 6 or more agents in Neo, screenshots fail ("Unable to capture") | Leave visual QA to one agent. |
| Stall alerts fire during long xhigh thinking | A stall is 15 minutes or more of an unchanged log (the watch's default), not 12. |
| Codex sits in `unknown` after a reply, or Kimi stays `working` after an error turn, and `agent wait` times out | The report file is the signal. `STALL?` covers Claude and Codex only: check Hermes, Kimi and Gemini by their screen. |
| A turn ends "Selected model is at capacity" | Read the screen to confirm nothing changed, then resend the prompt with "Retry:" in front. Again, or a usage limit: the [fallback](agents-and-models.md#fallback). |
| A prompt sits unsent in Claude's box and the agent stays `idle` | `herdr-send` presses Enter once more and says so. After a raw `agent prompt`, read the screen and send `herdr agent send-keys <name> enter` once. |
| A CLI times out inside agents but works for the lead | The lead runs it (or the matching MCP tool) and writes the result into a brief. |
| The date rolls over and agents stamp yesterday | `date +%F`, a rule in `_common.md`. |
| A lead ran parallel lanes as built-in subagents: the owner, the phone, the watch and the review miss them | A pane per lane. Briefs name every parallel step as a pane (`research-web`, `research-local` in a `research` tab). |
| An agent restarted in its own pane after `/exit` comes up unnamed (`-` in `agent list`; "not a live agent") | `herdr agent rename <pane> <name>`, `herdr agent wait <name> --until idle --timeout 30000`, then send. Check `agent list` after every restart. |
| `agent prompt` returns `agent_not_running` | The agent exited and its name cleared. Read the pane before a restart. |
| A pane moved with `pane move` and its old id fails | Use `.result.move_result.pane.pane_id` or the agent's name. |
| A prompt typed into a pane the owner has focused lands in their typing | Check `.result.agent.focused` first and wait while it is true. `stampede tell` to a Claude agent writes its inbox and never types. |
| Claude's grey suggestion in an idle prompt looks like typed input | It is not: `herdr agent read <name> --ansi` shows it dim. |
| A Claude agent that ran `cd` missed its inbox | `stampede start` adds a `CwdChanged` hook that re-sends the watched paths. |
| Keys sent into another agent's dialog approved a plan nobody saw | Answer dialogs with commands and files (`stampede tell`, a brief), never keys. |
| A killed question waiter left its card on the phone | `stampede cancel <job> <id>` stops the waiter and its card together. |

## Kill and resume a hung Claude agent

```bash
P=<pane>; N=<name>
SID=$(herdr agent get "$N" | jq -r .result.agent.agent_session.value)   # null before a first turn for Codex, Hermes, Kimi: use the register
PID=$(herdr pane process-info --pane "$P" | jq -r '.result.process_info.foreground_processes[] | select(.argv0=="claude") | .pid')
kill -KILL "$PID"
herdr pane read "$P" --source visible --lines 10      # look for spilled text
herdr pane send-keys "$P" ctrl+c
herdr agent start "$N" --kind claude --pane "$P" --timeout 90000 -- --resume "$SID" --model claude-opus-5-5 --effort xhigh --permission-mode auto
herdr agent prompt "$N" "You were restarted after a hang in a browser call. Re-read your brief and carry on; skip Neo for pages that hang."
```

## Git and worktrees

| Symptom | Fix |
|---|---|
| A parallel session flips the main checkout's branch mid-task | Branch work in a worktree (`git worktree add <jobs_root>/worktrees/<name> <branch>`); symlink `node_modules`, never copy an env file. |
| Copied helper scripts `cd` to another worktree's path | Copies `cd "$(dirname "$0")/.."`. |
| Two agents append to one DECISIONS file and collide | A section letter each; resolve with a keep-both union, renumber at merge. |
| `workspace close` (after the yes) returns `workspace_group_close_required` | Linked worktree workspaces are still open: close those you made, with the same yes. Never add `--group` to get past it. |

## Closing and reopening

| Symptom | Fix |
|---|---|
| A lead closed its workspace and cleared the owner tag when the job ended; nothing could be reopened | Never: ask before close ([tui.md](tui.md#close-on-the-owners-yes-only)). |
| A closed workspace is needed again | `bash <job>/reopen.sh` (`--fresh` for new sessions; `--into <ws>` adds the tabs to an open workspace). No record: rebuild from `register.md` and each CLI's [resume form](clis.md#resume). |
| `reopen.sh`: "a workspace labelled ... is already open" | Use it, or `--into <ws>` for missing tabs. Never close it to reopen it. |
| `reopen.sh`: "cwd ... is gone" | `git worktree add <cwd> <branch>` (the branch is in the register), then run it again. |
| `reopen.sh` starts an agent on CLI defaults, or fresh instead of resumed | Its start was not recorded, or the snapshot ran before Codex, Hermes or Kimi had a session id. Start agents with `stampede start`, and refresh the snapshot after first turns and before any close. |
