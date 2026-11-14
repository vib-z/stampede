# Using stampede

stampede turns one ask into a job run by a lead agent in Herdr.
The lead plans in `plan.md`, starts helpers when it pays, and brings the owner only their questions and gates.
A job runs on the Herdr TUI (tabs and panes) or Herdr Core (a tree of terminals).

## Before you start

- Install: clone the repo, run `./install.sh` ([README, Install](README.md#install)).
- `stampede doctor` checks the machine, each line with its fix (`--core` for Herdr Core); warnings are the owner's.
- `stampede <command> --help`: flags and an example. `--json` on any: one object ([CLI-JSON](docs/CLI-JSON.md)).
- `herdr-trust <repo>` once per repo (under `FLEET_TRUST_ROOT`, default `~/code`), so agents skip the trust dialog.
- `stampede config show`: every setting, the layer that set it, and your config file; settings go there as in [config.example](config.example).
- Write the ask (the owner's words and plan) to a file outside the repo.

## Start a job

```bash
stampede new --file ask.md     # in a Herdr pane: the TUI; anywhere else: Herdr Core
```

- On Core it works on the git root here (or `--cwd <repo>`) and names it first. `--core` or `--pane` forces one; the setting `backend` is the standing choice.
- It prints `<lead> <job dir>` (on Core after `STARTED <lead> (<address>)`), exit 0. A refusal exits 2, before anything is made.
- `BLOCKED` or `NOT READY`: the lead waits. Do what the line says; never start a second lead.
- An agent chat that relays the owner's answers passes `--front-door`, on Core too. For the TUI it also passes `--pane` or `--workspace`: see [skills/stampede](skills/stampede/SKILL.md).

## Then

| command | who runs it | what it does |
|---|---|---|
| `stampede tell <job> lead "<the owner's words>"` | the front door | passes words on, verbatim |
| `stampede ask <job> "<question>" [--option <a>]` | the lead | asks the owner; prints `ASKED <id>` |
| `stampede ask <job> --gate [--kind merge] --sha <commit> "<action>"` | the lead | asks for a gate; prints `GATE <id>` |
| `stampede post <job> "<text>" [--file <path>]` | the lead | the plan, a report; prints `POSTED <n>` |
| `stampede finish <job> "<one line>"` | the lead | ends the job; prints `FINISHED <job dir>` |

On Herdr Core also: `stampede start <job> <role>-<scope> --brief <file>` (or `-- <program>`) starts a helper, its model from its role (`roles.build` for `build-api`).
`stampede tree <job>` lists the tree. `stampede close <job> [<agent>]` ends a subtree or the job: ask the owner first (code only stops a close from inside the job).
`stampede reopen <job>` brings back what stopped, and a whole job `close <job>` put away; an agent closed by name stays closed. A finished job reopens read-only.

## Where the job folder is

`<jobs_root>/jobs/<YYYY-MM-DD>-<owner or local>-<name>` (default root `~/code/herdr-jobs`); `<job>/workdir` holds the repo's path.

## What always needs the owner's yes

Merges, pushes to shared branches, deploys, sends, spends and closes ([gates.md](skills/herdr-fleet/references/gates.md) has the list and how a gate is passed). Merge with `stampede merge`, never `gh pr merge`. Who records the yes:

- A job a bot started: the bot runs the `approve-gate` line it is handed.
- A chat outside Herdr: it starts the job with `--front-door` and does the same.
- A job started locally: the owner answers through `ask.command` (the phone by default), so it must work before the first gate.

## Go deeper

- Starting a job: [skills/stampede](skills/stampede/SKILL.md). Leading one: [skills/herdr-fleet](skills/herdr-fleet/SKILL.md), on Core [core.md](skills/herdr-fleet/references/core.md)
- A bot over SSH: [skills/grokbot-herdr](skills/grokbot-herdr/SKILL.md). Showing the plan first: [skills/share-plan](skills/share-plan/SKILL.md)
- Every command, its output and exit codes: [docs/CLI.md](docs/CLI.md). Changing stampede: [AGENTS.md](AGENTS.md). The rest: [README.md](README.md)
- `.ignore` keeps `film/`, `site/`, `assets/` and eval runs out of ripgrep.
