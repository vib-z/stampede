# stampede evals

Behaviour-level checks of what stampede promises: the owner's yes, the lifecycle of a job, portability, dependencies and the backends. The unit tests under `tests/` pin functions; an eval drives the real `stampede` command, or a real Herdr, Herdr Core or Linux install, and records what happened.

## The dataset

[cases.json](cases.json) holds every case: an `id`, an `area`, a `backend`, the `runner` that implements it, a `title` and what must hold (`expect`). A case marked `known_gap` is a documented ceiling: the run records what really happens, and it never counts as a pass.

| backend | what it runs against | runner |
|---|---|---|
| `fixture` | the real `stampede` command with the repo's fake `herdr` and `hc`, in a scratch HOME | [run.py](run.py) |
| `linux-install` | a real Linux container: pinned Herdr, Herdr Core and Moshi installs, `install.sh`, `herdr-doctor` | `linux/run.sh` |
| `tui-live` | a real Herdr TUI server in a scratch home, with stand-in agents | `live/tui_e2e.py` (on a host, through `live/tui_scratch.sh`, which makes the scratch home and its Herdr server) |
| `core-live` | a real Herdr Core in a scratch session (`HC_SESSION` and XDG folders of its own), with stand-in agents | `live/core_e2e.py` |

Stand-in agents are small programs that behave like an agent CLI at the level Herdr and Herdr Core see (a prompt, a status, a turn). No agent is signed in and nothing is spent. A live case proves the backend and stampede work together; it does not prove a real Claude or Codex session does.

## A run

Every runner records through [record.py](record.py): `runs/<UTC time>-<label>/` holds `env.json` (OS, arch, Python, commit, and each tool's version), `results.jsonl` (one line per case: status, expected, actual, the commands and a log tail) and `summary.md` (the counts and a table). Everything written is scrubbed of the home folder, the checkout path, the host name and the user name, so a run can be committed.

Statuses: `pass` and `fail` (the expectation held or did not), `error` (the harness broke), `blocked` (it could not run here, for example no Docker), `skip` (it does not apply here, with the reason) and `gap` (a known ceiling).

```bash
python3 tests/evals/run.py --label baseline-macos          # every fixture case
python3 tests/evals/run.py --label quick --cases G01,G02   # some of them
python3 tests/evals/record.py fixture                      # the environment a run would record
python3 tests/evals/live/core_e2e.py --label core-macos    # the core-live cases, on a real Herdr Core in a scratch session
tests/evals/live/tui_scratch.sh --label tui-macos          # the tui-live cases, on a real Herdr TUI in a scratch home
tests/evals/linux/run.sh --label linux                     # all three live runners in a Linux container (linux/README.md)
```

`run.py` exits 0 when no case failed or broke, else 1. A case that cannot run here is `blocked`, never a pass. The live runners never use the machine's own Herdr server or Herdr Core: `core_e2e.py` names a scratch `HC_SESSION` on every `hc` call and refuses any other, and `tui_scratch.sh` checks that Herdr's socket sits under its scratch home before it starts or stops anything.

## Adding a case

Add it to `cases.json` with a new id in its area's letter (G gate, S side effects, L lifecycle, P portability, D dependencies, V versions, I Linux install, T TUI live, C Core live; a case's backend may differ from its area, as V03, a versions case that needs a real Herdr Core), then implement it in its runner. `tests/test_evals.py` checks that every fixture case has an implementation, and that every runner the dataset names exists and names each case it owns. An eval that can never fail is not an eval: each one must be able to catch the regression it is about.

## Results, 11 Nov 2026: Herdr Core 0.1.20

Before is main's product code (commit dca8ba9, product digest `0a1d6bef90cc`); after is this branch (product digest `07be6e60e6cd`). Both columns used one harness (`1ea870ab3a38`) and one dataset (`c12007c19294`), so a row's before and after differ only in the product files. Each before ran from a throwaway commit, never pushed: this branch's tests with main's product files checked out. That harness is this folder and the test files it names as they stood for the runs; what came after changes only this README and how `live/tui_scratch.sh` stops its stand-in route server when it ends (it used to leave that process running).

| runner | platform | before | after | runs |
|---|---|---|---|---|
| fixture, 60 cases | macOS 27.2 arm64 | 55 pass, 2 fail (D10, D11), 2 blocked, 1 gap | 57 pass, 0 fail, 2 blocked, 1 gap | `20261111T041731Z-before-final-harness-fixture-macos`, `20261111T042202Z-after-fixture-macos` |
| core-live, C01 to C16 and V03 | macOS 27.2 arm64, Herdr Core 0.1.20 | 12 pass, 3 fail (C13, C14, C16), 1 blocked (C15, which needs C16), 1 skip (C12 is Linux only) | 16 pass, 1 skip | `20261111T041945Z-before-final-harness-core-macos`, `20261111T042415Z-after-core-macos` |
| tui-live, T01 to T10 | macOS 27.2 arm64, Herdr 0.9.5 | 10 pass | 10 pass | `20261111T002946Z-before-tui-macos`, `20261111T042719Z-after-tui-macos` |
| linux-install, I01 to I06 | Ubuntu 24.04 arm64 in a container, Herdr 0.9.5, Herdr Core 0.1.20 | not run | 6 pass | `20261111T041723Z-after-0120-linux-install` |
| tui-live, T01 to T10 | the same | not run | 10 pass | `20261111T042024Z-after-0120-linux-tui` |
| core-live, C01 to C16 and V03 | the same | not run | 17 pass | `20261111T042224Z-after-0120-linux-core` |

What the before column says: on main, a draft a person leaves in a worker's terminal is submitted together with a tell (C13: main's `tell` has no time limit, so it waits until Core's hold runs out and Core types the tell after the draft; `SUBMITTED`, exit 0, after 29 s on a core with a 30 s hold), `new --core --lead codex` is refused (C14), `--app-space` does not exist (C16, and so C15 never runs), `herdr-doctor` checks one backend (D10) and `new` does not name Core when the Herdr TUI is down (D11). Of the 62 unit tests in the two test files added with this work (`tests/test_core_releases.py`, `tests/test_hc_contract.py`), 49 fail or break against main's product files (28 failures and 21 errors in that run), the follower's handling of a lost agent under keep among them.

The first runs of this round used main as it was, harness included (`20261111T002330Z-before-fixture-macos`: 55 pass, 2 blocked, 1 gap of 58; `20261111T002538Z-before-core-macos`: 11 pass, 1 skip of 12; the tui-live before above, which needed one harness fix to run from inside a Herdr pane: its outside-Herdr commands now have pid 1 as parent). Nothing in the cases of that time failed on Herdr Core 0.1.20 before any change; C13's left draft is what the new cases found. The recorder also learned to scrub a core's name, which Herdr Core 0.1.20 prints and makes from the machine's name (the first core-live run of this round was scrubbed again with it). Blocked, as before: D01 and D04 on macOS. The gap: G15.

## Results, 8 and 9 Nov 2026

Before is main's product code (0.1.8, commit 04cf523, product digest `8f99b46a668f`); after is this branch (product digest `0a1d6bef90cc`). Every run in the table used one harness (`e6f1f21ee23a`) and one dataset (`f3363bc3ac63`), so the before and after of a row differ only in the product files. That harness is this folder and the test files it names as of commit 9fe8276; the commits after it change only this README. Each before ran from a throwaway commit, never pushed: this branch's tests with main's product files checked out.

| runner | platform | before | after | runs |
|---|---|---|---|---|
| fixture, 58 cases | macOS 27.2 arm64 | 39 pass, 16 fail, 2 blocked, 1 gap | 55 pass, 0 fail, 2 blocked, 1 gap | `20261109T092223Z-baseline-final-harness-macos`, `20261109T091702Z-after-fixture-macos` |
| fixture, 58 cases | Ubuntu 24.04 arm64 | 40 pass, 16 fail, 1 blocked, 1 gap | 56 pass, 0 fail, 1 blocked, 1 gap | `20261109T092448Z-baseline-final-harness-linux`, `20261109T090812Z-after-fixture-linux` |
| linux-install, I01 to I06 | Ubuntu 24.04 arm64 | 5 pass, 1 fail (I04) | 6 pass | `20261108T223920Z-final-before-linux-install`, `20261108T224353Z-final-after-linux-install` |
| tui-live, T01 to T10 | Ubuntu 24.04 arm64, Herdr 0.9.5 | 10 pass | 10 pass | `20261108T224133Z-final-before-linux-tui`, `20261108T224606Z-final-after-linux-tui` |
| core-live, C01 to C12 | Ubuntu 24.04 arm64, Herdr Core 0.1.19 | 11 pass, 1 fail (C08) | 12 pass | `20261108T224302Z-final-before-linux-core`, `20261108T224735Z-final-after-linux-core` |
| core-live, C01 to C12 | macOS 27.2 arm64, Herdr Core 0.1.19 | 10 pass, 1 fail (C08), 1 skip (C12 is Linux only) | 11 pass, 1 skip | `20261108T223535Z-final-before-core-macos`, `20261108T223635Z-final-after-core-macos` |

The failures before: D02, D07, D08, G17, G18, G20, G21, L09, L12, L14, L15, L16, L17, L18, P06 and V02 (fixture, the same 16 on both systems) and C08 (live, on both). I04 fails before by construction: it runs this branch's unit suite, whose new tests fail against main's code. Blocked: D01 and D04 on macOS (Homebrew's herdr and the system jq sit in folders `herdr-doctor` always searches, so their absence cannot be staged), D04 on Linux. The gap: G15, an agent that double-forks to pid 1 with a scrubbed environment can run `approve-gate` (same Unix user; measured: it records a yes).

The first baseline, `20261108T210639Z-baseline-fixture-macos` and `20261108T210823Z-baseline-fixture-linux`, ran the 54 cases and the harness as they stood before any fix (harness `4f85be9f0988`) on the same product: 12 failures on each system (D02, D07, D08, G17, G18, G20, G21, L09, L12, L14, P06, V02). The cases added since came from the live Linux runs (L15, L16) and the cross-model review (L17, L18).

T09 saw no plain turn end from a reopened workspace reach the bot, before or after: Herdr sent the plugin no status event for that workspace's panes in these runs, so T09 guards the relay only when Herdr does. The marker notes of T06 and T07 are the evidence for L15 live: after, `jobs/<new workspace>` and `<job>/workspace` follow each reopen, also after a Herdr server restart; before, they did not.
