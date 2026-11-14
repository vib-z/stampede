"""The stampede command teaches itself: grouped help with examples, errors that name the next step, stampede doctor and
stampede check. Everything runs in a scratch HOME with fakes; nothing reaches a live Herdr or Herdr Core."""
import contextlib, io, json, os, re, shlex, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/herdr-fleet/scripts'
BOT = ROOT / 'skills/grokbot-herdr/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / 'tests'))
from stampede import base as base_, check as check_, doctor as doctor_  # noqa: E402
from test_fleet_job import fake_herdr, valid_brief  # noqa: E402
from quiet import quiet  # noqa: E402

ORDER = ('new', 'start', 'tell', 'ask', 'post', 'wait', 'next', 'tree', 'approve', 'approve-gate', 'gate-ok', 'cancel', 'merge',
         'finish', 'snapshot', 'reopen', 'close', 'config', 'doctor', 'check', 'update')
HIDDEN = ('hook', 'prepush', '_reopen', '_deliver', '_wake', '_ask')


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
                self.assertRegex(result.stdout, r'\n\nexamples?( \(.*\))?:\n(  .*\n)*  stampede ' + name)
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
            for folder, said in ((self.home / 'gone', 'job folder not found: '), (plain, 'not a job folder, it has no lead or ask.md file: ')):
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

    def check(self, setup):
        """stampede check in its own process, as --json, with check.py changed by setup first."""
        out = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); from stampede import check; '
                              + setup + '; sys.exit(check.main(as_json=True))', str(SCRIPTS)], capture_output=True, text=True, timeout=120)
        return out.returncode, json.loads(out.stdout)

    def test_check_needs_a_tests_folder_and_reports_each_module(self):
        with mock.patch.object(check_, 'ROOT', self.home), self.assertRaisesRegex(ValueError, 'no tests folder in '):
            check_.main()
        code, report = self.check('check.FAST = ("test_version",)')
        self.assertEqual(code, 0)
        self.assertTrue(report['ok'])
        self.assertEqual([m['name'] for m in report['modules']], ['test_version'])
        self.assertEqual(report['tests'], report['modules'][0]['tests'])
        self.assertGreater(report['tests'], 0)

    def test_check_fails_for_a_missing_fast_module_and_an_empty_full_run(self):
        code, report = self.check('check.FAST = ("test_version", "test_no_such_module")')
        self.assertEqual((code, report['ok']), (1, False))
        missing = [m for m in report['modules'] if m['name'] == 'test_no_such_module']
        self.assertEqual([m['output'] for m in missing], ['tests/test_no_such_module.py is missing from this checkout'])
        self.assertIn('test_settings', check_.FAST)
        self.assertFalse(hasattr(check_, 'OPTIONAL'), 'every fast module is required: test_settings comes with the config')
        (self.home / 'tests').mkdir()
        with mock.patch.object(check_, 'ROOT', self.home), quiet():
            self.assertEqual(check_.main(full=True), 1, 'a full run of no tests is no pass')

    def test_check_fails_a_run_that_ran_no_tests(self):
        """Python 3.9's unittest exits 0 for a module of no tests, so check counts them itself, fast and full."""
        (self.home / 'tests').mkdir()
        (self.home / 'tests/test_empty.py').write_text('# no tests here\n')
        (self.home / 'tests/test_nothing.py').write_text('import unittest\nclass Nothing(unittest.TestCase):\n    pass\n')
        out = io.StringIO()
        with mock.patch.object(check_, 'ROOT', self.home), mock.patch.object(check_, 'FAST', ('test_empty',)), \
                contextlib.redirect_stdout(out):
            self.assertEqual(check_.main(full=True), 1)
            self.assertEqual(check_.main(), 1)
            self.assertEqual(check_.main(as_json=True), 1)
        self.assertIn('ran no tests', out.getvalue())
        self.assertIn('"ok": false', out.getvalue())

    def fake_herdr_doctor(self, body):
        helpers = self.home / 'helpers'
        helpers.mkdir()
        (helpers / 'herdr-doctor').write_text('#!/bin/bash\n' + body)
        (helpers / 'herdr-doctor').chmod(0o755)
        return mock.patch.object(doctor_, 'HELPERS', helpers)

    def test_doctor_counts_a_failing_herdr_doctor_as_a_problem(self):
        with self.fake_herdr_doctor('echo "ok herdr on PATH"\necho "warn x: y"\necho BACKEND_CRASH >&2\nexit 7\n'), \
                mock.patch.object(doctor_, 'CHECKS', ()), quiet():
            checks = doctor_.herdr_doctor(False, False)
            code = doctor_.main(as_json=True)
        self.assertEqual([c['level'] for c in checks], ['ok', 'warn', 'PROBLEM'], 'its lines are kept')
        self.assertEqual(checks[-1]['text'], 'herdr-doctor exited 7 (BACKEND_CRASH)')
        self.assertEqual(code, 1)

    def doctor_output(self, home, **patches):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'HOME': str(home)}), contextlib.redirect_stdout(out), contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(doctor_, name, value))
            doctor_.main()
            doctor_.main(as_json=True)
        return out.getvalue()

    def test_doctor_shows_home_paths_with_a_tilde(self):
        said = self.doctor_output(ROOT.parent, CHECKS=(doctor_.checkout,), herdr_doctor=lambda core, tui: [])
        self.assertIn(' in ~/' + ROOT.name + ', ', said)
        self.assertNotIn(str(ROOT.parent), said)
        self.assertEqual(doctor_.shown('/elsewhere/x'), '/elsewhere/x')

    def test_doctor_strips_another_program_s_control_bytes(self):
        self.assertEqual(doctor_.shown('claude \x1b]7501;state=idle\x07said \x1b[31mred\x1b[0m\x00\tok'), 'claude said red\tok')

    def test_doctor_redacts_an_errors_own_text_by_both_spellings_of_home(self):
        physical = self.home / 'physical home'
        physical.mkdir()
        physical = physical.resolve()   # where the link lands, as the error names it (on macOS /tmp is /private/tmp)
        (self.home / 'link').symlink_to(physical)
        failing = doctor_.check('checkout', 'PROBLEM', f"stampede.x does not import (No such file: '{physical}/a.py')",
                                f'git -C {self.home / "link"} status')
        said = self.doctor_output(self.home / 'link', CHECKS=(lambda: [failing],), HELPERS=physical / 'no-helpers')
        self.assertIn('herdr-doctor did not run', said)   # a missing herdr-doctor: its own error names the folder
        for home in (str(physical), str(self.home / 'link')):
            self.assertNotIn(home, said)
        self.assertIn("(No such file: '~/a.py')", said)
        self.assertIn('git -C ~ status', said)

    def test_the_gate_examples_bind_one_commit_for_the_check_and_the_act(self):
        texts = [self.stampede(name, '--help').stdout for name in ('ask', 'gate-ok', 'merge')] + [(ROOT / 'docs/CLI.md').read_text()]
        for text in texts:
            for merge in re.findall(r'gh pr merge[^\n]*', text):
                self.assertIn('--match-head-commit', merge)
            self.assertNotIn('rev-parse HEAD', text)
        self.assertIn('stampede gate-ok <job> 0123456789ab --sha "$sha"', texts[1])
        self.assertIn('stampede merge <job> 12 --sha "$sha" --review', texts[2])

    def test_the_hint_outside_herdr_runs_as_printed_with_spaces_in_its_paths(self):
        repo = self.home / 'repo with spaces'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        ask = repo.parent / 'ask plan.md'
        ask.write_text('Fix the login bug\n')
        result = subprocess.run([str(ROOT / 'scripts/stampede'), 'new', '--file', str(ask), '--set', 'backend=tui'], capture_output=True, text=True,
                                env=self.env, cwd=repo, timeout=60)
        self.assertEqual(result.returncode, 2, result.stderr)
        command = shlex.split(result.stderr.splitlines()[-1])
        self.assertEqual(command, ['stampede', 'new', '--core', '--file', str(ask), '--cwd', str(repo.resolve())])

    def test_the_hint_keeps_every_character_of_its_paths(self):
        for name in ('two  spaces', 'a\ttab', "a 'quote'", 'a $dollar', 'all  \t\'"$ of it'):
            with self.subTest(name=name):
                repo = self.home / ('repo ' + name)
                repo.mkdir()
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                ask = self.home / ('ask ' + name + '.md')
                ask.write_text('Fix the login bug\n')
                result = subprocess.run([str(ROOT / 'scripts/stampede'), 'new', '--file', str(ask), '--set', 'backend=tui'], capture_output=True,
                                        text=True, env=self.env, cwd=repo, timeout=60)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(result.stderr.splitlines()[0].endswith('to run it here on Herdr Core, run the next line'))
                self.assertEqual(shlex.split(result.stderr.split('run the next line\n', 1)[1]),
                                 ['stampede', 'new', '--core', '--file', str(ask), '--cwd', str(repo.resolve())])

    def test_every_help_example_is_valid_shell(self):
        for name in ORDER[:-1]:
            with self.subTest(name):
                epilog = self.stampede(name, '--help').stdout.split('\n\nexample')[1].split('\n', 1)[1]
                script = re.sub(r'<[^>]+>', 'X', '\n'.join(line.strip() for line in epilog.splitlines()))
                checked = subprocess.run(['sh', '-n'], input=script, capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, script + checked.stderr)

    def test_a_blocked_tui_start_exits_0_as_the_exit_table_says(self):
        repo = self.home / 'repo'
        repo.mkdir()
        (self.home / 'ask.md').write_text('Fix the login bug\n')
        herdr, _ = fake_herdr(repo, 'blocked')
        new = self.stampede('new', '--file', self.home / 'ask.md', '--workspace', 'w9', HERDR=herdr)
        job = next((self.home / 'jobs-root/jobs').iterdir())
        start = self.stampede('start', job, 'build-x', '--kind', 'claude', '--pane', 'w9:p3', '--brief', valid_brief(job), HERDR=herdr)
        for result in (new, start):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('BLOCKED', result.stdout)
        table = (ROOT / 'docs/CLI.md').read_text()
        self.assertIn('| 0 | done; also `new` and `start` on the Herdr TUI that print `BLOCKED <agent>: clear the startup dialog', table)

    def test_a_job_that_lost_its_lead_file_is_still_a_job(self):
        job = self.job()
        (job / 'lead').unlink()
        (job / 'ask.md').write_text('the ask\n')
        result = self.stampede('tree', job)   # past the folder check, to the command's own answer
        self.assertEqual(result.stderr, f'stampede tree: tree is for a native job (new --core); {job} is a tui job\n')

if __name__ == '__main__':
    unittest.main()
