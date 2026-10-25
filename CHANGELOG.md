# Changelog

## Unreleased

- **Optional pstack support for the lead.** If the Claude Code plugin pstack is installed, a lead loads it like any Claude Code session and, for coding jobs only, follows [references/pstack.md](skills/herdr-fleet/references/pstack.md) wherever pstack says otherwise: its fan-out runs as Herdr panes, the fleet model table and Herdr ownership win, the architect sketch is the contract commit, and the todo list is `todo.md` in the job folder. herdr-fleet points to it from "Panes, not built-in subagents"; the README has a short "Works well with" section. Without pstack nothing changes.

## 0.1.3 (25 Oct 2026)

- **Complete worker hand-offs.** Your lead writes each worker's brief on the hand-off template; `stampede start` refuses a missing brief or a missing or empty section before writing hooks or calling Herdr. The playbooks and examples use the template, and the docs explain stateful leads, stateless workers and independently swappable models per role. Tested with fake Herdr, including restarted leads with their generated briefs.

## 0.1.2 (23 Oct 2026)

- **Small jobs stay in Herdr:** a small job still needs no stampede job, but it runs as one agent session in a single Herdr pane of its own, tagged with `herdr-events-owner` and prompted with `herdr-send`, never as a bare agent CLI call over SSH or nohup outside Herdr. Updated in herdr-fleet, grokbot-herdr, SKILL.md and the README.
- **Gate questions go back to whoever started the job.** `stampede new` records the starting bot (`HERDR_EVENTS_OWNER`, else the workspace's owner tag) in `<job>/owner`. In a bot-started job, `stampede ask` sends a `question` event to that bot instead of a phone card, and both go through `herdr-event-post --strict`: only that bot's own route with a URL, never the default route, and a refusal unless the event is queued. A queued question or gate waits out a route with no URL instead of being dropped, and its lead gets an `UNDELIVERED` line in `inbox.log` when it is held and if it expires after 24 h; events carry `lead_pane`, not `pane`, so the flusher never drops one for a later turn end, and each answer names its question. `stampede ask --gate --sha <commit> [--pr <n>] "<action>"` sends a `gate` event to that bot, which asks you in chat and records your yes with `stampede approve-gate`; a job started locally asks on your phone through `FLEET_ASK_CMD`, as before. A yes typed in the lead's pane always works. The lead acts on a recorded yes only after `stampede gate-ok` matches it to the gate and the commit; a push after it withdraws it, and `approve-gate` refuses inside Herdr, for a local job and for another commit. The relay sends every gate as its own event.
- **The README flowchart is a live mermaid block again**, left to right, showing the gate question going back to Grok Bot, Moshi only for a job you started locally, and a yes typed in Herdr. "Only when they pay" is now "only when it's worth it". The README opens with the story, before anything else: the Grok Bot is the inlet that spins up local agents over Tailscale, then the chain from you to Grok to your stampede bot to the lead to its agents and back. Then the Grok Bot flow: it starts and ends with the bot, each bot owns its own Herdr workspace, the lead is the valve that passes each worker only the context it needs, recommended for everyone and not required. The Herdr plugin description leads with the same sentence.
- **Plugin updates keep stampede working:** run from a Herdr-managed checkout (`<plugins>/github-installations/stampede-<id>/<N>-<M>/checkout`), `install.sh` moves a link that points at the same file in another `<N>-<M>/checkout` of that same install to the new one (`relinked`), so a `herdr plugin update` or reinstall no longer leaves it to dangle once Herdr deletes the old checkout. Paths are compared as plain text; another plugin's link, a backup's, a different file's or one of yours is still left as is, and a clone relinks nothing.
- **herdr-doctor:** for a GitHub-managed plugin, a `PROBLEM` when `stampede` or a skill link resolves outside the checkout `herdr plugin list --json` reports; a `warn` when the `FLEET_TRUST_ROOT` folder (default `~/code`) is missing, in place of an `ok`.
- **stampede update in a plugin install:** Herdr's managed checkout keeps `.git`, so a checkout whose path ends in `plugins/github-installations/stampede-<id>/<N>-<M>/checkout` counts as a plugin install too (an ordinary clone under a folder of that name does not). `stampede update` changes nothing there, and it and the daily check name `herdr plugin update stampede --yes`, not `git switch main`.
- **Docs:** the README Install shows the plugin route with the PATH line and `herdr-trust`; Updating has `--yes` and a one-time path from 0.1.0; SETUP.md has the uninstall commands for a managed install (link targets compared as plain text, never a `find -lname` pattern) and the `~/.cache/stampede` note, and no longer calls the plugin "needed only for the event relay".

## 0.1.1 (23 Oct 2026)

- **Updating:** `stampede update` fast-forwards a clean checkout on `main` and reruns `install.sh`; it refuses local changes, untracked files, another branch, or an ignored file the update would overwrite, and outside a git checkout names `herdr plugin update`. Once a day, `stampede --version` (on stderr), `stampede update --check` and `herdr-doctor` (a `warn`) say when a newer GitHub release is out; silent offline or on any failure, off with `STAMPEDE_NO_UPDATE_CHECK=1`. The README has an [Updating](README.md#updating) section.
- **One version:** `herdr-plugin.toml` matches VERSION, and a test keeps them equal. [RELEASING.md](RELEASING.md) says how to cut a release.
- **One version, wider:** the version test also checks the README badge, the README's `stampede --version` line and the site's install prompt against VERSION.
- **A clean core install:** `herdr-doctor` runs the core checks only and exits 0 on a clean install with Herdr running. The event relay checks run when the relay is installed, or with `herdr-doctor --relay`. Exit 0 ok, 1 a `PROBLEM`, 2 usage.
- **A short README top and macOS CI:** the README opens with what stampede is, a 3-command install, a first ask, a flow diagram and its limits. CI (`.github/workflows/ci.yml`) runs the tests, the install and `herdr-doctor` against a real Herdr on macOS, on every push and pull request.
- **Size the job first:** before any workspace, the lead or front door sizes the job on length, agents, risk and durability. A small job needs no stampede (one Claude session with built-in subagents); a big one runs as a stampede job. The rule is in [herdr-fleet](skills/herdr-fleet/SKILL.md#size-the-job-first-small-or-big), linked from SKILL.md, grokbot-herdr and the README FAQ.
- **Site:** the landing page is rebuilt around the film: a frosted header with a theme toggle, the Open gate mark's full run with a red beat and no outlines, one gold Get started that copies the install prompt and says to paste it into your agent, and a short footer. Live at https://vib-z.github.io/stampede/ and https://stampede-xi.vercel.app/.

## 0.1.0 (22 Oct 2026)

The first public version: one ask, one lead, and only the panes that pay.

- **The job:** `stampede new` makes a job folder and starts a Claude lead with its hooks; the lead plans in `plan.md` and starts work at once.
- **Workers:** `stampede start` starts Claude, Codex or Cursor in a Herdr pane, in auto mode, with hooks that report back; no polling.
- **Questions and gates:** `stampede ask` puts a question on your phone through Moshi while the lead keeps working; every merge, push to a shared branch, deploy, send, spend and close waits for your own tap.
- **Share the plan first**, on request: `--review` and `stampede approve`, locked to the plan's fingerprint.
- **Front doors:** a Herdr chat, Claude or Codex desktop, Cursor, Grok Bot and other bots, or a whole remote computer.
- **Reopen:** `reopen.sh` brings a closed job back.
- **Install:** `install.sh` links three skills and the commands; `stampede --version` prints the version.
