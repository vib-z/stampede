"""grokbot-herdr's herdr-trust in a throwaway HOME: trusts the main checkout's root once, keeps the rest (stdlib)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/grokbot-herdr/scripts/herdr-trust'


class HerdrTrust(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.env = dict(os.environ, HOME=str(self.home))
        self.repo = self.home / 'code/app'
        self.repo.mkdir(parents=True)
        git = ['git', '-C', str(self.repo), '-c', 'user.name=t', '-c', 'user.email=t@t']
        subprocess.run(git + ['init', '-q', '-b', 'main'], check=True)
        subprocess.run(git + ['commit', '-q', '--allow-empty', '-m', 'x'], check=True)
        subprocess.run(git + ['worktree', 'add', '-q', str(self.repo / '.claude/worktrees/w1'), '-b', 'w1'], check=True)
        self.claude = self.home / '.claude.json'
        self.claude.write_text(json.dumps({'numStartups': 3, 'projects': {'/other': {'allowedTools': []}}}))
        self.claude.chmod(0o600)
        self.codex = self.home / '.codex/config.toml'
        self.codex.parent.mkdir()
        self.codex.write_text('model = "gpt-6.1-sol"\n[mcp_servers.x]\nurl = "u"')   # no final newline

    def tearDown(self):
        self.tmp.cleanup()

    def trust(self, d):
        return subprocess.run(['bash', str(SCRIPT), str(d)], env=self.env, capture_output=True, text=True, timeout=30)

    def test_worktree_trusts_main_root_once(self):
        for _ in range(2):
            self.assertEqual(self.trust(self.repo / '.claude/worktrees/w1').returncode, 0)
        s = json.loads(self.claude.read_text())
        self.assertEqual(s['projects'][str(self.repo)], {'hasTrustDialogAccepted': True})
        self.assertEqual((s['numStartups'], s['projects']['/other']), (3, {'allowedTools': []}))
        self.assertEqual(self.claude.stat().st_mode & 0o777, 0o600)
        toml = self.codex.read_text()
        self.assertEqual(toml.count(f'[projects."{self.repo}"]'), 1)
        self.assertIn('url = "u"\n\n[projects.', toml)

    def test_outside_code_or_not_a_repo_is_refused(self):
        other = self.home / 'elsewhere'
        other.mkdir()
        subprocess.run(['git', '-C', str(other), 'init', '-q'], check=True)
        for d in (other, self.home / 'code'):
            self.assertEqual(self.trust(d).returncode, 2)
        self.assertNotIn('hasTrustDialogAccepted', self.claude.read_text())

    def test_no_code_folder_refuses_everything(self):
        # Without ~/code the allowed root must not fall back to "/", which matched any repo.
        bare = self.home / 'bare-home'
        repo = bare / 'elsewhere'
        repo.mkdir(parents=True)
        subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
        (bare / '.claude.json').write_text('{}')
        env = dict(self.env, HOME=str(bare))
        out = subprocess.run(['bash', str(SCRIPT), str(repo)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertNotIn('hasTrustDialogAccepted', (bare / '.claude.json').read_text())


if __name__ == '__main__':
    unittest.main()
