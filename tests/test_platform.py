"""Portable file facts and the relay scripts that use them, on this host's stat (GNU or BSD)."""
import hashlib
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / 'skills/grokbot-herdr/scripts/herdr-platform'
FLUSH = ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush'
WATCH = ROOT / 'skills/herdr-fleet/scripts/fleet-watch.sh'


def bash(script, *args, env=None):
    return subprocess.run(['bash', '-c', script, 'bash', *args], env=env, capture_output=True, text=True, timeout=20)


def fake_loop(home):
    """A live process that runs a script named herdr-event-supervise, as the real loop does. The caller kills it."""
    script = Path(home) / 'fake-loop/herdr-event-supervise'
    script.parent.mkdir(exist_ok=True)
    script.write_text('#!/bin/bash\nsleep 300\n')
    script.chmod(0o755)
    loop = subprocess.Popen([str(script)], start_new_session=True)
    for _ in range(50):  # until the kernel shows it running the script
        if Path(f'/proc/{loop.pid}/cmdline').read_bytes().endswith(b'/herdr-event-supervise\0'):
            return loop
        time.sleep(0.02)
    return loop


class Platform(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.env = {k: v for k, v in os.environ.items() if k != 'XDG_STATE_HOME'}
        self.env.update(HOME=str(self.home), PATH='/usr/bin:/bin')

    def fact(self, fn, path):
        result = bash(f'. "{PLATFORM}"\n{fn} "$1"\n', str(path), env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_size_mtime_and_mode_describe_the_file(self):
        path = self.home / 'n'
        path.write_text('abc')
        os.chmod(path, 0o640)
        old = time.time() - 50
        os.utime(path, (old, old))
        self.assertEqual(self.fact('file_bytes', path), '3')
        self.assertEqual(self.fact('file_mode', path), '640')
        self.assertAlmostEqual(int(self.fact('file_mtime', path)), int(old), delta=2)
        # GNU stat -f would report the filesystem here and still exit 0. The helper must not.
        gnu = subprocess.run(['stat', '-f', '%z', str(path)], capture_output=True, text=True)
        if gnu.returncode == 0 and gnu.stdout.strip() != '3':
            self.assertNotEqual(self.fact('file_bytes', path), gnu.stdout.strip())

    def hold(self, lock):
        """A process that holds herdr-platform's lock on <lock> until killed."""
        holder = subprocess.Popen(['bash', '-c', f'exec 9>"$1"; . "{PLATFORM}"; hold_lock 9; echo held; exec sleep 60', 'bash', str(lock)],
                                  env=self.env, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (holder.kill(), holder.wait(), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), 'held')
        return holder

    def test_the_de_dupe_lock_is_exclusive(self):
        """Two posts never rewrite dedupe.tsv at once: a second taker is refused while the first holds the lock."""
        lock = self.home / 'dedupe.lock'
        self.hold(lock)
        if Path('/usr/bin/lockf').exists():
            second = subprocess.run(['/usr/bin/lockf', '-t', '0', str(lock), 'true'], capture_output=True)
        else:
            second = subprocess.run(['flock', '-n', '-E', '75', str(lock), 'true'], capture_output=True)
        self.assertEqual(second.returncode, 75)

    def test_the_event_loop_runs_only_when_its_pid_file_names_it(self):
        if not Path('/proc/self/cmdline').exists():
            self.skipTest('the flock loop is the Linux fallback')
        state = self.home / '.local/state/herdr-events'
        state.mkdir(parents=True)
        running = lambda: bash(f'. "{PLATFORM}"\nevent_loop_running\n', env=self.env).returncode == 0
        self.assertFalse(running(), 'no pid file: no loop')
        unrelated = subprocess.Popen(['sleep', '60'])
        self.addCleanup(lambda: (unrelated.kill(), unrelated.wait()))
        (state / 'supervise.pid').write_text(f'{unrelated.pid}\n')
        self.assertFalse(running(), 'a live pid in a stale pid file is not the loop')
        # checks at the same time never count each other as the loop (review-codex round 2)
        many = bash(f'. "{PLATFORM}"\nfor i in 1 2 3 4 5 6; do (for j in 1 2 3 4 5 6 7 8 9 10; do '
                    'event_loop_running && echo RUNNING; done) & done; wait\n', env=self.env)
        self.assertNotIn('RUNNING', many.stdout)
        loop = fake_loop(self.home)
        self.addCleanup(lambda: (os.killpg(loop.pid, signal.SIGKILL), loop.wait()))
        (state / 'supervise.pid').write_text(f'{loop.pid}\n')
        self.assertTrue(running())

    def test_hash_stdin_matches_md5(self):
        result = bash(f'. "{PLATFORM}"\nprintf abc | hash_stdin\n', env=self.env)
        self.assertEqual(result.stdout.strip(), hashlib.md5(b'abc').hexdigest())

    def test_flush_rotates_a_large_log_breaks_a_stale_lock_and_expires_old_events(self):
        home = self.home / 'q'
        queue = home / 'queue'
        queue.mkdir(parents=True)
        log = home / 'flush.log'
        log.write_bytes(b'x' * (1048576 + 8))
        env = {**self.env, 'HERDR_EVENTS_HOME': str(home)}
        fresh = queue / 'fresh.json'
        fresh.write_text('{"route":"default","payload":{"source":"x","state":"done"}}\n')
        lock = home / 'flush.lock'
        lock.mkdir()
        os.utime(lock, (time.time() - 10, time.time() - 10))  # younger than 5 min: the queue stays
        held = subprocess.run(['bash', str(FLUSH)], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(held.returncode, 0, held.stderr)
        self.assertTrue(fresh.is_file(), 'a lock younger than 5 min keeps the queue')
        self.assertEqual(log.stat().st_size, 0)
        os.utime(lock, (time.time() - 400, time.time() - 400))
        stale = subprocess.run(['bash', str(FLUSH)], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(stale.returncode, 0, stale.stderr)
        self.assertFalse(fresh.exists())
        self.assertFalse(lock.exists())
        self.assertIn('dropped', log.read_text())
        old = queue / 'aged.json'
        old.write_text('{"route":"default","payload":{"source":"x","state":"done"}}\n')
        os.utime(old, (time.time() - 90000, time.time() - 90000))
        aged = subprocess.run(['bash', str(FLUSH)], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(aged.returncode, 0, aged.stderr)
        self.assertTrue((home / 'dead/aged.json').is_file())
        self.assertFalse(old.exists())

    def test_fleet_watch_stall_uses_mtime(self):
        home = self.home
        reports = home / 'reports'
        reports.mkdir()
        sid = 'abc123'
        log = home / '.claude/projects/demo' / f'{sid}.jsonl'
        log.parent.mkdir(parents=True)
        log.write_text('{}\n')
        herdr = home / 'bin/herdr'
        herdr.parent.mkdir()
        herdr.write_text(
            '#!/bin/bash\necho \'{"result":{"agents":[{"name":"build","agent_status":"working",'
            '"agent_session":{"value":"abc123"},"workspace_id":"w1"}]}}\'\n')
        herdr.chmod(0o755)
        env = {**self.env, 'HOME': str(home), 'PATH': f'{herdr.parent}:/usr/bin:/bin',
               'FLEET_WATCH_PASSES': '1', 'FLEET_WATCH_INTERVAL': '0', 'FLEET_WATCH_NOTIFY': '0'}

        def once():
            return subprocess.run(['bash', str(WATCH), str(reports), 'w1', '15'],
                                  env=env, capture_output=True, text=True, timeout=15)

        fresh = once()
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertNotIn('STALL?', fresh.stdout)
        os.utime(log, (time.time() - 3600, time.time() - 3600))
        stalled = once()
        self.assertEqual(stalled.returncode, 0, stalled.stderr)
        self.assertIn('STALL? build log idle', stalled.stdout)


if __name__ == '__main__':
    unittest.main()
