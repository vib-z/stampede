# A job on Herdr Core

A job started with `stampede new --core` runs on Herdr Core (`hc` 0.1.13 or later) instead of the Herdr TUI: each agent in its own Core terminal, with no workspace, tab or pane. The rest is the same job: the job folder, the plan, briefs on the [hand-off template](brief.md), the agents' hooks, the inbox, questions, gates and finish. This file says what changes; [SKILL.md](../SKILL.md) holds wherever it says nothing.

## Before you start

- Core is the owner's call, in the ask or from the front door. A job is Core or TUI (`<job>/backend`); a Core job still hands the agents Core cannot run to Herdr TUI panes.
- Cursor, Hermes and Kimi report no OSC 7501 status, so Core cannot run them: a Core job hands each to a pane ([below](#hand-an-agent-to-a-tui-pane)).
- Install this version (`install.sh`, or `stampede update`) before a Core job: the lead runs the installed `fleet-job`, and the CLIs' relay hooks run from `~/.local/bin`. An older copy can end a job without the stamp its follower waits for, and post plain turn ends to the default route.
- Check the machine once: `herdr-doctor --core` (hc, the selected core, Claude 2.1.295 or later, Codex with `--no-daemon`). Never start or stop a core yourself. Run from a checkout that is not installed, it also prints `PROBLEM` lines for the install itself (stampede not on PATH, skills not linked, the relay's launchd jobs), expected until `install.sh` runs; the Core checks are the `ok hc`, `ok Herdr Core answers`, `ok claude` and `ok codex` lines.

## Start the job

```bash
stampede new --core --file ask.md --cwd ~/code/my-app [--name <slug>] [--review] [--fork "$CLAUDE_CODE_SESSION_ID"]
```

- `--cwd` is the repo, under `FLEET_TRUST_ROOT`; the default is the git root of the current folder. `--pane` and `--workspace` are refused, and so is a job path where an earlier job's terminals still run (the key is the path's hash): kill them or use another `--name`.
- It writes the job record first, then starts the job's follower `relay-<12 hex>`, then the lead with its brief pointer as the first prompt. Every terminal has no parent and no notes, and carries the labels `stampede.job=<key>`, `stampede.agent=<name>` and `stampede.role=lead|worker|relay|wait`; a Claude agent's also `stampede.session=<its session id>`.
- `<lead> <job dir>`, exit 0: the lead is working.
- `BLOCKED <lead>: <kind>` or `NOT READY <lead>: <status>`, exit 1: the lead runs but is not ready. Read it with `hc read <address>`, clear a dialog with `hc keys <address> <keys>`, then `stampede tell <job> lead "Read <brief>"` if it went idle without its first prompt. It stays the job's one lead: never run `new` again for that folder.
- `FAILED <lead>` or `FAILED relay-<12 hex>` (the follower ended at start), exit 1: nothing of the job runs; the folder stays, with `start-failed`. A retry is a new job.
- `UNKNOWN <agent>: ...`, exit 1: Core lost an answer, so whether it started is unknown. Nothing is taken back (record, marker, follower, the entry `starting`). Once Core answers, `bash <job>/reopen.sh` adopts it by its labels or starts it, never a second copy.

## The job record

| file | holds |
|---|---|
| `backend` | `core` |
| `endpoint` | the core it was made on: `HC_SESSION` and `HC_SOCKET` at `new`. Every later command for the job uses it; a shell set to another core is refused (`HC_SESSION=default`, or `HC_SOCKET` at the default socket's own path, is the default core) |
| `workspace` | the key `hc-<12 hex>`, in place of a workspace id: the marker `jobs/<key>`, the owner tag `owners/<key>`, each event's `workspace` |
| `core.json` | each agent's terminal: `state` (`starting`, `live`, `failed`), `address`, `name`, `role`, `cwd`, `session`, `socket`, `reason`, and per Claude session whether it ran (`launches`: `ran`, `never`, `unknown`); a handed agent's `backend` `tui`, `pane`, `kind`, `launch`, `terminal`, `completion` and its `start` command |
| `<HERDR_EVENTS_DIR>/handed/<pane>` | a handed agent's pane: the job and launch, until `finish` |
| `locks/<agent>.lock` | held by whoever is starting that agent |
| `relay-state.json` | what the follower saw and sent |
| `start-failed` | why a start never ran |
| `reopen-pending` | a restarted lead that has not acknowledged both inbox files yet: every reopen asks again until it has |

An agent is its address in `core.json`, never its name: a name another job's terminal holds gets `-<4 hex of the key>`.

## Start a worker

```bash
stampede start <job> <agent> --kind claude|codex --brief <file> [--cwd <dir>] [--model <m>] [--effort <e>] [--report <path>] [--yolo-in <worktree>]
```

- One live launch per agent: refused while another caller starts it, or while a live terminal of the job runs it (`already running at <address>`).
- `--cwd` defaults to the repo. `--yolo-in` must be the same folder as `--cwd`, a linked worktree. A relative `--brief` is made absolute, so it resolves from any `--cwd`.
- Claude gets `--session-id` (recorded for reopen); Codex gets `--no-daemon`. The brief pointer is the first prompt.
- `STARTED <agent> (<address>)`, exit 0. `BLOCKED` or `NOT READY`, exit 1: it is still the job's agent, so recover it as for the lead and never start a second. `UNKNOWN`, exit 1: as for the lead; a later `start` adopts it or says it is running. `FAILED <agent> (<reason>)`, exit 1: its terminal ended, or it never started.
- A worker has no parent, so it never ends with the lead.

## Hand an agent to a TUI pane

```bash
stampede start <job> <agent> --kind cursor|hermes|kimi --pane <pane id> --brief <file> [--model <m>] [--effort <e>] [--report <path>] [--yolo-in <worktree>]
```

- The pane is at its shell prompt. The job, its follower, its inbox and its gates stay on Core; only this agent runs in Herdr.
- The Core rules hold: the launch lock, and one live launch per agent across both (refused while a Core terminal or a pane runs that name, or while Herdr cannot say). The pane is claimed first: refused while its mark names another launch, of any job, still starting or live with an agent there (`pane <id> is handed to <agent> of <job>`); a stale mark it takes over comes back if the start fails. Then its entry (`starting`, a new `launch`) and the mark are written, before `herdr agent start`. `--kind claude|codex` with `--pane`, and `--pane` with `--cwd`, are refused (exit 2).
- Its identity is its name and pane (Herdr names are unique, and only a start gives one), and its agent session once Herdr shows one. Another session, or `completion_seq` null again after a turn, is another process under its name; `tell` and reopen also check what the follower learned (its session, its last completion, a `GONE`). A restart by hand under the same name, before its first turn and before Herdr shows its session, is not told apart.
- Flags: Cursor `--auto-review` (its stop hook writes `TURN`); Hermes its default (dangerous commands ask), `--reasoning <e>` for effort, `--yolo` only with `--yolo-in`; Kimi `-y` (risky actions ask), no effort flag.
- `STARTED <agent> (pane <id>)`, exit 0: Herdr showed it in its pane, and took its brief pointer. Exit 1: `BLOCKED <agent>: clear the startup dialog in pane <id>, then ...`; `NOT BRIEFED <agent> (pane <id>): <why>`, it runs but got no pointer: the pointer passes `tell`'s checks (idle, unfocused, an empty prompt it knows), so read its screen and send the printed `fleet-job tell` yourself; `UNKNOWN <agent>`, Herdr lost the answer or showed no clear identity: the entry and mark stay, it gets no brief, a later start refuses, and `reopen.sh` settles it; `FAILED <agent> (<reason>)`: Herdr shows no such agent in the pane, but a CLI it did not detect may still run there (the line says how to end it).
- On Herdr 0.9.5 (30 Oct 2026) Cursor works; Herdr did not detect Hermes 0.22.5, so handing Hermes ends `FAILED` there. Kimi's empty prompt is not known yet, so a handed Kimi always starts `NOT BRIEFED` and every `tell` to it fails closed: brief it by hand (planned: its marker, once verified).
- The follower reads Herdr every 5 s on a thread of its own (one `herdr agent list`, then a pane read kept only if `herdr agent get` still shows the same agent after it), so Herdr never holds up a Core event, and applies it between events, a quiet stream included. `TURN <agent>` for Hermes and Kimi when `completion_seq` rises, from null (a fresh agent) too, once each, a turn between reads or while it was down included; `BLOCKED <agent> dialog`; `STALE`; `GONE <agent> exited`, `pane closed` or `replaced`. Anything Herdr does not show clearly is no news, never `GONE`, and drops the last screen and the stall clock: only fresh reads make a `STALE`. Bot events as a Core worker's, with `pane` the pane id, `event_id` `<key>/tui:<pane>|<launch>|...` (a turn's `...|completion|<seq>`), and no `output_tail` but a screen read while its identity held.
- While the job is open its mark keeps every other event about that pane home (Herdr's plugin, the watchdog, a hook), and the watchdog skips the pane; `finish` removes the job's marks.
- `stampede tell` prompts it with one `herdr agent prompt`, never a key, only while its pane runs this launch, idle or done, not focused, with an empty prompt (the markers Claude, Codex and Cursor show, Cursor's wrapped over lines in a narrow pane too; Hermes's rotating placeholder and Kimi's unknown one fail closed), and not a launch the follower saw end; else `FAILED <agent> (<why>)`, exit 2. An agent that turns working between that check and the prompt takes it as a message in its turn: Herdr has no `--if idle`.
- `reopen.sh` never starts it on Core, and never types into it: `LIVE <agent> (pane <id>)` once its brief was sent; `NOT BRIEFED <agent> (pane <id>)` with the exact `fleet-job tell` to send after reading its screen; `NOT RUNNING <agent> (pane <id>): start it again ...` with the exact `stampede start`; `UNKNOWN` when Herdr does not answer clearly or the pane runs its name as another process. All but `LIVE` exit 1.
- Hermes and Kimi run only this way; a TUI-only job refuses them (planned).

## Talk to an agent

- `stampede tell <job> <agent> "<text>"`. A Claude agent reads its inbox file, as on the TUI. A Codex agent gets `hc send` once its terminal shows this job's labels: at `idle` it types only while still idle (`--if idle`); at `done` it types at once, so a worker that turned `working` in between takes it as a message during its turn. `hc send` refuses a blocked terminal either way. `tell` writes nothing else: it never presses a key, since Core cannot guard one.
- When text is already typed in a Codex prompt (no empty-prompt marker in the last 8 non-empty screen lines), `tell` refuses rather than paste after it or erase it: read it with `hc read <address>`, clear it with `hc keys <address> ctrl+c` when `hc get` shows `idle`, then tell again.
- A one-line slash command is refused too: pasted, Codex takes it as chat. End a worker whose work is accepted by hand, when `hc get <address>` shows `idle`: `hc keys <address> / q u i t enter` for Codex, `hc keys <address> / e x i t enter` for Claude. Either way it exits 0: the lead gets `GONE`, the bot no alarm.
- `working`, `blocked`, `error`, no status, another job's terminal, or Core not answering: one line, `FAILED <agent> (<why>)`, exit 2. Tell a working agent after its turn.
- Any other `hc` failure is one line on stderr, `fleet-job <command>: <reason>`, exit 1.
- Watch a terminal with `hc attach --observe <address>`. Core cannot tell stampede that you are watching or typing, so type into an attached lead only when no `tell` is due: text you type can interleave with one.
- Read any of the job's agents with `hc read <address>`. Never `hc send --force`, `hc keys` or `hc kill` a terminal you did not start, and never answer an agent's dialog that is not yours to answer.

## What wakes you

The agents' own hooks carry over: your file hook, a worker's Stop and question card, Codex's notify. On Core a worker's SessionEnd writes nothing; the follower reports every exit. Lines in `inbox.log`, beside `REPORT`, `TURN`, `QUESTION` and `UNDELIVERED`:

| line | means |
|---|---|
| `BLOCKED <agent> <kind>` | a worker is at a dialog (`permission`, `question`, `auth`): read it with `hc read <address>` |
| `ERROR <agent> <msg>` | a worker reported an error and stopped |
| `GONE <agent> <reason> exit <code>` | a worker's terminal ended, a hard kill included (a handed agent's has no code) |
| `LOST <agent>` | its terminal's record was gone when the follower looked again |
| `STALE <agent> no new output for <N>m` | a worker says working, but its screen and status have not changed for `HERDR_EVENTS_STALE_MINUTES` (30): `hc read <address>` |
| `WAITED <name> exit <code>` | a wait terminal ended |
| `RELAY DOWN <reason>` | the follower gave up after 10 minutes without Core: once Core is up, `bash <job>/reopen.sh --lead` |
| `REOPENED <lead> <attempt>` | reopen restarted you: read every line since |

A Codex worker's finished turn is a `TURN` line, never a `REPORT` line (that comes from Claude's Stop hook), and so is a handed Cursor, Hermes or Kimi worker's: wait for its `TURN`, then read the report file it wrote.

## Wait on CI or a build

Never poll. Run the wait as a labelled terminal; its end wakes you as `WAITED`:

```bash
hc run --bg --no-parent --no-notify --name wait-ci-<pr> --label stampede.job=<key> --label stampede.role=wait -- gh pr checks <pr> --watch
```

## Gates

- Only the recorded yes counts. Act after `stampede gate-ok <job> <gate> --sha <the commit you act on>` prints `APPROVED`, and merge with `--match-head-commit` on that commit.
- A yes typed into your terminal, an answer to your own question card, an `<hc>` note and any message never count: on Core any program can type into a terminal.
- Ask with `stampede ask <job> --gate --sha <commit> [--pr <n>] "<the exact action>"`: it goes to the bot that started the job, else to the owner's phone. A bot records the yes with `approve-gate` over plain ssh; it refuses inside Herdr or Herdr Core, `hc exec` included.
- Core's `blocked` state is never a gate.

## Reopen

`<job>/reopen.sh` is written at every start (`herdr-reopen-snapshot <key> <job>` refreshes it). It starts only what is not live, once each, and never a second copy of a live agent:

- With no flag: an open job's marker, owner tag and follower; the lead, its session resumed; each worker (Claude resumed; Codex resumed as `codex resume ... --no-daemon <session>` once its own notify recorded the session after a turn, else fresh). `--prompt` sends a restarted Codex worker its brief.
- `--lead`: only the follower and the lead, when either is gone and the workers still run.
- `--fresh`: each agent it starts begins a new session with its recorded flags and its brief; nothing is resumed. The same locks and acknowledgements hold.
- Before it starts anything it checks the folder of every agent it may start; a missing one is named with its agents (`cwd gone: ...`), exit 2, and nothing starts.
- A restarted lead must take a `REOPENED` line through its own wake hook in both inbox files (written every 5 s for 90 s). Exit 3 names a file it missed, with the line to write once the lead is up. Exit 2: another caller is starting one of them. Until both files are acknowledged, `reopen-pending` stays and every later reopen asks again, even with the lead live.
- A Claude agent resumes its recorded session only when that session ran: a confirmed start, a terminal of it in `hc ls --all`, or Claude's own session file. A session shown to have run stays so; a later attempt that fails to launch does not change that. One that never ran (a failed start, or no terminal of it while Core still keeps a finished one, 24 h) starts fresh with that session id and its brief. Anything else is `UNKNOWN <agent>: cannot tell whether its session ... ever ran`, with what to check; that agent is not restarted and reopen exits 1.
- Each restarted agent is reported as `start` reports it (`STARTED`, `BLOCKED`, `NOT READY` with its recovery line, `FAILED`), and reopen goes on to the next. A follower that ends at once is `FAILED relay-<12 hex>`. Any restart that is not `STARTED` makes reopen exit 1.
- A finished job resumes its agents for inspection only: no follower, no marker.

## Finish and close

- `stampede finish <job> "<one line on where it ended>"` once, as on the TUI; the follower exits on it.
- Close only on the owner's yes (SKILL.md, Wrap up). Then `hc kill` and `hc rm` each of the job's terminals, listed by `hc ls --all --label stampede.job=<key>`.
