# Using stampede

stampede turns one ask into a job run by a lead agent in Herdr.
The lead plans in `plan.md`, starts helper agents only when it pays, and brings the owner only the questions and gates that are theirs.
A job runs on the Herdr TUI (tabs and panes) or on Herdr Core (a tree of terminals).

## Before you start

- `stampede doctor` checks the machine and this checkout, one line each with its fix (`stampede doctor --core` for Herdr Core). Its warnings are the owner's to fix.
- `stampede --help` lists every command; `stampede <command> --help` gives its flags and an example.
- `herdr-trust <repo>` once per repo, so Claude and Codex skip the trust dialog. The repo must sit under `FLEET_TRUST_ROOT` (default `~/code`).
- Write the ask (the owner's words, and any agreed plan) to a file outside the repo.
- See what a job will do: `stampede config show` (every setting, and the layer that set it).

## Start a job

```bash
stampede new --file ask.md     # in a Herdr pane: the TUI; anywhere else: Herdr Core
```

- On Core it works on the git root here (or `--cwd <repo>`) and says so first. `--core` or `--pane` forces one; the setting `backend` is the standing choice.
- It prints `<lead> <job dir>` (on Core after a `STARTED <lead> (<address>)` line) and exits 0.
- A line starting `BLOCKED` or `NOT READY` means the lead is up but waiting: do what that line says, never start a second lead.
- A refusal exits 2 with the reason, before anything is made.
- A chat outside Herdr that wants the TUI passes `--pane` or `--workspace`, and usually `--front-door`: see [skills/stampede](skills/stampede/SKILL.md).

## Then

| command | who runs it | what it does |
|---|---|---|
| `stampede tell <job> lead "<the owner's words>"` | the front door | passes words on, verbatim |
| `stampede ask <job> "<question>" [--option <a>]` | the lead | asks the owner; prints `ASKED <id>` |
| `stampede ask <job> --gate [--kind merge] --sha <commit> "<action>"` | the lead | asks for a gate; prints `GATE <id>` |
| `stampede post <job> "<text>" [--file <path>]` | the lead | the plan, a screenshot, a report; prints `POSTED <n>` and who hears it |
| `stampede finish <job> "<one line>"` | the lead | ends the job; prints `FINISHED <job dir>` |

On Herdr Core also: `stampede start <job> <role>-<scope> --brief <file>` (or `-- <program>`) starts a helper, its model from its role (`roles.build` for `build-api`).
`stampede tree <job>` lists the tree, `stampede close <job> [<agent>]` ends a subtree or the job (owner's yes only), and `stampede reopen <job>` brings back what is not live.

## Where the job folder is

Always `<jobs_root>/jobs/<YYYY-MM-DD>-<owner or local>-<name>` (default root `~/code/herdr-jobs`), the repo in `<job>/workdir`. An older `<repo>/.herdr-<name>` job still works.

## What always needs the owner's yes

Merges, pushes to shared branches, deploys, sends, spends and closes: the list and how a gate is asked and passed are in [gates.md](skills/herdr-fleet/references/gates.md). Merge with `stampede merge`, never `gh pr merge`.

## Searching this repo

`.ignore` keeps `film/`, `site/`, `assets/` and `tests/evals/runs/` out of ripgrep and similar searches, so a search stays in the product.

## Go deeper

- Starting a job (the front door): [skills/stampede/SKILL.md](skills/stampede/SKILL.md)
- Leading one: [skills/herdr-fleet/SKILL.md](skills/herdr-fleet/SKILL.md), and on Herdr Core [core.md](skills/herdr-fleet/references/core.md) and [docs/CORE-NATIVE.md](docs/CORE-NATIVE.md)
- A bot front door over SSH: [skills/grokbot-herdr/SKILL.md](skills/grokbot-herdr/SKILL.md)
- Showing the plan first: [skills/share-plan/SKILL.md](skills/share-plan/SKILL.md)
- Changing this repo: [AGENTS.md](AGENTS.md)
- Every command, what it prints and its exit codes: [docs/CLI.md](docs/CLI.md)
- Everything else: [README.md](README.md)
