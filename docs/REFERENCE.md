# Reference

Every command and helper script with its exit codes, how the code is laid out, every doc, and the credits.

## `stampede` commands and exit codes

Every command with its flags, the status words it prints (`STARTED`, `QUEUED`, `DELIVERED`, `SUBMITTED`, `BLOCKED`, `APPROVED`, `TIMEOUT`, `LEAD_GONE` and the rest) and one table of exit codes: [docs/CLI.md](CLI.md).

Every command an agent runs takes `--json` and prints one JSON object instead (`ok`, `command`, `status` and the facts the line names, or `error` and `retry` for a refusal), with the same exit code: [docs/CLI-JSON.md](CLI-JSON.md).

The command lists itself too: `stampede --help`, and `stampede <command> --help` for each one's flags and an example. `stampede` and `fleet-job` are the same command ([fleet_job.py](../skills/herdr-fleet/scripts/fleet_job.py), the entry; the [stampede package](../skills/herdr-fleet/scripts/stampede/) holds the commands, `stampede merge` and the hidden `stampede prepush` among them). In short: 0 done, 1 Herdr, Herdr Core or a program failed (or `doctor` found a `PROBLEM`), 2 a usage error or a refusal with its reason on one line, 3 `tell` queued behind a question card or `wait` timed out.

## Helper scripts

In [skills/grokbot-herdr/scripts/](../skills/grokbot-herdr/scripts/):

| script | does | exit |
|---|---|---|
| `herdr-trust <dir>` | pre-trusts a repo for Claude and Codex | 0, or 2 refused |
| `herdr-send <agent> <text>` | prompts an agent and confirms it from the status and the screen: `SUBMITTED` once a turn starts or the text leaves the prompt, a late start too. Text left in the prompt gets Enter again (never a slash command), then ctrl+c and `FAILED`. Refuses a pane you have focused before any key | 0, 1 failed, 2 usage |
| `herdr-reopen-snapshot <ws> <job dir>` | reads the live workspace (read only) and writes `REOPEN.md` and `reopen.sh` in the job folder: the tabs holding the job's agents (from `agents.tsv`), never another's agent. Given a `--relay` job's `<hc-key>`, it writes that job's record from `agents.tsv` and `core.json` | 0, or 1 with the reason |
| `<job>/reopen.sh` | recreates the workspace and resumes each agent's session; `--fresh` new sessions, `--prompt` re-sends the briefs, `--into <ws>` adds to an open workspace | 0, 2 a workspace with that label is open or policy refuses an agent, 3 a pane's folder is gone, 4 a tab did not open, 5 the new workspace could not be tagged for its bot, 64 usage |
| `<job>/reopen.sh` (a Core job) | the same as `stampede reopen <job>`: brings back what is not live from `tree.json`, parents first, under the cap | as `stampede reopen` |
| `<job>/reopen.sh` (a `--relay` job) | starts only what is not live, each once: the follower, the lead, then each worker; `--lead`, `--prompt` and `--fresh` as in [core-relay.md](../skills/herdr-fleet/references/core-relay.md#reopen) | 0, 1 a restart was not `STARTED`, 2 another caller is starting one, a folder is gone or policy refuses an agent, 3 the lead did not acknowledge a file |
| `herdr-doctor [--relay] [--tui\|--core]` | read-only health check: `ok`, `warn`, `PROBLEM` lines; `-h` prints usage. It checks the stampede install and each backend that is installed (the Herdr TUI when `herdr` is on PATH, Herdr Core when `hc` is); one usable backend is enough, and `ok backend tui,core` (or `tui`, or `core`) names where a job can run. `--tui` or `--core` checks that one only, each gap a `PROBLEM`. The event relay is checked when installed, or with `--relay`. It never starts a core | 0 ok, 1 a PROBLEM, 2 usage |
| `herdr-events-owner <ws> [<bot>\|--clear]` | tags a workspace, or an open Herdr Core job's key `hc-<12 hex>`, with the bot its events go to; `-h` prints usage | 0, or 2 refused |
| `herdr-event-sweep` | run by the watchdog timer every 5 minutes: one look at the lead of each open Core job, and one `source` `hc` event per episode (`blocked`, `error`, `stale`, `dead`) ([remote/events-core.md](../remote/events-core.md#a-core-native-job-the-sweep)). `--alive` asks the selected core's socket for `hello`, never starting one; `--core-version` prints the running core's version; `--socket` prints its path | 0; `--alive` and `--core-version`: 0 up, 1 down; 2 usage |
| `herdr-event-core <job dir>` | the follower of a `--relay` job, started by `stampede new --core --relay`: follows the job's terminals, writes their lines to the lead's inbox and posts `source` `hc` events for the bot ([remote/events-core.md](../remote/events-core.md)) | 0 the job finished or never started, 1 relay down, 2 usage |
| `herdr-event-post`, `herdr-event-flush`, `herdr-event-watchdog`, `herdr-event-claude-hook`, `herdr-event-codex-notify` | the event relay to a bot, with every exit code: [remote/events.md](../remote/events.md). While a job marker is present, a plain turn end in that workspace is not sent | 0; `herdr-event-post --strict`: 3 no route of its own, 4 not queued, 6 a malformed `workspace`; 5 a follower's event not queued |

## Repo layout

```text
README.md  CHANGELOG.md  CONTRIBUTING.md  RELEASING.md  SECURITY.md  LICENSE  VERSION
AGENTS.md  CLAUDE.md  SKILL.md  USING.md  config.example  install.sh  herdr-plugin.toml
.github/                issue and pull request templates, workflows/ci.yml (macOS and Linux CI)
skills/herdr-fleet/     the job: SKILL.md, references/ (core.md: a Core job; core-relay.md: the --relay path),
                        scripts/fleet-job, fleet_job.py (the entry), fleet-watch.sh, and scripts/stampede/,
                        the commands, one module per concern: base, job (the job folder), hcapi (Herdr Core),
                        herdrapi (Herdr), agents (per CLI), owner (questions, gates, tell, finish), hooks, tui,
                        native (a Core job), relay and handed (the --relay path), cli (the parser and help),
                        doctor and check (stampede doctor and stampede check), gates (stampede merge, the
                        pre-push hook and each job's gate record), out (--json),
                        settings (the layered config) with defaults.toml (every key and its default);
                        core_native.py re-exports native
skills/grokbot-herdr/   the bot front door: SKILL.md, scripts/ (herdr-send, herdr-trust, herdr-doctor,
                        the relay, herdr-event-sweep: the Core sweep and probes,
                        herdr-event-core: a --relay job's follower)
skills/share-plan/      the plan review, on request
skills/stampede/        the front door: "use stampede" in any chat starts a lead
scripts/stampede        the command (also linked as fleet-job); answers --version and update
scripts/stampede_update.py   the daily release check and stampede update
scripts/herdr-plugin-event   the Herdr plugin's event hook
remote/                 front-door guides
docs/                   GUIDE.md, SETUP.md, CORE.md, SAFETY.md, CONFIGURE.md, TROUBLESHOOT.md, REFERENCE.md,
                        STATUS.md, LINUX.md, RUNS.md, CLIENTS.md, CLI.md (every command), CLI-JSON.md (--json),
                        CORE-NATIVE.md (a Core job's shape), superpowers/specs/ (the design), images/
assets/                 the poster, the teaser and the demo GIF
site/                   the hero site: index.html, assets/
site/brand/             the identity assets and the brand guide
tests/                  python3 -m unittest discover tests; fake_hc.py (a fake Herdr Core),
                        fake_herdr.py (a fake Herdr TUI, for mixed jobs), core_smoke.py (CI, a real one)
                        test_clients.py and clients_run.py: the cross-client suite (docs/CLIENTS.md)
tests/evals/            the evals: cases.json, run.py, record.py, live/, linux/, runs/ (tests/evals/README.md)
```

## Docs

| doc | for |
|---|---|
| [README.md](../README.md) | the front page: what stampede is, what you need, install, your first job, safety in short |
| [docs/GUIDE.md](GUIDE.md) | how a job flows, with and without a bot, what it works with, the screenshots, how it works, one job walked through, the front doors |
| [docs/SETUP.md](SETUP.md) | the full setup: installer, unattended agents, the event relay, uninstall |
| [docs/CORE.md](CORE.md) | running a job on Herdr Core: the tree and the roles, one Core job start to finish, reopen and close |
| [docs/SAFETY.md](SAFETY.md) | every gate that needs your yes, who records it, and what code holds |
| [docs/CONFIGURE.md](CONFIGURE.md) | the layers, every key with its default, and the environment-only variables |
| [docs/TROUBLESHOOT.md](TROUBLESHOOT.md) | each message you may see with its fix, and the FAQ |
| [docs/REFERENCE.md](REFERENCE.md) | this page: the commands and helper scripts with their exit codes, the repo layout, the docs, the credits |
| [docs/STATUS.md](STATUS.md) | what works and how it was tested, and the roadmap |
| [docs/LINUX.md](LINUX.md) | stampede on Linux: what was verified and how, the install, the timers, what differs from macOS, the gaps |
| [USING.md](../USING.md) | the one page an agent reads first to run a job: start it, the commands that follow, the job folder, the gates |
| [SKILL.md](../SKILL.md) | the skill entry point, routing each role to its skill |
| [skills/herdr-fleet](../skills/herdr-fleet/SKILL.md) | the lead's playbook, with [failure modes](../skills/herdr-fleet/references/failure-modes.md) [a job on Herdr Core](../skills/herdr-fleet/references/core.md) and [the earlier `--core --relay` path](../skills/herdr-fleet/references/core-relay.md) |
| [docs/CLI.md](CLI.md) | every command: its flags, the status words it prints, and the exit codes |
| [docs/CLI-JSON.md](CLI-JSON.md) | `--json`: the one object each command prints, its status values and facts |
| [docs/CORE-NATIVE.md](CORE-NATIVE.md) | the shape of a Core job: the tree, labels, messages, events, the job folder and the commands, for a client that draws one |
| [remote/](../remote/README.md) | one guide per front door, Moshi and the event relay |
| [docs/RUNS.md](RUNS.md) | real runs, with timelines and what changed because of them |
| [docs/CLIENTS.md](CLIENTS.md) | the cross-client suite: every client stampede claims reaching the same outcomes on the Herdr TUI and on Herdr Core, the matrix, the live runbook, and which client does worse |
| [tests/evals/README.md](../tests/evals/README.md) | the evals: the dataset, how a run is recorded, the baseline and after runs |
| [the lean design](superpowers/specs/2026-10-21-stampede-lean-design.md) | why stampede is shaped this way |
| [site/](../site/README.md) | the hero site, and its [brand kit](../site/brand/README.md) |
| [CHANGELOG.md](../CHANGELOG.md) | what each version shipped |
| [RELEASING.md](../RELEASING.md) | how a maintainer cuts a release: VERSION, the changelog, the tag, the GitHub Release |
| [CONTRIBUTING.md](../CONTRIBUTING.md), [SECURITY.md](../SECURITY.md) | how to help, and how to report a security problem privately |

## Credits and license

Built on [Herdr](https://herdr.dev) and its agent automation, with [Moshi](https://getmoshi.app/docs/herdr) for the phone. A stream of many small, independent coding tasks fits [herdr-projects](https://github.com/eliasstravik/herdr-projects) better. [tests/fixtures/hc-schema-0.1.20.json](../tests/fixtures/hc-schema-0.1.20.json) is the output of `hc schema` from Herdr Core 0.1.20, which names its licence as Apache-2.0; it is kept unchanged, for the tests only.

Product marks: [docs/images/logos/SOURCES.md](images/logos/SOURCES.md). The brand kit, in [site/brand](../site/brand/README.md) with its [visual guide](../site/brand/guide.html), holds the Open gate logo, the Star link, the painterly grounds and the brand guide.

[MIT](../LICENSE), copyright 2026 stampede contributors. The code licence does not grant rights to the stampede name or marks. See [site/brand/CREDITS.md](../site/brand/CREDITS.md).
