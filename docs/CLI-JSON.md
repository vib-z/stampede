# JSON output

Add `--json` to any command an agent runs, before or after the command's name (`stampede --json tell ...` or `stampede tell ... --json`), and it prints one JSON object on stdout instead of its lines, and nothing else there. After the `--` that starts a program in `start`, `--json` is the program's. The exit code is the same as without `--json`. The lines without `--json` do not change. The commands are in [CLI.md](CLI.md); `tree`, `doctor`, `check` and `config show` keep the `--json` documents named there.

```console
$ stampede start <job> build-api --kind claude --brief <job>/briefs/build-api.md --json
{"ok": true, "command": "start", "status": "STARTED", "job": "<job>", "agent": "build-api", "address": "t2", "parent": "lead-demo"}
$ stampede merge <job> 3 --sha <sha> --review <job>/reports/review.md --json
{"ok": false, "command": "merge", "status": null, "job": "<job>", "error": "stampede merge: the merge gate is on: ask the owner with the next line, then run this again with --gate <id>", "retry": "stampede ask <job> --gate --kind merge --sha <sha> --pr 3 'merge PR 3 at <sha>'"}
```

## The shape

- `ok`: true when the exit code is 0. A held result such as `BLOCKED_ON_CARD` (exit 3) or `TIMEOUT` (exit 3) is `ok: false` with its `status`.
- `command`: the command's name, such as `start` or `approve-gate`.
- `status`: the status word of the command's last line, the word or words that start it (`STARTED`, `NOT READY`, `NOTHING QUEUED`), or null when the line has none.
- The facts of that last line, at the top level, named the same everywhere (below). `job` is the absolute job folder, on every command given one.
- `results`: every line as an object with its own `status` and facts, in order, when the command printed more than one, and always for `next`, `reopen`, `close` and `wait`. The top level repeats the last one.
- A refusal: `error`, the one line the command prints on stderr without `--json` (`stampede <command>: ...`), and `retry`, the command it prints on the next line, or null. A usage error is a refusal too.
- An unexpected error or an interrupt: `{"ok": false, "error": "<type>: <message>", "retry": null}`, the traceback on stderr as without `--json`, exit 1 (130 for an interrupt).
- `notes`: any other line stampede printed, such as `on Herdr Core (backend auto: ...)` before `new`'s result, `gates off: <names>` before `FINISHED`, or the problems `new` refuses on. What a program stampede runs writes goes to stderr, never into the object.

## Facts

| fact | what it is |
|---|---|
| `job` | the job folder, absolute |
| `agent` | the agent the line is about; `lead` the job's lead, where the line names it |
| `address` | a Core terminal's address; `pane` a Herdr TUI pane |
| `parent` | the agent a Core helper runs under |
| `id` | a question's or a gate's id (12 hex) |
| `sha`, `pr`, `kind` | a gate's commit, PR number and kind (`merge`, `push_default_branch`, null); in `wait`, an item's kind; in `start`, the agent's CLI |
| `outbox`, `path`, `text` | an outbox item's number (`"003"`), its file, its text |
| `running`, `cap`, `queued` | helpers running in the tree, the cap, starts waiting |
| `reason` | why: the error, the dialog's kind, or for `SKIPPED` and `DONE` a short code (below) |
| `retry` | the command to run next, where the line names one |
| `to` | who hears a post or a question: the bot, `front door`, or null |

## Per command

| command | status values | facts |
|---|---|---|
| `new` | `STARTED`, `BLOCKED`, `NOT READY`, `FAILED`, `UNKNOWN`; on the TUI the lead's brief pointer first, as `tell` gives it (`DELIVERED`, `BLOCKED_ON_CARD`, `SUBMITTED`) | `backend` (`tui`, `native`, or `core` for `--relay`), `agent`, `lead`, `job`; on Core `address`; `reason`, `retry` |
| `start` | `STARTED`, `QUEUED`, `DELIVERED`, `BLOCKED_ON_CARD` or `SUBMITTED` (a TUI worker's brief pointer), `BLOCKED`, `NOT BRIEFED`, `NOT READY`, `UNKNOWN`, `FAILED`, `DROPPED` | `kind`, `model`, `effort` (as resolved from the flags and the role; `program` for one after `--`), `agent`, `address` or `pane`, `parent`, `running`, `cap`, `reason`, `retry` |
| `tell` | `DELIVERED`, `BLOCKED_ON_CARD`, `SUBMITTED`, `FAILED` | `agent`, `address` or `pane`, `reason` |
| `ask` | `ASKED` | `id`; `outbox` (a front door), `to` (a bot) |
| `ask --gate` | `GATE` (a phone gate has an `ASKED` result first) | `id`, `sha`, `pr`, `kind`; `outbox` or `to` |
| `post` | `POSTED` | `outbox`, `path`, `to` |
| `wait` | `ITEM` per outbox item, `BLOCKED`, `BLOCKED_ON_CARD`, `LEAD_GONE`, `TIMEOUT` | `outbox`, `kind`, `path`, `text`; `lead`, `address`, `reason`, `screen`; `retry` |
| `finish` | `FINISHED`, after a `CANCELLED` or `NOT CANCELLED` result per waiting question | `gates_off` (a list); `id`, `reason` |
| `next` | `STARTED`, `DROPPED`, `FAILED`, `UNKNOWN`, then `WAITING` or `NOTHING QUEUED` | `agent`, `address`, `parent`; `queued`, `running`, `cap` |
| `snapshot` | null, or `FAILED` | `path`; `reason` |
| `reopen` | `LIVE`, `STARTED`, `QUEUED`, `SKIPPED`, `DONE`, `FAILED`, `NOT TOLD`, and from the queue `DROPPED` and `UNKNOWN` | `agent`, `address`, `parent`, `running`, `cap`, `reason` |
| `close` | `CLOSED`, `SKIPPED`, `FAILED` | `agent`, `address`, `reason` |
| `approve` | the `tell` line to the lead: `DELIVERED`, `BLOCKED_ON_CARD`, `SUBMITTED`, `FAILED` | as `tell` |
| `approve-gate` | `APPROVED`, after the `tell` line to the lead (`DELIVERED`, `BLOCKED_ON_CARD`, `SUBMITTED`, `FAILED`) | `id`, `sha` |
| `gate-ok` | `APPROVED` | `id`, `sha`, `by`, `at`, `action`, `kind` |
| `cancel` | `CANCELLED` | `id` |
| `merge` | `MERGED` | `pr`, `sha`, `merge_commit`, `method`, `gate` |

## Always present

Outside a refusal, a fact listed here is always in the object. A `*` row holds for the top level, and a status row for the top level when it has that status; in `next`, `reopen`, `close` and `wait`, a status row holds for every result in `results` too. Null allowed: `model`, `effort`, `to`, `pr`, `kind`, `merge_commit`, `gate`; every other fact here is never null.

| command | status | always present |
|---|---|---|
| `new` | `*` | `backend`, `agent` |
| `new` | `STARTED` | `lead`, `job` |
| `start` | `*` | `job`, `agent`, `kind`, `model`, `effort` |
| `start` | `QUEUED` | `running`, `cap` |
| `start` | `DROPPED` | `parent` |
| `tell` | `*` | `job`, `agent` |
| `tell` | `FAILED` | `reason` |
| `ask` | `*` | `job`, `id` |
| `ask` | `GATE` | `sha`, `pr`, `kind` |
| `post` | `POSTED` | `job`, `outbox`, `path`, `to` |
| `wait` | `ITEM` | `outbox`, `kind`, `path`, `text` |
| `wait` | `BLOCKED` | `lead`, `reason`, `address`, `screen` |
| `wait` | `BLOCKED_ON_CARD` | `lead`, `screen` |
| `wait` | `LEAD_GONE` | `lead` |
| `wait` | `TIMEOUT` | `path`, `retry` |
| `finish` | `FINISHED` | `gates_off` |
| `next` | `STARTED` | `agent`, `address`, `parent` |
| `next` | `WAITING` | `queued`, `running`, `cap` |
| `next` | `DROPPED` | `agent`, `parent` |
| `next` | `FAILED` | `agent`, `reason` |
| `snapshot` | `null` | `path` |
| `snapshot` | `FAILED` | `reason` |
| `reopen` | `LIVE` | `agent`, `address` |
| `reopen` | `STARTED` | `agent`, `address` |
| `reopen` | `QUEUED` | `agent`, `running`, `cap` |
| `reopen` | `SKIPPED` | `agent`, `reason` |
| `reopen` | `DONE` | `agent`, `reason` |
| `reopen` | `DROPPED` | `agent`, `parent` |
| `close` | `CLOSED` | `agent`, `address` |
| `close` | `SKIPPED` | `agent`, `address`, `reason` |
| `approve` | `*` | `job`, `agent` |
| `approve-gate` | `APPROVED` | `id`, `sha` |
| `gate-ok` | `APPROVED` | `id`, `sha`, `by`, `at`, `action`, `kind` |
| `cancel` | `CANCELLED` | `id` |
| `merge` | `MERGED` | `pr`, `sha`, `method`, `merge_commit`, `gate` |

The short codes in `reason`: `reopen`'s `SKIPPED` gives `finished`, `parent not running`, `plain`, `program` or `codex`, and its `DONE` gives `closed` or `exited 0`; `close`'s `SKIPPED` gives `another job` or `another job under it`; a native `tell` to no live terminal gives `no live terminal`. The line itself, with the whole reason, is what the command prints without `--json`.

The tests: [tests/test_json.py](../tests/test_json.py) plays a whole job on each backend twice against the fakes, plain and with `--json`, and checks every command's object against its plain lines and the table above; it also reads the package's code, and fails when a status a command can print is missing from its row in Per command.
