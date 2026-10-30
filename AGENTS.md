# Rules for agents working on stampede

These rules apply to every agent that edits this repo: Claude, Codex, Cursor, Hermes, Grok Bot or any other. The rules for *running* a job with stampede are not here: they live in [SKILL.md](SKILL.md) and the skills it names.

The design is in [docs/superpowers/specs/2026-10-21-stampede-lean-design.md](docs/superpowers/specs/2026-10-21-stampede-lean-design.md). Read it before your first change.

## 1. The README is the product's front page. Keep it current at every step

- **Same commit:** any change to behaviour, commands, scripts, skills, front doors, the layout or the status updates README.md in that commit. It also updates every doc under `docs/` and `remote/` that the change affects.
- **Incomplete otherwise:** a change without its README update is not done.
- **True today:**
  - Every claim, command and number in the README is true of the current code.
  - Every command in it was run, against a scratch job folder with a fake Herdr when it would otherwise touch real panes.
  - Anything not built yet goes under the roadmap, marked as planned.
- **Roadmap and status:** update them at every milestone: what works, what was tested, what is next.
- **The cross-client suite:** any change to behaviour, a front door, a client or a worker kind updates, in that same commit, `CLIENTS` (and `WORKERS`) in `tests/test_clients.py`, the suite in `tests/clients_run.py`, and [docs/CLIENTS.md](docs/CLIENTS.md) (its matrix, what differs, and the live runbook). A client that does worse gets a finding there and a test marked as an expected failure.
- **Standard:** short, true and complete. A stranger can understand, install, use, configure, troubleshoot and extend stampede from the README and its docs alone, with no questions to anyone.

### What the README and docs must cover
Shape the sections to fit the content; no template is fixed. Together, the README, `docs/`, `remote/` and the skills answer all of these:
- **What and why:** what stampede is, the problem it solves, and who it is for.
- **See it:** real screenshots of a run, with captions.
- **How it works:** the flow from ask to report and reopen, the roles (owner, front door, lead, workers, reviewer), and what lives where.
- **Every option:**
  - Every front door: a Herdr chat, Claude, Codex or Cursor, Grok Bot (preferred bot), Moshi with any of them, or others.
  - Every agent CLI the lead can start: Claude, Codex, Cursor.
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

The README is the front door. It covers every point at least briefly, then links to the doc with the depth.

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
- Render the README the way GitHub does (`gh api markdown -F text=@README.md`) and look at it. Fix overflow, stacked badges and broken images.

## 2. The skills and the playbooks
- **Where they live:** the playbooks are `skills/` (the four skills) and `remote/` (the front-door guides).
- **The four skills are copies.** `skills/stampede`, `skills/herdr-fleet`, `skills/grokbot-herdr` and `skills/share-plan` come from the owner's own skills, which are their source. Change a skill there first, then copy it here and scrub it (section 3); never edit it here first. Only what makes the copy public (a scrubbed name or path, a setting with a default) differs from the source.
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
