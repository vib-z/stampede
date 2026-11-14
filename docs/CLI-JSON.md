# JSON output

Add `--json` to any command an agent runs and it prints one JSON object on stdout instead of its lines, and nothing else there. The exit code is the same as without `--json`. The lines without `--json` do not change. The commands are in [CLI.md](CLI.md); `tree`, `doctor`, `check` and `config show` keep the `--json` documents named there.

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
| `new` | `STARTED`, `BLOCKED`, `NOT READY`, `FAILED`, `UNKNOWN`; on the TUI a `DELIVERED` (or a Codex lead's `SUBMITTED`) result comes first | `backend` (`tui`, `native`, or `core` for `--relay`), `agent`, `lead`, `job`; on Core `address`; `reason`, `retry` |
| `start` | `STARTED`, `QUEUED`, `DELIVERED` or `SUBMITTED` (a TUI worker's brief pointer), `BLOCKED`, `NOT BRIEFED`, `NOT READY`, `UNKNOWN`, `FAILED`, `DROPPED` | `kind`, `model`, `effort` (as resolved from the flags and the role; `program` for one after `--`), `agent`, `address` or `pane`, `parent`, `running`, `cap`, `reason`, `retry` |
| `tell` | `DELIVERED`, `BLOCKED_ON_CARD`, `SUBMITTED`, `FAILED` | `agent`, `address` or `pane`, `reason` |
| `ask` | `ASKED` | `id`; `outbox` (a front door), `to` (a bot) |
| `ask --gate` | `GATE` (a phone gate has an `ASKED` result first) | `id`, `sha`, `pr`, `kind`; `outbox` or `to` |
| `post` | `POSTED` | `outbox`, `path`, `to` |
| `wait` | `ITEM` per outbox item, `BLOCKED`, `BLOCKED_ON_CARD`, `LEAD_GONE`, `TIMEOUT` | `outbox`, `kind`, `path`, `text`; `lead`, `address`, `reason`, `screen`; `retry` |
| `finish` | `FINISHED`, after a `CANCELLED` or `NOT CANCELLED` result per waiting question | `gates_off` (a list); `id`, `reason` |
| `next` | `STARTED`, `DROPPED`, `FAILED`, `UNKNOWN`, then `WAITING` or `NOTHING QUEUED` | `agent`, `address`, `parent`; `queued`, `running`, `cap` |
| `snapshot` | null, or `FAILED` | `path`; `reason` |
| `reopen` | `LIVE`, `STARTED`, `QUEUED`, `SKIPPED`, `DONE`, `FAILED`, `NOT TOLD` | `agent`, `address`, `parent`, `running`, `cap`, `reason` |
| `close` | `CLOSED`, `SKIPPED`, `FAILED` | `agent`, `address`, `reason` |
| `approve` | the `tell` line to the lead | as `tell` |
| `approve-gate` | `APPROVED`, after the `tell` line to the lead | `id`, `sha` |
| `gate-ok` | `APPROVED` | `id`, `sha`, `by`, `at`, `action`, `kind` |
| `cancel` | `CANCELLED` | `id` |
| `merge` | `MERGED` | `pr`, `sha`, `merge_commit`, `method`, `gate` |

The short codes in `reason`: `reopen`'s `SKIPPED` gives `finished`, `parent not running`, `plain`, `program` or `codex`, and its `DONE` gives `closed` or `exited 0`; `close`'s `SKIPPED` gives `another job` or `another job under it`; a native `tell` to no live terminal gives `no live terminal`. The line itself, with the whole reason, is what the command prints without `--json`.

The tests: [tests/test_json.py](../tests/test_json.py) plays a whole job on each backend twice against the fakes, plain and with `--json`, and checks every command's object against its plain lines.
