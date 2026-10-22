# Changelog

## 0.1.0 (22 Oct 2026)

The first public version: one ask, one lead, and only the panes that pay.

- **The job:** `stampede new` makes a job folder and starts a Claude lead with its hooks; the lead plans in `plan.md` and starts work at once.
- **Workers:** `stampede start` starts Claude, Codex or Cursor in a Herdr pane, in auto mode, with hooks that report back; no polling.
- **Questions and gates:** `stampede ask` puts a question on your phone through Moshi while the lead keeps working; every merge, push to a shared branch, deploy, send, spend and close waits for your own tap.
- **Share the plan first**, on request: `--review` and `stampede approve`, locked to the plan's fingerprint.
- **Front doors:** a Herdr chat, Claude or Codex desktop, Cursor, Grok Bot and other bots, or a whole remote computer.
- **Reopen:** `reopen.sh` brings a closed job back.
- **Install:** `install.sh` links three skills and the commands; `stampede --version` prints the version.
