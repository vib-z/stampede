"""The stampede command teaches itself: grouped help with examples, errors that name the next step, stampede doctor and
stampede check. Everything runs in a scratch HOME with fakes; nothing reaches a live Herdr or Herdr Core."""
import json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/herdr-fleet/scripts'
BOT = ROOT / 'skills/grokbot-herdr/scripts'
sys.path.insert(0, str(SCRIPTS))
from stampede import base as base_, check as check_  # noqa: E402

ORDER = ('new', 'start', 'tell', 'ask', 'post', 'wait', 'next', 'tree', 'approve', 'approve-gate', 'gate-ok', 'cancel',
         'finish', 'snapshot', 'reopen', 'close', 'doctor', 'check', 'update')
HIDDEN = ('hook', '_reopen', '_deliver', '_wake', '_ask')


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('HERDR_', 'FLEET_', 'STAMPEDE_', 'HC_'))}
        self.env.update(HOME=str(self.home), HC_SOCKET=str(self.home / 'no-core.sock'), STAMPEDE_NO_UPDATE_CHECK='1',
                        FLEET_JOBS_ROOT=str(self.home / 'jobs-root'))

    def stampede(self, *args, **env):
        return subprocess.run([str(ROOT / 'scripts/stampede'), *map(str, args)], capture_output=True, text=True,
                              env={**self.env, **env}, cwd=self.home, timeout=60)

    def job(self, *agents):
        job = self.home / 'job'
        job.mkdir()
        (job / 'lead').write_text('lead-demo\n')
        (job / 'agents.tsv').write_text(''.join(f'{name}\tclaude\t-\t-\t-\n' for name in ('lead-demo', *agents)))
        return job

    def test_bare_stampede_prints_the_help_and_exits_2(self):
        result = self.stampede()
        self.assertEqual((result.returncode, result.stdout), (2, ''))
        self.assertTrue(result.stderr.startswith('usage: stampede <command>'), result.stderr)
        self.assertIn('stampede new --core --file ask.md', result.stderr)

    def test_the_help_groups_every_command_in_order_and_hides_the_internal_ones(self):
        result = self.stampede('--help')
        self.assertEqual(result.returncode, 0)
        listed = re.findall(r'^    (\S+) ', result.stdout, re.M)
        self.assertEqual(tuple(listed), ORDER)
        for group in ('start a job:', 'work in it:', 'gates:', 'end and return:', 'the machine:'):
            self.assertIn('  ' + group, result.stdout)
        self.assertIn('USING.md', result.stdout)
        self.assertNotIn('fleet-job', result.stdout)
        for name in HIDDEN:
            self.assertNotIn(name, result.stdout)
        self.assertNotIn('_reopen', self.stampede('bogus').stderr)   # an unknown command lists nothing internal either

    def test_every_command_has_a_description_flag_help_and_an_example(self):
        for name in ORDER[:-1]:  # update is stampede_update.py's own help
            with self.subTest(name):
                result = self.stampede(name, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertRegex(result.stdout, r'\n\nexamples?( \(.*\))?:\n  stampede ' + name)
                self.assertTrue(result.stdout.split('\n\n')[1].strip(), 'a description')
                for flag in re.findall(r'^  (-[-\w]+(?: [A-Z_]+)?)\s*$', result.stdout, re.M):  # a flag on a line of its own
                    self.assertNotRegex(result.stdout, re.escape(flag) + r'\n\n', f'{flag} has help')
        start = self.stampede('start', '--help').stdout
        for kind in ('claude', 'codex', 'cursor', 'hermes', 'kimi'):
            self.assertIn(kind, start)
        self.assertIn('nothing is handed to a Herdr\n', self.stampede('new', '--help').stdout.replace('                        ', ''))

    def test_a_missing_job_folder_or_a_folder_with_no_lead_is_named_before_anything_else(self):
        plain = self.home / 'plain'
        plain.mkdir()
        for argv in (('tell', '{}', 'lead', 'hi'), ('tree', '{}'), ('start', '{}', 'build-x'), ('post', '{}', 'x'),
                     ('approve', '{}', '--by', 'o'), ('close', '{}'), ('finish', '{}', 'done')):
            for folder, said in ((self.home / 'gone', 'job folder not found: '), (plain, 'not a job folder, it has no lead file: ')):
                with self.subTest(argv=argv[0], folder=folder.name):
                    result = self.stampede(*[str(folder) if a == '{}' else a for a in argv])
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (2, '', f'stampede {argv[0]}: {said}{folder}\n'))
        self.assertEqual(list(plain.iterdir()), [], 'nothing was written in it')

    def test_tell_to_an_unknown_agent_names_the_ones_it_has(self):
        job = self.job('build-api', 'build-ui')
        result = self.stampede('tell', job, 'build-web', 'hi')
        self.assertEqual((result.returncode, result.stderr),
                         (2, 'stampede tell: agent build-web is not in this job (it has: lead, build-api, build-ui)\n'))

    def test_new_with_no_ask_file_says_so_first(self):
        result = self.stampede('new', '--file', self.home / 'ask.md', '--cwd', 'x')   # --cwd without --core is a later error
        self.assertEqual((result.returncode, result.stderr),
                         (2, f'stampede new: the ask file {self.home / "ask.md"} does not exist: write what the job is for '
                             'in it, then run new again\n'))
        self.assertFalse((self.home / 'jobs-root').exists())

    def test_a_post_no_one_hears_says_so(self):
        result = self.stampede('post', self.job(), 'hello')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('POSTED 001 to the outbox only'), result.stdout)
        self.assertNotIn('front door to relay', result.stdout)

    def test_the_helpers_help_exits_0_with_no_dates(self):
        for argv in ((ROOT / 'scripts/stampede', 'update', '--help'), (BOT / 'herdr-events-owner', '--help'),
                     (BOT / 'herdr-reopen-snapshot', '--help')):
            with self.subTest(argv[0].name):
                result = subprocess.run(argv, capture_output=True, text=True, env=self.env, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage' if argv[1] == 'update' else argv[0].name, result.stdout)
                self.assertNotRegex(result.stdout, r'20\d\d|owner\'s rule|fleet-job')
        self.assertFalse((self.home / '.config').exists(), 'herdr-events-owner --help made nothing')

    def test_an_old_python_is_refused_with_the_minimum(self):
        code = ('import runpy, sys; entry = sys.argv[2]; sys.path.insert(0, sys.argv[1]); from stampede import base; '
                'base.MIN_PYTHON = (99, 0); sys.argv = ["stampede", "--help"]; runpy.run_path(entry, run_name="__main__")')
        result = subprocess.run([sys.executable, '-I', '-c', code, str(SCRIPTS), str(SCRIPTS / 'fleet_job.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r'^stampede needs Python 99\.0 or later \(this is 3\.\d+\.\d+\): put a newer python3 first on PATH')
        self.assertEqual(base_.MIN_PYTHON, (3, 9))
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn("python-version: '3.9'", ci, 'CI runs the unit suite on the minimum')
        for doc in ('README.md', 'CONTRIBUTING.md'):
            self.assertIn('Python 3.9 or later', (ROOT / doc).read_text(), doc)

    def test_doctor_lines_json_and_exit(self):
        bare = {'PATH': '/usr/bin:/bin'}  # no stampede, no herdr, no hc: the commands line and herdr-doctor are PROBLEMs
        result = self.stampede('doctor', **bare)
        self.assertEqual(result.returncode, 1, result.stderr)
        lines = result.stdout.splitlines()
        self.assertRegex(lines[0], r'^ok python3 3\.\d+')
        self.assertRegex(lines[1], r'^ok stampede \d+\.\d+\.\d+ in .*, all \d+ modules import$')
        self.assertTrue(lines[2].startswith('PROBLEM not on PATH: stampede, fleet-job, herdr-doctor'), lines[2])
        self.assertIn('install.sh', lines[2])
        self.assertTrue(all(re.match(r'(ok|warn|PROBLEM) ', line) for line in lines), lines)
        report = json.loads(self.stampede('doctor', '--json', **bare).stdout)
        self.assertFalse(report['ok'])
        self.assertEqual(set(report['checks'][0]), {'name', 'level', 'text', 'fix'})
        self.assertEqual([c['name'] for c in report['checks'][:3]], ['python', 'checkout', 'commands'])
        self.assertIn('herdr-doctor', {c['name'] for c in report['checks']}, 'its lines are passed through')
        self.assertEqual(self.stampede('doctor', '--core', '--tui').returncode, 2)

    def test_check_needs_a_tests_folder_and_reports_each_module(self):
        with mock.patch.object(check_, 'ROOT', self.home), self.assertRaisesRegex(ValueError, 'no tests folder in '):
            check_.main()
        out = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); from stampede import check; '
                              'check.FAST = ("test_version", "test_no_such_module"); sys.exit(check.main(as_json=True))', str(SCRIPTS)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        report = json.loads(out.stdout)
        self.assertTrue(report['ok'])
        self.assertEqual([m['name'] for m in report['modules']], ['test_version'])
        self.assertEqual(report['tests'], report['modules'][0]['tests'])
        self.assertGreater(report['tests'], 0)


if __name__ == '__main__':
    unittest.main()
