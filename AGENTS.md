# Rules for agents working on stampede

To run a job with stampede, read [USING.md](USING.md); the rules below are for changing this repo.

These rules apply to every agent that edits this repo: Claude, Codex, Cursor, Hermes, Grok Bot or any other.

The current contract is the [README](README.md), the pages under `docs/` it links, and [docs/CORE-NATIVE.md](docs/CORE-NATIVE.md). The original design, kept as history, is [docs/superpowers/specs/2026-10-21-stampede-lean-design.md](docs/superpowers/specs/2026-10-21-stampede-lean-design.md).

## 1. The README is a short front page, and the pages under `docs/` hold the rest. Keep both current at every step

- **The README:** at most 100 lines (`test_shape.py`), in plain words a reader with no coding background can follow: short sentences, everyday words, each term explained in half a sentence or behind a link, no sales words. It has seven parts, in this order, and nothing else:
  1. The name, one sentence that says what it is, the version badge and at most two more, and at most one picture with its caption.
  2. What it is, in three to five sentences.
  3. What you need, with versions.
  4. Install: the quick start, ending with the `stampede --version` line and `stampede doctor`.
  5. Your first job, step by step.
  6. How it keeps you safe, in a few lines, linking to [docs/SAFETY.md](docs/SAFETY.md).
  7. Read more: one list of links to the pages under `docs/`, the changelog, contributing and the license.
- **Same commit:** any change to behaviour, commands, scripts, skills, front doors, the layout or the status updates, in that commit, every page under `docs/` and `remote/` that describes it, and README.md when one of its seven parts changes.
- **Incomplete otherwise:** a change without its docs update is not done.
- **True today:**
  - Every claim, command and number in the README and the docs is true of the current code.
  - Every command in them was run, against a scratch job folder with a fake Herdr when it would otherwise touch real panes.
  - Anything not built yet goes under the roadmap in [docs/STATUS.md](docs/STATUS.md), marked as planned.
- **Roadmap and status:** update [docs/STATUS.md](docs/STATUS.md) at every milestone: what works, what was tested, what is next.
- **The cross-client suite:** any change to behaviour, a front door, a client or a worker kind updates, in that same commit, the suite (`tests/test_clients.py`, `tests/clients_run.py`) and [docs/CLIENTS.md](docs/CLIENTS.md) (its matrix, what differs, and the live runbook). A front door or a client is a row in `CLIENTS` and in that doc; a worker kind is an entry in `WORKERS` under each backend that takes it, with its refusal in `REFUSED` for one that does not, and in `HANDED` when a Core job hands it to a Herdr TUI pane. A client that does worse gets a finding there and a test marked as an expected failure.
- **Standard:** short, true and complete. A stranger can understand, install, use, configure, troubleshoot and extend stampede from the README and its docs alone, with no questions to anyone.

### What the README and docs must cover
Shape the pages under `docs/` to fit the content; no template is fixed there. Together, the README, `docs/`, `remote/` and the skills answer all of these, each in one place:
- **What and why:** what stampede is, the problem it solves, and who it is for.
- **See it:** real screenshots of a run, with captions.
- **How it works:** the flow from ask to report and reopen, the roles (owner, front door, lead, workers, reviewer), and what lives where.
- **Every option:**
  - Every front door: a Herdr chat, Claude, Codex or Cursor, Grok Bot (preferred bot), Moshi with any of them, or others.
  - Every agent CLI the lead can start: Claude, Codex, Cursor.
  - The backend: the Herdr TUI is the default; Herdr Core runs a job only when the user asks, with `--core` or the setting `backend`, and no page says Core is picked for anyone.
- **Install:**
  - Prerequisites, with versions.
  - A copy-paste quick start.
  - A full setup, and the setup per front door.
- **Use:** a walkthrough of one job, start to finish, with the actual commands and their output.
- **Configure:** every key in [config.example](config.example), with its default.
- **Safety:** every gate that needs the owner's yes, what never happens without asking, and how to reopen.
- **Troubleshoot:** known failures with their fixes, and an FAQ.
- **Reference:** every script, its flags and its exit codes. Also the repo layout.
- **Contribute:** how to add a front door or an agent CLI, and how to run the tests.
- **Roadmap, status and license.**

The README covers what stampede is, what you need, the install, a first job and safety in short. For the rest it links to the page that holds it, and [docs/REFERENCE.md](docs/REFERENCE.md#docs) lists every doc.

### Imagery and video
- **Images** go in `docs/images/`, 1800 px wide.
  - Each is either a real screenshot or rendered from an HTML source in `docs/images/src/`, using `system.css` and `render.sh`, so it can be re-rendered.
  - Each has alt text that says what it shows.
  - Each caption says what is real, what is a mock-up, and the date.
  - Keep only images a doc uses.
  - Product marks go in `docs/images/logos/` as the owner's own SVG, each credited in its `SOURCES.md`.
- **Screenshots:** take them from real runs. Crop out personal details first.
- **Video:** the film assets stay as they are for now. The owner decides when to re-cut them, after significant progress.
  - The poster and the teaser go in `assets/`.
  - The master goes in a GitHub release, never in git.

### Before each commit that touches the README or docs
- `python3 -m unittest discover tests` passes. This includes `test_shape.py`: links, anchors, line limits, frontmatter, no em or en dashes, and no personal details (home paths, private paths, private names), in `docs/superpowers` too.
- Render the README, and each page the commit changed, the way GitHub does (`gh api markdown -F text=@README.md`) and look at it. Fix overflow, stacked badges and broken images.

## 2. The skills and the playbooks
- **Where they live:** the playbooks are `skills/` (the four skills) and `remote/` (the front-door guides).
- **This repo is the one source.** `skills/stampede`, `skills/herdr-fleet`, `skills/grokbot-herdr` and `skills/share-plan` are changed here first, and every machine runs their code from a checkout through `install.sh` (`--replace` takes over an older install). What one owner wants and others do not is a setting with a default in [config.example](config.example), never a private edit; that owner's values live in their own config.
- **One context per agent:** every skill, guide and brief stands on its own. An agent gets only its own file plus its brief, never the whole repo.
- **Line limits:** a skill's `SKILL.md` at most 140 lines, every other playbook file at most 160 (`test_shape.py`).
- **Credit:** a linked role or skill from someone else names its owner, its license and a pinned commit.
- **No history or reasoning** in playbooks. Git keeps it.
- **One place per rule:** each rule lives in one file. Others link to it.

## 3. Open source hygiene
- **Nothing personal or secret:**
  - No secrets, `.env` files, keys or tokens.
  - No personal paths, names, hostnames, owner tags or private repo or skill names.
  - The three skills herdr-fleet, grokbot-herdr and share-plan may be named (the owner's call, 21 Oct 2026).
- **Machine-specific settings** are environment variables listed in [config.example](config.example). Each has a default.
- **Scan before every push** for keys and personal details.
- **The repo is private until the owner says yes** to making it public.

## 4. Git
- Work on a branch and open a draft PR. Merging to main is the owner's call.
- Commit only your own change. Never commit caches, scratch files or media over 10 MB.
- Do not touch the owner's private skills repo from here; it is changed only in its own checkout, by the owner's own jobs.
