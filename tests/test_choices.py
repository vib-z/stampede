"""The choices: backend, one job folder rule, roles, the lead's flags, the layout and the review step. For each key the
default is today's behaviour, a config value changes it, and a flag beats it. Every Core call goes to tests/fake_hc.py."""
import contextlib, io, json, os, subprocess, sys, unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, SCRIPTS, LEAD  # noqa: E402
from stampede import job as job_, native as native_, owner as owner_, relay as relay_, cli as cli_, settings as settings_, agents as agents_, \
    doctor as doctor_  # noqa: E402

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

    def test_auto_is_the_tui_inside_a_herdr_pane_and_core_elsewhere(self):
        self.assertEqual(self.choice(), (True, 'backend auto: not inside a Herdr pane'))
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (False, ''), 'inside Herdr, as today')
        self.assertEqual(self.choice(pane='w1:p1'), (False, ''), 'a TUI target is the TUI')
        code, out, err = self.new()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], f'on Herdr Core (backend auto: not inside a Herdr pane), repo {self.repo.resolve()}')
        self.assertEqual(out.splitlines()[-1], f'{LEAD} {self.job}')
        self.assertEqual(job_.backend(self.job), 'native')

    def test_tui_is_todays_error_and_core_runs_core_unless_a_tui_target_is_named(self):
        self.config('backend = "tui"\n')
        self.assertEqual(self.choice(), (False, ''))
        code, _, err = self.main('new', '--file', self.ask)
        self.assertEqual(code, 2)
        self.assertIn('new needs --workspace or --pane, or run it inside Herdr', err)
        self.config('backend = "core"\n')
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (True, 'backend core'))
            self.assertEqual(self.choice(workspace='w1'), (False, ''))
        settings_.SETS[:] = ['backend=tui']
        self.assertEqual(self.choice(), (False, ''), '--set beats the file')
        settings_.SETS.clear()
        (self.repo / '.stampede.toml').write_text('backend = "auto"\n')
        with mock.patch.dict(os.environ, {'HERDR_WORKSPACE_ID': 'w1'}):
            self.assertEqual(self.choice(), (False, ''), 'a repo\'s file beats the user\'s')

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
        with mock.patch.dict(os.environ, {'HC': '/nonexistent/hc'}):
            code, _, err = self.new()
        self.assertEqual(code, 2)
        self.assertIn('Herdr Core is not installed', err)
        self.assertIn('start Herdr Core (hc server start)', err)
        self.assertIn('pass --workspace or --pane', err)


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
        self.assertIn('-m gpt-6-astra -c model_reasoning_effort="ultra"', argv)

    def test_an_unknown_role_takes_roles_default(self):
        self.config('[roles.default]\nmodel = "claude-sonnet-5-5"\neffort = "low"\n')
        argv, _ = self.start('zzz-api')
        self.assertIn('--model claude-sonnet-5-5 --effort low', argv)

    def test_a_config_role_and_a_flag(self):
        self.config('[roles.build]\nkind = "codex"\nmodel = "gpt-6.1-sol"\neffort = "medium"\n')
        argv, _ = self.start('build-api', '--effort', 'high')
        self.assertIn('-m gpt-6.1-sol -c model_reasoning_effort="high"', argv, 'the flag wins')

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
    ROLES = {'all': {'kind': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'high'}, 'model': {'model': 'claude-sonnet-5-5'},
             'effort': {'effort': 'low'}, 'kind': {'kind': 'codex'}, 'none': {}}

    def resolve(self, role, kind):
        values = dict(self.DEFAULT)
        values.update({f'roles.{role}.{k}': v for k, v in self.ROLES.get(role, {}).items()})
        return cli_.role_values(values, role, kind, None, None)

    def test_the_table(self):
        D = ('claude-opus-5-5', 'medium')
        want = {  # role -> {--kind: (kind, model, effort)}; None is no --kind
            'all': {None: ('codex', 'gpt-6.1-sol', 'high'), 'codex': ('codex', 'gpt-6.1-sol', 'high'), 'claude': ('claude', *D)},
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
        values = {**self.DEFAULT, 'roles.all.kind': 'codex', 'roles.all.model': 'gpt-6.1-sol'}
        self.assertEqual(cli_.role_values(values, 'all', None, 'gpt-6-astra', 'max'), ('codex', 'gpt-6-astra', 'max'))


class Lead(Choices):
    def test_lead_model_and_effort_flags_set_the_lead_cli_pair(self):
        code, out, err = self.new('--core', '--lead-model', 'claude-fable-5-1', '--lead-effort', 'max')
        self.assertEqual(code, 0, err)
        self.assertIn('--model claude-fable-5-1 --effort max', ' '.join(self.lead_run()))
        saved = json.loads((self.job / 'settings.json').read_text())
        self.assertEqual((saved['values']['lead.claude.model'], saved['sources']['lead.claude.model']), ('claude-fable-5-1', 'flag'))
        self.assertEqual(saved['values']['lead.codex.model'], 'gpt-6-astra', 'the other CLI keeps its own')

    def test_a_codex_lead_takes_them_too(self):
        code, out, err = self.new('--core', '--lead', 'codex', '--lead-effort', 'high')
        self.assertEqual(code, 0, err)
        self.assertIn('-m gpt-6-astra -c model_reasoning_effort="high"', ' '.join(self.lead_run()))


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
                          "builder's: start review-<scope>, which gets codex gpt-6-astra ultra.", brief.read_text())

    def test_each_and_none(self):
        self.config('[review]\nstep = "each"\n[roles.review]\nkind = "claude"\nmodel = "claude-fable-5-1"\neffort = "max"\n')
        for brief in self.briefs():
            self.assertIn('one review pass for each pull request or step', brief.read_text())
            self.assertIn('claude claude-fable-5-1 max', brief.read_text())

    def test_none_from_set(self):
        settings_.SETS[:] = ['review.step=none']
        for brief in self.briefs():
            self.assertIn('the owner switched the review step off for this job', brief.read_text())


class Shown(Choices):
    def test_config_show_lists_every_new_key(self):
        result = subprocess.run([str(FLEET), 'config', 'show'], capture_output=True, text=True, cwd=self.root)
        for line in ('backend = "auto"  (default)', 'roles.build.kind = "claude"  (default)', 'roles.review.model = "gpt-6-astra"  (default)',
                     'helpers.layout = "grid"  (default)', 'review.step = "end"  (default)'):
            self.assertIn(line, result.stdout)


if __name__ == '__main__':
    unittest.main()
