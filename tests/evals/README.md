# stampede evals

Behaviour-level checks of what stampede promises: the owner's yes, the lifecycle of a job, portability, dependencies and the backends. The unit tests under `tests/` pin functions; an eval drives the real `stampede` command, or a real Herdr, Herdr Core or Linux install, and records what happened.

## The dataset

[cases.json](cases.json) holds every case: an `id`, an `area`, a `backend`, the `runner` that implements it, a `title` and what must hold (`expect`). A case marked `known_gap` is a documented ceiling: the run records what really happens, and it never counts as a pass.

| backend | what it runs against | runner |
|---|---|---|
| `fixture` | the real `stampede` command with the repo's fake `herdr` and `hc`, in a scratch HOME | [run.py](run.py) |
| `linux-install` | a real Linux container: pinned Herdr, Herdr Core and Moshi installs, `install.sh`, `herdr-doctor` | `linux/run.sh` |
| `tui-live` | a real Herdr TUI server in a scratch home, with stand-in agents | `live/tui_e2e.py` |
| `core-live` | a real Herdr Core in a scratch session (`HC_SESSION` and XDG folders of its own), with stand-in agents | `live/core_e2e.py` |

Stand-in agents are small programs that behave like an agent CLI at the level Herdr and Herdr Core see (a prompt, a status, a turn). No agent is signed in and nothing is spent. A live case proves the backend and stampede work together; it does not prove a real Claude or Codex session does.

## A run

Every runner records through [record.py](record.py): `runs/<UTC time>-<label>/` holds `env.json` (OS, arch, Python, commit, and each tool's version), `results.jsonl` (one line per case: status, expected, actual, the commands and a log tail) and `summary.md` (the counts and a table). Everything written is scrubbed of the home folder, the checkout path, the host name and the user name, so a run can be committed.

Statuses: `pass` and `fail` (the expectation held or did not), `error` (the harness broke), `blocked` (it could not run here, for example no Docker), `skip` (it does not apply here, with the reason) and `gap` (a known ceiling).

```bash
python3 tests/evals/run.py --label baseline-macos          # every fixture case
python3 tests/evals/run.py --label quick --cases G01,G02   # some of them
python3 tests/evals/record.py fixture                      # the environment a run would record
```

`run.py` exits 0 when no case failed or broke, else 1. A case that cannot run here is `blocked`, never a pass.

## Adding a case

Add it to `cases.json` with a new id in its area's letter (G gate, S side effects, L lifecycle, P portability, D dependencies, V versions, I Linux install, T TUI live, C Core live), then implement it in its runner. `tests/test_evals.py` checks that every fixture case has an implementation, and that every runner the dataset names exists and names each case it owns. An eval that can never fail is not an eval: each one must be able to catch the regression it is about.

## Results, 8 Nov 2026

Before is main's product code (0.1.8, product digest `8f99b46a668f`); after is this branch's fixes (product digest `b60c22104803`). Each row compares the same harness and dataset before and after. The fixture rows' "before" are the `baseline-final-harness` runs, the final runner on main's product code checked out into a throwaway commit; the first baseline, `baseline-fixture-*`, ran the harness as it stood before any fix and found the same 12 failures (L15 and L16 came later, from the live Linux runs).

| runner | platform | before | after |
|---|---|---|---|
| fixture, 56 cases | macOS 27.2 arm64 | 39 pass, 14 fail, 2 blocked, 1 gap | 53 pass, 0 fail, 2 blocked, 1 gap |
| fixture, 56 cases | Ubuntu 24.04 arm64 | 40 pass, 14 fail, 1 blocked, 1 gap | 54 pass, 0 fail, 1 blocked, 1 gap |
| linux-install, I01 to I06 | Ubuntu 24.04 arm64 | 6 pass | 6 pass |
| tui-live, T01 to T10 | Ubuntu 24.04 arm64, Herdr 0.9.5 | 10 pass | 10 pass |
| core-live, C01 to C12 | Ubuntu 24.04 arm64, Herdr Core 0.1.19 | 11 pass, 1 fail (C08) | 12 pass |
| core-live, C01 to C12 | macOS 27.2 arm64, Herdr Core 0.1.19 | 10 pass, 1 fail (C08), 1 skip (C12 is Linux only) | 11 pass, 1 skip |

The failures before: D02, D07, D08, G17, G18, G20, G21, L09, L12, L14, L15, L16, P06, V02 (fixture) and C08 (live). Blocked: D01 and D04 on macOS (Homebrew's herdr and the system jq sit in folders `herdr-doctor` always searches, so their absence cannot be staged), D04 on Linux. The gap: G15, an agent that double-forks to pid 1 with a scrubbed environment can run `approve-gate` (same Unix user; measured: it records a yes). The live runners also recorded two findings no case had caught yet; they are now L15 and L16.
