"""install.sh and the Herdr plugin, only in temporary HOME directories with fakes (stdlib)."""
import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('herdr-fleet', 'grokbot-herdr', 'share-plan')


class Install(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        (self.home / '.claude').mkdir()
        self.env = {**os.environ, 'HOME': str(self.home)}

    def run_install(self, *flags):
        return subprocess.run(['bash', str(ROOT / 'install.sh'), *flags], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_links_skills_and_commands_and_is_idempotent(self):
        kept = self.home / '.local/bin/herdr-send'
        kept.parent.mkdir(parents=True)
        kept.write_text('the owner\'s own file')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for skill in SKILLS:
            self.assertEqual((self.home / '.claude/skills' / skill).resolve(), ROOT / 'skills' / skill)
        self.assertFalse((self.home / '.codex').exists())
        self.assertIn('skip ~/.codex/skills: no ~/.codex', result.stdout)
        bin_dir = self.home / '.local/bin'
        self.assertEqual((bin_dir / 'stampede').resolve(), ROOT / 'scripts/stampede')
        self.assertEqual((bin_dir / 'fleet-job').resolve(), ROOT / 'scripts/stampede')
        for name in ('herdr-trust', 'herdr-doctor', 'herdr-event-post', 'herdr-reopen-snapshot'):
            self.assertTrue((bin_dir / name).is_symlink(), name)
        self.assertFalse((bin_dir / 'test-relay.sh').exists())
        self.assertEqual(kept.read_text(), 'the owner\'s own file')
        self.assertIn(f'skip {kept}', result.stdout)
        self.assertIn('herdr-trust <repo dir>', result.stdout)
        again = self.run_install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn('linked', again.stdout)
        self.assertIn(f'ok {bin_dir / "stampede"}', again.stdout)

    def test_a_real_skill_folder_is_left_alone(self):
        own = self.home / '.claude/skills/herdr-fleet'
        own.mkdir(parents=True)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(own.is_symlink())
        self.assertIn(f'skip {own}', result.stdout)

    def test_codex_and_claude_links_survive_reinstall(self):
        (self.home / '.codex').mkdir()
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        links = {self.home / app / 'skills' / skill: ROOT / 'skills' / skill
                 for app in ('.claude', '.codex') for skill in SKILLS}
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        for path, target in links.items():
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), target)
        before = {str(p.relative_to(self.home)): os.readlink(p) if p.is_symlink() else None
                  for p in self.home.rglob('*')}
        self.assertEqual(self.run_install('--dry-run').returncode, 0)
        after = {str(p.relative_to(self.home)): os.readlink(p) if p.is_symlink() else None
                 for p in self.home.rglob('*')}
        self.assertEqual(before, after)

    def test_dry_run_changes_nothing_and_bad_flags_are_usage_errors(self):
        result = self.run_install('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would link', result.stdout)
        self.assertFalse((self.home / '.local').exists())
        self.assertFalse((self.home / '.claude/skills').exists())
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        self.assertEqual(self.run_install('--unknown').returncode, 2)

    def test_manifest_commands_exist(self):
        manifest = tomllib.loads((ROOT / 'herdr-plugin.toml').read_text())
        self.assertEqual(manifest['min_herdr_version'], '0.9.4')
        self.assertEqual(manifest['events'][0]['on'], 'pane.agent_status_changed')
        for kind in ('build', 'events'):
            for entry in manifest[kind]:
                self.assertEqual(entry['command'][0], 'bash')
                self.assertTrue((ROOT / entry['command'][1]).is_file(), entry['command'])

    def test_plugin_event_posts_done_and_idle_after_working_only(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        posted = self.home / 'posted.jsonl'
        (bin_dir / 'herdr-event-post').write_text(f'#!/bin/bash\ncat >> "{posted}"\n')
        (bin_dir / 'herdr').write_text('#!/bin/bash\ncase "$1 $2" in "workspace list") '
                                       'echo \'{"result":{"workspaces":[{"workspace_id":"w1","label":"demo"}]}}\';; esac\n')
        for f in bin_dir.iterdir():
            f.chmod(0o755)
        env = {**self.env, 'PATH': f'{bin_dir}:/usr/bin:/bin:/opt/homebrew/bin'}
        env.pop('HERDR_BIN_PATH', None)
        for status in ('working', 'idle', 'idle', 'done'):
            event = {'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': status, 'agent': 'claude'}}
            subprocess.run(['bash', str(ROOT / 'scripts/herdr-plugin-event')], check=True, timeout=30,
                           env={**env, 'HERDR_PLUGIN_EVENT_JSON': json.dumps(event)})
        sent = [json.loads(line) for line in posted.read_text().splitlines()]
        self.assertEqual([(e['state'], e['previous_state']) for e in sent], [('idle', 'working'), ('done', 'idle')])
        self.assertEqual((sent[0]['pane'], sent[0]['workspace_label'], sent[0]['source']), ('w1:p1', 'demo', 'herdr'))

    def test_plugin_event_without_relay_logs_only_and_never_sends(self):
        self.assertEqual(self.run_install().returncode, 0)
        bin_dir = self.home / '.local/bin'
        (bin_dir / 'herdr').write_text('#!/bin/bash\necho \'{"result":{"workspaces":[]}}\'\n')
        (bin_dir / 'curl').write_text('#!/bin/bash\ntouch "$HOME/network-called"\nexit 1\n')
        for name in ('herdr', 'curl'):
            (bin_dir / name).chmod(0o755)
        env = {k: v for k, v in self.env.items() if not k.startswith('HERDR_')}
        event = {'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': 'done'}}
        env.update(PATH=f'{bin_dir}:/opt/homebrew/bin:/usr/bin:/bin',
                   HERDR_PLUGIN_EVENT_JSON=json.dumps(event), HERDR_EVENTS_MACHINE='fixture')
        result = subprocess.run(['bash', str(ROOT / 'scripts/herdr-plugin-event')],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('logged-only (no route URL)', (self.home / 'Library/Logs/herdr-events.log').read_text())
        self.assertFalse((self.home / 'network-called').exists())
        self.assertFalse((self.home / '.herdr-events/queue').exists())


if __name__ == '__main__':
    unittest.main()
