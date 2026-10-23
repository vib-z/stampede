"""Read-only doctor checks in a temporary HOME, with no live Herdr or launchd access."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Doctor(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.bin = self.home / '.local/bin'
        for app in ('.claude', '.codex'):
            (self.home / app).mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('HERDR_', 'FLEET_', 'STAMPEDE_'))}
        self.env.update(HOME=str(self.home), PATH=f'{self.bin}:/opt/homebrew/bin:/usr/bin:/bin',
                        STAMPEDE_NO_UPDATE_CHECK='1')
        subprocess.run(['bash', str(ROOT / 'install.sh')], env=self.env, check=True,
                       capture_output=True, timeout=15)
        self.fake('herdr', '''case "$1 $2" in
  "status ") printf 'client:\n  version: 0.9.5\nserver:\n  status: %s\n  version: %s\n' "${TEST_SERVER_STATE:-running}" "${TEST_SERVER_VERSION:-0.9.5}";;
  "plugin list") [ "${TEST_PLUGIN:-0}" = 1 ] && echo '- stampede (stampede) enabled [local:test]';;
  "workspace list") echo '{"result":{"workspaces":[]}}';;
  *) exit 99;;
esac
exit 0
''')
        self.fake('launchctl', '''echo launchctl >> "$HOME/calls"
[ "${TEST_LAUNCHD:-0}" = 1 ] && printf '%s\n' '- 0 local.herdr-event-watchdog' '- 0 local.herdr-events-flush'
exit 0
''')
        self.fake('df', "printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999999 0 %s 0%% /\\n' \"${TEST_DISK_KB:-52428800}\"\n")

    def fake(self, name, body):
        path = self.bin / name
        if path.is_symlink():
            path.unlink()
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o755)

    def doctor(self, *flags, **env):
        return subprocess.run([str(self.bin / 'herdr-doctor'), *flags],
                              env={**self.env, **env}, capture_output=True, text=True, timeout=15)

    def assert_problem(self, result, text):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('PROBLEM ' + text, result.stdout)

    def test_clean_core_is_read_only_and_never_calls_launchctl(self):
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*'))
        result = self.doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok stampede ' + (ROOT / 'VERSION').read_text().strip(), result.stdout)
        self.assertEqual(result.stdout.count('ok event relay not installed (optional)'), 1)
        self.assertIn('warn event plugin not enabled (optional)', result.stdout)
        self.assertNotIn('PROBLEM', result.stdout)
        self.assertEqual(before, sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*')))

    def test_enabled_plugin_alone_does_not_require_the_bot_relay(self):
        result = self.doctor(TEST_PLUGIN='1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok event plugin enabled', result.stdout)
        self.assertIn('event relay not installed (optional)', result.stdout)

    def test_explicit_relay_requires_hooks_plugin_jobs_and_routes(self):
        result = self.doctor('--relay')
        for text in ('event plugin not enabled', 'Claude hook Stop missing',
                     'Codex notify line missing', 'launchd local.herdr-event-watchdog not loaded',
                     'launchd local.herdr-events-flush not loaded', 'no route file'):
            self.assert_problem(result, text)
        self.assertNotIn('event relay not installed', result.stdout)

    def test_each_relay_configuration_signal_enables_full_checks(self):
        signals = {
            '.config/herdr-events/routes': None,
            'Library/LaunchAgents/local.herdr-event-watchdog.plist': '',
            'Library/LaunchAgents/local.herdr-events-flush.plist': '',
            '.claude/settings.json': json.dumps({'hooks': {'Stop': [{'hooks': [
                {'command': 'herdr-event-claude-hook'}]}]}}),
            '.codex/config.toml': 'notify = ["herdr-event-codex-notify"]\n',
        }
        for name, content in signals.items():
            with self.subTest(signal=name):
                path = self.home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if content is None:
                    path.mkdir()
                else:
                    path.write_text(content)
                result = self.doctor()
                self.assert_problem(result, 'launchd local.herdr-events-flush not loaded')
                if content is None:
                    path.rmdir()
                else:
                    path.unlink()

    def configure_relay(self):
        hooks = {event: [{'hooks': [{'command': 'herdr-event-claude-hook'}]}]
                 for event in ('Stop', 'StopFailure', 'Notification')}
        (self.home / '.claude/settings.json').write_text(json.dumps({'hooks': hooks}))
        (self.home / '.codex/config.toml').write_text('notify = ["herdr-event-codex-notify"]\n')
        routes = self.home / 'custom-routes'
        routes.mkdir()
        route = routes / 'bot'
        route.write_text('private route content must never print\n')
        route.chmod(0o600)
        return {'TEST_PLUGIN': '1', 'TEST_LAUNCHD': '1', 'HERDR_EVENTS_ROUTES_DIR': str(routes)}

    def test_full_relay_passes_with_custom_routes_and_hides_contents(self):
        result = self.doctor(**self.configure_relay())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok 1 route files', result.stdout)
        self.assertNotIn('private route content', result.stdout + result.stderr)

    def test_stale_queue_remains_a_problem(self):
        env = self.configure_relay()
        queue = self.home / 'custom-events/queue'
        queue.mkdir(parents=True)
        event = queue / 'old.json'
        event.write_text('{}')
        os.utime(event, (time.time() - 1200, time.time() - 1200))
        self.assert_problem(self.doctor(**env, HERDR_EVENTS_HOME=str(queue.parent)), 'queue holds 1 events, 1 older')

    def test_missing_relay_script_remains_a_problem(self):
        (self.bin / 'herdr-event-flush').unlink()
        self.assert_problem(self.doctor('--relay'), 'herdr-event-flush not installed')

    def test_missing_or_wrong_stampede_version_is_a_problem(self):
        self.fake('stampede', 'echo wrong-version\n')
        self.assert_problem(self.doctor(), 'stampede --version does not match VERSION')
        self.fake('stampede', f'echo "{(ROOT / "VERSION").read_text().strip()}"\nexit 1\n')
        self.assert_problem(self.doctor(), 'stampede --version does not match VERSION')
        (self.bin / 'stampede').unlink()
        self.assert_problem(self.doctor(), 'stampede not on PATH')

    def test_a_copy_outside_a_checkout_needs_only_a_working_version(self):
        copy = self.home / 'skill-copy/scripts/herdr-doctor'  # no VERSION three folders up
        copy.parent.mkdir(parents=True)
        shutil.copy(ROOT / 'skills/grokbot-herdr/scripts/herdr-doctor', copy)
        self.fake('stampede', 'echo 9.9.9\n')
        result = subprocess.run([str(copy)], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok stampede 9.9.9', result.stdout)

    def test_missing_broken_or_unlinked_skill_is_a_problem(self):
        path = self.home / '.codex/skills/herdr-fleet'
        path.unlink()
        self.assert_problem(self.doctor(), '~/.codex/skills/herdr-fleet not linked')
        path.symlink_to(self.home / 'missing')
        self.assert_problem(self.doctor(), '~/.codex/skills/herdr-fleet not linked')
        path.unlink()
        path.mkdir()
        (path / 'SKILL.md').write_text('a local copy')
        self.assert_problem(self.doctor(), '~/.codex/skills/herdr-fleet not linked')

    def test_agent_home_not_installed_is_not_required(self):
        shutil.rmtree(self.home / '.codex')
        self.assertEqual(self.doctor().returncode, 0)

    def test_server_stopped_mismatched_and_low_disk_still_fail(self):
        self.assert_problem(self.doctor(TEST_SERVER_STATE='not running'), 'herdr server not running')
        self.assert_problem(self.doctor(TEST_SERVER_VERSION='0.9.4'), 'herdr client 0.9.5, server 0.9.4')
        self.assert_problem(self.doctor(TEST_DISK_KB='1048576'), '1 GB free')

    def test_help_and_usage_do_not_run_health_checks(self):
        for flag in ('--help', '-h'):
            result = self.doctor(flag)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, 'usage: herdr-doctor [--relay] [-h|--help]\n')
        for args in (('--unknown',), ('relay',), ('--relay', 'extra')):
            result = self.doctor(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('usage: herdr-doctor', result.stderr)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
