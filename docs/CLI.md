# The stampede command

`stampede` runs a job: it makes the job folder, starts the lead and its workers, carries messages, asks the owner and records the owner's yes. `fleet-job` is the same command under its first name. Every command explains itself: `stampede --help` lists them in the order an agent meets them, and `stampede <command> --help` gives its flags and an example. The whole flow for an agent is [USING.md](../USING.md).

The entry is [fleet_job.py](../skills/herdr-fleet/scripts/fleet_job.py); the parser and its help are in [cli.py](../skills/herdr-fleet/scripts/stampede/cli.py). `stampede --version` (or `-V`) prints [VERSION](../VERSION), then on stderr the update line when a newer release is out. stampede needs Python 3.9 or later: an older `python3` first on PATH stops at once with `stampede needs Python 3.9 or later (this is <version>): ...` and exit 2.

Three kinds of job, chosen at `new`, decide what some commands do:
- **A Herdr TUI job:** `stampede new` inside Herdr. Each agent has a Herdr pane.
- **A Core job** (native): `stampede new --core`. Each agent is a Herdr Core terminal; its shape is [CORE-NATIVE.md](CORE-NATIVE.md).
- **A `--relay` job:** `stampede new --core --relay`, the earlier Core path ([core-relay.md](../skills/herdr-fleet/references/core-relay.md)).

## Start a job

| command | flags | prints |
|---|---|---|
| `new --file <ask.md>` | `--workspace <id>` (default `$HERDR_WORKSPACE_ID`), `--pane <id>`, `--name <slug>`, `--review`, `--lead claude\|codex` (default `$FLEET_LEAD_KIND`, else claude), `--fork <session id>` (Claude only), `--front-door` | `<lead> <job folder>` once its brief pointer went in; `BLOCKED <lead>: clear the startup dialog, then stampede tell ...` |
| `new --core --file <ask.md>` | `--cwd <repo>` (default: the git root here), `--name`, `--review`, `--lead`, `--fork`, `--space <name>`, `--max-helpers <n>` (default `$STAMPEDE_MAX_HELPERS`, else 12) | `STARTED <lead> (<address>)`, then `<lead> <job folder>`; `BLOCKED`, `NOT READY`, `FAILED` or `UNKNOWN <lead>: ...` with the next step |
| `new --core --relay --file <ask.md>` | `--cwd`, `--name`, `--review`, `--lead`, `--fork`, `--app-space` | as `new --core`, for the earlier path |

## Work in it

| command | flags | prints |
|---|---|---|
| `start <job> <agent> --kind <cli> --brief <file>` | Herdr TUI: `--pane <id>` (required); every job: `--model`, `--effort`, `--report <path>` (repeatable), `--yolo-in <worktree>`; a Core job: `--cwd`, `--tab`, `--parent`, `--outlive-parent`; a `--relay` job: `--cwd`, and `--pane` for cursor, hermes or kimi | `STARTED <agent> (<pane or address>)`, `QUEUED <agent> (<n> running, cap <c>)` (a Core job at its cap), `DELIVERED <agent>` (a TUI worker's brief pointer), `BLOCKED`, `NOT BRIEFED`, `NOT READY`, `UNKNOWN` |
| `start <job> <agent> -- <program> [args]` | a Core job: `--cwd`, `--tab`, `--parent`, `--outlive-parent` | as above; any CLI or program runs this way |
| `tell <job> <agent> <text>` | `lead` names the lead | `DELIVERED <agent> (inbox file)`, `BLOCKED_ON_CARD <agent>: ...` (queued; it waits at a question card), `SUBMITTED <agent> (<address>)`, `FAILED <agent> (<why>)` |
| `ask <job> <question>` | `--option <a>` (repeatable) | `ASKED <id> ...`, saying where the answer comes back |
| `ask <job> --gate --sha <commit> <action>` | `--pr <n>`; no `--option` | `GATE <id> ...; act after stampede gate-ok ... prints APPROVED` |
| `post <job> <text>` | `--file <path>` (repeatable) | `POSTED <n> to <bot> (and <item>)` in a job a bot started; `POSTED <n> for the front door to relay (<item>)` in a `--front-door` job; otherwise `POSTED <n> to the outbox only (<item>): no bot or front door hears it`, with how the owner would be told |
| `wait <job>` | `--timeout <s>` (default 3600) | every outbox item not shown yet, `BLOCKED_ON_CARD` with the lead's screen, or `LEAD_GONE <lead>: ...`; `TIMEOUT nothing new ...` |
| `next <job>` (a Core job) | | `STARTED` per queued helper, `DROPPED <name>: its parent ... is gone`, then `WAITING <k> queued (...)` or `NOTHING QUEUED` |
| `tree <job>` (a Core job) | `--json` | `space <name> (<key>)`, then one line per terminal, indented by depth, then the queue; `NO LEAD` |

## Gates

| command | flags | prints |
|---|---|---|
| `approve <job> --by <who>` | | records the plan's fingerprint, then tells the lead (the `tell` line); in a `--front-door` job only a plan the lead posted and `wait` handed on |
| `approve-gate <job> <gate> --sha <commit> --by <who> --digest <d>` | run the `approve` line a gate event carries, as given | `APPROVED <gate> at <sha>`; refused inside Herdr or Herdr Core |
| `gate-ok <job> <gate> --sha <commit>` | | `APPROVED <gate> by <who> at <time>: <action> at <sha>`, only for the owner's recorded yes at that commit |
| `cancel <job> <id>` | | `CANCELLED <id>` |

## End and return

| command | flags | prints |
|---|---|---|
| `finish <job> <summary>` | | `FINISHED <job>`, after one `done` event (sent once); `NOT CANCELLED <id>: ...` for a question it could not stop |
| `snapshot <job>` (a Core job) | | the record's path, or `FAILED snapshot (<why>)` |
| `reopen <job>` (a Core job) | `--fresh`, `--prompt`, `--rerun-programs` | per agent: `LIVE`, `STARTED`, `QUEUED`, `SKIPPED`, `DONE`, `NOT TOLD` or `FAILED` |
| `close <job> [<agent>]` (a Core job) | | `CLOSED <agent> (<address>)` per agent, deepest first; no agent closes the whole job |

## The machine

| command | flags | prints |
|---|---|---|
| `doctor` | `--core` or `--tui` (passed to `herdr-doctor`), `--json` | one line per check, `ok ...`, `warn ...: <fix>` or `PROBLEM ...: <fix>`: Python, the checkout (VERSION and every module imports), the commands on PATH, then `herdr-doctor`'s own lines. `--json`: `{"ok": bool, "checks": [{"name", "level", "text", "fix"}]}` |
| `check` | `--full`, `--json` | one line per test module (`ok` or `FAIL`, its tests and seconds, a failure's output), then `ok <n> tests in <s> s` or `FAILED <k> of <m>: ...`. The fast part takes a few seconds; `--full` runs the whole suite |
| `update` | `--check` | `stampede <old> -> <new>` after a fast-forward of a clean `main` and `install.sh`; `refused: ...` with what to move; a Herdr plugin install names `herdr plugin update stampede --yes`. `--check`: one line on whether a newer release is out |

`doctor` reads; it fixes nothing and starts nothing. `check` runs each module in its own process in a scratch HOME, with no `herdr` or `hc` on PATH, so it is safe beside live jobs; it needs a git checkout (an install without `tests/` exits 2).

`hook <action> <job> --agent <name>` and the commands that start with `_` are run by the agents' hooks and `reopen.sh`, never by hand, and appear in no help.

## Errors

Every refusal is one line on stderr, `stampede <command>: <what is wrong>: <what to do>`, never a traceback. Among them:
- `stampede tell: job folder not found: <path>`, or `not a job folder, it has no lead or ask.md file: <path>`, for every command given a job folder, before anything else.
- `stampede tell: agent <name> is not in this job (it has: lead, <names>)`.
- `stampede new: the ask file <path> does not exist: ...`, before any other check.
- `stampede new: new needs --workspace or --pane, or run it inside Herdr; to run it here on Herdr Core: stampede new --core --file <ask> --cwd <git root>`.
- `stampede: error: ...` with the usage line, for a flag or command it does not know; bare `stampede` prints the help.

The full list, each with its fix, is the README's [Troubleshoot](../README.md#troubleshoot).

## Exit codes

| code | means | from |
|---|---|---|
| 0 | done; also `new` and `start` on the Herdr TUI that print `BLOCKED <agent>: clear the startup dialog ...`: the agent runs, held at a dialog; clear it, then send the printed `tell` line | every command |
| 1 | Herdr, Herdr Core or a program failed (one `stampede <command>: ...` line); on Herdr Core (a Core job, a `--relay` job, or an agent handed to a TUI pane) a `new` or `start` that did not end with a ready agent (`BLOCKED`, `NOT READY`, `NOT BRIEFED`, `UNKNOWN`, `FAILED`); on the Herdr TUI a Codex lead whose brief pointer did not go in (`BLOCKED <lead>: its brief pointer did not go in`); a failed `next`, `snapshot`, `reopen` or `close`; `doctor` found a `PROBLEM`; `check` had a failure; `update` refused or failed; `update --check` saw a newer release | any command for a failure; the rest as named |
| 2 | a usage error or a refusal, with the reason: no such job folder, an agent not in the job, a kind it does not run there, a start before approval, yolo outside a worktree, a gate with no yes at that commit, no route for the bot, `approve-gate` inside Herdr, a Python older than 3.9; also `tell` when nothing was typed (`FAILED`, every backend), `start` of a non-Claude worker on the Herdr TUI whose brief pointer was not sent (the same `FAILED`), and `check` with no `tests/` | every command |
| 3 | `tell`: `BLOCKED_ON_CARD`, the message is queued; `wait`: nothing came before `--timeout`; a `--relay` job's `reopen.sh` (`_reopen`): `NOT ACKNOWLEDGED` | `tell`, `wait`, `_reopen` |

The `wake` hook exits 2 on purpose: that wakes Claude.

A Core job's commands, one by one (what each does: [CORE-NATIVE.md](CORE-NATIVE.md#commands)):

| command | 0 | 1 | 2 |
|---|---|---|---|
| `new --core` | the lead started | `BLOCKED`, `NOT READY`, `FAILED`, `UNKNOWN` | bad flags, a used folder, Core silent before anything was made |
| `start` | `STARTED` or `QUEUED` | a `FAILED` start, during the drain too | a refusal: the name taken, `--pane`, a bad brief or kind, an unknown parent, a finished job, a job that is not native |
| `next` | `STARTED`, `WAITING`, `NOTHING QUEUED`, `DROPPED` | a `FAILED` start, or `UNKNOWN` | a finished job; not a native job |
| `tree` | the tree | `NO LEAD` | not a native job |
| `tell` | `SUBMITTED` | | `FAILED` (nothing typed) |
| `snapshot` | the record's path | `FAILED snapshot`: Core did not answer | not a native job |
| `reopen` | only `LIVE`, `STARTED`, `QUEUED`, `SKIPPED`, `DONE`, `NOT TOLD` | any `FAILED` restart | not a native job; `--fresh` or `--rerun-programs` on a finished job |
| `close` | every `CLOSED` | any `FAILED`; the rest still closed | from inside the subtree, no such agent, not a native job |

`hook`, `_deliver` and `_wake` exit 0 and do nothing on a Core job; `_reopen` exits 2 there and names `stampede reopen`.
