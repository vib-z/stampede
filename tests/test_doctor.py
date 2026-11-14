"""Read-only doctor checks in a temporary HOME, with no live Herdr or launchd access."""
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_platform import fake_loop

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
                        STAMPEDE_NO_UPDATE_CHECK='1', HC_SOCKET=str(self.home / 'no-core.sock'))  # never this machine's own core
        for name in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME'):   # a GitHub Linux runner sets both: the settings file is HOME's
            self.env.pop(name, None)
        subprocess.run(['bash', str(ROOT / 'install.sh')], env=self.env, check=True,
                       capture_output=True, timeout=15)
        self.fake('herdr', '''case "$1 $2" in
  "--version ") echo "herdr ${TEST_CLIENT_VERSION:-0.9.5}";;
  "status ") printf 'client:\n  version: 0.9.5\nserver:\n  status: %s\n  version: %s\n' "${TEST_SERVER_STATE:-running}" "${TEST_SERVER_VERSION:-0.9.5}";;
  "plugin list") if [ "${3:-}" = --json ]; then
      [ -n "${TEST_MANAGED:-}" ] && printf '{"result":{"plugins":[{"plugin_id":"stampede","source":{"managed_path":"%s"}}]}}' "$TEST_MANAGED"
    elif [ "${TEST_PLUGIN:-0}" = 1 ]; then echo '- stampede (stampede) enabled [local:test]'; fi;;
  "workspace list") echo '{"result":{"workspaces":[]}}';;
  *) exit 99;;
esac
exit 0
''')
        self.fake('launchctl', '''echo launchctl >> "$HOME/calls"
[ "${TEST_LAUNCHD:-0}" = 1 ] && printf '%s\n' "- 0 ${TEST_LAUNCHD_PREFIX:-local}.herdr-event-watchdog" "- 0 ${TEST_LAUNCHD_PREFIX:-local}.herdr-events-flush"
exit 0
''')
        self.fake('df', "printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999999 0 %s 0%% /\\n' \"${TEST_DISK_KB:-52428800}\"\n")
        self.fake('systemctl', 'exit 1\n')  # a real user bus must not decide these checks

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
                     'Codex notify line missing', 'no route file', *self.timer_problems()):
            self.assert_problem(result, text)
        self.assertNotIn('event relay not installed', result.stdout)

    def test_each_relay_configuration_signal_enables_full_checks(self):
        signals = [
            ('.config/herdr-events/routes', None),
            ('Library/LaunchAgents/local.herdr-event-watchdog.plist', ''),
            ('Library/LaunchAgents/local.herdr-events-flush.plist', ''),
            ('.claude/settings.json', json.dumps({'hooks': {'Stop': [{'hooks': [
                {'command': 'herdr-event-claude-hook'}]}]}})),
            ('.codex/config.toml', 'notify = ["herdr-event-codex-notify"]\n'),
            ('.codex/config.toml', 'model = "x"\nnotify = [\n  "herdr-event-codex-notify",\n]\n'),  # over several lines
        ]
        for name, content in signals:
            with self.subTest(signal=name, content=content):
                path = self.home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if content is None:
                    path.mkdir()
                else:
                    path.write_text(content)
                result = self.doctor()
                self.assert_problem(result, self.timer_problems()[-1])
                if name == '.codex/config.toml':
                    self.assertIn('ok Codex notify chains herdr-event-codex-notify', result.stdout)
                if content is None:
                    path.rmdir()
                else:
                    path.unlink()

    def configure_relay(self, armed=True):
        hooks = {event: [{'hooks': [{'command': 'herdr-event-claude-hook'}]}]
                 for event in ('Stop', 'StopFailure', 'Notification')}
        (self.home / '.claude/settings.json').write_text(json.dumps({'hooks': hooks}))
        (self.home / '.codex/config.toml').write_text('notify = ["herdr-event-codex-notify"]\n')
        routes = self.home / 'custom-routes'
        routes.mkdir()
        route = routes / 'bot'
        route.write_text('private route content must never print\n')
        route.chmod(0o600)
        env = {'TEST_PLUGIN': '1', 'HERDR_EVENTS_ROUTES_DIR': str(routes)}
        if armed:
            env.update(self.arm_supervisor())
        return env

    def timer_problems(self):
        if platform.system() == 'Darwin':
            return ('launchd local.herdr-event-watchdog not loaded', 'launchd local.herdr-events-flush not loaded')
        return ('event loop not running',)

    def arm_supervisor(self):
        """The timer check passes: launchd on macOS, a live loop in the pid file on Linux (the fake systemctl declines the bus)."""
        if platform.system() == 'Darwin':
            return {'TEST_LAUNCHD': '1'}
        state = self.home / '.local/state/herdr-events'
        state.mkdir(parents=True, exist_ok=True)
        proc = fake_loop(self.home)

        def stop(p=proc):
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=5)
        self.addCleanup(stop)
        (state / 'supervise.pid').write_text(f'{proc.pid}\n')
        return {}

    def test_linux_a_stale_loop_pid_is_not_a_running_loop(self):
        if platform.system() != 'Linux':
            self.skipTest('the flock loop is the Linux fallback')
        env = self.configure_relay(armed=False)
        unrelated = subprocess.Popen(['sleep', '300'])  # the dead loop's pid, now another process's
        self.addCleanup(lambda: (unrelated.kill(), unrelated.wait()))
        state = self.home / '.local/state/herdr-events'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'supervise.pid').write_text(f'{unrelated.pid}\n')
        self.assert_problem(self.doctor(**env), 'event loop not running')

    def test_full_relay_passes_with_custom_routes_and_hides_contents(self):
        result = self.doctor(**self.configure_relay())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok 1 route files', result.stdout)
        self.assertNotIn('private route content', result.stdout + result.stderr)

    def test_a_route_that_is_not_private_is_a_warning(self):
        env = self.configure_relay()
        route = next(Path(env['HERDR_EVENTS_ROUTES_DIR']).iterdir())
        route.chmod(0o644)
        result = self.doctor(**env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f'warn route {route.name} is mode 644: chmod 600', result.stdout)

    def test_linux_systemd_timers_pass_when_systemctl_says_active(self):
        if platform.system() != 'Linux':
            self.skipTest('systemd user timers are the Linux supervisor')
        self.fake('systemctl', '''case "$1 $2" in
  "--user show-environment") exit 0;;
  "--user is-enabled") echo enabled; exit 0;;
  "--user is-active") echo active; exit 0;;
esac
echo disabled; exit 1
''')
        result = self.doctor(**self.configure_relay())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok systemd herdr-event-watchdog.timer active', result.stdout)
        self.assertIn('ok systemd herdr-events-flush.timer active', result.stdout)

    def test_linux_systemd_timers_missing_are_a_problem(self):
        if platform.system() != 'Linux':
            self.skipTest('systemd user timers are the Linux supervisor')
        self.fake('systemctl', '''case "$1 $2" in
  "--user show-environment") exit 0;;
esac
echo disabled; exit 1
''')
        result = self.doctor('--relay')
        self.assert_problem(result, 'systemd herdr-event-watchdog.timer not enabled')
        self.assert_problem(result, 'systemd herdr-events-flush.timer not enabled')

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

    def test_the_launchd_label_prefix_is_a_setting(self):
        if platform.system() != 'Darwin':
            self.skipTest('launchd is the macOS timer')
        plist = self.home / 'Library/LaunchAgents/org.example.herdr-events-flush.plist'   # its plist alone turns the relay checks on
        plist.parent.mkdir(parents=True)
        plist.write_text('')
        self.assertIn('ok event relay not installed', self.doctor().stdout)              # unset: the prefix local, as before
        self.assert_problem(self.doctor(HERDR_EVENTS_LAUNCHD='org.example'), 'launchd org.example.herdr-event-watchdog not loaded')
        env = {**self.configure_relay(), 'TEST_LAUNCHD_PREFIX': 'org.example'}
        self.assert_problem(self.doctor(**env), 'launchd local.herdr-event-watchdog not loaded')
        result = self.doctor(**env, HERDR_EVENTS_LAUNCHD='org.example')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok launchd org.example.herdr-events-flush loaded', result.stdout)

    def test_the_extra_check_runs_last_and_its_problems_count(self):
        extra = self.home / 'doctor-extra'
        extra.write_text('#!/bin/bash\necho "ok my watchdog loaded"\necho "warn my updater is old: update it"\n')
        extra.chmod(0o755)
        plain = self.doctor()
        result = self.doctor(HERDR_DOCTOR_EXTRA=str(extra))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), plain.stdout.splitlines() + ['ok my watchdog loaded', 'warn my updater is old: update it'])
        extra.write_text('#!/bin/bash\necho "PROBLEM route mine missing: restore it"\n')
        self.assert_problem(self.doctor(HERDR_DOCTOR_EXTRA=str(extra)), 'route mine missing: restore it')
        extra.write_text('#!/bin/bash\necho "ok half done"\nexit 4\n')                   # a failing one: one warn, no crash
        result = self.doctor(HERDR_DOCTOR_EXTRA=str(extra))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-2:], ['ok half done', 'warn HERDR_DOCTOR_EXTRA exited 4: run it by hand to see why'])
        marker = self.home / 'ran'
        not_run = [str(self.home / 'nowhere'), 'doctor-extra', str(self.home), f'touch {marker}', f'{extra}; touch {marker}']
        extra.chmod(0o644)
        not_run.append(str(extra))                                                   # not executable
        for value in not_run:
            with self.subTest(value=value):
                result = self.doctor(HERDR_DOCTOR_EXTRA=value)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.splitlines()[-1],
                                 'warn HERDR_DOCTOR_EXTRA is not an absolute path to an executable file: fix it or unset it')
                self.assertFalse(marker.exists())
        extra.chmod(0o755)
        config = self.home / '.config/stampede/config'   # the settings file reaches the doctor with no shell profile line
        config.parent.mkdir(parents=True)
        config.write_text(f'HERDR_DOCTOR_EXTRA={extra}\n')
        self.assertIn('ok half done', self.doctor().stdout)

    def short_doctor(self, extra):
        """The same doctor with its extra check's limit 2 s, run with that check, and how long it took."""
        copy = self.home / 'short/herdr-doctor'
        if not copy.exists():
            copy.parent.mkdir()
            copy.write_text((ROOT / 'skills/grokbot-herdr/scripts/herdr-doctor').read_text().replace('EXTRA_SECS=30', 'EXTRA_SECS=2'))
            copy.chmod(0o755)
            shutil.copy(ROOT / 'skills/grokbot-herdr/scripts/herdr-platform', copy.parent / 'herdr-platform')
        began = time.monotonic()
        result = subprocess.run([str(copy)], env={**self.env, 'HERDR_DOCTOR_EXTRA': str(extra)}, capture_output=True, text=True, timeout=15)
        return result, time.monotonic() - began

    def test_an_extra_check_that_hangs_is_ended_with_its_process_group(self):
        pids = self.home / 'pids'
        extra = self.home / 'doctor-extra'
        extra.write_text(f'#!/bin/bash\necho "ok started"\nsleep 60 &\necho $$ $! > {pids}\nwait\n')
        extra.chmod(0o755)
        result, took = self.short_doctor(extra)
        self.assertLess(took, 10)
        self.assertIn('ok started', result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], 'warn HERDR_DOCTOR_EXTRA did not finish in 2 s, so it and its process group were ended: run it by hand to see why')
        self.assertEqual(result.stdout.count('HERDR_DOCTOR_EXTRA'), 1)
        for pid in pids.read_text().split():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid), 0)

    def test_what_a_hanging_extra_check_said_still_counts(self):
        extra = self.home / 'doctor-extra'
        extra.write_text('#!/bin/bash\necho "PROBLEM my disk is full: clear it"\nexec sleep 60\n')
        extra.chmod(0o755)
        result, _ = self.short_doctor(extra)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-2:], ['PROBLEM my disk is full: clear it',
                         'warn HERDR_DOCTOR_EXTRA did not finish in 2 s, so it and its process group were ended: run it by hand to see why'])

    def test_an_extra_check_whose_escaped_child_holds_the_pipe_cannot_hold_the_doctor(self):
        pid = self.home / 'escaped'
        extra = self.home / 'doctor-extra'
        extra.write_text(f'#!/bin/bash\necho "ok started"\npython3 -c "import os, time; os.setsid(); open(\'{pid}\', \'w\').write(str(os.getpid())); time.sleep(30)" &\nwait\n')
        extra.chmod(0o755)
        self.addCleanup(lambda: pid.exists() and subprocess.run(['kill', pid.read_text()], capture_output=True))
        result, took = self.short_doctor(extra)
        self.assertLess(took, 8)
        self.assertEqual(result.stdout.splitlines()[-2:], ['ok started',
                         'warn HERDR_DOCTOR_EXTRA did not finish in 2 s, so it and its process group were ended: run it by hand to see why'])

    def test_an_extra_checks_control_bytes_never_reach_the_output(self):
        extra = self.home / 'doctor-extra'
        extra.write_text("#!/bin/bash\nprintf '\\033[2J\\033[Hok clean\\b!\\r\\n\\033]0;title\\007ok\\ttab\\n'\n")
        extra.chmod(0o755)
        result = self.doctor(HERDR_DOCTOR_EXTRA=str(extra))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-2:], ['ok clean!', 'ok\ttab'])
        self.assertFalse(set(result.stdout) & {'\x1b', '\b', '\r', '\x07'})

    def test_a_copy_outside_a_checkout_needs_only_a_working_version(self):
        copy = self.home / 'skill-copy/scripts/herdr-doctor'  # no VERSION three folders up
        copy.parent.mkdir(parents=True)
        shutil.copy(ROOT / 'skills/grokbot-herdr/scripts/herdr-doctor', copy)
        shutil.copy(ROOT / 'skills/grokbot-herdr/scripts/herdr-platform', copy.parent / 'herdr-platform')
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

    def test_links_outside_the_managed_plugin_checkout_are_a_problem(self):
        result = self.doctor(TEST_MANAGED=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ok stampede and the skills resolve into the plugin checkout', result.stdout)
        new = self.home / '.config/herdr/plugins/github-installations/stampede-x/2-0/checkout'
        new.mkdir(parents=True)  # Herdr updated the plugin; the links still point at the old checkout
        self.assert_problem(self.doctor(TEST_MANAGED=str(new)),
                            f'~/.local/bin/stampede ~/.claude/skills/stampede ~/.claude/skills/herdr-fleet '
                            f'~/.claude/skills/grokbot-herdr ~/.claude/skills/share-plan ~/.codex/skills/stampede '
                            f'~/.codex/skills/herdr-fleet ~/.codex/skills/grokbot-herdr ~/.codex/skills/share-plan '
                            f'not in the plugin checkout {new}: bash {new}/install.sh relinks')
        self.assertNotIn('plugin checkout', self.doctor().stdout)  # a clone, no managed plugin: no check

    def test_a_missing_trust_root_is_a_warning(self):
        result = self.doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('warn no ~/code (FLEET_TRUST_ROOT): create it or set the key before herdr-trust\n', result.stdout)
        (self.home / 'code').mkdir()
        self.assertIn('ok worktrees under ~/code checked', self.doctor().stdout)

    def test_agent_home_not_installed_is_not_required(self):
        shutil.rmtree(self.home / '.codex')
        self.assertEqual(self.doctor().returncode, 0)

    def test_server_stopped_mismatched_and_low_disk_still_fail(self):
        self.assert_problem(self.doctor(TEST_SERVER_STATE='not running'), 'herdr server not running')
        self.assert_problem(self.doctor(TEST_SERVER_VERSION='0.9.4'), 'herdr client 0.9.5, server 0.9.4')
        self.assert_problem(self.doctor(TEST_DISK_KB='1048576'), '1 GB free')

    def test_a_program_found_off_the_caller_s_path_says_where(self):
        self.assertIn('ok herdr on PATH', self.doctor('--tui').stdout)
        self.assertIn(f'ok herdr (found in {self.bin})', self.doctor('--tui', PATH='/usr/bin:/bin').stdout)

    def test_help_and_usage_do_not_run_health_checks(self):
        for flag in ('--help', '-h'):
            result = self.doctor(flag)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, 'usage: herdr-doctor [--relay] [--tui|--core] [-h|--help]\n')
        for args in (('--unknown',), ('relay',), ('--relay', 'extra')):
            result = self.doctor(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('usage: herdr-doctor', result.stderr)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
