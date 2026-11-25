# Troubleshoot

Find the message you see in the left column, then do what the right column says. A word in `<angle brackets>`, or `...`, stands for a part of the message that changes.

- [Install, update and the health check](#install-update-and-the-health-check)
- [Starting and running a job](#starting-and-running-a-job)
- [Plans, reviews and gates](#plans-reviews-and-gates)
- [Herdr Core jobs](#herdr-core-jobs)
- [The relay and bots](#the-relay-and-bots)
- [More help](#more-help)
- [FAQ](#faq)

## Install, update and the health check

PATH is the list of folders your terminal searches for commands. More: [Setup problems](SETUP.md#setup-problems).

| what you see | fix |
|---|---|
| `stampede needs Python 3.9 or later (this is <version>)` | put a newer `python3` first on PATH: stampede runs the first one it finds there |
| `PROBLEM not on PATH: ...` from `stampede doctor` | run this checkout's `install.sh`, and put `~/.local/bin` first on PATH |
| `PROBLEM on PATH from another checkout: ...` from `stampede doctor`, or `skip ...: something else is there; left as is` from `install.sh` | an older copy, or a link into another checkout, is in the way. Run this checkout's `install.sh --replace`: it backs each one up first and prints its `rollback.sh` ([Install](SETUP.md#install)). Put `~/.local/bin` first on PATH |
| `PROBLEM` from `stampede doctor` or `herdr-doctor` | the line names the broken part and its fix. Why some gaps are only a `warn`: [Health check](SETUP.md#health-check) |
| `PROBLEM herdr <version> is older than 0.9.4` or `herdr --version printed no version` | update Herdr, then restart its server yourself |
| `PROBLEM herdr server not running` (a `warn` while Herdr Core is usable) | start Herdr (run `herdr` in a terminal), then run `herdr-doctor` again |
| `PROBLEM Herdr Core not running` from `herdr-doctor --core` | start the core yourself (`hc server start`), then check again. The doctor and stampede never start one |
| `PROBLEM no usable backend` | neither the Herdr TUI nor Herdr Core can run a job: fix the lines above it for one of them |
| `PROBLEM` lines for stampede on PATH, linked skills or the relay's timers from `herdr-doctor --core` in a checkout that is not installed | expected until `install.sh` runs. The Core checks are the `ok hc`, `ok Herdr Core answers`, `ok claude` and `ok codex` lines |
| `warn hc <version> is older than 0.1.20` | `hc update`, then reopen each open Core job's terminals once (end each, then `bash <job>/reopen.sh`): terminals opened before the update keep the old behaviour |
| `warn <N> terminal(s) were opened before the Herdr Core bundle here was installed` (macOS) | those terminals keep their old holder (local network and microphone access, and later fixes). Reopen each once, a job's with its `reopen.sh` |
| `warn Herdr Core was started from inside an agent or a pane` | every new terminal inherits that environment. From a terminal outside Herdr, run `hc server restart --fresh` yourself (running programs keep running) |
| `refused: ... is outside ~/code` from `herdr-trust`, or `warn no ~/code (FLEET_TRUST_ROOT)` from `herdr-doctor` | `herdr-trust` trusts repos only under `FLEET_TRUST_ROOT`: move the repo, create the folder, or set the key |
| `PROBLEM ... not in the plugin checkout ...`, or `stampede: command not found` after a Herdr restart | the links point at an old plugin checkout, which Herdr deletes at its next start. Run the current checkout's installer ([Update](SETUP.md#update)) |
| `stampede` still works after `herdr plugin uninstall stampede` | Herdr keeps its checkout until its server next starts, and never removes the links: [Uninstall](SETUP.md#uninstall) |
| `refused: ... has local changes or untracked files`, `... is on <branch>, not main` or `... the update adds <path>, already in ...` from `stampede update` | commit, stash or move the files it names, or `git switch main`, then run it again |
| no update line, though a release is out | the check runs at most once a day and says nothing offline. Delete `~/.cache/stampede/latest-release` to check now, and make sure `STAMPEDE_NO_UPDATE_CHECK` is not `1` |

## Starting and running a job

A refusal from `new`'s checks makes nothing: fix what the line names, then run `new` again. A `BLOCKED`, `NOT READY` or `UNKNOWN` line means the job already exists: do what the line says, and never start a second lead.

| what you see | fix |
|---|---|
| `stampede new: the ask file <path> does not exist` | write what the job is for in that file, then run `new` again |
| `stampede <command>: job folder not found: <path>`, or `not a job folder, it has no lead or ask.md file: <path>` | pass the folder `stampede new` printed (`<jobs_root>/jobs/<date>-<owner>-<name>`, or `<repo>/.herdr-<name>` for an older job) |
| `<file>: helpers.maxx is not a setting (did you mean helpers.max?); skipped`, then `stampede new: fix it or remove the key: stampede config show` (exit 2) | a config file, the environment or a `--set` holds an unknown key, a value of the wrong type, a file that is not TOML, or a user-only key in a repo's `.stampede.toml`. Fix or remove what the line names, check with `stampede config show` (exit 0 when clean), then run `new` again |
| `stampede new: new runs the job on the Herdr TUI and needs a Herdr pane: ...` (exit 2) | run it inside Herdr, pass `--workspace <id>` or `--pane <id>`, or add `--core` to run the job on Herdr Core (for every job: `stampede config set backend core`) |
| `on Herdr Core (backend auto: not inside a Herdr pane), repo <path>` then `stampede new: Herdr Core did not answer ...` (or `is not installed`, or `needs --cwd`) | your `backend` setting chose Herdr Core, which is not running. Start it (`hc server start`), or pass `--cwd <repo>` outside a git repo. For the Herdr TUI, run `new` inside a Herdr pane or pass `--workspace` or `--pane` |
| `stampede new: ...; Herdr Core answers here, so this job can run on it: new --core ...` | start Herdr, or run the job on Core with `--core` |
| `stampede new: --fork forks a Claude chat, so it takes a Claude lead` (exit 2) | drop `--lead codex` (or unset `FLEET_LEAD_KIND`), or start it without `--fork` |
| `stampede start: brief ... is missing: ...` or `brief ... does not exist` | write the brief on the [hand-off template](../skills/herdr-fleet/references/brief.md), fill every missing or empty section, then start again |
| `stampede start: fleet-job starts claude, codex or cursor ...`, or `hermes runs only as a handed agent of a Herdr Core job ...` (or kimi) | in a Core job, run any other CLI as a program (`stampede start <job> <name> -- <cli> ...`), or start it by hand and record it with `herdr-reopen-snapshot` |
| `stampede start: <agent> is already running in pane <pane>`, `... not as the launch this job recorded`, or `pane <pane> is handed to <agent> of <job>` | tell that agent instead, or pick another pane. For a replacement the job did not start, read it with `herdr agent get <pane>`, then end it or use another name |
| `stampede start: pane ...'s shell is in ..., not ...` | `--yolo-in` needs the pane's shell in that worktree: use auto mode, or `cd` the pane first |
| `stampede tell: agent <name> is not in this job (it has: ...)` | use one of the names it lists, or `lead` |
| `BLOCKED_ON_CARD <agent>` from `stampede tell` or `stampede wait` | the agent waits at a question card in its pane and reads nothing else, so your message waits in line: answer the card there. In a `--front-door` job the lead's own cards become posts, so this is rare |
| `BLOCKED <agent>: clear the startup dialog` | read the screen (`herdr agent read <agent> --source visible --lines 30`), clear the dialog, then send the printed `stampede tell` line |
| `BLOCKED <lead>: <kind>` from `stampede wait` on a Core job | the lead waits at a dialog (a permission, a trust prompt). Show the owner the screen `wait` printed, clear it only as they say (`hc keys <address> <keys>`), then run `wait` again |
| the lead's pane shows Claude's sign-in or first-run screen, though `stampede new` printed `DELIVERED` | sign in to Claude Code once in a plain terminal (`claude`) before your first ask. Then finish the screen in the lead's pane and send `stampede tell <job> lead "Read <job>/briefs/<lead>.md"` |
| a lead does not react to a worker's report or your `tell` | a Codex lead's lines, and a Claude lead's lines its file hook missed, are typed only while it is idle or done, unfocused, with nothing typed in its prompt but the deliverer's own earlier text. Leave its pane, clear a draft, and see `<job>/hooks/deliver.log` (`GAVE UP` after 4 h, `CANNOT REACH HERDR`). `stampede _wake <job>` starts the deliverer again |
| `herdr-send` says `FAILED <agent> (the text stayed in its prompt through 3 Enter; cleared it with ctrl+c, ...)` | the agent kept the text and every Enter was lost, so `herdr-send` cleared its prompt. Read its screen (`herdr agent read <agent> --source visible --lines 30`), then send again. The deliverer sends again by itself |
| a finished job's workspace stayed open with `finish.auto_close` on | `<job>/close.log` names why (`KEPT <ws>: ...`): a pane that is not the job's, an agent still working, uncommitted changes, a gate waiting on you, another open job, or a failed reopen record. Fix that, then close it yourself |
| `refused: a workspace labelled <label> is already open` from `reopen.sh`, with `none of this job's agents runs there` | a Herdr server restart brought the job's workspace back with plain shells. Close that workspace (your yes, as for any close), then run `reopen.sh` again |
| `REFUSED <agent>: ...; nothing started.` during reopen (exit 2) | Run `stampede config show` and change the active rule at the source it reports, such as your settings file or `FLEET_LEAD_ALLOW`. Then reopen again. If `stampede start` can start the named agent, you can keep the policy and use `stampede start <job> <agent> --brief <file> --model <m> --effort <e>` with allowed values. Include `--pane <id>` on the TUI and use `--kind` if you need to select the CLI. For a native lead, a native helper whose name is still queued or a finished native job, use the policy fix. See [Configure](CONFIGURE.md) |
| `reopen.sh: workspace <id> is open but not tagged for <bot>` (exit 5) | `herdr-events-owner` failed, so the bot would not hear that workspace: run the command it prints, then carry on |
| `SKIPPED <name> (<address>): it carries another job's key ...` from `stampede close` | another job's terminal runs under this job's: close it from its own job. This one stays open around it |

## Plans, reviews and gates

A gate is a step that needs your yes ([Safety](SAFETY.md)).

| what you see | fix |
|---|---|
| `stampede start: the owner asked to see this plan` | a `--review` job: approve the plan as it stands with `stampede approve <job> --by <who>` |
| `stampede approve: the owner has not been shown this plan.md` (or `this fleet-plan.md`) | a `--front-door` job. The lead posts `plan.md` (`stampede post <job> "PLAN READY" --file <job>/plan.md`), the front door sends that file to you, and only your yes to it is approved. Post again after any change |
| `stampede approve: the front door has not received this plan.md yet` | the front door has not run `stampede wait` since the lead posted the plan. Run it, send the owner the file it names, and approve only their yes to that file |
| `stampede merge: no review report <file>`, `... says Status: FINDINGS, not PASS` or `... names no Reviewed: <full sha>` | the reviewer writes `Status: PASS` and `Reviewed: <full sha>` in its report's first 10 lines. Fix any findings, review again, then merge |
| `stampede merge: the review report <file> has 2 Status: lines ...`, `line <n> ... comes before or inside its header` or `says Reviewed: <text>: it takes one full sha and nothing else` | the header is a title line, then one `Status:` line and one `Reviewed: <40-hex sha>` line, before any code block, quote, comment or indented line. The reviewer fixes it |
| `stampede merge: the review report passes <a>, not <b>`, or `... but the PR head is <b>: review the new commit` | merge only the reviewed commit: review the new head, then ask the gate at it |
| `stampede merge: the merge gate is on ...`, `gate <id> is not a merge gate for PR <n> ...`, `gate <id> has no recorded yes` or `... was approved for <a>, not <b>` | run the `stampede ask ... --kind merge` line it prints for this PR at this commit. Wait for your yes, then merge with `--gate <id>` |
| `stampede merge: PR <n> is merged, not open` (or closed) | nothing to merge: check the PR number |
| `stampede merge: gh pr merge failed: <gh's line>` (exit 1), or `<job>/merges.log cannot be written (...): nothing was merged` | fix what gh names (auth, a protected branch, a head that moved), or make `merges.log` writable. Then merge again |
| `stampede gate-ok: gate <id> changed after the yes`, or `stampede approve-gate: gate <id> changed while the owner was asked` | the gate's action, PR or route changed after you were asked: the lead asks again |
| `stampede gate-ok: gate ... was approved for <sha>, not <sha>` | a push came after the yes: ask the gate again at the new commit |
| `stampede approve-gate: approve-gate needs --digest` | a bot built the command itself: run the gate event's `approve` line as given, which carries the digest |
| `stampede approve-gate: approve-gate runs only outside Herdr` | it is the starting bot's command, over plain ssh, never `hc exec`. On the Herdr TUI, type yes in a Claude lead's pane instead, except for a merge or a push to the default branch ([Safety](SAFETY.md)) |
| `stampede prepush: a push of <sha> to main needs the owner's yes. Ask it with the next line ...` | a job's agent pushed to the default branch. Run the `stampede ask ... --kind push_default_branch` line it prints, then push again once `gate-ok` prints `APPROVED`. Or push the work branch |
| `stampede-hook: stampede is not on PATH, so the push gate was not checked` (or `stampede prepush failed (exit <n>)`) | put stampede on PATH (`./install.sh`) or run `stampede update` |
| `stampede new: the push gate is not enforced by a hook in this repo, because it has its own (...)` | the repo has its own `pre-push` or `core.hooksPath`. A push to the default branch is the lead's to ask; `stampede merge` still holds the merge gate |
| `stampede new: --no-gate <name> is no gate` | use one of the names it lists: `merge`, `push_default_branch`, `deploy`, `publish`, `send`, `spend`, `close` |

## Herdr Core jobs

| what you see | fix |
|---|---|
| `QUEUED <name> (...)` from `stampede start` on a Core job, and the helper never starts | the cap was full, and nobody started the queue since. Run `stampede next <job>` (the lead runs it on each child's note) |
| `UNKNOWN <name>: ...; run stampede next once Herdr Core answers` from `stampede next` (exit 1) | Core stopped answering after a failed start, so the request stays queued. Once `hc ls` answers, run `stampede next <job>` again; it never starts a helper twice |
| a helper of a Core job cannot reach its parent after a reopen | the parent has a new address: the helper reads it with `hc get $HC_TERMINAL_ID` (its `parent`) and sends there |
| a Core job's lead is dead (a `dead` event from the watchdog, or no lead in `stampede tree <job>`) | `bash <job>/reopen.sh` (or `stampede reopen <job>`) starts it again with its session resumed, then its helpers under it |
| `stampede tree <job>` shows `<address> (<address>) plain shell live ... left in <agent>'s place` | the agent's program was lost, and Core kept its terminal as a plain shell: it is not the agent. Reopen the job if the agent is gone; a whole-job `close` ends the shell too |
| `... runs on Herdr Core HC_SESSION=<a>, but HC_SESSION here is <b>` | unset `HC_SESSION` (or `HC_SOCKET`), or set it to the job's, and run the command again |
| from a `--core --relay` job: `BLOCKED <lead>: <kind>` or `NOT READY <lead>: ...`, `FAILED <lead> (...): nothing of <job> runs`, `terminals of an earlier job at this path still run`, `UNKNOWN <agent>: ... Nothing was taken back`, `stampede start: <agent> is already running at <address>`, `is being started by another caller (pid <n>)`, `Cursor reports no OSC 7501 status ...`, `Kimi reports its status on Herdr Core, but stampede has no turn hook ...`, `FAILED <agent> (Herdr Core cancelled the send ...)`, `(hc send: no answer in <N> s ...)`, `GONE <agent> ... (a shell is in its place at <address> ...)`, `its program was lost and Herdr Core put a shell in its place`, `NOT RUNNING <agent> (pane <pane>): ...`, `NOT BRIEFED <agent> (pane <pane>): ...`, `Herdr did not see <kind> start in pane <pane>`, `UNKNOWN <agent>: Herdr did not show it in pane <pane> ...`, `RELAY DOWN <reason>` | each line and its fix: [core-relay.md](../skills/herdr-fleet/references/core-relay.md). Never run `new` again for that folder |
| `NOT ACKNOWLEDGED <file>` from a `--relay` job's `reopen.sh` (exit 3) | the restarted lead has not read that file yet: once it is up, run the printed `echo` line |
| `stampede new: --front-door on Herdr Core is for a native job: drop --relay` (exit 2) | a `--relay` job has no front door: start it with `stampede new --core --front-door`; nothing was made |
| `stampede new: a Codex lead on Herdr Core gets its inbox typed into its terminal, and ...` (exit 2), or `HELD: a send to <lead> got no answer ...` in `<job>/hooks/deliver.log` | a Codex lead on a `--relay` job needs Herdr Core 0.1.20 or later with `draft_wait` at 30 or more; or use `--lead claude`. A held line most often means text sits typed in its prompt: send or clear it. If you cleared it without sending, remove `<job>/hooks/deliver-held.json` |

## The relay and bots

| what you see | fix |
|---|---|
| `POSTED <n> to the outbox only ...: no bot or front door hears it` | a local job's post is in `<job>/outbox`, and nobody is told. A bot sets `HERDR_EVENTS_OWNER=<bot>` when it runs `new`, and a chat outside Herdr starts the job with `--front-door` |
| a bot gets no events | `herdr-doctor --relay` names the broken part ([remote/events.md](../remote/events.md)) |
| `stampede ask: the relay did not queue this for <bot>` | a job that bot started asks it by its own route only. Add `~/.config/herdr-events/routes/<bot>` with a `URL=` (the same webhook as `default` is fine), and check with `herdr-doctor --relay`. Meanwhile, answer in the lead's pane |
| `UNDELIVERED gate <id> for <bot> held: route <bot> has no URL` in `inbox.log` (or `UNDELIVERED post outbox <NNN> ...`) | put the `URL=` back in `~/.config/herdr-events/routes/<bot>`, and the flusher sends it within 2 minutes. Do not post a held post again. After 24 h it moves to `dead/`: ask or post again |
| `lock-not-taken` in the relay log | another relay held the de-dupe lock past 5 s, or there is no `lockf` (macOS) or `flock` (Linux, util-linux). The event still went out |
| relay `PROBLEM` lines on a Mac without a bot | a routes folder, a relay launch agent or a relay hook is left over. Finish its setup ([remote/events.md](../remote/events.md)), or remove what you no longer use |
| `PROBLEM event loop not running` or `systemd ... not enabled` from `herdr-doctor --relay` | on Linux, re-run `install.sh`; on macOS, load the launchd jobs in [watchdogs](../remote/watchdogs.md) |
| on Linux the systemd timers stop when you log out, or the flock loop is gone after a reboot | on a computer nobody logs in to, run `loginctl enable-linger $USER` once. After a reboot, run `install.sh` again for the flock loop ([watchdogs](../remote/watchdogs.md)) |

## More help

- Every known failure with its fix: [failure-modes.md](../skills/herdr-fleet/references/failure-modes.md) (at a start) and [failure-modes-run.md](../skills/herdr-fleet/references/failure-modes-run.md) (while running, in git, at close).
- The error format, with examples: [docs/CLI.md](CLI.md#errors).
- Startup dialogs: [unattended-setup.md](../skills/herdr-fleet/references/unattended-setup.md).

## FAQ
- *Do I need stampede for this?* Only for a big job. A job is big when it is hours long, uses more than one agent family, does anything that leaves your computer (merge, push, send, spend, publish, deploy), or must survive a restart.
  A small job runs as one agent session with its built-in subagents (helpers the agent starts inside itself). It still runs inside Herdr, in a single tagged pane of its own, so its finish arrives as an event.
  That also answers "why not subagents": for small jobs, use them. The rule: [Size the job first](../skills/herdr-fleet/SKILL.md#size-the-job-first-small-or-big).
- *Why two names?* `stampede` is the public name of `fleet-job`, its first name. Both names run the same command.
- *Can Codex or Cursor lead?* Codex can, on the Herdr TUI and on Herdr Core: `stampede new --lead codex` ([Pick the lead](GUIDE.md#use-one-job-start-to-finish)). Cursor not yet ([roadmap](STATUS.md)).
- *Can workers run on Gemini, Kimi or the other agents Herdr knows?* In a Core job, any CLI runs as a program (`stampede start <job> <name> -- <cli> ...`). In a `--core --relay` job, Hermes and Kimi are handed to Herdr TUI panes. As first-class kinds, not yet ([roadmap](STATUS.md)).
- *Can a job run without the Herdr TUI?* Yes, on Herdr Core ([Herdr Core](CORE.md)).
