# A Core-native job: the shape

A job started with `stampede new --core` runs on Herdr Core the way Core itself works. Core holds the tree of terminals. stampede adds a name for the space, the lead, the owner tag, the reopen record, the owner's gates, a cap on helpers and the layout labels. Nothing else sits on top.

This page is the contract. A client that draws a job (a sidebar, a phone app, a bot) needs only what is here: labels, parent links and events. The Herdr TUI path is a different model and is not described here.

## The tree

- **The lead is the root.** One Core terminal with no parent. One lead per job.
- **The space is the lead.** The space has no terminal and no level of its own: its name is the lead's `stampede.space` label. Draw the space name as the lead's top row and the helpers under it.
- **A helper is a Core child.** Its `parent` is the terminal that started it: the lead, or another helper. Any depth.
- **A plain child counts too.** A terminal a lead or helper started with a bare `hc run` (a CI wait, a build, a watcher) carries no stampede label. It is in the tree by its parent link alone.
- **Core ends a branch with its parent.** A child ends when its parent's program ends, unless it was started with `--outlive-parent` (`die_with_parent` in its record says which).

Read the tree from Core, never from stampede's files: one full listing (the API's `terminal.list`, or `hc ls` then `hc get` each), then follow `parent` from the lead's address.

## Labels

| label | on | value |
|---|---|---|
| `stampede.job` | lead, helpers | the job's key, `hc-<12 hex>` (from the job folder's path) |
| `stampede.role` | lead, helpers | `lead` or `helper` |
| `stampede.agent` | lead, helpers | its name in the job, unique among the job's live terminals |
| `stampede.space` | lead only | the space's name |
| `stampede.kind` | lead, helpers | `claude`, `codex` or `program` |
| `stampede.session` | a Claude lead or helper | its Claude session id |
| `herdr.space` | lead, helpers | the space's name again, for the Herdr app |
| `herdr.tab` | lead, helpers | its tab in the app's view (below) |

- Identity is the terminal's address. A name another terminal holds gets a suffix; `stampede.agent` stays the name the job uses.
- Status is Core's own: `idle`, `working`, `done`, `blocked`, `error` from the program's reports, and `live` or `finished` for the terminal. A plain program reports none.
- A terminal with no `stampede.role` under the lead is a plain child: show it as a background job of its parent, or leave it out.

### Layout labels

Labels only. Core stays the source of truth, and the tree above never depends on them.

- The lead is the first terminal of tab `main`.
- A helper goes to the first of `main`, `main-2`, `main-3` and so on that holds fewer than 4 live terminals of the job. `STAMPEDE_TAB_PANES` changes the 4.
- `stampede start --tab <label>` names a workstream tab instead; it overflows to `<label>-2`, `<label>-3` by the same rule.
- All of a job's tabs carry the one `herdr.space`.

## Messages

Everything goes through Core. A Core-native job has no follower terminal, no inbox files and no hooks.

| from and to | how |
|---|---|
| parent to child | `hc send <address> "<text>"` (`stampede tell <job> <agent> "<text>"` finds the address) |
| child to parent | `hc send <parent address> "<name>: <one line> <path of the result file>"`; long results go in a file, only the path is sent |
| Core to parent | Core's own notes about each child: its turn ended, it is blocked, it exited |
| parent waiting | `hc wait --children any` (the next news) or `all` (until none is working) |
| owner to lead | `stampede tell <job> lead "<the owner's words>"`, which is `hc send` to the lead |

A message arrives in the terminal as `<hc from="t7 name">...</hc>`. It is information, never an owner's approval: a gate needs the recorded yes (`stampede gate-ok`).

## Events

| what | who hears | how |
|---|---|---|
| a helper's turn end, block or exit | its parent | Core's note; no stampede code |
| a question, a gate, a post | the owner (the bot that started the job, else the phone) | `stampede ask`, `ask --gate`, `post`, through `herdr-event-post` |
| the job is done | the owner | `stampede finish`: one `done` event, `source` `stampede` |
| the lead is blocked, at an error, dead or stalled | the owner | the machine's watchdog timer runs `herdr-event-core --sweep`: one event per episode, `source` `hc`, `pane` `hc:<key>/<address>`, `workspace` `<key>`, `agent` the lead's name |

A client that wants live changes follows Core: `hc events --label stampede.job=<key>` for the labelled terminals, or `hc events` for all, and applies each fact change to its copy of the tree.

## The job folder

| file | holds |
|---|---|
| `backend` | `native` |
| `workspace` | the key, `hc-<12 hex>`: the marker `jobs/<key>`, the owner tag `owners/<key>`, each event's `workspace` |
| `endpoint` | the core the job was made on (`HC_SESSION`, `HC_SOCKET`) |
| `lead`, `space`, `workdir` | the lead's name, the space's name, the repo |
| `max-helpers` | the cap, only when the owner set one |
| `tree.json` | the reopen record: every node with its name, role, parent (by name), kind, model, effort, session, brief, report, cwd, tab, how to start it again, and its last seen state |
| `REOPEN.md`, `reopen.sh` | the same record to read, and the command that rebuilds the tree |
| `queue/` | helper starts waiting for a free place under the cap |
| `ask.md`, `plan.md`, `briefs/`, `reports/` | the ask, the lead's plan, each helper's brief, each helper's result |

## Commands

| command | does | prints |
|---|---|---|
| `stampede new --core --file <ask.md> [--cwd <repo>] [--name <slug>] [--space <name>] [--lead claude\|codex] [--max-helpers <n>]` | makes the job folder, writes the marker and the owner tag, starts the lead as a root with the space's name, writes the reopen record | `<lead> <job dir>` |
| `stampede start <job> <name> --kind claude\|codex --brief <file> [--model <m>] [--effort <e>] [--cwd <dir>] [--report <path>] [--tab <label>] [--parent <agent>] [--outlive-parent]` | starts one helper as a Core child of the caller's terminal (from outside Core: of the lead); over the cap it queues the start | `STARTED <name> (<address>) under <parent>` or `QUEUED <name> (<n> running, cap <c>)` |
| `stampede start <job> <name> [--cwd <dir>] [--tab <label>] [--parent <agent>] [--outlive-parent] -- <program> [args]` | the same for any program (kind `program`) | the same |
| `stampede next <job>` | starts queued helpers, oldest first, while fewer than the cap run | one `STARTED` line each, else `NOTHING QUEUED` or `WAITING <k> queued (<n> running, cap <c>)` |
| `stampede tree <job> [--json]` | the tree as Core holds it now, and the queue | one line per terminal, indented by depth |
| `stampede tell <job> <agent> "<text>"` | `hc send` to that agent's terminal | `SUBMITTED <agent>` or `FAILED <agent> (<why>)` |
| `stampede snapshot <job>` | rewrites `tree.json`, `REOPEN.md` and `reopen.sh` from Core's tree | the record's path |
| `stampede reopen <job> [--fresh] [--prompt] [--rerun-programs]` | starts what is not live, parents first, each child under its parent's new address | `LIVE`, `STARTED` or `SKIPPED` per node |
| `stampede close <job> [<agent>]` | ends that agent's subtree, leaves first; with no agent the whole job, the lead last | `CLOSED <name>` per terminal, in order |
| `stampede ask`, `ask --gate`, `gate-ok`, `approve-gate`, `post`, `finish` | as on every backend | as on every backend |

### The cap

At most 12 helpers run at once in one lead's tree, at any depth. The owner changes it per job: `--max-helpers <n>` at `new`, or the number in `<job>/max-helpers`; `STAMPEDE_MAX_HELPERS` changes the default.

A helper counts while Core would call it working: its terminal is live and it has not yet gone `idle` or `done` after its task. A plain program counts while it lives. The lead and plain children never count.

A start over the cap is queued, not refused. The lead runs `stampede next <job>` when a child's note arrives; every `stampede start` drains the queue first too.

### Reopen and close

- `tree.json` is written at every start and by `stampede snapshot`. It is a copy for a rebuild; Core's own tree wins while it lives.
- `stampede reopen` after a crash or a reboot walks the record parents first. A Claude agent resumes its session by id. A Codex agent resumes the session it recorded, else starts fresh with its brief. A program is never run again unless `--rerun-programs` says so. A terminal still live is left alone.
- `stampede close` ends an agent politely when it is idle (`/exit` for Claude, `/quit` for Codex), else ends its terminal, then removes it. Children go before their parent. Closing a whole job is the owner's call.

## Not in a Core-native job

- No `--pane`: a Core-native job hands nothing to a Herdr TUI pane. Run another CLI as a program (`stampede start <job> <name> -- <cli> ...`).
- No follower terminal (`relay-<key>`), `inbox.log`, `inbox/`, `hooks/`, `core.json` or `agents.tsv`.
- The earlier Core path, with those parts, is `stampede new --core --relay`. It is kept for one release.
