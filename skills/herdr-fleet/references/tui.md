# A job on the Herdr TUI

The lead's side of a job started inside a Herdr pane. The installed `herdr` is the authority: `herdr <cmd> --help`, and after an upgrade or a failed command the [CLI reference](https://herdr.dev/docs/cli-reference/) and [agent automation](https://herdr.dev/docs/agent-automation/).

## Look first

```bash
herdr workspace list
herdr tab list --workspace <ws>
herdr agent list | jq -r '.result.agents[] | "\(.pane_id) \(.name // "-") \(.agent) \(.agent_status)"'
```

- `<ws>` is `$HERDR_WORKSPACE_ID`. Take every id from Herdr's JSON, never from an example.
- Never run bare `herdr`: it attaches the TUI.

## From outside Herdr

- Run your entry skill first (connect, health check, workspace by label, safe start). Never set `HERDR_ENV`.
- Write literal ids where this page says `$HERDR_WORKSPACE_ID`, `$HERDR_PANE_ID` or `--current`: in a single-quoted ssh command they expand on the Mac, empty.
- Run `herdr` on the Mac over ssh, never `herdr --remote` or `--machine`; only on the owner's own machines, never a work machine.
- Report in your own chat, not in a lead pane.
- A bot tags the workspace (`herdr-events-owner <ws> <bot-slug>`) before any agent starts, launches, and exits. It never waits on a job (no `herdr agent wait` for a result, no sleep loop, no repeated reads; bounded startup checks are fine): stuck events and the one `finish` reach it by the relay.

## The shape

- **Workspace = project.** Reuse the project's workspace, else `herdr workspace create --cwd <repo> --label <project> --no-focus`.
- **Tab = workstream:** `herdr tab create --workspace <ws> --cwd <dir> --label <name> --no-focus`. `stampede new` gives the lead a tab `lead`, or the `--pane` it was given.
- **First tab:** `workspace create` makes tab 1 with a root pane: rename it for the first workstream (`herdr tab rename` on `.result.tab.tab_id`) and use `.result.root_pane.pane_id`. In an existing workspace, list tabs and reuse an empty one.
- **Pane = one agent,** named `<role>-<scope>` (`build-api`, `review-api`), matching `[a-z][a-z0-9_-]{0,31}`, unique. `stampede start` renames the pane and gives Claude the same `-n` name.
- **Geometry:** the pane's own rect is `herdr pane layout --pane <id> | jq '.result.layout.panes[] | select(.pane_id=="<id>") | .rect'` (`.result.layout.area` is the tab). Split right while both halves keep 80 columns, else down while both keep 15 rows. Always `--no-focus` and an explicit `--cwd`.
- **Limits:** at most 4 panes per tab on a laptop, 6 on a big monitor (open a tab rather than shrink panes); at most 4 parallel pieces, and 6 copies of a repeated task at once. A sub-lead only past 10 items, or for a workstream of 3 or more parallel pieces.

## Where agents work

- The job folder is `<jobs_root>/jobs/<date>-<owner or local>-<slug>`, never in a repo; the repo is `<job>/workdir`. `stampede start` gives every agent `--add-dir <job>`, so a report lands from any worktree.
- A worktree goes in `<jobs_root>/worktrees/<name>` (`git worktree add`, then only `git worktree move`), a finished item in `<jobs_root>/archive/`. Nothing Herdr-related goes in the repo or in `~`.
- **One shared worktree with file ownership** for content where each agent owns its files.
- **A worktree per agent** (a branch each; the lead merges) when slices touch the same code, with `--cwd`, so agents stay in the project's workspace. `herdr worktree create` opens a separate workspace instead.

## Start an agent

```bash
W=<abs work dir>; B=<abs job folder>
P=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$W" --label research --no-focus | jq -r .result.root_pane.pane_id)
Q=$(herdr pane split --pane "$P" --direction right --cwd "$W" --no-focus | jq -r .result.pane.pane_id)
stampede start "$B" research-web --pane "$P" --brief "$B/briefs/research-web.md" --report reports/research-web.md
herdr agent read research-web --source visible --lines 30
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"
```

- `start` renames the pane, adds auto mode, the job's hooks, `--add-dir <job>` and the start record, then sends the brief pointer. `--kind`, `--model` and `--effort` default to the role.
- Before the first start in a repo: `herdr-trust <repo dir>` (its worktrees are covered).
- `BLOCKED <agent>: clear the startup dialog ...`: clear it ([unattended-setup.md](unattended-setup.md#startup-dialogs-the-lead-clears)), then send the printed `stampede tell` line.
- Read every new agent's screen before its first prompt: Herdr reports most startup dialogs as `idle`.
- With no [unattended setup](unattended-setup.md), or a start the classifier denies: finish every other step, then give the owner the exact lines to run as `!` commands.
- Restart a lead on the other CLI: `stampede start <job> <lead> --kind claude|codex --pane <its pane> --brief <job>/briefs/<lead>.md`.

## Talk to an agent

- `stampede tell <job> <agent> "<text>"`: a Claude agent's inbox file (it never types), else a typed prompt.
- Else `herdr-send <name> "<text>"`, or `herdr agent prompt`; never `pane send-text` plus Enter (Codex leaves it unsent), never `ctrl+c` an idle Codex (it quits). Go on only on `SUBMITTED`.
- Before every prompt, `herdr agent get <name>`: idle or done, not focused. At a dialog a prompt is refused with `agent_blocked`.
- Exit each worker once its work is merged or accepted (`/exit`, or `/quit` for Codex), so its row in the app archives itself.
- After a `timeout`, `agent_prompt_stalled` or an ssh drop, read the screen (`herdr agent read <name> --source recent-unwrapped --lines 40`) and resend only if it clearly never landed.

## What wakes you

- Hooks write `REPORT`, `TURN`, `QUESTION`, `GONE` and `UNDELIVERED` (a question, gate or post its bot has not heard) to `<job>/inbox.log`; answers and messages go to `<job>/inbox/<lead>.md`.
- A Claude lead's file hook reads them. A Codex lead has none: a short-lived deliverer types each new line into its pane, marked `[fleet-job inbox for <lead>, not typed by the owner]`, once it is idle and unfocused.
- Confirm a `TURN` with the report file. Never wait in a loop: end your turn.
- `fleet-watch.sh` is for a bot outside Herdr, never the lead ([collaboration.md](collaboration.md#a-bots-watch)).

## Reopen record

- `herdr-reopen-snapshot <ws> <job>` writes `<job>/REOPEN.md` and `<job>/reopen.sh` from `<job>/agents.tsv`, which every `stampede start` fills. Run it once the launch's agents run, after every later start, and before any close.
- `bash <job>/reopen.sh` rebuilds the job's tabs and panes and resumes every session: `--fresh` for new sessions, `--prompt` to resend each brief pointer, `--into <ws>` to add the tabs to an open workspace.
- It refuses while a workspace with that label is open, or when a pane's cwd is gone (add the worktree back first).

## Close, on the owner's yes only

The last step is a question, "Close workspace <label>? Reopen with <job>/reopen.sh.": AskUserQuestion in a local job, the end of your report in a bot's job. No answer is a no. On an explicit yes, in this order:

1. Exit each agent so its session stays resumable: `/exit` for Claude, Hermes and Kimi, `/quit` for Codex.
2. Refresh the reopen record.
3. Clear the owner tag: `herdr-events-owner <ws> --clear`.
4. Close only what you created: the whole workspace (`herdr workspace close <ws>`) if the job made it, else only your panes and tabs.
5. Remove only your worktrees, after their panes close; keep the branches.
