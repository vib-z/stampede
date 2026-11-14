"""stampede/settings.py: layers, sources, the environment names, problems, show, and the two TOML readers."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / 'skills' / 'herdr-fleet' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from stampede import settings as st, agents as agents_, job as job_, owner as owner_, hcapi as hcapi_, native as native_, cli as cli_

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
            'jobs_root': '~/code/herdr-jobs', 'trust_root': '~/code', 'lead.kind': 'claude',
            'lead.claude.model': 'claude-opus-5-5', 'lead.claude.effort': 'xhigh',
            'lead.codex.model': 'gpt-6-astra', 'lead.codex.effort': 'ultra',
            'ask.command': 'moshi-hook ask --require-remote --source herdr-fleet --timeout 24h',
            'brief.sections': ['Goal', 'Why', 'Inputs', 'Constraints', 'Done when', 'Report back', 'If blocked'],
            'helpers.max': 12, 'helpers.tab_panes': 4,
            'timeouts.wait': 3600, 'timeouts.hc_call': 60, 'timeouts.leave': 15, 'timeouts.hold_settle': 5})
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
        self.assertEqual((out.returncode, out.stderr.strip()), (2, f'fleet-job config: {self.dir / "nowhere"} is not a job folder'))


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
