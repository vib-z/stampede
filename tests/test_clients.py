"""The cross-client suite: stampede driven from every client it claims, with like-for-like outcomes (docs/CLIENTS.md).

CLIENTS is the one list the suite runs over. A front door added to README's table, or a client added here, fails
ClientsInSync until both docs/CLIENTS.md and this table name it. Stdlib only; nothing leaves the machine.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name: README front-door row (None: not a README front door yet), where it runs, the backends it can start
CLIENTS = {
    'herdr-chat': {'readme': 'a chat in Herdr', 'where': 'inside', 'backends': ('tui', 'core')},
    'claude-code': {'readme': 'Claude desktop or the Claude app', 'where': 'outside', 'backends': ('tui', 'core')},
    'codex': {'readme': 'Codex desktop or the ChatGPT app', 'where': 'outside', 'backends': ('tui', 'core')},
    'cursor': {'readme': 'Cursor', 'where': 'outside', 'backends': ('tui', 'core')},
    'hermes': {'readme': None, 'where': 'outside', 'backends': ('tui', 'core')},
    'grokbot': {'readme': 'Grok Bot', 'where': 'ssh', 'backends': ('tui', 'core')},
    'other-bot': {'readme': 'any other bot', 'where': 'ssh', 'backends': ('tui', 'core')},
    'remote-computer': {'readme': 'a whole remote computer', 'where': 'inside', 'backends': ('tui', 'core')},
}
WORKERS = {'tui': ('claude', 'codex', 'cursor'), 'core': ('claude', 'codex')}  # the kinds stampede start takes
OUTCOMES = {
    'O1': 'health', 'O2': 'start', 'O3': 'workers', 'O4': 'question', 'O5': 'gate',
    'O6': 'tell', 'O7': 'finish', 'O8': 'reopen-safe', 'O9': 'no-poll',
}


def table_rows(text, heading):
    """First cells of the first table under a heading, with bold and parentheses removed."""
    section = text.split('\n' + heading + '\n', 1)[1].split('\n## ', 1)[0]
    rows = [line for line in section.splitlines() if line.startswith('|')][2:]
    return [re.sub(r'\*\*|\s*\(.*?\)', '', row.split('|')[1]).strip() for row in rows]


class ClientsInSync(unittest.TestCase):
    def test_every_readme_front_door_is_a_client(self):
        named = {c['readme'] for c in CLIENTS.values()}
        for door in table_rows((ROOT / 'README.md').read_text(), '## Front doors'):
            self.assertIn(door, named, f'README front door {door!r} has no CLIENTS row in tests/test_clients.py')

    def test_every_client_has_a_docs_row(self):
        rows = table_rows((ROOT / 'docs/CLIENTS.md').read_text(), '## Clients')
        self.assertEqual(sorted(r.strip('`') for r in rows), sorted(CLIENTS))

    def test_every_outcome_is_documented(self):
        text = (ROOT / 'docs/CLIENTS.md').read_text()
        for oid, name in OUTCOMES.items():
            self.assertIn(f'**{oid} {name}**', text)


if __name__ == '__main__':
    unittest.main()
