# Changelog

## Unreleased

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
