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

Add it to `cases.json` with a new id in its area's letter (G gate, S side effects, L lifecycle, P portability, D dependencies, V versions, I Linux install, T TUI live, C Core live), then implement it in its runner. `tests/test_evals.py` checks that every fixture case has an implementation and every runner that exists names each case it owns. An eval that can never fail is not an eval: each one must be able to catch the regression it is about.
