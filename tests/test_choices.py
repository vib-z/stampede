"""The choices: backend, one job folder rule, roles, the lead's flags, the layout and the review step. For each key the
default is today's behaviour, a config value changes it, and a flag beats it. Every Core call goes to tests/fake_hc.py."""
import contextlib, io, json, os, subprocess, sys, unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, SCRIPTS, LEAD  # noqa: E402
from stampede import job as job_, native as native_, owner as owner_, relay as relay_, cli as cli_, settings as settings_, agents as agents_, \
    doctor as doctor_, hcapi as hcapi_  # noqa: E402

FLEET = SCRIPTS / 'fleet-job'


class Choices(CoreCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(settings_.SETS.clear)
        self.user = self.root / 'home/.config/stampede/config.toml'
        self.user.parent.mkdir(parents=True)
        self.ask = self.root / 'ask.md'
        self.ask.write_text('Fix the login bug\n')

    def config(self, text):
        self.user.write_text(text)

    def main(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def new(self, *flags, env=None):
        return self.main('new', '--file', self.ask, '--cwd', self.repo, *flags, env=env)

    def lead_run(self):
        (run,) = [r for r in self.calls('run') if self.labels(r).get('stampede.role') == 'lead']
        return run


class Backend(Choices):
    def choice(self, **flags):
        a = Namespace(**{'core': False, 'pane': None, 'workspace': None, 'cwd': str(self.repo), **flags})
        return cli_.backend_for(a)

    def test_the_tui_is_the_default_and_core_runs_only_when_asked(self):
        """The rule: the Herdr TUI is the default; Herdr Core runs a job only with --core or the setting backend."""
        self.assertEqual(settings_.load(repo=self.repo).get('backend'), 'tui')
        self.assertEqual(self.choice(), (False, ''), 'no flag, no setting: the TUI')
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (False, ''), 'inside a Herdr pane: the TUI')
        self.assertEqual(self.choice(core=True), (True, ''), '--core is Core')
        code, out, err = self.main('new', '--file', self.ask, '--json')  # bare new outside a pane: refused, nothing made
        self.assertEqual(code, 2, err)
        refusal = ('stampede new: new runs the job on the Herdr TUI and needs a Herdr pane: run it inside Herdr, or pass '
                   '--workspace or --pane; to run the job on Herdr Core instead, add --core, or for every job: '
                   'stampede config set backend core')
        self.assertEqual(json.loads(out), {'ok': False, 'command': 'new', 'status': None, 'backend': 'tui', 'error': refusal, 'retry': None})
        code, out, err = self.main('new', '--file', self.ask)
        self.assertEqual((code, out, err.strip()), (2, '', refusal))
        self.assertFalse(self.job.exists())
        self.assertEqual(self.calls('run'), [])
        code, out, err = self.new('--core')
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (--core), repo {self.repo.resolve()}')
        self.assertEqual(job_.backend(self.job), 'native')

    def test_auto_in_the_users_file_is_the_tui_inside_a_herdr_pane_and_core_elsewhere(self):
        self.config('backend = "auto"\n')
        self.assertEqual(self.choice(), (True, 'backend auto: not inside a Herdr pane'))
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (False, ''), 'inside Herdr, as before')
        self.assertEqual(self.choice(pane='w1:p1'), (False, ''), 'a TUI target is the TUI')
        code, out, err = self.new()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (backend auto: not inside a Herdr pane), repo {self.repo.resolve()}')
        self.assertEqual(out.splitlines()[-1], f'{LEAD} {self.job}')
        self.assertEqual(job_.backend(self.job), 'native')
        self.user.unlink()  # the default tui comes back: the open job keeps the backend <job>/backend recorded
        self.assertEqual(job_.backend(self.job), 'native')
        code, out, err = self.main('start', self.job, 'prog', '--', 'sleep', '60')
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith(f'STARTED prog (t2) under {LEAD}'), out)

    def test_core_in_the_users_file_runs_core_with_no_flag(self):
        self.config('backend = "core"\n')
        code, out, err = self.new()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (backend core), repo {self.repo.resolve()}')
        self.assertEqual(job_.backend(self.job), 'native')

    def test_tui_is_todays_error_and_core_runs_core_unless_a_tui_target_is_named(self):
        self.config('backend = "tui"\n')
        self.assertEqual(self.choice(), (False, ''))
        code, _, err = self.main('new', '--file', self.ask)
        self.assertEqual(code, 2)
        self.assertIn('new runs the job on the Herdr TUI and needs a Herdr pane', err)
        self.config('backend = "core"\n')
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (True, 'backend core'))
            self.assertEqual(self.choice(workspace='w1'), (False, ''))
        settings_.SETS[:] = ['backend=tui']
        self.assertEqual(self.choice(), (False, ''), '--set beats the file')
        settings_.SETS.clear()

    def test_a_bad_value_is_a_problem_and_new_refuses(self):
        self.config('backend = "cloud"\n')
        code, _, err = self.new('--core')
        self.assertEqual(code, 2)
        self.assertIn('backend must be one of auto, tui, core, not \'cloud\'', err)

    def test_an_explicit_core_start_names_its_repo_first_and_as_a_fact(self):
        code, out, err = self.new('--core')
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (--core), repo {self.repo.resolve()}')
        self.assertEqual(out.splitlines()[-1].split()[0], LEAD, 'the last line stays <lead> <job dir>')
        code, out, err = self.main('new', '--file', self.ask, '--cwd', self.repo, '--core', '--name', 'second', '--json')
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['repo'], str(self.repo.resolve()))

    def test_config_show_and_doctor_catch_a_bad_value_as_new_does(self):
        self.config('[lead]\nkind = "claud"\n[merge]\nmethod = "fast"\n[roles.review]\nkind = "gemini"\n[roles.mine]\nkind = "x"\n')
        code, out, _ = self.main('config', 'show')
        self.assertEqual(code, 1)
        for text in ("lead.kind must be one of claude, codex, not 'claud'", "merge.method must be one of squash, merge, rebase",
                     "roles.review.kind must be one of claude, codex, cursor, hermes, kimi, not 'gemini'", "roles.mine.kind must be one of"):
            self.assertIn(text, out)
        found = doctor_.config()
        self.assertTrue(any(c['level'] == 'PROBLEM' and "not 'claud'" in c['text'] for c in found), found)
        code, _, err = self.new('--core')
        self.assertEqual(code, 2)
        self.assertIn("lead.kind must be one of claude, codex, not 'claud'", err)

    def test_core_not_answering_says_what_to_start_or_pass(self):
        self.config('backend = "auto"\n')
        with mock.patch.dict(os.environ, {'HC': '/nonexistent/hc'}):
            code, _, err = self.new()
        self.assertEqual(code, 2)
        self.assertIn('Herdr Core is not installed', err)
        self.assertIn('start Herdr Core (hc server start)', err)
        self.assertIn('pass --workspace or --pane', err)


    def test_a_repo_file_never_puts_a_job_on_core(self):
        for value in ('core', 'auto'):
            with self.subTest(value=value):
                (self.repo / '.stampede.toml').write_text(f'backend = "{value}"\n')
                self.assertEqual(self.choice(), (False, ''))
                shown = settings_.show(settings_.load(repo=self.repo), False)  # what config show prints in that repo
                self.assertIn('backend = "tui"  (default)', shown)
                self.assertIn(f'.stampede.toml: backend is taken only from your own {self.user}', shown)
                code, _, err = self.main('new', '--file', self.ask, '--cwd', self.repo, '--core')
                self.assertEqual(code, 2)
                self.assertIn('backend is taken only from your own', err)
                self.assertFalse(self.job.exists())
        (self.repo / '.stampede.toml').unlink()
        self.config('backend = "core"\n')
        self.assertEqual(self.choice(), (True, 'backend core'), 'the user\'s own file still chooses')
        code, out, err = self.new('--core')
        self.assertEqual(code, 0, err)
        self.assertNotIn('backend', json.loads((self.job / 'settings.json').read_text())['values'], 'never saved in the job')


class SetBackend(Choices):
    """config set backend: one line in the user's own file, every other byte kept, and new follows it."""
    def set(self, *argv):
        return self.main('config', 'set', *argv)

    def test_a_missing_file_is_made_and_new_follows_it(self):
        self.user.parent.rmdir()
        code, out, err = self.set('backend', 'core')
        self.assertEqual((code, out, err), (0, f'backend = "core" ({self.user})\n', ''))
        self.assertEqual(self.user.read_text(), 'backend = "core"\n')
        code, out, _ = self.main('config', 'show')
        self.assertIn('backend = "core"  (user)', out)
        code, out, err = self.new()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (backend core), repo {self.repo.resolve()}')
        code, out, _ = self.set('backend', 'tui', '--json')
        self.assertEqual((code, json.loads(out)), (0, {'ok': True, 'command': 'config', 'status': None, 'path': str(self.user)}))

    def test_an_existing_line_is_replaced_and_every_other_byte_kept(self):
        before = '# mine\n\nbackend = "auto"   # was auto\njobs_root = "~/jobs"\n\n[lead]\nkind = "codex"  # backend = no\n'
        self.config(before)
        self.assertEqual(self.set('backend', 'tui')[0], 0)
        self.assertEqual(self.user.read_text(), before.replace('backend = "auto"   # was auto', 'backend = "tui"'))

    def test_with_tables_and_no_line_it_goes_first_and_the_file_still_parses(self):
        self.config('[lead]\nkind = "codex"\n[roles.build]\nbackend = "x"\n')
        self.assertEqual(self.set('backend', 'core')[0], 0)
        self.assertEqual(self.user.read_text(), 'backend = "core"\n[lead]\nkind = "codex"\n[roles.build]\nbackend = "x"\n')
        found = settings_.load(repo=self.repo)
        self.assertEqual((found.get('backend'), found.get('lead.kind'), found.sources['backend']), ('core', 'codex', 'user'))

    def test_bytes_are_kept_and_a_crlf_file_stays_crlf(self):
        self.user.write_bytes(b'# a\r\nbackend = "auto"  \r\n\r\n[lead]\r\nkind = "codex"\r\n')
        self.assertEqual(self.set('backend', 'tui')[0], 0)
        self.assertEqual(self.user.read_bytes(), b'# a\r\nbackend = "tui"\r\n\r\n[lead]\r\nkind = "codex"\r\n')
        self.user.write_bytes(b'[lead]\r\nkind = "codex"\r\n')
        self.assertEqual(self.set('backend', 'core')[0], 0)
        self.assertEqual(self.user.read_bytes(), b'backend = "core"\r\n[lead]\r\nkind = "codex"\r\n')

    def test_a_linked_file_stays_a_link_and_its_target_changes(self):
        real = self.root / 'dotfiles/stampede.toml'
        real.parent.mkdir()
        real.write_text('backend = "auto"\n')
        self.user.symlink_to(real)
        self.assertEqual(self.set('backend', 'core')[0], 0)
        self.assertTrue(self.user.is_symlink())
        self.assertEqual(real.read_text(), 'backend = "core"\n')

    def test_the_mode_is_kept(self):
        for mode in (0o600, 0o400):
            with self.subTest(mode=oct(mode)):
                self.user.write_text('backend = "auto"\n')
                self.user.chmod(mode)
                self.assertEqual(self.set('backend', 'core')[0], 0)
                self.assertEqual((self.user.stat().st_mode & 0o7777, self.user.read_text()), (mode, 'backend = "core"\n'))
                self.user.chmod(0o600)
                self.user.unlink()

    def test_a_planted_temporary_name_is_never_followed(self):
        other = self.root / 'other.toml'
        other.write_text('keep me\n')
        for name in ('config.toml.new', 'config.toml.tmp', '.config.toml.tmp'):
            (self.user.parent / name).symlink_to(other)
        self.config('backend = "auto"\n')
        self.assertEqual(self.set('backend', 'core')[0], 0)
        self.assertEqual((other.read_text(), self.user.read_text()), ('keep me\n', 'backend = "core"\n'))
        self.assertEqual(sorted(p.name for p in self.user.parent.iterdir()),
                         ['.config.toml.tmp', 'config.toml', 'config.toml.new', 'config.toml.tmp'])

    def test_a_file_it_cannot_change_safely_is_refused_byte_for_byte(self):
        for text in ('"backend" = "auto"\n', 'backend = """\nauto"""\n', "backend = 'auto'\n", 'backend = \n', '[lead\nkind = 1\n',
                     'backend = "auto"\r\nx = "\xff"\n'):
            with self.subTest(text=text):
                self.user.write_bytes(text.encode('latin-1'))
                code, out, err = self.set('backend', 'core')
                self.assertEqual((code, out), (2, ''), err)
                self.assertIn(str(self.user), err)
                self.assertIn('nothing was changed', err)
                self.assertEqual(self.user.read_bytes(), text.encode('latin-1'))
                self.assertEqual([p.name for p in self.user.parent.iterdir()], ['config.toml'])

    def test_a_look_alike_line_inside_another_value_is_never_taken_for_the_setting(self):
        """3.13's tomllib reads each and the whole-file check refuses it; 3.9's fallback parser refuses multi-line strings
        before that. Either way: exit 2, bytes unchanged."""
        for text in ('lead.claude.model = """\nbackend = "auto"\n"""\n"backend" = "core"\n',
                     "lead.claude.model = \'\'\'\nbackend = \"auto\"\n\'\'\'\nbackend = \'core\'\n",
                     'x = """\nbackend = "tui"\n"""\nbackend = """auto"""\n'):
            with self.subTest(text=text):
                self.user.write_text(text)
                code, _, err = self.set('backend', 'core')
                self.assertEqual(code, 2, err)
                self.assertIn('nothing was changed', err)
                self.assertEqual(self.user.read_text(), text)

    def test_with_no_backend_a_look_alike_inside_a_string_stays_as_it_is(self):
        """The line goes first and the string keeps its text; 3.9's fallback parser refuses the file: exit 2, unchanged."""
        for text in ('lead.claude.model = """\nbackend = "auto"\n"""\n', "lead.claude.model = \'\'\'\nbackend = \"auto\"\n\'\'\'\n"):
            with self.subTest(text=text):
                self.user.write_text(text)
                code, _, err = self.set('backend', 'core')
                if settings_.tomllib:
                    self.assertEqual((code, self.user.read_text()), (0, 'backend = "core"\n' + text), err)
                    self.assertEqual(settings_.parse(self.user.read_text())['lead'], settings_.parse(text)['lead'])
                else:
                    self.assertEqual((code, self.user.read_text()), (2, text), err)

    def test_the_plain_line_is_replaced_and_every_other_value_is_the_same(self):
        self.config('# mine\njobs_root = "~/jobs"\nbackend = "auto"\ntrust_root = "~/src"\n\n[lead]\nkind = "codex"\nforbid = ["a", "b"]\n'
                    '[lead.codex]\nmodel = "m"\n[roles.build]\nkind = "claude"\neffort = "high"\n[helpers]\nmax = 6\n')
        before = settings_.parse(self.user.read_text())
        self.assertEqual(self.set('backend', 'core')[0], 0)
        self.assertEqual(settings_.parse(self.user.read_text()), {**before, 'backend': 'core'})

    def test_a_failure_before_the_rename_leaves_the_file_whole_and_no_temporary_file(self):
        self.config('backend = "auto"\n')
        with mock.patch.object(settings_.os, 'replace', side_effect=OSError('disk full')):
            code, _, err = self.set('backend', 'core')
        self.assertEqual(code, 1, err)
        self.assertEqual(self.user.read_text(), 'backend = "auto"\n')
        self.assertEqual([p.name for p in self.user.parent.iterdir()], ['config.toml'])

    def test_another_key_or_a_bad_value_is_refused_and_writes_nothing(self):
        code, out, err = self.set('lead.kind', 'codex')
        self.assertEqual((code, out, err.strip()), (2, '', f'stampede config: config set takes backend only; for lead.kind, edit {self.user}'))
        code, _, err = self.set('backend', 'cloud')
        self.assertEqual((code, err.strip()), (2, "stampede config: backend must be one of auto, tui, core, not 'cloud'"))
        self.assertFalse(self.user.exists())
        self.assertFalse((self.repo / '.stampede.toml').exists())


class Folder(Choices):
    def test_every_path_makes_the_folder_in_the_jobs_root_with_the_repo_in_workdir(self):
        for relay in (False, True):
            name = 'relay' if relay else 'native'
            code, out = self.quiet(cli_.new, str(self.ask), None, name=name, core=True, relay=relay, cwd=str(self.repo))
            self.assertEqual(code, 0, out)
            (job,) = (job_.jobs_root() / 'jobs').glob('*-local-' + name)
            self.assertEqual((job / 'workdir').read_text().strip(), str(self.repo))
            self.assertEqual((job / 'lead').read_text().strip(), 'lead-' + name)
            self.assertEqual((job / 'workspace').read_text().strip(), job_.job_key(job), 'the key is the folder\'s hash')
        self.assertEqual(list(self.repo.iterdir()), [], 'nothing in the repo')
        code, out = self.quiet(cli_.new, str(self.ask), None, name='native', core=True, cwd=str(self.repo))
        self.assertEqual(code, 0, out)
        self.assertTrue(list((job_.jobs_root() / 'jobs').glob('*-local-native-2')), 'the same name again takes -2')

    def test_every_agent_of_a_core_job_reads_and_writes_the_job_folder(self):
        for relay in (False, True):
            name = 'relay' if relay else 'native'
            self.quiet(cli_.new, str(self.ask), None, name=name, core=True, relay=relay, cwd=str(self.repo))
            (job,) = (job_.jobs_root() / 'jobs').glob('*-local-' + name)
            for kind in ('claude', 'codex'):
                code, out = self.quiet(cli_.start, job, f'build-{kind}', kind, None, str(self.brief(job, f'build-{kind}')))
                self.assertEqual(code or 0, 0, out)
            for run in [r for r in self.calls('run') if self.labels(r).get('stampede.job') == job_.job_key(job)]:
                agent = self.labels(run).get('stampede.agent') or self.labels(run).get('stampede.role')
                if agent and agent.startswith(('lead', 'build')):
                    with self.subTest(job=name, agent=agent):
                        program = self.program(run)
                        self.assertEqual(program[program.index('--add-dir') + 1], str(job))
                        self.assertEqual(self.option(run, '--cwd'), str(self.repo), 'it starts in the repo')

    def test_a_job_made_in_the_repo_before_the_rule_still_works(self):
        """An open .herdr-<slug> job, as the code before the one folder rule left it (in the repo, no workdir file):
        its helpers start in the repo, and tell, snapshot, reopen and finish take it."""
        for relay in (False, True):
            old = self.repo / ('.herdr-' + ('relay' if relay else 'native'))
            with mock.patch.object(job_, 'new_folder', return_value=(old, old.name[len('.herdr-'):])):
                code, out = self.quiet(cli_.new, str(self.ask), None, core=True, relay=relay, cwd=str(self.repo))
            self.assertEqual(code, 0, out)
            (old / 'workdir').unlink()
            with self.subTest(relay=relay):
                self.assertEqual(job_.workdir(old), self.repo)
                code, out = self.quiet(cli_.start, old, 'build-api', 'claude', None, str(self.brief(old, 'build-api')))
                self.assertEqual(code or 0, 0, out)
                run = [r for r in self.calls('run') if self.labels(r).get('stampede.agent') == 'build-api'][-1]
                self.assertEqual(self.option(run, '--cwd'), str(self.repo))
                self.assertRegex(self.quiet(owner_.tell, old, 'build-api', 'hello')[1], '^(SUBMITTED|DELIVERED) build-api')
                if relay:
                    job_.snapshot(old)
                    self.quiet(relay_.reopen, old)
                else:
                    self.quiet(native_.snapshot, old)
                    self.quiet(native_.reopen, old)
                self.assertTrue((old / 'reopen.sh').is_file())
                self.assertIn('FINISHED', self.quiet(owner_.finish, old, 'done')[1])
            for address, terminal in self.state()['terminals'].items():
                if terminal['state'] == 'live':
                    self.terminal(address, state='finished', reason='killed')


class Roles(Choices):
    def start(self, name, *flags):
        self.quiet(cli_.new, str(self.ask), None, core=True, cwd=str(self.repo))
        brief = self.brief(self.job, name)
        code, out, err = self.main('start', self.job, name, '--brief', brief, *flags)
        self.assertEqual(code, 0, out + err)
        (run,) = [r for r in self.calls('run') if self.labels(r).get('stampede.agent') == name]
        return ' '.join(self.program(run)), json.loads((self.job / 'tree.json').read_text())['nodes'][name]

    def test_the_role_gives_the_kind_model_and_effort(self):
        argv, node = self.start('build-api')
        self.assertTrue(argv.split(' ', 1)[0].endswith('/claude'))
        self.assertIn('--model claude-opus-5-5 --effort medium', argv)
        self.assertEqual((node['kind'], node['model'], node['effort']), ('claude', 'claude-opus-5-5', 'medium'), 'the reopen record')

    def test_review_is_codex(self):
        argv, _ = self.start('review-api')
        self.assertIn('-m gpt-6.2-astra -c model_reasoning_effort="medium"', argv)  # every worker at medium, the reviewer too

    def test_a_jobs_role_effort_and_one_workers_own(self):
        code, out, err = self.new('--core', '--set', 'roles.research.effort=high')  # per job: saved in its settings.json
        self.assertEqual(code, 0, out + err)
        settings_.SETS.clear()
        for name, flags, want in (('research-web', (), 'high'), ('research-api', ('--effort', 'max'), 'max'), ('build-api', (), 'medium')):
            code, out, err = self.main('start', self.job, name, '--brief', self.brief(self.job, name), *flags)
            self.assertEqual(code, 0, out + err)
            (run,) = [r for r in self.calls('run') if self.labels(r).get('stampede.agent') == name]
            self.assertIn(f'--effort {want}', ' '.join(self.program(run)), name)

    def test_an_unknown_role_takes_roles_default(self):
        self.config('[roles.default]\nmodel = "claude-sonnet-5-5"\neffort = "low"\n')
        argv, _ = self.start('zzz-api')
        self.assertIn('--model claude-sonnet-5-5 --effort low', argv)

    def test_a_config_role_and_a_flag(self):
        self.config('[roles.build]\nkind = "codex"\nmodel = "gpt-6.2-sol"\neffort = "medium"\n')
        argv, _ = self.start('build-api', '--effort', 'high')
        self.assertIn('-m gpt-6.2-sol -c model_reasoning_effort="high"', argv, 'the flag wins')

    def test_a_kind_flag_drops_the_roles_model_of_another_cli(self):
        argv, _ = self.start('build-api', '--kind', 'codex')
        self.assertNotIn('claude-opus', argv)
        self.assertNotIn('-m ', argv)

    def test_a_users_own_role(self):
        self.config('[roles.docs]\nkind = "claude"\nmodel = "claude-sonnet-5-5"\neffort = "high"\n')
        self.assertEqual(settings_.current().get('roles.docs.effort'), 'high')
        argv, _ = self.start('docs-readme')
        self.assertIn('--model claude-sonnet-5-5 --effort high', argv)
        self.config('[roles.docs]\nkind = 3\n')
        self.assertIn('roles.docs.kind must be a str', settings_.current().problems[0])

    def test_b1_a_role_with_only_a_model_or_only_an_effort_takes_the_rest_from_default(self):
        self.config('[roles.docs]\nmodel = "claude-sonnet-5-5"\n[roles.lint]\neffort = "low"\n')
        argv, node = self.start('docs-api')
        self.assertIn('--model claude-sonnet-5-5 --effort medium', argv)
        self.assertEqual((node['kind'], node['model'], node['effort']), ('claude', 'claude-sonnet-5-5', 'medium'))
        brief = self.brief(self.job, 'lint-web')
        self.assertEqual(self.main('start', self.job, 'lint-web', '--brief', brief)[0], 0)
        node = json.loads((self.job / 'tree.json').read_text())['nodes']['lint-web']
        self.assertEqual((node['kind'], node['model'], node['effort']), ('claude', 'claude-opus-5-5', 'low'))

    def test_b2_kind_codex_on_a_role_with_no_kind_gets_no_claude_model(self):
        self.config('[roles.docs]\nmodel = "claude-sonnet-5-5"\n')
        argv, node = self.start('docs-api', '--kind', 'codex')
        self.assertTrue(argv.split(' ', 1)[0].endswith('/codex'))
        self.assertNotIn('claude-sonnet', argv)
        self.assertNotIn('-m ', argv)
        self.assertEqual((node['kind'], node['model'], node['effort']), ('codex', None, None))

    def test_a_program_takes_no_role(self):
        self.quiet(cli_.new, str(self.ask), None, core=True, cwd=str(self.repo))
        code, out, err = self.main('start', self.job, 'build-ci', '--', 'sleep', '1')
        self.assertEqual(code, 0, out + err)
        node = json.loads((self.job / 'tree.json').read_text())['nodes']['build-ci']
        self.assertEqual((node['kind'], node['model'], node['effort']), ('program', None, None))


class RoleValues(unittest.TestCase):
    """cli.role_values: each of kind, model and effort by itself, the flag, else the role's, else roles.default's; a
    table's model and effort only with that table's kind (its own, else roles.default.kind)."""
    DEFAULT = {'roles.default.kind': 'claude', 'roles.default.model': 'claude-opus-5-5', 'roles.default.effort': 'medium'}
    ROLES = {'all': {'kind': 'codex', 'model': 'gpt-6.2-sol', 'effort': 'high'}, 'model': {'model': 'claude-sonnet-5-5'},
             'effort': {'effort': 'low'}, 'kind': {'kind': 'codex'}, 'none': {}}

    def resolve(self, role, kind):
        values = dict(self.DEFAULT)
        values.update({f'roles.{role}.{k}': v for k, v in self.ROLES.get(role, {}).items()})
        return cli_.role_values(values, role, kind, None, None)

    def test_the_table(self):
        D = ('claude-opus-5-5', 'medium')
        want = {  # role -> {--kind: (kind, model, effort)}; None is no --kind
            'all': {None: ('codex', 'gpt-6.2-sol', 'high'), 'codex': ('codex', 'gpt-6.2-sol', 'high'), 'claude': ('claude', *D)},
            'model': {None: ('claude', 'claude-sonnet-5-5', 'medium'), 'claude': ('claude', 'claude-sonnet-5-5', 'medium'),
                      'codex': ('codex', None, None)},
            'effort': {None: ('claude', 'claude-opus-5-5', 'low'), 'claude': ('claude', 'claude-opus-5-5', 'low'),
                       'codex': ('codex', None, None)},
            'kind': {None: ('codex', None, None), 'codex': ('codex', None, None), 'claude': ('claude', *D)},
            'none': {None: ('claude', *D), 'claude': ('claude', *D), 'codex': ('codex', None, None)},
            'unknown': {None: ('claude', *D), 'claude': ('claude', *D), 'codex': ('codex', None, None)}}
        for role, cases in want.items():
            for kind, expected in cases.items():
                with self.subTest(role=role, kind=kind):
                    self.assertEqual(self.resolve(role, kind), expected)

    def test_a_flag_always_wins(self):
        values = {**self.DEFAULT, 'roles.all.kind': 'codex', 'roles.all.model': 'gpt-6.2-sol'}
        self.assertEqual(cli_.role_values(values, 'all', None, 'gpt-6.2-astra', 'max'), ('codex', 'gpt-6.2-astra', 'max'))


class Lead(Choices):
    def test_lead_model_and_effort_flags_set_the_lead_cli_pair(self):
        code, out, err = self.new('--core', '--lead-model', 'claude-fable-5-2', '--lead-effort', 'max')
        self.assertEqual(code, 0, err)
        self.assertIn('--model claude-fable-5-2 --effort max', ' '.join(self.lead_run()))
        saved = json.loads((self.job / 'settings.json').read_text())
        self.assertEqual((saved['values']['lead.claude.model'], saved['sources']['lead.claude.model']), ('claude-fable-5-2', 'flag'))
        self.assertEqual(saved['values']['lead.codex.model'], 'gpt-6.2-sol', 'the other CLI keeps its own')

    def test_a_codex_lead_takes_them_too(self):
        code, out, err = self.new('--core', '--lead', 'codex', '--lead-effort', 'high')
        self.assertEqual(code, 0, err)
        self.assertIn('-m gpt-6.2-sol -c model_reasoning_effort="high"', ' '.join(self.lead_run()))


    def test_a_forbidden_lead_model_is_refused_before_anything_is_made(self):
        root = job_.jobs_root() / 'jobs'
        cases = (('the default', '', {}, ()), ('--lead-model', '', {}, ('--lead-model', 'claude-fable-5-2')),
                 ('the user file', '[lead.claude]\nmodel = "claude-fable-5-2"\n', {}, ()),
                 ('the environment', '', {'FLEET_LEAD_MODEL': 'claude-fable-5-2'}, ()),
                 ('a codex lead', '', {}, ('--lead', 'codex')))
        for how, user, env, flags in cases:
            model = 'gpt-6.2-sol' if 'codex' in flags else 'claude-opus-5-5' if how == 'the default' else 'claude-fable-5-2'
            for forbid in (f'[lead]\nforbid = ["{model}"]\n', None):
                with self.subTest(how=how, forbid=forbid):
                    self.config(user + (forbid or ''))
                    env_ = {**env, 'FLEET_LEAD_FORBID': '' if forbid else f'other, {model}'}
                    code, out, err = self.new('--core', *flags, env=env_)
                    self.assertEqual(code, 2, out + err)
                    self.assertIn(f'the lead may not run on {model} (lead.forbid)', err)
                    self.assertFalse(root.exists() and list(root.iterdir()))
                    self.assertEqual(self.calls('run'), [])
        self.config('[lead]\nforbid = ["claude-fable-5-2"]\n')                  # another model leads, and a worker is not checked
        code, out, err = self.new('--core')
        self.assertEqual(code, 0, err)
        self.assertNotIn('lead.forbid', json.loads((self.job / 'settings.json').read_text())['values'])
        code, out, err = self.main('start', self.job, 'build-x', '--model', 'claude-fable-5-2', '--brief', self.brief(self.job, 'build-x'))
        self.assertEqual(code, 0, out + err)

    def test_a_lead_model_off_lead_allow_is_refused_before_anything_is_made(self):
        root = job_.jobs_root() / 'jobs'
        allow = '[lead]\nallow = ["claude-opus-5-5", "gpt-6.2-sol"]\n'
        for how, user, env, flags in (('--lead-model', '', {}, ('--lead-model', 'claude-sonnet-5-5')),
                                      ('the environment', '', {'FLEET_LEAD_MODEL': 'claude-sonnet-5-5'}, ())):
            with self.subTest(how=how):
                self.config(allow + user)
                code, out, err = self.new('--core', *flags, env=env)
                self.assertEqual(code, 2, out + err)
                self.assertIn('the lead may not run on claude-sonnet-5-5 (lead.allow', err)
                self.assertFalse(root.exists() and list(root.iterdir()))
                self.assertEqual(self.calls('run'), [])
        self.config(allow)                                                       # a model on the list leads
        code, out, err = self.new('--core')
        self.assertEqual(code, 0, err)
        self.assertNotIn('lead.allow', json.loads((self.job / 'settings.json').read_text())['values'])

    def test_a_repo_never_sets_lead_forbid(self):
        (self.repo / '.stampede.toml').write_text('[lead]\nforbid = ["claude-opus-5-5"]\n')
        settings = settings_.load(repo=self.repo, env={})
        self.assertEqual(settings.get('lead.forbid'), [])
        self.assertIn('lead.forbid is taken only from your own', ' '.join(settings.problems))

    def test_lead_allow_checks_the_file_layers_set_and_other_cli_default(self):
        allow = '[lead]\nallow = ["claude-opus-5-5"]\n'
        sonnet = '[lead.claude]\nmodel = "claude-sonnet-5-5"\n'
        root = job_.jobs_root() / 'jobs'
        for user, repo, flags, model in (
                (sonnet, '', (), 'claude-sonnet-5-5'),
                ('[lead.codex]\nmodel = "gpt-6.2-astra"\n', '', ('--lead', 'codex'), 'gpt-6.2-astra'),
                ('', sonnet, (), 'claude-sonnet-5-5'),
                ('', '', ('--set', 'lead.claude.model=claude-sonnet-5-5'), 'claude-sonnet-5-5'),
                ('', '', ('--lead', 'codex'), 'gpt-6.2-sol')):
            with self.subTest(user=user, repo=repo, flags=flags):
                self.config(allow + user)
                (self.repo / '.stampede.toml').write_text(repo)
                code, out, err = self.new('--core', *flags)
                self.assertEqual(code, 2, out + err)
                self.assertIn(f'the lead may not run on {model} (lead.allow: claude-opus-5-5)', err)
                self.assertFalse(root.exists() and list(root.iterdir()))
                self.assertEqual(self.calls('run'), [])

    def test_lead_allow_from_the_environment_and_forbid_wins(self):
        env = {'FLEET_LEAD_ALLOW': ' claude-fable-5-2 , gpt-6.2-astra, '}
        code, _, err = self.new('--core', env=env)
        self.assertEqual(code, 2, err)
        self.assertIn('(lead.allow: claude-fable-5-2, gpt-6.2-astra)', err)
        self.config('[lead]\nforbid = ["claude-fable-5-2"]\n')
        flags = ('--core', '--lead-model', 'claude-fable-5-2')
        code, _, err = self.new(*flags, env=env)
        self.assertEqual(code, 2, err)
        self.assertIn('the lead may not run on claude-fable-5-2 (lead.forbid)', err)
        self.assertEqual(self.calls('run'), [])
        self.config('')
        code, _, err = self.new(*flags, env=env)
        self.assertEqual(code, 0, err)
        self.assertIn('--model claude-fable-5-2 --effort xhigh', ' '.join(self.lead_run()))

    def test_restarted_leads_check_live_allow_and_forbid_on_tui_and_core(self):
        job, _ = self.core_job()
        brief = job / 'briefs/lead-demo.md'
        for backend in ('tui', 'core'):
            (job / 'backend').write_text(backend + '\n')
            for rule, config in (('lead.allow: claude-opus-5-5', 'allow = ["claude-opus-5-5"]\n'),
                                 ('lead.forbid', 'forbid = ["claude-fable-5-2"]\n')):
                with self.subTest(backend=backend, rule=rule):
                    self.config('[lead]\n' + config)
                    pane = ('--pane', 'w1:p1') if backend == 'tui' else ()
                    code, out, err = self.main('start', job, 'lead-demo', '--kind', 'claude', '--model', 'claude-fable-5-2',
                                               '--brief', brief, *pane)
                    self.assertEqual(code, 2, out + err)
                    self.assertIn(f'the lead may not run on claude-fable-5-2 ({rule})', err)
                    self.assertEqual(self.calls('run'), [])


class RelayReopenPolicy(Choices):
    def test_relay_reopen_preflights_lead_and_worker_before_the_follower_starts(self):
        code, out, err = self.new('--core', '--relay')
        self.assertEqual(code, 0, out + err)
        code, out, err = self.main('start', self.job, 'review-api', '--brief', self.brief(self.job, 'review-api'))
        self.assertEqual(code, 0, out + err)
        before = self.calls('run')
        self.config('[lead]\nforbid = ["claude-opus-5-5"]\n')
        code, out, err = self.main('_reopen', self.job)
        self.assertEqual(code, 0, out + err)  # the disallowed lead is still live
        for address in self.state()['terminals']:
            self.terminal(address, state='finished')
        for text, name, rule in (
                ('[lead]\nforbid = ["claude-opus-5-5"]\n', LEAD, 'lead.forbid'),
                ('[lead]\nallow = ["claude-opus-5-5"]\n[workers]\nforbid = ["gpt-6.2-astra"]\n', 'review-api', 'workers.forbid')):
            self.config(text)
            for flags in ((), ('--fresh',)):
                with self.subTest(name=name, flags=flags):
                    code, out, err = self.main('_reopen', self.job, *flags)
                    self.assertEqual(code, 2, out + err)
                    self.assertEqual(out, '')
                    self.assertTrue(err.startswith(f'REFUSED {name}: '), err)
                    self.assertIn(rule, err)
                    self.assertIn('nothing started. Change the list or limit in your own config', err)
                    self.assertEqual(self.calls('run'), before)

    def test_relay_skips_a_changed_record_and_continues_with_the_next_agent(self):
        code, out, err = self.new('--core', '--relay')
        self.assertEqual(code, 0, out + err)
        for name in ('review-api', 'qa-api'):
            code, out, err = self.main('start', self.job, name, '--brief', self.brief(self.job, name))
            self.assertEqual(code, 0, out + err)
            self.terminal(self.entries(self.job)[name]['address'], state='finished')
        self.config('[workers]\nforbid = ["gpt-6.2-sol"]\n')
        before = len(self.calls('run'))
        original = job_.launching

        @contextlib.contextmanager
        def changed_record(job, name):
            with original(job, name):
                if name == 'review-api':
                    job_.record(job, name, 'codex', self.brief(job, name), ['-m', 'gpt-6.2-sol'])
                yield

        with mock.patch.object(job_, 'launching', changed_record):
            code, out, err = self.main('_reopen', self.job)
        self.assertEqual(code, 1, out + err)
        self.assertIn('SKIPPED review-api (its record changed during reopen: run reopen again)', out)
        self.assertEqual([self.labels(run)['stampede.agent'] for run in self.calls('run')[before:]], ['qa-api'])

    def test_codex_model_flag_takes_precedence_over_config_regardless_of_order(self):
        config = ('--config', 'model = "gpt-6.2-astra"')
        model = ('-m', 'gpt-6.2-sol')
        for args in (config + model, model + config):
            self.assertEqual(agents_.model_effort('codex', args), ('gpt-6.2-sol', None))
        self.assertEqual(agents_.model_effort('codex', ('-c', 'model=gpt-6.2-sol', *config)), ('gpt-6.2-astra', None))


class WorkerPolicy(Choices):
    def test_start_checks_worker_role_defaults_and_flags_on_every_backend(self):
        job, _ = self.core_job()
        self.config('[workers]\nforbid = ["claude-opus-5-5"]\nmax_effort = "medium"\n')
        brief = self.brief(job, 'build-x')
        for backend, pane in (('tui', ('--pane', 'w1:p1')), ('core', ()), ('core', ('--pane', 'w1:p1')), ('native', ())):
            (job / 'backend').write_text(backend + '\n')
            for flags, message in (
                    ((), 'may not run on claude-opus-5-5 (workers.forbid)'),
                    (('--model', 'claude-sonnet-5-5', '--effort', 'high'), 'may not run at high effort (workers.max_effort: medium)'),
                    (('--model', 'claude-sonnet-5-5', '--effort', 'custom'), 'may not run at custom effort (workers.max_effort: medium)')):
                with self.subTest(backend=backend, pane=pane, flags=flags):
                    code, out, err = self.main('start', job, 'build-x', '--brief', brief, *pane, *flags)
                    self.assertEqual(code, 2, out + err)
                    self.assertIn('build-x ' + message, err)
                    self.assertEqual(self.calls('run'), [])

    def test_native_workers_at_the_cap_or_without_a_cap_can_start(self):
        code, _, err = self.new('--core')
        self.assertEqual(code, 0, err)
        for name, config, flags in (('build-at-cap', '[workers]\nmax_effort = "medium"\n', ()),
                                    ('build-no-cap', '', ('--effort', 'ultra'))):
            with self.subTest(name=name):
                self.config(config)
                code, out, err = self.main('start', self.job, name, '--brief', self.brief(self.job, name), *flags)
                self.assertEqual(code, 0, out + err)
                self.assertIn(f'STARTED {name}', out)
        self.config('[workers]\nforbid = ["claude-opus-5-5"]\nmax_effort = "none"\n')
        code, out, err = self.main('start', self.job, 'build-program', '--', 'sleep', '60')
        self.assertEqual(code, 0, out + err)
        self.assertIn('STARTED build-program', out)

    def test_switching_cli_requires_resolved_values_when_a_worker_limit_is_set(self):
        code, _, err = self.new('--core')
        self.assertEqual(code, 0, err)
        brief = self.brief(self.job, 'build-x')
        args = ('start', self.job, 'build-x', '--brief', brief, '--kind', 'codex')
        self.config('[workers]\nforbid = ["gpt-6.2-astra"]\n')
        code, out, err = self.main(*args)
        self.assertEqual(code, 2, out + err)
        self.assertIn('build-x has no model to check against workers.forbid: name one with --model', err)
        self.config('[workers]\nmax_effort = "medium"\n')
        code, out, err = self.main(*args)
        self.assertEqual(code, 2, out + err)
        self.assertIn('build-x has no effort to check against workers.max_effort: name one with --effort', err)
        self.config('[workers]\nforbid = ["gpt-6.2-astra"]\n')
        code, out, err = self.main(*args, '--model', 'gpt-6.2-sol')
        self.assertEqual(code, 0, out + err)
        self.assertIn('STARTED build-x', out)

    def test_queued_native_helper_uses_the_policy_in_force_when_it_launches(self):
        code, out, err = self.new('--core', '--max-helpers', '1')
        self.assertEqual(code, 0, out + err)
        for name, status in (('build-first', 'STARTED'), ('build-waiting', 'QUEUED')):
            code, out, err = self.main('start', self.job, name, '--brief', self.brief(self.job, name))
            self.assertEqual(code, 0, out + err)
            self.assertIn(f'{status} {name}', out)
        self.config('[workers]\nforbid = ["claude-opus-5-5"]\n')
        self.terminal('t2', state='finished')
        before = self.calls('run')
        code, out, err = self.main('next', self.job)
        self.assertEqual(code, 1, out + err)
        self.assertIn('FAILED build-waiting (build-waiting may not run on claude-opus-5-5 (workers.forbid))', out)
        self.assertEqual(self.calls('run'), before)
        self.assertEqual(native_.queued(self.job), [])

    def test_core_launch_uses_the_callers_xdg_config_home_when_set(self):
        job, _ = self.core_job()
        self.assertFalse(any(arg.startswith('XDG_CONFIG_HOME=') for arg in hcapi_.launch_env(job)))
        config_home = self.root / 'custom config'
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config_home)}):
            self.assertIn(f'XDG_CONFIG_HOME={config_home}', hcapi_.launch_env(job))
        prefix = hcapi_.launch_env(job)  # a core with its own XDG_CONFIG_HOME: the terminal follows the caller, who has none
        seen = subprocess.run(prefix + ['/usr/bin/printenv', 'XDG_CONFIG_HOME'], capture_output=True, text=True,
                              env={**os.environ, 'XDG_CONFIG_HOME': str(self.root / 'core config')})
        self.assertEqual((seen.returncode, seen.stdout), (1, ''))

    def test_a_bad_cap_is_a_config_problem(self):
        self.config('[workers]\nmax_effort = "custom"\n')
        code, out, _ = self.main('config', 'show')
        self.assertEqual(code, 1)
        self.assertIn('workers.max_effort must be one of none, minimal, low, medium, high, xhigh, max, ultra, ""', out)
        code, _, err = self.new('--core')
        self.assertEqual(code, 2, err)
        self.assertIn('workers.max_effort must be one of', err)


class Layout(Choices):
    def places(self):
        return [(t['labels']['stampede.pane'], t['labels'].get('stampede.split'), t['labels'].get('stampede.beside'))
                for t in self.state()['terminals'].values() if t['state'] == 'live']

    def run_four(self):
        self.quiet(cli_.new, str(self.ask), None, core=True, cwd=str(self.repo))
        for n in range(1, 4):
            self.quiet(cli_.start, self.job, f'h{n}', 'claude', None, str(self.brief(self.job, f'h{n}')))
        return self.places()

    def test_grid_is_the_default(self):
        self.assertEqual(self.run_four(), [('1', None, None), ('2', 'right', LEAD), ('3', 'down', 'h1'), ('4', 'down', LEAD)])

    def test_columns(self):
        self.config('[helpers]\nlayout = "columns"\n')
        self.assertEqual(self.run_four(), [('1', None, None), ('2', 'right', LEAD), ('3', 'right', 'h1'), ('4', 'right', 'h2')])

    def test_rows_from_set(self):
        self.config('[helpers]\nlayout = "columns"\n')
        settings_.SETS[:] = ['helpers.layout=rows']
        self.assertEqual(self.run_four(), [('1', None, None), ('2', 'down', LEAD), ('3', 'down', 'h1'), ('4', 'down', 'h2')])


class Review(Choices):
    def briefs(self):
        self.quiet(cli_.new, str(self.ask), None, name='n', core=True, cwd=str(self.repo))
        self.quiet(cli_.new, str(self.ask), None, name='r', core=True, relay=True, cwd=str(self.repo))
        return [next((job_.jobs_root() / 'jobs').glob(f'*-{n}')) / 'briefs' / f'lead-{n}.md' for n in ('n', 'r')]

    def test_end_is_the_default_with_the_reviewer_of_roles_review(self):
        for brief in self.briefs():
            self.assertIn('Review: one review pass at the end of what ships or reaches the owner, by another model than the '
                          "builder's: start review-<scope>, which gets codex gpt-6.2-astra medium.", brief.read_text())

    def test_each_and_none(self):
        self.config('[review]\nstep = "each"\n[roles.review]\nkind = "claude"\nmodel = "claude-fable-5-2"\neffort = "max"\n')
        for brief in self.briefs():
            self.assertIn('one review pass for each pull request or step', brief.read_text())
            self.assertIn('claude claude-fable-5-2 max', brief.read_text())

    def test_none_from_set(self):
        settings_.SETS[:] = ['review.step=none']
        for brief in self.briefs():
            self.assertIn('the owner switched the review step off for this job', brief.read_text())


class Shown(Choices):
    def test_config_show_lists_every_new_key(self):
        result = subprocess.run([str(FLEET), 'config', 'show'], capture_output=True, text=True, cwd=self.root)
        for line in ('backend = "tui"  (default)', 'roles.build.kind = "claude"  (default)', 'roles.review.model = "gpt-6.2-astra"  (default)',
                     'helpers.layout = "grid"  (default)', 'review.step = "end"  (default)'):
            self.assertIn(line, result.stdout)


if __name__ == '__main__':
    unittest.main()
