"""The update check and stampede update, with a local reply file or fake server and scratch git repos; no network."""
import http.server, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import stampede_update as su

VERSION = (ROOT / 'VERSION').read_text().strip()
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}


class RateLimited(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(403)
        self.end_headers()
        self.wfile.write(b'{"message": "API rate limit exceeded"}')

    def log_message(self, *args):
        pass


class Check(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.reply = self.dir / 'reply.json'
        self.cache = self.dir / 'cache/stampede/latest-release'
        self.env = {**os.environ, 'XDG_CACHE_HOME': str(self.dir / 'cache'), 'STAMPEDE_UPDATE_URL': self.reply.as_uri()}
        self.env.pop('STAMPEDE_NO_UPDATE_CHECK', None)

    def release(self, tag):
        self.reply.write_text('{"tag_name": "%s", "name": "stampede"}' % tag)

    def run_stampede(self, *args, **env):
        return subprocess.run([str(ROOT / 'scripts/stampede'), *args], env={**self.env, **env},
                              capture_output=True, text=True, timeout=30)

    def test_versions_compare_as_numbers(self):
        self.assertGreater(su.parse('0.10.0'), su.parse('v0.9.0'))
        self.assertEqual(su.parse('v1.2.3'), (1, 2, 3))
        for bad in ('1.2', 'nightly', 'v1.2.3-rc1', ''):
            self.assertIsNone(su.parse(bad), bad)

    def test_behind_warns_on_stderr_and_the_version_stays_first(self):
        self.release('v99.0.0')
        out = self.run_stampede('--version')
        self.assertEqual((out.returncode, out.stdout), (0, VERSION + '\n'))
        self.assertEqual(out.stderr, f'stampede 99.0.0 is out, this is {VERSION}: run stampede update\n')
        out = self.run_stampede('update', '--check')
        self.assertEqual((out.returncode, out.stdout), (1, f'stampede 99.0.0 is out, this is {VERSION}: run stampede update\n'))

    def test_the_same_or_an_older_release_is_not_behind(self):
        for tag in ('v' + VERSION, '0.0.1'):
            self.cache.unlink(missing_ok=True)
            self.release(tag)
            out = self.run_stampede('--version')
            self.assertEqual((out.returncode, out.stdout, out.stderr), (0, VERSION + '\n', ''), tag)
            out = self.run_stampede('update', '--check')
            self.assertEqual(out.returncode, 0, tag)
            self.assertIn('the latest release is ' + tag.lstrip('v'), out.stdout)

    def test_offline_rate_limited_or_malformed_is_silent(self):
        server = http.server.HTTPServer(('127.0.0.1', 0), RateLimited)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        cases = {'offline': (self.dir / 'missing.json').as_uri(), 'rate limited': f'http://127.0.0.1:{server.server_port}/'}
        for name, body in (('not json', 'Bad gateway'), ('no tag', '{"message": "Not Found"}'), ('a list', '[]'),
                           ('not X.Y.Z', '{"tag_name": "nightly"}')):
            (self.dir / name).write_text(body)
            cases[name] = (self.dir / name).as_uri()
        for name, url in cases.items():
            self.cache.unlink(missing_ok=True)
            for args, code in ((['--version'], 0), (['update', '--check'], 0)):
                out = self.run_stampede(*args, STAMPEDE_UPDATE_URL=url)
                self.assertEqual((out.returncode, out.stderr), (code, ''), (name, args))
                self.assertEqual(out.stdout, VERSION + '\n' if args == ['--version'] else '', (name, args))
            self.assertTrue(self.cache.exists(), name)  # the failure is cached too: no retry for a day

    def test_the_cache_answers_for_24_hours(self):
        self.release('v99.0.0')
        self.assertEqual(self.run_stampede('update', '--check').returncode, 1)
        self.release('v' + VERSION)  # a newer reply is not read while the cache is fresh
        self.assertEqual(self.run_stampede('update', '--check').returncode, 1)
        day_ago = time.time() - 24 * 3600 - 60
        os.utime(self.cache, (day_ago, day_ago))
        self.assertEqual(self.run_stampede('update', '--check').returncode, 0)
        self.assertEqual(self.cache.read_text().strip(), 'v' + VERSION)

    def test_the_opt_out_checks_nothing(self):
        self.release('v99.0.0')
        for args in (['--version'], ['update', '--check']):
            out = self.run_stampede(*args, STAMPEDE_NO_UPDATE_CHECK='1')
            self.assertEqual((out.returncode, out.stderr), (0, ''))
            self.assertNotIn('99.0.0', out.stdout)
        self.assertFalse(self.cache.exists())

    def test_herdr_doctor_warns_never_a_problem(self):
        home = self.dir / 'home'
        (home / '.local/bin').mkdir(parents=True)
        (home / '.local/bin/stampede').symlink_to(ROOT / 'scripts/stampede')
        (home / '.local/bin/herdr').write_text('#!/bin/bash\necho {}\n')  # never the real Herdr
        (home / '.local/bin/herdr').chmod(0o755)
        self.release('v99.0.0')
        out = subprocess.run([str(ROOT / 'skills/grokbot-herdr/scripts/herdr-doctor')], capture_output=True, text=True,
                             timeout=60, env={**self.env, 'HOME': str(home), 'FLEET_TRUST_ROOT': str(home)})
        self.assertIn(f'warn stampede 99.0.0 is out, this is {VERSION}: run stampede update\n', out.stdout)
        self.assertNotIn('PROBLEM stampede', out.stdout)


class Update(unittest.TestCase):
    """stampede update in scratch checkouts of a scratch origin: refusals keep every local change."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        origin = self.dir / 'origin'
        (origin / 'scripts').mkdir(parents=True)
        shutil.copy(ROOT / 'scripts/stampede_update.py', origin / 'scripts')
        (origin / 'VERSION').write_text('0.1.0\n')
        (origin / 'install.sh').write_text('touch "$(dirname "$0")/installed"\n')
        (origin / '.gitignore').write_text('installed\n__pycache__/\n')
        self.git(origin, 'init', '-q', '-b', 'main')
        self.git(origin, 'add', '.')
        self.git(origin, 'commit', '-qm', 'one')
        self.origin, self.clone = origin, self.dir / 'clone'
        self.git(self.dir, 'clone', '-q', str(origin), str(self.clone))
        (origin / 'VERSION').write_text('0.2.0\n')
        self.git(origin, 'commit', '-qam', 'two')

    def git(self, where, *args):
        subprocess.run(['git', '-C', str(where), *args], env={**os.environ, **GIT_ENV}, check=True, capture_output=True)

    def update(self, where):
        return subprocess.run([sys.executable, '-I', str(where / 'scripts/stampede_update.py')],
                              env={**os.environ, **GIT_ENV}, capture_output=True, text=True, timeout=60)

    def test_a_clean_main_fast_forwards_and_reinstalls(self):
        out = self.update(self.clone)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('stampede 0.1.0 -> 0.2.0', out.stdout)
        self.assertEqual((self.clone / 'VERSION').read_text(), '0.2.0\n')
        self.assertTrue((self.clone / 'installed').exists())

    def test_a_dirty_tree_or_another_branch_is_refused_and_kept(self):
        (self.clone / 'install.sh').write_text('# my change\n')
        out = self.update(self.clone)
        self.assertEqual(out.returncode, 1)
        self.assertIn('has local changes', out.stderr)
        self.assertEqual((self.clone / 'install.sh').read_text(), '# my change\n')
        self.assertEqual((self.clone / 'VERSION').read_text(), '0.1.0\n')
        self.git(self.clone, 'checkout', '-q', '--', 'install.sh')
        self.git(self.clone, 'switch', '-qc', 'mine')
        out = self.update(self.clone)
        self.assertEqual(out.returncode, 1)
        self.assertIn('is on mine, not main', out.stderr)

    def test_a_plugin_install_names_herdr_plugin_update(self):
        plain = self.dir / 'plain'
        shutil.copytree(self.origin, plain, ignore=shutil.ignore_patterns('.git'))
        out = self.update(plain)
        self.assertEqual(out.returncode, 1)
        self.assertIn('run herdr plugin update', out.stdout)


if __name__ == '__main__':
    unittest.main()
