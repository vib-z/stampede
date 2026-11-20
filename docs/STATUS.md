# Status and roadmap

**0.2.3, 15 Nov 2026, and early:** commands and files may still change. What each release shipped, and how it was tested: [CHANGELOG.md](../CHANGELOG.md). Real jobs, with timelines: [docs/RUNS.md](RUNS.md).

**Works and tested.** Every command in the README and the pages under `docs/` was run against a scratch job with the fakes, or against `--help`.
- **A job on the Herdr TUI:** the job folder, the lead's start with its hooks, Claude, Codex and Cursor workers, complete worker briefs, plan approval, background questions and cancel, gates that go back to whoever started the job, quieter events while a job is open, a lead forked from the planning chat, a Codex lead, a front door outside Herdr, and reopen.
  - Tested with fakes. Live on macOS (21 Oct 2026): a hooked Claude lead woken by its inbox file, a Codex reviewer's turn through Codex's notify hook, a Cursor worker under auto-review, and a question on the owner's phone that did not block the lead and was cancelled cleanly. A Codex lead on Codex 0.167.1 was checked live on Linux in a Herdr 0.9.5 pane; no whole job has run live with a real Codex lead yet.
  - The lead's reply to a typed gate approval on Core has not been checked with a live agent.
- **A Core job, run the way Core works:** the tree, the cap and queue, the layout labels, `tell`, `snapshot`, `reopen`, `close`, the watchdog sweep and the native front door.
  - Tested with the fake `hc` ([test_native.py](../tests/test_native.py), [test_native_events.py](../tests/test_native_events.py)) and every command in [One Core job, start to finish](CORE.md#one-core-job-start-to-finish).
  - Live on a real Herdr Core 0.1.21 on macOS with stand-in programs: the ten-check fleet test ([docs/RUNS.md](RUNS.md#core-native-sandbox-fleet-test-13-nov-2026)). CI's real-Core smoke run covers the native part on Herdr Core 0.1.20, on macOS and Linux.
  - One job with real agents ran on it (a Claude lead with a Codex reviewer and a Claude tester as its Core children). Not run: the fleet test on Linux, and the native path or its front door from a live client.
- **The earlier `--core --relay` path:** tested with the fake `hc` and a fake `herdr`; live on real cores (`hc` 0.1.13 to 0.1.20) with a Claude lead and Claude and Codex workers, every bot route replaced by a local stand-in, and a handed Cursor on Herdr 0.9.5; later runs used stand-in agents.
  - The draft-hold fixture times the send itself, with the same deadline and a check that the owner's draft was not sent; metadata lookups and checks after the send are outside that clock.
  - Not run live: Kimi, the follower's `TURN` for Hermes and Kimi, a signed-in Codex as a Core lead, and the Herdr app looking at a job.
  - Not run live for a handed worker: `STALE`, `BLOCKED`, and a `tell` refused while it works or is focused.
- **Gates:** only the recorded yes opens a merge, a push to the default branch, or any gate on Core; a yes covers the gate as asked (its digest). Tested with the unit suite, the evals and the cross-client suite on every client. One documented ceiling: an agent that detaches to pid 1 as the same user can still run `approve-gate` (eval case G15).
- **Install, updating and plugin installs:** both install routes from a throwaway home (the quick start ran up to the lead's first turn, with no signed-in Claude there), `stampede update` and the daily check (a local reply file, a fake rate-limited server, scratch git repos, and once the live GitHub API), and the plugin lifecycle; the `herdr plugin` commands themselves ran only in a sandboxed test.
  - An install that keeps an existing command path prints a version check and a replacement preview. Checked in temporary homes with a copied command, an older link and a missing link target.
- **Linux:** the install, a whole TUI job and a whole Core job, live on Ubuntu 24.04 arm64 with Herdr 0.9.5, Herdr Core 0.1.19 and stand-in agents; CI runs the unit suite, the relay samples and the evals there ([docs/LINUX.md](LINUX.md)). The systemd timers were checked only against a fake `systemctl`; not run on Linux: a signed-in agent, Moshi paired, a real systemd user manager, or a bot over SSH.
- **The cross-client suite:** every client drives one job per backend through the real `stampede` command against the fakes; live runs on one Mac covered a Herdr chat, Claude, Codex, Hermes and a test bot over SSH (a real Grok Bot and Cursor were not run; Claude on Core, Codex and Hermes passed all but O4, O5 and O7, which wait on the owner's tap). The matrix, and which client does worse: [docs/CLIENTS.md](CLIENTS.md).
- **Posts to a bot:** in a job a bot started, `stampede post` also sends that bot a `post` event; tested with the unit tests and the cross-client suite, not yet with a live bot.
- **The evals:** the fixture cases run in CI on macOS and Linux; the live runners and the before and after runs: [tests/evals/README.md](../tests/evals/README.md).
- **The command:** layered config with `stampede config show` and `stampede config set backend`, `--help` for every command, `stampede doctor` and `stampede check`, and `--json` on every command an agent runs (tested on all three backends, on Python 3.9 too, and on a real scratch core).
- **Model policy:** `lead.allow` and `lead.forbid` check new leads and TUI or Core relay lead restarts. `stampede start` applies optional worker model and effort limits across backends. Queued native workers use the policy in force at launch. On the TUI and both Core paths, reopen checks agents it would relaunch before any restart. Local tests use fake Herdr and Core. Live checks remain open.
- **Models:** Codex leads default to GPT-6.2 Sol. The review, design and QA roles default to GPT-6.2 Astra.
- **Effort:** by default the lead at extra high (`xhigh` on either CLI) and every worker at `medium`, on any model, changed per job, per role or per worker. Tested with the unit suite (the settings, and the start of each role); not yet checked in a live job.
- **The site** is live at https://vib-z.github.io/stampede/ and mirrored on Vercel at https://stampede-xi.vercel.app/.

**Next:**
- On Herdr Core: Cursor, Hermes and Kimi as first-class kinds in a Core job (today they run as programs), then removing the `--core --relay` path.
- On Linux: the systemd user timers on a real user manager, x86_64 live (CI covers it with fakes and a Core smoke run), a signed-in Claude and Codex, Moshi paired, and a bot over SSH.
- A Herdr server restart: `reopen.sh` into the workspace Herdr restores, starting the agents in its plain shells, instead of asking to close it first.
- The open cross-client finding in [docs/CLIENTS.md](CLIENTS.md#doing-worse): a TUI job whose bot is named by `HERDR_EVENTS_OWNER` tagging its workspace.
- On Herdr Core, planned:
  - opt-in alerts to the owner for helpers (blocked, error, stale, dead), as the watchdog sends for the lead today;
  - workers on a second machine (`hc run --on`; a job is local to one machine today);
  - a look at an `--app-space` job in the Herdr app, and a name for its space set through the app;
  - Kimi as a Core agent (Kimi 2.5.3 reports its status on Herdr Core 0.1.20) once a signed-in run shows its turns and its empty prompt;
  - Hermes and Kimi workers on a TUI-only job, and Hermes's empty prompt, so a handed one is briefed and told without a hand.
- Starting workers on the other agents Herdr detects, beyond Claude, Codex, Cursor, Hermes and Kimi.
- Workers on a second machine over Tailscale.
- Cursor as the lead, and a signed-in Codex leading a live Herdr Core job.
- ChatGPT Dots as a front door, once it can be woken by a webhook.
- Report to Herdr that the panes of a reopened workspace sent the plugin no status events in the live Linux runs (needs the owner's yes).
- Report to Herdr that Codex's "Implement this plan?" and Cursor's "Ready to build?" dialogs read as `idle` and `done`, not `blocked` (needs the owner's yes).
