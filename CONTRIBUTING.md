# Contributing

Thank you for helping. The short version:

- **Read first:** the README's [Contribute](README.md#contribute) section, then [AGENTS.md](AGENTS.md), the rules every change follows (the README stays true in the same commit, no personal details, no em or en dashes).
- **Run the tests:** `python3 -m unittest discover tests` (Python 3.11 or later). They use fakes and never touch a live Herdr.
- **A front door or a client:** add its row to `CLIENTS` in `tests/test_clients.py` and to [docs/CLIENTS.md](docs/CLIENTS.md), and run `python3 -m unittest tests.test_clients`.
- **A worker kind (an agent CLI):** follow the README's Contribute steps, then add it to `WORKERS` in `tests/test_clients.py` under each backend that takes it, with the refusal `start` gives in `REFUSED` for a backend that does not, and in `HANDED` when a Core job hands it to a Herdr TUI pane (`--pane`); the suite then starts it for every client.
- **Open a pull request** with what changed, why, and how you checked it. Keep it to one change.
- **Report a bug** with an issue: what you ran, what you saw, and `stampede --version`. Security problems go through [SECURITY.md](SECURITY.md), not an issue.
