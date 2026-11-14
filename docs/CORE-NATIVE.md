# A Core-native job: the shape

A job started with `stampede new --core` runs on Herdr Core the way Core itself works. Core holds the tree of terminals. stampede adds a name for the space, the lead, the owner tag, the reopen record, the owner's gates, a cap on helpers and the layout labels. Nothing else sits on top.

This page is the contract. A client that draws a job (a sidebar, a phone app, a bot) needs only what is here: labels, parent links and events. The Herdr TUI path is a different model and is not described here.

## The tree

- **The lead is the root.** One Core terminal with no parent. One lead per job.
- **The space is the lead.** The space has no terminal and no level of its own: its name is the lead's `stampede.space` label. Draw the space name as the lead's top row and the helpers under it.
- **A helper is a Core child.** Its `parent` is the terminal that started it: the lead, or another helper. Any depth.
- **A plain child counts too.** A terminal a lead or helper started with a bare `hc run` (a CI wait, a build, a watcher) carries no stampede label. It is in the tree by its parent link alone.
- **Core ends a branch with its parent.** A child ends when its parent's program ends, unless it was started with `--outlive-parent` (`die_with_parent` in its record says which).
- **A child can outlive its lead.** Core sets `parent` once, so an `--outlive-parent` child of a lead that ended still names the old lead after a reopen. The job's terminals are every terminal labelled `stampede.job=<key>` and everything under them; one whose chain no longer reaches the live lead is shown at depth 1 as `outlived <its old parent>`, counts under the cap, stays `live` in a snapshot and is closed with the job.

Read the tree from Core, never from stampede's files: one full listing, then follow `parent` from the lead's address. `hc ls --json` shows `parent` but no labels, so stampede sends one `terminal.list` line to `hc connect`, which answers full records (or run `hc ls`, then `hc get` each).

## Labels

| label | on | value |
|---|---|---|
| `stampede.job` | lead, helpers | the job's key, `hc-<12 hex>` (from the job folder's path) |
| `stampede.role` | lead, helpers | `lead` or `helper` |
| `stampede.agent` | lead, helpers | its name in the job, unique among the job's live terminals |
| `stampede.space` | lead only | the space's name |
| `stampede.kind` | lead, helpers | `claude`, `codex` or `program` |
| `stampede.session` | a Claude lead or helper | its Claude session id |
| `stampede.resumed` | an agent `stampede reopen` resumed | `1`: while it is `idle` it holds no place under the cap, whatever its turn |
| `herdr.space` | lead, helpers | the space's id in the Herdr app: the same value as `stampede.space` |
| `herdr.tab` | lead, helpers | its tab's id in the app's view (below) |
| `stampede.pane` | lead, helpers | its place in its tab, from 1 (below) |
| `stampede.split` | lead, helpers, not pane 1 | `right` or `down`: how its pane is made |
| `stampede.beside` | lead, helpers, not pane 1 | the `stampede.agent` of the terminal whose pane it splits |

- Identity is the terminal's address. A name another terminal holds gets a suffix; `stampede.agent` stays the name the job uses.
- Status is Core's own: `idle`, `working`, `done`, `blocked`, `error` from the program's reports, and `live` or `finished` for the terminal. A plain program reports none.
- A terminal with no `stampede.role` under the lead is a plain child: show it as a background job of its parent, or leave it out.

### Layout labels

Labels only. Core stays the source of truth, and the tree above never depends on them.

- The lead is pane 1 of tab `main`.
- A helper goes to the first of `main`, `main-2`, `main-3` and so on that holds fewer than 4 live terminals of the job, at the lowest pane number none of them holds. The setting `helpers.tab_panes` (or `STAMPEDE_TAB_PANES`) changes the 4. A terminal without `stampede.pane` holds a place but no number.
- `stampede start --tab <label>` names a workstream tab instead; it overflows to `<label>-2`, `<label>-3` by the same rule.
- Pane 2 splits pane 1 right. Pane 3 splits pane 2 down. Pane 4 splits pane 1 down. Each pane from 5 on splits the pane before it right.
- When the pane a split names is not live, panes 2 and 3 split pane 1 right and pane 4 splits it down; with pane 1 free too, a pane has no split labels.
- The setting `helpers.layout` changes only the `stampede.split` and `stampede.beside` labels of new terminals: `grid` is the order above (the default), `columns` splits each pane right of the one before it, and `rows` below it; when that pane is not live, it splits pane 1 the same way. Tabs and pane numbers stay as above.
- A reopen keeps each node's recorded tab and pane; one that goes through the queue keeps its place while that place is free, else takes one by these rules.

| pane | corner | made by |
|---|---|---|
| 1 | top left | the lead on `main`; the first helper on any other tab |
| 2 | top right | splitting pane 1 right |
| 3 | bottom right | splitting pane 2 down |
| 4 | bottom left | splitting pane 1 down |

- The Herdr app itself reads only `herdr.space` and `herdr.tab` and adds each terminal to the tab's row, so a client draws the places from these labels.
- All of a job's tabs carry the one `herdr.space`.
- To the Herdr app both values are ids, not names. It shows a space it was not told a name for by the folder of its first terminal, and a tab by its place (1, 2 and so on), until someone renames it in the app. The space's name of record is the lead's `stampede.space`.

## Messages

Everything goes through Core. A Core-native job has no follower terminal, no inbox files and no hooks.

| from and to | how |
|---|---|
| parent to child | `hc send <address> "<text>"` (`stampede tell <job> <agent> "<text>"` finds the address) |
| child to parent | `hc send <parent address> "<name>: <one line> <path of the result file>"`; long results go in a file, only the path is sent |
| Core to parent | Core's own notes about each child: its turn ended, it is blocked, it exited |
| parent waiting | `hc wait --children any` (the next news) or `all` (until none is working) |
| owner to lead | `stampede tell <job> lead "<the owner's words>"`, which is `hc send` to the lead |

A message from an agent (a terminal that reports a status) arrives in the terminal as `<hc from="t7 name">...</hc>`; a plain program's `hc send` arrives as bare text, with no tag (hc 0.1.21). Either is information, never an owner's approval: a gate needs the recorded yes (`stampede gate-ok`).

## Events

| what | who hears | how |
|---|---|---|
| a helper's turn end, block or exit | its parent | Core's note; no stampede code |
| a question, a gate | the owner: the bot that started the job; in a front-door job the chat, from `<job>/outbox/`; else the phone | `stampede ask`, `ask --gate`, through `herdr-event-post` to a bot, or one outbox item for a front door |
| a post | the bot that started the job; in a front-door job the chat, through `stampede wait`; in a local job no one (it is only written to `<job>/outbox/`) | `stampede post`, through `herdr-event-post` to a bot |
| the job is done | the bot that started the job; in a front-door job the chat (a `done` item); in a local job the machine's default route when one is set (else it is only logged) | `stampede finish`: one `done` event, `source` `stampede`, or a `done` item for a front door |
| the lead is blocked, at an error, dead or stalled | the owner | the machine's watchdog timer runs `herdr-event-sweep`: one event per episode, `source` `hc`, `pane` `hc:<key>/<address>`, `workspace` `<key>`, `agent` the lead's name |

A client that wants live changes follows Core: `hc events --label stampede.job=<key>` for the labelled terminals, or `hc events` for all, and applies each fact change to its copy of the tree.

## The job folder

`<jobs_root>/jobs/<YYYY-MM-DD>-<owner or local>-<slug>` (the setting `jobs_root`, default `~/code/herdr-jobs`), as for every job: never in the repo, which is recorded in `workdir` and is each agent's default `--cwd`. Every agent gets `--add-dir <job>` (for Codex a writable root). The key is the hash of this path. A job an older stampede made in `<repo>/.herdr-<slug>` keeps working: with no `workdir` file, its repo is the folder above it.

| file | holds |
|---|---|
| `backend` | `native` |
| `workspace` | the key, `hc-<12 hex>`: the marker `jobs/<key>`, the owner tag `owners/<key>`, each event's `workspace` |
| `endpoint` | the core the job was made on (`HC_SESSION`, `HC_SOCKET`) |
| `lead`, `space`, `workdir` | the lead's name, the space's name, the repo |
| `max-helpers` | the cap, only when the owner set one |
| `settings.json` | the settings `stampede new` resolved (not the user-only keys, which always come from your own layers), with the layer that set each and the stampede version; every later command of the job reads it (`stampede config show --job <job>`) |
| `tree.json` | the reopen record, `{"space", "key", "nodes": {<name>: node}}`: every node with its name, role, parent (by name), kind, model, effort, session, brief, report, cwd, tab, pane, split, beside, `argv` (how to start it again), `outlive`, `address` and its last seen `state` |
| `REOPEN.md`, `reopen.sh` | the same record to read, and the command that rebuilds the tree (`fleet-job reopen <job> "$@"` of this checkout, else `stampede reopen`); both are rendered from `tree.json` alone each time it changes |
| `closed` | written by a whole-job `stampede close`, removed by `stampede reopen`: the watchdog raises no alarm for a lead closed on purpose |
| `front-door`, `outbox/`, `outbox.log` | the mark of a front-door job, and the items the lead posted for the owner (`outbox/.seen`: the last one `stampede wait` handed on) |
| `queue/` | helper starts waiting for a free place under the cap, one `<time>-<name>.json` each, oldest first; `queue/dropped/` holds those whose parent was gone |
| `gates/` | each gate asked and the owner's recorded yes |
| `gates.log` | one line per gate switched off for the job (`<UTC time> OFF <name> (<layer>)`), and each merge or push made without one; read by people, never by stampede. The job's gates themselves are recorded outside the folder, in `$HERDR_EVENTS_DIR/gates/<key>.json` |
| `merges.log` | one line per `stampede merge`: PR, reviewed commit, merge commit, method, review report, gate |
| `ask.md`, `plan.md`, `briefs/`, `reports/` | the ask, the lead's plan, each helper's brief, each helper's result |

## Commands

| command | does | prints |
|---|---|---|
| `stampede new --core --file <ask.md> [--cwd <repo>] [--name <slug>] [--space <name>] [--lead claude\|codex] [--lead-model <m>] [--lead-effort <e>] [--max-helpers <n>] [--front-door]`; without `--core` outside a Herdr pane too (the setting `backend`, default `auto`, after the line `on Herdr Core (backend auto: not inside a Herdr pane)`) | makes the job folder, writes the marker and the owner tag, starts the lead as a root with the space's name, writes the reopen record | `<lead> <job dir>` |
| `stampede start <job> <name> --brief <file> [--kind claude\|codex] [--model <m>] [--effort <e>] [--cwd <dir>] [--report <path>] [--tab <label>] [--parent <agent>] [--outlive-parent] [--yolo-in <worktree>]` | starts one helper as a Core child of the caller's terminal, with the kind, model and effort of its role (the name up to its first `-`: the setting `roles.<role>`, else `roles.default`) for each flag not given (from outside Core, or from a terminal that is not the job's: of the lead); over the cap it queues the start. The name `lead`, a name a live terminal or a queued start of the job holds, and a finished job are refused | `STARTED <name> (<address>) under <parent>` or `QUEUED <name> (<n> running, cap <c>)`; `FAILED <name> (<why>)`, exit 1, when Core refuses the run |
| `stampede start <job> <name> [--cwd <dir>] [--tab <label>] [--parent <agent>] [--outlive-parent] -- <program> [args]` | the same for any program (kind `program`) | the same |
| `stampede next <job>` | starts queued helpers, oldest first, while fewer than the cap run (a finished job is refused, exit 2); a live terminal of the job that already carries a queued name is adopted, not started again | one `STARTED` line each (`DROPPED <name>: its parent <p> is gone` for one whose parent is neither live nor queued; `UNKNOWN <name>: <why>; run stampede next once Herdr Core answers`, exit 1, when Core stopped answering after a failed run: the request stays and the drain stops), then `WAITING <k> queued (<n> running, cap <c>)` while any wait, or `NOTHING QUEUED` when nothing started or waits |
| `stampede tree <job> [--json]` | the tree as Core holds it now, and the queue | `space <name> (<key>)`, then `<name> (<address>) <role> <kind> <status> tab <tab> pane <n>` per terminal, indented by depth (a plain child: role `plain`, kind and tab `-`), then `queued <name> under <parent> (<kind>)`; `--json`: `{space, key, nodes: [{depth, name, address, parent, role, kind, status, state, tab, pane, split, beside, outlived}], queue}` |
| `stampede tell <job> <agent> "<text>"` | `hc send` to that agent's terminal | `SUBMITTED <agent>` or `FAILED <agent> (<why>)` |
| `stampede snapshot <job>` | rewrites `tree.json`, `REOPEN.md` and `reopen.sh` from Core's tree: address, Core name, state (`live`, `finished` with exit code and reason, `gone` when Core no longer lists it), parent, cwd, tab; a plain child becomes a node of role `plain` with its argv. What only the start knew is kept | the record's path; `FAILED snapshot (<why>)`, exit 1, when Core does not answer |
| `stampede reopen <job> [--fresh] [--prompt] [--rerun-programs]` | brings back what is not live, parents first, each child under its parent's new address. It never hands out work by itself: a resumed Claude session comes back idle, and a helper that would start its brief again is queued under the cap. On a finished job `--fresh` and `--rerun-programs` are refused (exit 2), and nothing in its queue starts | per node: `LIVE <name> (<address>)`, `STARTED <name> (<address>) under <parent>` (the lead: no `under`), `QUEUED <name> (<n> running, cap <c>)`, `SKIPPED <name> (codex keeps no session to resume: ...)`, `SKIPPED <name>: its parent <p> is not running`, `SKIPPED <name> (a plain child: ...)`, `SKIPPED <name> (a program: ...)`, `DONE <name> (exited 0)`, `DONE <name> (closed)`, `SKIPPED <name> (the job is finished: its queued start stays in the queue)` or `FAILED <name> (<why>)`, exit 1; `NOT TOLD <name> (<why>)` when a line to it could not go |
| `stampede close <job> [<agent>]` | ends that agent's subtree, deepest first; with no agent (or `lead`) the whole job, the lead last. Refused, exit 2, from a terminal in that subtree. A terminal labelled with another job's key is never closed: it, its branch and the terminals above it stay | `CLOSED <name> (<address>)` per terminal, in order; `FAILED <name> (<why>)`, exit 1, going on with the rest; `SKIPPED <name> (<address>): ...` per terminal kept, exit 1 |
| `stampede ask`, `ask --gate`, `gate-ok`, `approve-gate`, `approve`, `post`, `finish` | as on every backend | as on every backend |
| `stampede wait <job> [--timeout <s>]` | a front door's wait ([Front door](#front-door)) | each new outbox item, `BLOCKED <lead>: <kind>` and its screen, or `LEAD_GONE <lead>`, exit 0; `TIMEOUT ...`, exit 3 |

Every command's flags, what it prints and its exit code: [CLI.md](CLI.md), with [a Core job's exit codes](CLI.md#exit-codes).

### The cap

At most 12 helpers run at once in one lead's tree, at any depth. The owner changes it per job: `--max-helpers <n>` at `new`, or the number in `<job>/max-helpers`; the setting `helpers.max` (or `STAMPEDE_MAX_HELPERS`) changes the default, and a `--set helpers.max=<n>` at `new` is saved in the job's `settings.json` ([README, Configure](../README.md#configure)).

A helper counts while Core would call it working: its terminal is live and it has not yet gone `idle` or `done` after its task. A plain program counts while it lives. The lead and plain children never count.

A start over the cap is queued, not refused. The lead runs `stampede next <job>` when a child's note arrives; every `stampede start` drains the queue first too. Core takes a finished terminal as `--parent` (hc 0.1.21), so the drain itself checks that a queued start's parent is live and drops it otherwise.

### Reopen and close

- `tree.json` is written at `new`, at every start, by `stampede snapshot`, `reopen`, `close`, and after `finish`. It is a copy for a rebuild; Core's own tree wins while it lives.
- `stampede reopen` after a crash or a reboot walks the record parents first. A reopen never hands out work by itself: whatever would make a helper work again goes through the queue and the cap, and the rest comes back idle or stays out.
  - The lead of an open job comes back as before: Claude resumes its session when Claude's own session file shows it ran, else starts with that id and its brief; Codex starts fresh with its brief. It gets one line saying it was reopened.
  - A Claude helper whose session ran is resumed idle, labelled `stampede.resumed=1`; `--prompt` gives it its parent's new address.
  - A Claude helper whose session never ran, any helper with `--fresh` (a new id for Claude) and a program with `--rerun-programs` are written to the queue as `start` writes them. One drain after the walk starts what the cap allows, so a first prompt names the parent's address at that moment; the rest prints `QUEUED` and waits for `stampede next`. A Codex helper without `--fresh` is skipped: a native job records no Codex session.
  - A finished job is reopened for reading only, with no marker and no owner tag: `--fresh` and `--rerun-programs` are refused, the lead comes back only as a resumed Claude session told the job is finished, and a lead or helper that would need a first prompt is skipped. Nothing is queued, and nothing already queued starts: each queued start is named in a `SKIPPED` line and stays in the queue, inert. `stampede start` and `stampede next` on a finished job start no helper: one line, exit 2.
  - A program is never run again unless `--rerun-programs` says so. A terminal still live is left alone.
- A queued start is the record of its intent: it goes only once the start's outcome is known. A live terminal of the job that already carries its name is adopted (recorded, counted, `STARTED`). When `hc run` fails, the drain lists again: a terminal of that name is adopted; none is `FAILED`; no answer leaves the request queued, prints `UNKNOWN` and stops the drain.
- `stampede close` ends an agent politely when it is idle or done (`/exit` for Claude, `/quit` for Codex, typed with `hc keys`, then its state is looked at every half second for up to 15 s), else kills its terminal, then removes it (`hc rm`). An agent closed by name keeps the state `closed`, and a reopen leaves it and its branch closed; a whole-job close marks no node `closed`, so a reopen brings back what ran. Children go before their parent. Closing a whole job is the owner's call.

## Front door

`stampede new --core --front-door` makes a job whose owner talks only to the chat that started it, outside Herdr and Core (a desktop app, a terminal). It writes `<job>/front-door`. It is refused with `--relay`, and when a bot would own the job (`HERDR_EVENTS_OWNER`, or the workspace's owner tag): a bot relays its own jobs.

- **The lead posts, never shows.** Its brief says: the plan, files, decisions and the report go out with `stampede post <job> "<text>" --file <path>`, a question with `stampede ask`, a gate with `stampede ask --gate`. Each is one item, `<job>/outbox/NNN.md` (its files in `outbox/NNN/`, a line in `outbox.log`). A question card or a file-send tool reaches no one: a native job has no hooks to turn them into posts. With `--review` the lead posts `plan.md` and ends its turn.
- **The chat waits:** `stampede wait <job>` in the background prints each item it has not shown yet, then exits 0. It prints `BLOCKED <lead>: <kind>` with the tail of the lead's screen (`hc read`) when Core says the lead is `blocked`, and `LEAD_GONE <lead>` when Core holds no live lead; exit 3 after `--timeout` seconds (default 3600) with nothing new.
- **The chat answers** by running each item's own line: a question's `fleet-job tell <job> lead "ANSWER <id> ...: <their words>"`; the plan's yes with `stampede approve <job> --by "..."`, which takes only a plan the lead posted as it stands and `wait` has handed on; a gate's `approve-gate ... --by "owner in <chat>: <their words>"`, or its no line. All of these reach the lead as one `hc send` to its terminal (`SUBMITTED`); there is no inbox file.
- **Only the recorded yes opens a gate.** `approve` and `approve-gate` refuse to run inside Herdr or a Core terminal; the lead acts only after `stampede gate-ok` prints `APPROVED`, and nothing typed into its terminal counts.
- `finish` posts a `done` item, which `wait` hands on; no event goes to a bot or the default route.

## Not in a Core-native job

- **Without a front door,** the chat that starts a Core job passes the owner's words with `stampede tell <job> lead "..."` and reads the lead with `hc read <address>`.
  - **A job a bot started** (it has an owner tag): questions, gates, posts and done reach that bot as events, and the bot records a gate's yes with `approve-gate`.
  - **A job started locally:** a question or a gate goes to the owner's phone, and `approve-gate` refuses it; a post is only written to `<job>/outbox/` and no one is told; `finish` sends its `done` event through the ordinary relay, to the default route when one is set, and it is only logged when no route has a URL.
- No `--pane`: a Core-native job hands nothing to a Herdr TUI pane. Run another CLI as a program (`stampede start <job> <name> -- <cli> ...`).
- No follower terminal (`relay-<key>`), `inbox.log`, `inbox/`, `hooks/`, `core.json` or `agents.tsv`.
- The earlier Core path, with those parts, is `stampede new --core --relay`. It is kept for one release.
