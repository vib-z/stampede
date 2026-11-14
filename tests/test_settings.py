"""stampede/settings.py: layers, sources, the environment names, problems, show, and the two TOML readers."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / 'skills' / 'herdr-fleet' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from stampede import settings as st, agents as agents_, job as job_, owner as owner_, hcapi as hcapi_, native as native_, cli as cli_, relay as relay_, doctor as doctor_

SAMPLE = '''# a user file
jobs_root = "~/jobs"   # a comment after a value
lead.kind = 'codex'
[lead.claude]
model = "claude-fable-5-1"
[brief]
sections = [
  "Goal",  # one
  "Why",
]
[helpers]
max = 6
[timeouts]
wait = 1_800
[other]
ratio = 0.5
on = true
list = [1, -2, 3e2, "a \\"b\\""]
'''
# the table in skills/herdr-fleet/SKILL.md, Pick the agent and model: builders at medium, review on the other vendor
ROLES = {'default': ('claude', 'claude-opus-5-5', 'medium'), 'build': ('claude', 'claude-opus-5-5', 'medium'),
         'research': ('claude', 'claude-opus-5-5', 'xhigh'), 'review': ('codex', 'gpt-6-astra', 'ultra'),
         'design': ('codex', 'gpt-6-astra', 'ultra'), 'qa': ('codex', 'gpt-6-astra', 'ultra'),
         'copy': ('claude', 'claude-opus-5-5', 'high'), 'test': ('claude', 'claude-sonnet-5-5', 'medium')}


class Settings(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.home, self.repo = self.dir / 'home', self.dir / 'repo'
        (self.home / '.config' / 'stampede').mkdir(parents=True)
        self.repo.mkdir()

    def write(self, where, text):
        path = self.home / '.config' / 'stampede' / 'config.toml' if where == 'user' else self.repo / '.stampede.toml'
        path.write_text(text)
        return path

    def load(self, env=None, **kw):
        return st.load(repo=self.repo, env=env or {}, home=self.home, **kw)

    def test_defaults_are_todays_values(self):
        s = self.load()
        self.assertEqual(s.values, {
            'backend': 'auto', 'jobs_root': '~/code/herdr-jobs', 'trust_root': '~/code', 'lead.kind': 'claude',
            'lead.claude.model': 'claude-opus-5-5', 'lead.claude.effort': 'xhigh',
            'lead.codex.model': 'gpt-6-astra', 'lead.codex.effort': 'ultra',
            'ask.command': 'moshi-hook ask --require-remote --source herdr-fleet --timeout 24h',
            'brief.sections': ['Goal', 'Why', 'Inputs', 'Constraints', 'Done when', 'Report back', 'If blocked'],
            **{f'roles.{role}.{field}': value for role, row in ROLES.items() for field, value in zip(('kind', 'model', 'effort'), row)},
            'review.step': 'end', 'helpers.max': 12, 'helpers.layout': 'grid', 'helpers.tab_panes': 4,
            'timeouts.wait': 3600, 'timeouts.hc_call': 60, 'timeouts.leave': 15, 'timeouts.hold_settle': 5,
            'alerts.helpers': False})
        self.assertEqual(set(s.sources.values()), {'default'})
        self.assertEqual(s.problems, [])
        self.assertEqual(s.files, {'user': {'path': str(self.home / '.config/stampede/config.toml'), 'exists': False},
                                   'repo': {'path': str(self.repo / '.stampede.toml'), 'exists': False}})

    def test_each_layer_overrides_the_one_below(self):
        self.write('user', '[helpers]\nmax = 5\n')
        self.write('repo', '[helpers]\nmax = 6\n')
        env = {'STAMPEDE_MAX_HELPERS': '7'}
        self.assertEqual((self.load(env).get('helpers.max'), self.load(env).source('helpers.max')), (7, 'env:STAMPEDE_MAX_HELPERS'))
        s = self.load(env, flags={'helpers.max': 8})
        self.assertEqual((s.get('helpers.max'), s.source('helpers.max')), (8, 'flag'))
        s = self.load(env, flags={'helpers.max': 8}, sets=['helpers.max=9'])
        self.assertEqual((s.get('helpers.max'), s.source('helpers.max')), (9, 'set'))
        s = self.load(env, flags={'helpers.max': None})  # a flag not given leaves the layer below
        self.assertEqual(s.source('helpers.max'), 'env:STAMPEDE_MAX_HELPERS')
        (self.repo / '.stampede.toml').unlink()
        self.assertEqual(self.load().source('helpers.max'), 'user')
        self.write('repo', '[helpers]\nmax = 6\n')
        self.assertEqual(self.load().source('helpers.max'), 'repo')

    def test_a_key_in_several_layers_reports_each_winner(self):
        self.write('user', 'lead.kind = "codex"\n[timeouts]\nwait = 10\nleave = 20\n')
        self.write('repo', '[timeouts]\nwait = 30\n')
        s = self.load({'FLEET_LEAD_KIND': 'claude'}, sets=['timeouts.hc_call=5'])
        self.assertEqual({k: s.source(k) for k in ('lead.kind', 'timeouts.wait', 'timeouts.leave', 'timeouts.hc_call',
                                                    'timeouts.hold_settle')},
                         {'lead.kind': 'env:FLEET_LEAD_KIND', 'timeouts.wait': 'repo', 'timeouts.leave': 'user',
                          'timeouts.hc_call': 'set', 'timeouts.hold_settle': 'default'})

    def test_every_environment_name(self):
        for name, key, text, value in (('FLEET_LEAD_KIND', 'lead.kind', 'codex', 'codex'),
                                       ('FLEET_ASK_CMD', 'ask.command', 'ask-me now', 'ask-me now'),
                                       ('FLEET_JOBS_ROOT', 'jobs_root', '~/j', '~/j'),
                                       ('FLEET_TRUST_ROOT', 'trust_root', '~/t', '~/t'),
                                       ('STAMPEDE_MAX_HELPERS', 'helpers.max', '3', 3),
                                       ('STAMPEDE_TAB_PANES', 'helpers.tab_panes', '2', 2)):
            with self.subTest(name=name):
                s = self.load({name: text})
                self.assertEqual((s.get(key), s.source(key)), (value, 'env:' + name))
                self.assertEqual(self.load({name: ''}).source(key), 'default', 'an empty one means unset')
        self.assertEqual(set(st.ENV), {'FLEET_LEAD_KIND', 'FLEET_ASK_CMD', 'FLEET_JOBS_ROOT', 'FLEET_TRUST_ROOT',
                                       'STAMPEDE_MAX_HELPERS', 'STAMPEDE_TAB_PANES'})

    def test_the_lead_model_and_effort_set_the_pair_of_the_cli_their_model_names(self):
        """The cases of fleet_job.lead_model's own test: a gpt model sets the Codex pair, any other the Claude pair."""
        for env, codex, claude in (
                ({}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'xhigh')),
                ({'FLEET_LEAD_MODEL': 'claude-opus-5-5', 'FLEET_LEAD_EFFORT': 'xhigh'}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'xhigh')),
                ({'FLEET_LEAD_MODEL': 'opus', 'FLEET_LEAD_EFFORT': 'max'}, ('gpt-6-astra', 'ultra'), ('opus', 'max')),
                ({'FLEET_LEAD_EFFORT': 'high'}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'high')),
                ({'FLEET_LEAD_MODEL': 'gpt-6.1-sol', 'FLEET_LEAD_EFFORT': 'xhigh'}, ('gpt-6.1-sol', 'xhigh'), ('claude-opus-5-5', 'xhigh'))):
            with self.subTest(env=env):
                s = self.load(env)
                self.assertEqual((s.get('lead.codex.model'), s.get('lead.codex.effort')), codex)
                self.assertEqual((s.get('lead.claude.model'), s.get('lead.claude.effort')), claude)
        s = self.load({'FLEET_LEAD_MODEL': 'gpt-6.1-sol', 'FLEET_LEAD_EFFORT': 'xhigh'})
        self.assertEqual((s.source('lead.codex.model'), s.source('lead.codex.effort'), s.source('lead.claude.effort')),
                         ('env:FLEET_LEAD_MODEL', 'env:FLEET_LEAD_EFFORT', 'default'))

    def test_set_values_of_each_type(self):
        for pair, want in (('helpers.max=6', ('helpers.max', 6)), ('a.b=0.5', ('a.b', 0.5)), ('a.b=true', ('a.b', True)),
                           ('lead.kind="codex"', ('lead.kind', 'codex')), ('lead.kind=codex', ('lead.kind', 'codex')),
                           ('ask.command=ask me --now', ('ask.command', 'ask me --now')),
                           ('brief.sections=["Goal", "Why"]', ('brief.sections', ['Goal', 'Why']))):
            with self.subTest(pair=pair):
                self.assertEqual(st.parse_set(pair), want)
        for bad in ('helpers.max', '=6', 'helpers.max=', 'bad key=1'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'key=value'):
                st.parse_set(bad)
        s = self.load(sets=['brief.sections=["Goal"]', 'lead.kind=codex'])
        self.assertEqual((s.get('brief.sections'), s.get('lead.kind'), s.problems), (['Goal'], 'codex', []))

    def test_an_unknown_key_a_wrong_type_and_a_bad_file_are_one_problem_each(self):
        user = self.write('user', '[helpers]\nmaxx = 3\n')
        s = self.load()
        self.assertEqual(s.problems, [f'{user}: helpers.maxx is not a setting (did you mean helpers.max?); skipped'])
        self.write('user', '[helpers]\nmax = "six"\n')
        self.assertEqual(self.load().problems, [f"{user}: helpers.max must be int, not 'six'; skipped"])
        self.write('user', 'brief.sections = [1]\n')
        self.assertEqual(self.load().problems, [f'{user}: brief.sections must be a list of str, not [1]; skipped'])
        self.write('user', '[helpers\nmax = 3\n')
        s = self.load()
        self.assertEqual(len(s.problems), 1)
        self.assertIn(f'{user}: not readable TOML', s.problems[0])
        self.assertEqual(s.source('helpers.max'), 'default')
        s = self.load({'STAMPEDE_TAB_PANES': 'four'}, flags={'helpers.max': '6'}, sets=['timeouts.wait=soon'])
        self.assertEqual(s.problems, [self.load().problems[0], "environment STAMPEDE_TAB_PANES: helpers.tab_panes must be int, not 'four'; skipped",
                                      "flag helpers.max: helpers.max must be int, not '6'; skipped",
                                      "--set timeouts.wait=soon: timeouts.wait must be int, not 'soon'; skipped"])
        self.assertEqual(s.get('helpers.tab_panes'), 4)

    def test_a_user_only_key_in_a_repo_file_is_skipped(self):
        repo = self.write('repo', 'jobs_root = "/x"\ntrust_root = "/"\n[ask]\ncommand = "rm -rf ~"\n[gates]\nmerge = false\n'
                                  '[helpers]\nmax = 2\n')
        s = self.load()
        self.assertEqual([p.split(':')[1].split()[0] for p in s.problems], ['jobs_root', 'trust_root', 'ask.command', 'gates.merge'])
        self.assertTrue(all(p.startswith(f'{repo}: ') and 'never from a repo' in p for p in s.problems))
        self.assertEqual((s.get('jobs_root'), s.get('ask.command'), s.get('helpers.max')),
                         ('~/code/herdr-jobs', st.DEFAULTS['ask.command'], 2))
        self.write('user', 'jobs_root = "~/elsewhere"\n')
        self.assertEqual(self.load().source('jobs_root'), 'user')

    def test_xdg_config_home_moves_the_user_file(self):
        xdg = self.dir / 'xdg'
        (xdg / 'stampede').mkdir(parents=True)
        (xdg / 'stampede' / 'config.toml').write_text('[helpers]\nmax = 1\n')
        s = self.load({'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((s.get('helpers.max'), s.files['user']), (1, {'path': str(xdg / 'stampede/config.toml'), 'exists': True}))

    def test_show_as_text_and_as_json(self):
        self.write('user', '[helpers]\nmax = 5\nbogus = 1\n')
        s = self.load({'HC_SESSION': 'scratch', 'FLEET_LEAD_KIND': 'codex'})
        text = st.show(s)
        lines = text.splitlines()
        self.assertIn('helpers.max = 5  (user)', lines)
        self.assertIn('lead.kind = "codex"  (env:FLEET_LEAD_KIND)', lines)
        self.assertIn('jobs_root = "~/code/herdr-jobs"  (default)', lines, 'paths as written')
        self.assertIn('HC_SESSION = "scratch"  (env)', lines)
        self.assertIn('HC = "hc"  (default)', lines)
        self.assertLess(lines.index('helpers.max = 5  (user)'), lines.index('# environment only: other programs read these too'))
        self.assertEqual(lines[lines.index('# problems') + 1:], s.problems)
        self.assertEqual(lines[lines.index('helpers.max = 5  (user)') - 1], '', 'a blank line before each table')
        data = json.loads(st.show(s, as_json=True))
        self.assertEqual(set(data), {'values', 'sources', 'files', 'environment', 'problems'})
        self.assertEqual((data['values']['helpers.max'], data['sources']['helpers.max']), (5, 'user'))
        self.assertEqual(data['environment']['HC_SESSION'], 'scratch')
        self.assertEqual(set(data['environment']), {name for name, _, _ in st.ENV_ONLY})
        self.assertEqual(data['files']['user']['exists'], True)
        self.assertEqual(len(data['problems']), 1)


LIVE = ('FLEET_LEAD_KIND', 'FLEET_LEAD_MODEL', 'FLEET_LEAD_EFFORT', 'FLEET_ASK_CMD', 'FLEET_JOBS_ROOT', 'FLEET_TRUST_ROOT',
        'STAMPEDE_MAX_HELPERS', 'STAMPEDE_TAB_PANES', 'XDG_CONFIG_HOME')


class Wired(unittest.TestCase):
    """Each key as the code reads it: the old way (its environment name, <job>/max-helpers, a flag) still sets it, a
    config file sets it, and a higher layer beats the file. A job keeps what it saved at new."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()
        patch = mock.patch.dict(os.environ, {'HOME': str(self.dir), **{name: '' for name in LIVE}})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(st.SETS.clear)
        self.user = self.dir / '.config' / 'stampede' / 'config.toml'
        self.user.parent.mkdir(parents=True)
        self.job = self.dir / 'job'
        self.job.mkdir()
        (self.job / 'ask.md').write_text('Fix the login bug\n')  # a job folder, as stampede's commands check

    def config(self, text):
        self.user.write_text(text)

    def env(self, **values):
        return mock.patch.dict(os.environ, values)

    def test_the_lead(self):
        self.config('[lead]\nkind = "codex"\n[lead.claude]\nmodel = "claude-fable-5-1"\neffort = "high"\n[lead.codex]\neffort = "low"\n')
        self.assertEqual(st.current().get('lead.kind'), 'codex')
        self.assertEqual(agents_.lead_model('claude'), ('claude-fable-5-1', 'high'))
        self.assertEqual(agents_.lead_model('codex'), ('gpt-6-astra', 'low'))
        with self.env(FLEET_LEAD_KIND='claude', FLEET_LEAD_MODEL='gpt-6.1-sol', FLEET_LEAD_EFFORT='xhigh'):
            self.assertEqual(st.current().get('lead.kind'), 'claude')
            self.assertEqual(agents_.lead_model('codex'), ('gpt-6.1-sol', 'xhigh'))
            self.assertEqual(agents_.lead_model('claude'), ('claude-fable-5-1', 'high'), 'a gpt model leaves the Claude pair')
        st.SETS[:] = ['lead.codex.effort=medium']
        self.assertEqual(agents_.lead_model('codex'), ('gpt-6-astra', 'medium'))
        self.assertEqual(agents_.lead_model('codex', 'gpt-6-luna', 'max'), ('gpt-6-luna', 'max'), 'the start flags win')

    def test_the_ask_command(self):
        self.config('[ask]\ncommand = "ask-from-file"\n')
        self.assertEqual(owner_.ask_command(self.job), 'ask-from-file')
        with self.env(FLEET_ASK_CMD='ask-from-env'):
            self.assertEqual(owner_.ask_command(self.job), 'ask-from-env')
        with mock.patch.object(owner_, 'ASK_CMD', 'stand-in'):
            self.assertEqual(owner_.ask_command(self.job), 'stand-in')

    def test_the_jobs_root_and_the_trust_root(self):
        repo = self.dir / 'trusted' / 'repo'
        repo.mkdir(parents=True)
        self.config(f'jobs_root = "~/from-file"\ntrust_root = "{self.dir / "trusted"}"\n')
        self.assertEqual(job_.jobs_root(), self.dir / 'from-file')
        self.assertEqual(job_.core_repo(str(repo)), repo)
        with self.env(FLEET_JOBS_ROOT=str(self.dir / 'from-env'), FLEET_TRUST_ROOT=str(self.dir / 'elsewhere')):
            self.assertEqual(job_.jobs_root(), self.dir / 'from-env')
            with self.assertRaisesRegex(ValueError, 'is not a folder under FLEET_TRUST_ROOT'):
                job_.core_repo(str(repo))
        st.SETS[:] = ['jobs_root=~/from-set']  # a user-only key from --set: the user's own act
        self.assertEqual(job_.jobs_root(), self.dir / 'from-set')

    def test_the_helpers_and_the_tab_panes(self):
        self.config('[helpers]\nmax = 5\ntab_panes = 2\n')
        self.assertEqual((native_.cap(self.job), native_.setting(self.job, None, 'helpers.tab_panes')), (5, 2))
        with self.env(STAMPEDE_MAX_HELPERS='3', STAMPEDE_TAB_PANES='6'):
            self.assertEqual((native_.cap(self.job), native_.setting(self.job, None, 'helpers.tab_panes')), (3, 6))
            (self.job / 'max-helpers').write_text('2\n')
            self.assertEqual(native_.cap(self.job), 2, '<job>/max-helpers wins for its job')
        self.config('[helpers]\nmax = 0\n')
        (self.job / 'max-helpers').unlink()
        with self.assertRaisesRegex(ValueError, 'helpers.max holds .0., not a whole number of 1 or more'):
            native_.cap(self.job)

    def test_the_brief_sections_and_the_timeouts(self):
        self.config('[brief]\nsections = ["Goal", "Risks"]\n[timeouts]\nhc_call = 7\nwait = 9\nleave = 4\nhold_settle = 2\n')
        self.assertEqual(agents_.missing_sections('## Goal\nShip it.\n'), ['Risks'])
        self.assertEqual(hcapi_.hc_call(), 7)
        self.assertEqual([st.current(self.job).get('timeouts.' + k) for k in ('wait', 'leave', 'hold_settle')], [9, 4, 2])
        st.SETS[:] = ['timeouts.hc_call=8']
        self.assertEqual(hcapi_.hc_call(), 8)
        self.config('')
        st.SETS.clear()
        self.assertEqual(agents_.missing_sections('## Goal\nShip it.\n')[:2], ['Why', 'Inputs'])
        self.assertEqual(hcapi_.hc_call(), 60)

    def test_a_job_keeps_what_it_saved_and_a_default_follows_the_live_layers(self):
        self.config('[helpers]\nmax = 5\n')
        with self.env(FLEET_LEAD_KIND='codex'):
            st.save(self.job, st.load(repo=None, env=os.environ, flags={'helpers.max': None}))
        saved = json.loads((self.job / 'settings.json').read_text())
        self.assertEqual((saved['values']['lead.kind'], saved['sources']['lead.kind'], saved['sources']['helpers.max']),
                         ('codex', 'env:FLEET_LEAD_KIND', 'user'))
        self.assertEqual(saved['version'], (SCRIPTS.parents[2] / 'VERSION').read_text().strip())
        self.config('[helpers]\nmax = 9\n')
        with self.env(FLEET_LEAD_KIND='claude', STAMPEDE_TAB_PANES='3'):
            s = st.current(self.job)
            self.assertEqual((s.get('lead.kind'), s.source('lead.kind')), ('codex', 'env:FLEET_LEAD_KIND'))
            self.assertEqual((s.get('helpers.max'), s.source('helpers.max')), (5, 'user'))
            self.assertEqual(native_.cap(self.job), 5)
            self.assertEqual(s.get('helpers.tab_panes'), 3, 'nobody set it at new: it follows the environment')
            self.assertEqual(s.files['job'], {'path': str(self.job / 'settings.json'), 'exists': True})
            st.SETS[:] = ['lead.kind=claude']
            self.assertEqual(st.current(self.job).source('lead.kind'), 'set')
        st.SETS.clear()
        self.assertEqual(st.current(self.dir / 'old-job').get('helpers.max'), 9, 'a job without settings.json: the live layers')

    def test_new_refuses_while_the_config_has_problems(self):
        repo = self.dir / 'code' / 'repo'
        repo.mkdir(parents=True)
        ask = self.dir / 'ask.md'
        ask.write_text('Fix the login bug\n')
        (repo / '.stampede.toml').write_text('jobs_root = "/x"\n[helpers]\nmaxx = 2\n')
        with self.env(FLEET_TRUST_ROOT=str(self.dir / 'code')), mock.patch('sys.stderr') as err, \
                self.assertRaisesRegex(ValueError, 'fix it or remove the key: stampede config show'):
            cli_.new(str(ask), None, core=True, cwd=str(repo))
        printed = ''.join(call.args[0] for call in err.write.call_args_list)
        self.assertIn('jobs_root is taken only from your own', printed)
        self.assertIn('helpers.maxx is not a setting (did you mean helpers.max?)', printed)
        self.assertEqual([p.name for p in repo.iterdir()], ['.stampede.toml'], 'nothing was made')

    def test_config_show(self):
        def show(*args, **env):
            return subprocess.run([str(SCRIPTS / 'fleet-job'), 'config', 'show', *args], capture_output=True, text=True,
                                  cwd=self.dir, env={**os.environ, **env})
        self.config('[helpers]\nmax = 5\n')
        out = show(STAMPEDE_TAB_PANES='3')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('helpers.max = 5  (user)', out.stdout)
        self.assertIn('helpers.tab_panes = 3  (env:STAMPEDE_TAB_PANES)', out.stdout)
        data = json.loads(show('--json').stdout)
        self.assertEqual(data['sources']['helpers.max'], 'user')
        st.save(self.job, st.load(env={'STAMPEDE_TAB_PANES': '2'}))
        out = show('--job', str(self.job), STAMPEDE_TAB_PANES='6')
        self.assertIn('helpers.tab_panes = 2  (env:STAMPEDE_TAB_PANES)', out.stdout, 'the saved value, not today\'s')
        self.config('[helpers]\nmaxx = 5\n')
        out = show()
        self.assertEqual(out.returncode, 1)
        self.assertIn('helpers.maxx is not a setting', out.stdout.split('# problems')[1])
        out = show('--job', str(self.dir / 'nowhere'))
        self.assertEqual((out.returncode, out.stderr.strip()), (2, f'stampede config: job folder not found: {self.dir / "nowhere"}'))


class Review(Wired):
    """The review of PR 45, B1 to B8 and its notes: each finding, then one more case of the builder's own."""

    def snapshot(self, values, sources):
        (self.job / 'settings.json').write_text(json.dumps({'values': values, 'sources': sources, 'version': 'x'}))

    def test_b1_a_job_snapshot_never_decides_a_user_only_key(self):
        self.snapshot({'ask.command': '/usr/bin/true', 'jobs_root': '/forged', 'trust_root': '/', 'gates.merge': False},
                      {'ask.command': 'user', 'jobs_root': 'user', 'trust_root': 'env:FLEET_TRUST_ROOT', 'gates.merge': 'user'})
        self.assertEqual(owner_.ask_command(self.job), st.DEFAULTS['ask.command'], 'the forged source grants nothing')
        s = st.current(self.job)
        self.assertEqual({k: (s.get(k), s.source(k)) for k in ('ask.command', 'jobs_root', 'trust_root')},
                         {k: (st.DEFAULTS[k], 'default') for k in ('ask.command', 'jobs_root', 'trust_root')})
        self.config('[ask]\ncommand = "ask-mine"\n')
        out = subprocess.run([str(SCRIPTS / 'fleet-job'), 'config', 'show', '--job', str(self.job)], capture_output=True,
                             text=True, env=dict(os.environ))
        self.assertIn('ask.command = "ask-mine"  (user)', out.stdout, 'show --job: the live source')
        with self.env(FLEET_ASK_CMD='ask-env', FLEET_JOBS_ROOT='/live'):  # and new never writes them
            st.save(self.job, st.load(env=os.environ, sets=['trust_root=/set']))
        saved = json.loads((self.job / 'settings.json').read_text())
        self.assertFalse([k for k in list(saved['values']) + list(saved['sources']) if k.startswith(st.USER_ONLY)])
        self.assertEqual(saved['values']['helpers.max'], 12, 'the other keys are kept')

    def test_g19_l09_an_ask_command_set_after_new_is_the_one_asked(self):
        """CI's evals G19 and L09 set FLEET_ASK_CMD after new; the snapshot new wrote with another value must not win."""
        with self.env(FLEET_ASK_CMD='ask-at-new'):
            st.save(self.job, st.load(env=os.environ))
        with self.env(FLEET_ASK_CMD='ask-later'):
            self.assertEqual(owner_.ask_command(self.job), 'ask-later')
        self.assertEqual(owner_.ask_command(self.job), st.DEFAULTS['ask.command'])

    def test_b2_brief_sections_hc_call_and_hold_settle_come_from_the_job(self):
        self.snapshot({'brief.sections': ['Goal'], 'timeouts.hc_call': 7, 'timeouts.hold_settle': 100},
                      {'brief.sections': 'repo', 'timeouts.hc_call': 'repo', 'timeouts.hold_settle': 'repo'})
        self.assertEqual(agents_.missing_sections('## Goal\nShip it.\n', self.job), [])
        self.assertEqual(agents_.missing_sections('## Goal\nShip it.\n')[:1], ['Why'], 'no job: the live layers')
        with mock.patch.object(hcapi_, 'TARGET', [self.job]):
            self.assertEqual(hcapi_.hc_call(), 7)
        self.assertEqual(hcapi_.hc_call(), 60)
        import time
        rest = {'state': 'live', 'status': 'idle', 'status_ms': time.time() * 1000 - 10_000, 'turn': 2}
        with mock.patch.object(hcapi_, 'core_status', return_value='idle'):
            self.assertIsNone(relay_.settled(rest, self.job), 'at rest 10 s of the job\'s 100')
            self.assertEqual(relay_.settled(rest), 2, 'the live 5 s')

    def test_b3_the_fallback_reader_refuses_what_toml_refuses(self):
        """Expected results written out, so this holds on every Python, for the fallback reader and for parse()."""
        refused = ['[helpers]\nmax = 3\n[helpers]\ntab_panes = 2', 'helpers.max = 3\n[helpers]\ntab_panes = 2',
                   'helpers.max = 1__2', 'helpers.max = 012', 'helpers.max = 12_', 'a = "a\\/b"', "a = 'a\x01b'",
                   'a = "a\x01b"', 'a = "\\uD800"', 'a = 1 # a \x07 bell', 'a = 1e', 'a = trueish',
                   '[a]\nb.c = 1\n[a.b]']
        accepted = {'a = "\\U00000041\\u0042"': {'a': 'AB'}, 'a = "x\ty"': {'a': 'x\ty'}, 'a = -0': {'a': 0},
                    'a = +1.5e3': {'a': 1500.0}, 'a = 1_000': {'a': 1000}, '[a.b]\n[a]': {'a': {'b': {}}},
                    'a.b = 1\n[a.c]': {'a': {'b': 1, 'c': {}}}, 'a = ["x", # c\n "y",]': {'a': ['x', 'y']}}
        for reader in (st.loads_subset, st.parse):
            for text in refused:
                with self.subTest(reader=reader.__name__, text=text), self.assertRaises(ValueError):
                    reader(text)
            for text, want in accepted.items():
                with self.subTest(reader=reader.__name__, text=text):
                    self.assertEqual(reader(text), want)
        self.config('[helpers]\nmax = 012\n')
        self.assertEqual((len(st.current().problems), st.current().get('helpers.max')), (1, 12), 'the layer is skipped')

    def test_b3_round_2_only_ascii_digits_and_toml_whitespace(self):
        """A file both readers refuse, on every Python: a non-ASCII digit, sign or space, a BOM, a lone carriage return.
        Written out, so the fallback reader (Python 3.9 and 3.10) is held to what tomllib does."""
        refused = {'unicode-digit': 'helpers.max = 1\u0663\n', 'nbsp': '\u00a0helpers.max = 3\n',
                   'vertical-tab': '\vhelpers.max = 3\n', 'bom': '\ufeffhelpers.max = 3\n',
                   'lone-cr': 'helpers.max = 3\rhelpers.tab_panes = 2\n', 'cr-in-array': 'a = [1,\r2]\n',
                   'non-ascii-key': '[helpers]\nm\u00e4x = 3\n', 'minus-sign': 'helpers.max = \u22123\n',
                   'fullwidth-digit': 'helpers.max = \uff13\n', 'superscript': 'helpers.max = \u00b3\n',
                   'em-space': 'helpers.max\u2003= 3\n', 'next-line': 'helpers.max = 3\u0085\n',
                   'line-separator': 'helpers.max = 3\u2028\n', 'zero-width': 'helpers.max\u200b= 3\n',
                   'ideographic-space': '\u3000helpers.max = 3\n', 'arabic-in-float': 'a = 1.\u0663\n'}
        accepted = {'crlf': ('[helpers]\r\nmax = 3\r\n# c\r\n', {'helpers': {'max': 3}}),
                    'tabs': ('\thelpers.max\t=\t3\n', {'helpers': {'max': 3}})}
        for reader in (st.loads_subset, st.parse):
            for name, text in refused.items():
                with self.subTest(reader=reader.__name__, case=name), self.assertRaises(ValueError):
                    reader(text)
            for name, (text, want) in accepted.items():
                with self.subTest(reader=reader.__name__, case=name):
                    self.assertEqual(reader(text), want)
        for text in ('[helpers]\n"max" = 3\n', 'helpers . max = 3\n'):  # TOML, but outside the subset: refused, with a line
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, '^line [0-9]+: '):
                st.loads_subset(text)
        self.config(refused['unicode-digit'])  # the reviewer's file-level case: one problem, never 13
        self.assertEqual((len(st.current().problems), st.current().get('helpers.max')), (1, 12))
        with self.env(STAMPEDE_MAX_HELPERS='\u0661\u0662'):
            self.assertEqual(st.current().get('helpers.max'), 12, 'an environment value of Arabic digits is no number')

    def test_b4_the_cap_file_new_writes_holds_the_resolved_cap(self):
        settings = st.load(env=os.environ, flags={'helpers.max': 3}, sets=['helpers.max=6'])
        self.assertEqual((settings.get('helpers.max'), settings.source('helpers.max')), (6, 'set'))
        # the new itself, against the fake Core: tests/test_native.py, test_b4_set_beats_max_helpers_in_the_cap_file

    def test_b5_new_validates_the_lead_the_layers_resolve(self):
        repo = self.dir / 'code' / 'repo'
        repo.mkdir(parents=True)
        sid = '0b5f1c2e-7d3a-4e8b-9c41-2a6f8e9d1b37'
        self.config('[lead]\nkind = "codex"\n')
        (repo / '.stampede.toml').write_text('[lead]\nkind = "claude"\n')
        with self.env(FLEET_TRUST_ROOT=str(self.dir / 'code')), mock.patch.object(native_, 'new', return_value=0) as made:
            self.assertEqual(cli_.new('ask.md', None, core=True, cwd=str(repo), fork=sid), 0)
            self.assertEqual(made.call_args.args[5], 'claude', 'the repo\'s Claude lead takes the fork')
            self.config('')
            (repo / '.stampede.toml').write_text('[lead]\nkind = "codex"\n')
            with mock.patch.object(hcapi_, 'typing_unsafe', return_value=''), \
                    self.assertRaisesRegex(ValueError, '--fork forks a Claude chat'):
                cli_.new('ask.md', None, core=True, cwd=str(repo), fork=sid)
        self.assertEqual(made.call_count, 1)

    def test_b6_a_snapshot_of_the_wrong_shape_is_a_problem_not_a_crash(self):
        for body in ('{"values": []}', '{"values": {}, "sources": null}', '[1, 2]', '"text"', '{"values": {"helpers.max": 4}}'):
            with self.subTest(body=body):
                (self.job / 'settings.json').write_text(body)
                s = st.current(self.job)
                self.assertEqual(s.get('helpers.max'), 12)
                self.assertEqual(len(s.problems), 1)
                self.assertIn('not a stampede settings file', s.problems[0])
                out = subprocess.run([str(SCRIPTS / 'fleet-job'), 'config', 'show', '--job', str(self.job)],
                                     capture_output=True, text=True, env=dict(os.environ))
                self.assertEqual((out.returncode, out.stderr), (1, ''))

    def test_b7_a_very_deep_key_is_one_problem(self):
        self.config('lead.kind = "codex"\n' + '.'.join(['deep'] * 1200) + ' = 1\n')
        s = st.current()
        self.assertEqual((len(s.problems), s.get('lead.kind')), (1, 'claude'), 'one line, the whole layer skipped')
        repo = self.dir / 'repo'
        repo.mkdir()
        (repo / '.stampede.toml').write_text('[' + '.'.join(['deep'] * 1200) + ']\n')
        self.config('')
        with mock.patch('sys.stderr'), self.assertRaisesRegex(ValueError, 'fix it or remove the key'):
            st.for_new(repo, {})

    def test_b8_the_environment_only_section(self):
        self.assertEqual(st.current().environment['HC_SESSION'], 'default')
        with self.env(HC_SESSION='other-core'):
            self.assertEqual(st.current().environment['HC_SESSION'], 'other-core', 'the memo sees it')
        with self.env(HC_SESSION='default', HERDR_EVENTS_DIR='/scratch/events', HERDR_EVENTS_HOME='/scratch/queue'):
            text = st.show(st.current())
        self.assertIn('HC_SESSION = "default"  (env)', text, 'set, even to its default')
        self.assertIn('HERDR_EVENTS_ROUTES_DIR = "/scratch/events/routes"  (default)', text)
        self.assertIn('HERDR_EVENTS_FLUSH_LOG = "/scratch/queue/flush.log"  (default)', text)
        self.assertIn('HC = "hc"  (default)', st.show(st.current()))

    def test_notes_the_wait_timeout_line_and_a_config_that_is_a_folder(self):
        self.config('[timeouts]\nwait = 0\n')
        with mock.patch.object(owner_, 'lead_alive', return_value=True), mock.patch('builtins.print') as said:
            self.assertEqual(owner_.wait(self.job), 3)
        self.assertIn('after 0s;', said.call_args.args[0])
        self.user.unlink()
        self.user.mkdir()
        s = st.current()
        self.assertEqual(len(s.problems), 1)
        self.assertIn('not readable TOML', s.problems[0])
        self.assertTrue(s.files['user']['exists'])


    def test_doctor_reports_each_config_problem_with_its_fix(self):
        repo = self.dir / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / '.stampede.toml').write_text('trust_root = "/"\n')
        self.config('[helpers]\nmaxx = 2\n')
        with mock.patch.object(doctor_.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, str(repo) + '\n', '')):
            found = doctor_.config()
        self.assertEqual([(c['level'], c['fix']) for c in found], [('PROBLEM', 'fix or remove what it names, then stampede config show')] * 2)
        self.assertIn('helpers.maxx is not a setting', found[0]['text'])
        self.assertIn('trust_root is taken only from your own', found[1]['text'])
        self.config('')
        (repo / '.stampede.toml').unlink()
        with mock.patch.object(doctor_.subprocess, 'run', return_value=subprocess.CompletedProcess([], 128, '', 'not a repo')):
            self.assertEqual([c['level'] for c in doctor_.config()], ['ok'])
        self.assertIn(doctor_.config, doctor_.CHECKS)

class Example(unittest.TestCase):
    def test_config_example_is_the_defaults(self):
        """config.example holds every key with the default defaults.toml gives it, and every environment-only name."""
        text = (SCRIPTS.parents[2] / 'config.example').read_text()
        self.assertEqual(st.flatten(st.parse(text)), st.DEFAULTS)
        self.assertEqual(text.split('\n[lead]\n')[1].split('\n# Environment only')[0],
                         st.DEFAULTS_FILE.read_text().split('\n[lead]\n')[1].rstrip('\n') + '\n')
        for name, default, _ in st.ENV_ONLY:
            self.assertIn(f'\n# {name}=' + ('$(hostname -s)' if name == 'HERDR_EVENTS_MACHINE' else default) + '  # ', text)


class Readers(unittest.TestCase):
    def test_the_subset_reader(self):
        self.assertEqual(st.loads_subset(SAMPLE), {
            'jobs_root': '~/jobs', 'lead': {'kind': 'codex', 'claude': {'model': 'claude-fable-5-1'}},
            'brief': {'sections': ['Goal', 'Why']}, 'helpers': {'max': 6}, 'timeouts': {'wait': 1800},
            'other': {'ratio': 0.5, 'on': True, 'list': [1, -2, 300.0, 'a "b"']}})
        for bad in ('a = ', 'a = "x', 'a = 1 2', '[a', 'a = 1\na = 2', 'a b = 1', 'a = [1 2]', 'a = nope'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                st.loads_subset(bad)

    @unittest.skipIf(st.tomllib is None, 'tomllib comes with Python 3.11')
    def test_both_readers_agree(self):
        for text in (st.DEFAULTS_FILE.read_text(), SAMPLE):
            self.assertEqual(st.loads_subset(text), st.tomllib.loads(text))


if __name__ == '__main__':
    unittest.main()
