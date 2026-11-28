"""stampede setup and the editor under it (settings.edit_user, write_user): the questions, typed or by flag, what is
written and what is kept, and every refusal. Each test has a scratch HOME: the real settings file is never touched."""
import contextlib, io, json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / 'skills' / 'herdr-fleet' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from stampede import cli as cli_, doctor as doctor_, settings as settings_, setup as setup_  # noqa: E402

MINE = '''# mine: keep this
backend = "auto"   # where jobs run
jobs_root = "~/jobs"

[lead]
kind = "claude"
forbid = ["gpt-old"]

[lead.claude]
  model = "claude-fable-5-2"  # my pick
[other]
ratio = 0.5
'''


class Typed(io.StringIO):
    """What a person types at a terminal, one line per answer."""
    def isatty(self):
        return True


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / 'home'
        self.user = self.home / '.config/stampede/config.toml'
        self.home.mkdir()
        patch = mock.patch.dict(os.environ, {'HOME': str(self.home), 'PATH': '/usr/bin:/bin'}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(settings_.SETS.clear)

    def config(self, text):
        self.user.parent.mkdir(parents=True, exist_ok=True)
        self.user.write_bytes(text.encode())

    def setup(self, *argv, typed=None, env=None):
        """(exit code, stdout, stderr) of stampede setup; typed: the lines a person types, else there is no terminal."""
        out, err = io.StringIO(), io.StringIO()
        stdin = Typed(typed) if typed is not None else io.StringIO()
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(sys, 'stdin', stdin), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_.main(['setup', *argv])
        return code, out.getvalue(), err.getvalue()

    def values(self):
        found = settings_.load()
        self.assertEqual(found.problems, [])
        return found


class Editor(Case):
    """settings.edit_user: each key is exactly that change, or a refusal with nothing written."""

    def edit(self, **changes):
        path, old, new = settings_.edit_user({key.replace('__', '.'): value for key, value in changes.items()})
        self.assertEqual(path, self.user)
        return new.decode()

    def test_a_line_in_its_table_is_replaced_with_its_indent_and_every_other_byte_kept(self):
        self.config(MINE)
        self.assertEqual(self.edit(lead__claude__model='claude-opus-5-5'),
                         MINE.replace('  model = "claude-fable-5-2"  # my pick', '  model = "claude-opus-5-5"'))
        self.assertEqual(self.edit(lead__kind='codex'), MINE.replace('kind = "claude"', 'kind = "codex"'))
        self.assertEqual(self.user.read_text(), MINE, 'edit_user writes nothing')

    def test_a_new_key_goes_first_in_its_table_and_a_new_table_at_the_end(self):
        self.config(MINE)
        self.assertEqual(self.edit(lead__claude__effort='high'), MINE.replace('[lead.claude]\n', '[lead.claude]\neffort = "high"\n'))
        self.assertEqual(self.edit(dev__pstack=False), MINE + '\n[dev]\npstack = false\n')
        self.config(MINE.rstrip('\n'))
        self.assertEqual(self.edit(review__step='each'), MINE + '\n[review]\nstep = "each"\n', 'a last line with no end gets one')
        self.user.unlink()
        self.assertEqual(self.edit(dev__pstack=False, backend='core'), 'backend = "core"\n[dev]\npstack = false\n')

    def test_several_keys_are_set_in_turn_and_a_value_already_there_is_left_alone(self):
        self.config(MINE)
        new = self.edit(backend='auto', lead__kind='claude', lead__codex__model='gpt-6.2-astra', helpers__max=6)
        self.assertEqual(new, MINE + '\n[lead.codex]\nmodel = "gpt-6.2-astra"\n\n[helpers]\nmax = 6\n')
        self.assertEqual(settings_.parse(new)['lead'], {'kind': 'claude', 'forbid': ['gpt-old'], 'claude': {'model': 'claude-fable-5-2'},
                                                         'codex': {'model': 'gpt-6.2-astra'}})

    def test_a_crlf_file_stays_crlf(self):
        self.config(MINE.replace('\n', '\r\n'))
        self.assertEqual(self.edit(lead__kind='codex', dev__pstack=False),
                         (MINE.replace('kind = "claude"', 'kind = "codex"') + '\n[dev]\npstack = false\n').replace('\n', '\r\n'))

    def test_values_are_written_as_toml(self):
        self.assertEqual([settings_.encode(v) for v in (True, False, 6, 'a "b" \\ c', ['x', 'y'], [])],
                         ['true', 'false', '6', '"a \\"b\\" \\\\ c"', '["x", "y"]', '[]'])
        new = self.edit(lead__forbid=['a b', 'c"d'], lead__claude__model='m\té')
        self.assertEqual(settings_.parse(new)['lead'], {'forbid': ['a b', 'c"d'], 'claude': {'model': 'm\té'}})

    def test_a_file_it_cannot_change_safely_is_refused(self):
        for text, key, why in (
                ("lead.kind = 'codex'\n", 'lead.kind', 'its lead.kind is not one plain line kind = <value>'),
                ('[lead]\nkind = "claude"\n[roles.build]\nkind = "codex"\n[lead]\n', 'lead.kind', 'does not parse'),
                ('lead = "claude"\n', 'lead.kind', 'lead is a value there, so lead.kind cannot be set'),
                ('[ lead ]\nforbid = []\n', 'lead.kind', 'the change would not set only lead.kind to "claude"'),
                ('[lead]\nkind = "codex"\nkind = "codex"\n', 'lead.kind', 'does not parse'),
                ('[lead\n', 'dev.pstack', 'does not parse')):
            with self.subTest(text=text):
                self.config(text)
                with self.assertRaises(ValueError) as refused:
                    settings_.edit_user({key: 'claude' if key == 'lead.kind' else False})
                self.assertIn(why, str(refused.exception))
                self.assertIn(str(self.user), str(refused.exception))
                self.assertIn('nothing was changed', str(refused.exception))

    @unittest.skipIf(settings_.tomllib is None, 'the fallback reader refuses a multi-line string before this')
    def test_a_look_alike_line_inside_a_string_is_never_taken_for_the_key(self):
        self.config('[lead]\nnote = """\nkind = "claude"\n"""\nkind = \'claude\'\n')
        with self.assertRaises(ValueError) as refused:
            settings_.edit_user({'lead.kind': 'codex'})
        self.assertIn('the change would not set only lead.kind', str(refused.exception))

    def test_write_user_refuses_a_file_that_changed_since_it_was_read(self):
        self.config(MINE)
        path, old, new = settings_.edit_user({'lead.kind': 'codex'})
        self.config(MINE + '# edited meanwhile\n')
        with self.assertRaises(ValueError) as refused:
            settings_.write_user(path, old, new)
        self.assertIn('changed while this ran', str(refused.exception))
        self.assertEqual(self.user.read_text(), MINE + '# edited meanwhile\n')


class NoTerminal(Case):
    """With flags and no terminal: a bot, a script, or stampede setup --defaults."""

    def test_on_a_new_machine_defaults_writes_a_file_with_every_default_and_says_what_applies(self):
        code, out, err = self.setup('--defaults')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.user.read_text(), setup_.HEADER)
        self.assertEqual(settings_.parse(setup_.HEADER), {})
        self.assertEqual(out.splitlines()[-10:], [
            f'SAVED {self.user}', 'What new jobs use now:', '  dev.pstack = true  (default)', '  lead.kind = "claude"  (default)',
            '  lead.claude.model = "claude-opus-5-5"  (default)', '  lead.claude.effort = "xhigh"  (default)',
            '  backend = "tui"  (default)', '  review.step = "end"  (default)', '  every worker\'s effort = "medium"',
            'pstack is not installed for a Claude lead yet. Install it with: claude plugin marketplace add '
            'michael-denyer/pstack-claude && claude plugin install pstack@pstack-claude'])
        self.assertEqual(out.splitlines()[0], f'New file {self.user}:')
        self.assertEqual(self.values().values, settings_.DEFAULTS)

    def test_a_second_run_changes_nothing(self):
        argv = ('--pstack', 'no', '--lead', 'codex', '--lead-effort', 'high', '--worker-effort', 'low', '--backend', 'core', '--review', 'none')
        self.assertEqual(self.setup(*argv)[0], 0)
        first = self.user.read_bytes()
        stamp = self.user.stat().st_mtime_ns
        code, out, err = self.setup(*argv)
        self.assertEqual((code, err, out.splitlines()[0]), (0, '', f'UNCHANGED {self.user}: your answers are what it already says'))
        self.assertEqual((self.user.read_bytes(), self.user.stat().st_mtime_ns), (first, stamp))

    def test_only_an_answer_that_differs_is_written(self):
        code, _, err = self.setup('--pstack', 'yes', '--lead', 'claude', '--lead-model', 'claude-opus-5-5', '--lead-effort', 'xhigh',
                                  '--worker-effort', 'medium', '--backend', 'tui', '--review', 'end')
        self.assertEqual((code, err, self.user.read_text()), (0, '', setup_.HEADER))
        code, _, err = self.setup('--pstack', 'no', '--lead', 'codex', '--lead-model', 'gpt-6.2-astra', '--yes')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.user.read_text(), setup_.HEADER + '\n[dev]\npstack = false\n\n[lead]\nkind = "codex"\n\n'
                         '[lead.codex]\nmodel = "gpt-6.2-astra"\n')

    def test_every_answer_reaches_the_settings_jobs_read(self):
        self.setup('--pstack', 'no', '--lead', 'codex', '--lead-model', 'gpt-6.2-astra', '--lead-effort', 'high', '--worker-effort',
                   'low', '--backend', 'core', '--review', 'each')
        found = self.values()
        self.assertEqual([found.get(key) for key in ('dev.pstack', 'lead.kind', 'lead.codex.model', 'lead.codex.effort', 'backend', 'review.step')],
                         [False, 'codex', 'gpt-6.2-astra', 'high', 'core', 'each'])
        self.assertEqual({found.get(key) for key in found.values if key.startswith('roles.') and key.endswith('.effort')}, {'low'})
        self.assertEqual({found.source(key) for key in ('dev.pstack', 'lead.codex.model', 'roles.review.effort', 'backend')}, {'user'})
        self.assertEqual((found.get('lead.claude.model'), found.source('lead.claude.model')), ('claude-opus-5-5', 'default'))

    def test_a_file_you_have_is_shown_and_left_alone_without_yes(self):
        self.config(MINE)
        code, out, err = self.setup('--pstack', 'no', '--lead-model', 'claude-opus-5-5')
        self.assertEqual(code, 2)
        self.assertEqual(err, f'note: {self.user}: other.ratio is not a setting; skipped\n'  # a key it does not know is said, and kept
                         f'stampede setup: {self.user} would change as shown: run it again with --yes to save that; nothing was changed\n')
        self.assertEqual(out.splitlines()[:2], ['--- now', '+++ with your answers'])
        for line in ('-  model = "claude-fable-5-2"  # my pick', '+  model = "claude-opus-5-5"', '+[dev]', '+pstack = false'):
            self.assertIn(line, out.splitlines())
        self.assertEqual(self.user.read_text(), MINE)
        self.assertEqual([p.name for p in self.user.parent.iterdir()], ['config.toml'])

    def test_with_yes_it_changes_its_own_lines_and_keeps_every_other(self):
        self.config(MINE)
        code, out, err = self.setup('--pstack', 'no', '--lead-model', 'claude-opus-5-5', '--backend', 'tui', '--yes')
        self.assertEqual(code, 0, err)
        self.assertEqual(err, f'note: {self.user}: other.ratio is not a setting; skipped\n', 'a key it does not know is said and kept')
        self.assertEqual(self.user.read_text(), MINE.replace('backend = "auto"   # where jobs run', 'backend = "tui"')
                         .replace('  model = "claude-fable-5-2"  # my pick', '  model = "claude-opus-5-5"') + '\n[dev]\npstack = false\n')
        self.assertIn(f'SAVED {self.user}', out.splitlines())

    def test_an_answer_it_does_not_take_is_refused_by_its_flag(self):
        for argv, why in ((('--pstack', 'maybe'), "--pstack: it takes yes or no, not 'maybe'"),
                          (('--lead', 'cursor'), "--lead: it takes claude or codex, not 'cursor'"),
                          (('--lead-model', 'two words'), "--lead-model: a model is one word, such as claude-opus-5-5, not 'two words'"),
                          (('--lead-effort', 'fast'), "--lead-effort: it takes none, minimal, low, medium, high, xhigh, max or ultra, not 'fast'"),
                          (('--worker-effort', 'fast'), "--worker-effort: it takes none, minimal, low, medium, high, xhigh, max or ultra, not 'fast'"),
                          (('--backend', 'cloud'), "--backend: it takes tui, core or auto, not 'cloud'"),
                          (('--review', 'twice'), "--review: it takes end, each or none, not 'twice'")):
            with self.subTest(argv=argv):
                code, out, err = self.setup(*argv, '--yes')
                self.assertEqual((code, out, err), (2, '', f'stampede setup: {why}\n'))
                self.assertFalse(self.user.exists())

    def test_the_lead_and_worker_rules_are_honoured(self):
        self.config('[lead]\nforbid = ["claude-opus-5-5"]\nallow = ["claude-opus-5-5", "claude-fable-5-2"]\n[workers]\nmax_effort = "medium"\n')
        before = self.user.read_text()
        for argv, why in (((), 'the lead may not run on claude-opus-5-5 (lead.forbid): name another with --lead-model'),
                          (('--lead', 'codex'), 'the lead may not run on gpt-6.2-sol (lead.allow: claude-opus-5-5, claude-fable-5-2): '
                                                'name another with --lead-model'),
                          (('--lead-model', 'claude-sonnet-5-5'), '--lead-model: the lead may not run on claude-sonnet-5-5 '
                                                                  '(lead.allow: claude-opus-5-5, claude-fable-5-2)'),
                          (('--lead-model', 'claude-fable-5-2', '--worker-effort', 'high'),
                           '--worker-effort: workers may not run at high effort (workers.max_effort: medium)')):
            with self.subTest(argv=argv):
                code, _, err = self.setup(*argv, '--yes')
                self.assertEqual((code, err), (2, f'stampede setup: {why}\n'))
                self.assertEqual(self.user.read_text(), before)
        code, _, err = self.setup('--lead-model', 'claude-fable-5-2', '--worker-effort', 'low', '--yes')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.values().get('lead.claude.model'), 'claude-fable-5-2')

    def test_a_role_of_your_own_gets_the_workers_effort_too(self):
        self.config('[roles.mine]\nkind = "codex"\neffort = "max"\n')
        code, out, _ = self.setup('--defaults')
        self.assertIn('  the workers\' efforts differ by role: stampede config show', out.splitlines())
        self.assertEqual(self.setup('--worker-effort', 'high', '--yes')[0], 0)
        found = self.values()
        self.assertEqual((found.get('roles.mine.effort'), found.get('roles.build.effort'), found.get('roles.mine.kind')), ('high', 'high', 'codex'))

    def test_a_file_that_cannot_be_changed_safely_is_refused_whole(self):
        text = "lead.kind = 'codex'\n"
        self.config(text)
        code, out, err = self.setup('--pstack', 'no', '--lead', 'claude', '--yes')
        self.assertEqual((code, out), (2, ''))
        self.assertIn('its lead.kind is not one plain line kind = <value>: edit the file by hand; nothing was changed', err)
        self.assertEqual(self.user.read_text(), text, 'not even the answer it could have written')

    def test_the_file_follows_xdg_config_home_and_the_summary_names_the_environment(self):
        elsewhere = self.home / 'xdg'
        code, out, _ = self.setup('--review', 'each', env={'XDG_CONFIG_HOME': str(elsewhere), 'FLEET_LEAD_KIND': 'codex'})
        self.assertEqual(code, 0)
        self.assertEqual((elsewhere / 'stampede/config.toml').read_text(), setup_.HEADER + '\n[review]\nstep = "each"\n')
        self.assertFalse(self.user.exists())
        self.assertIn('  lead.kind = "codex"  (env:FLEET_LEAD_KIND)', out.splitlines())

    def test_with_json_one_object_names_the_file_and_what_changed(self):
        code, out, err = self.setup('--json', '--pstack', 'no', typed='yes\n' * 9)
        self.assertEqual((code, err), (0, ''))
        result = json.loads(out)
        self.assertEqual({k: result[k] for k in ('ok', 'command', 'status', 'path', 'changed')},
                         {'ok': True, 'command': 'setup', 'status': 'SAVED', 'path': str(self.user), 'changed': {'dev.pstack': False}})
        code, out, _ = self.setup('--json', '--pstack', 'yes')
        self.assertEqual((code, json.loads(out)['error'], self.values().get('dev.pstack')),
                         (2, f'stampede setup: {self.user} would change as shown: run it again with --yes to save that; nothing was changed', False))
        code, out, _ = self.setup('--json', '--pstack', 'no')
        self.assertEqual((code, json.loads(out)['status'], json.loads(out)['changed']), (0, 'UNCHANGED', {}))


class Terminal(Case):
    """At a terminal: seven questions, Enter keeps the answer shown, and a file you have changes only on a yes. What is
    typed is not echoed here, so each prompt runs on into what follows it."""

    def asked(self, out):
        return re.findall(r'\d of 7  .*?\]: ', out)

    def test_the_questions_show_what_is_set_and_enter_keeps_it(self):
        code, out, err = self.setup(typed='\n' * 7)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.asked(out), [
            '1 of 7  Use pstack for coding jobs? It is a set of working rules for a coding agent. yes or no [yes]: ',
            '2 of 7  Which agent leads a job? claude or codex [claude]: ',
            "3 of 7  The lead's model [claude-opus-5-5]: ",
            "4 of 7  The lead's effort: none, minimal, low, medium, high, xhigh, max or ultra [xhigh]: ",
            "5 of 7  Every worker's effort [medium]: ",
            '6 of 7  Where do jobs run? tui (the Herdr TUI), core (Herdr Core) or auto (the TUI inside Herdr, else Core) [tui]: ',
            '7 of 7  When is the work reviewed? end (one pass at the end), each (every pull request or step) or none [end]: '])
        self.assertEqual(self.user.read_text(), setup_.HEADER)
        self.assertFalse({chr(0x2013), chr(0x2014)} & set(out))

    def test_typed_answers_are_saved_and_a_wrong_one_is_asked_again(self):
        code, out, err = self.setup(typed='N\ncodex\n\nhigh\nfast\nlow\n\neach\n')
        self.assertEqual((code, err), (0, ''))
        self.assertIn("5 of 7  Every worker's effort [medium]:         it takes none, minimal, low, medium, high, xhigh, max or ultra, "
                      "not 'fast'\n5 of 7  Every worker's effort [medium]: 6 of 7", out)
        self.assertEqual(len(self.asked(out)), 8)
        self.assertIn("3 of 7  The lead's model [gpt-6.2-sol]: ", out, 'the model asked is the chosen CLI\'s')
        found = self.values()
        self.assertEqual([found.get(key) for key in ('dev.pstack', 'lead.kind', 'lead.codex.model', 'lead.codex.effort', 'roles.qa.effort',
                                                     'backend', 'review.step')], [False, 'codex', 'gpt-6.2-sol', 'high', 'low', 'tui', 'each'])
        self.assertEqual(found.source('lead.codex.model'), 'default', 'Enter wrote nothing for it')

    def test_a_file_you_have_changes_only_on_a_yes(self):
        self.config(MINE)
        for reply, saved in (('no\n', False), ('', False), ('maybe\n', False), ('\n', True)):
            with self.subTest(reply=reply):
                self.config(MINE)
                code, out, _ = self.setup(typed='no\n' + '\n' * 6 + reply)
                self.assertEqual(code, 0)
                self.assertIn('Save this change? yes or no [yes]: ', out)
                self.assertIn('+pstack = false', out.splitlines())
                self.assertEqual(self.user.read_text() != MINE, saved)
                self.assertEqual(out.endswith(f'NOT SAVED {self.user}: nothing was changed\n'), not saved)
        self.assertEqual(self.user.read_text(), MINE + '\n[dev]\npstack = false\n')

    def test_what_the_file_says_is_what_the_brackets_show(self):
        self.config(MINE + '[dev]\npstack = false\n[roles.qa]\neffort = "high"\n')
        _, out, _ = self.setup(typed='\n' * 7)
        for shown in ('yes or no [no]: ', "The lead's model [claude-fable-5-2]: ", "Every worker's effort [mixed]: ", 'else Core) [auto]: '):
            self.assertIn(shown, out)
        self.assertIn(f'UNCHANGED {self.user}: your answers are what it already says\nWhat new jobs use now:\n', out)

    def test_the_end_of_input_keeps_the_rest_and_a_flag_is_not_asked(self):
        code, out, _ = self.setup('--pstack', 'no', '--defaults', typed='codex\n')
        self.assertEqual(code, 0)
        self.assertNotIn(' of 7  ', out, '--defaults asks nothing')
        self.user.unlink()
        code, out, _ = self.setup('--pstack', 'no', typed='codex\n')
        self.assertEqual(code, 0)
        self.assertNotIn('1 of 7', out)
        self.assertEqual(self.user.read_text(), setup_.HEADER + '\n[dev]\npstack = false\n\n[lead]\nkind = "codex"\n')

    def test_a_kept_model_the_rules_forbid_is_asked_until_one_passes(self):
        self.config('[lead]\nforbid = ["claude-opus-5-5"]\n')
        code, out, _ = self.setup(typed='\n\n\nclaude-fable-5-2\n\n\n\n\n\n')
        self.assertEqual(code, 0)
        self.assertIn("3 of 7  The lead's model [claude-opus-5-5]:         the lead may not run on claude-opus-5-5 (lead.forbid)\n"
                      "3 of 7  The lead's model [claude-opus-5-5]: 4 of 7", out)
        self.assertEqual(self.values().get('lead.claude.model'), 'claude-fable-5-2')


class Offered(Case):
    """Where a new user meets setup: doctor says so while no settings file of their own exists."""

    def lines(self):
        with mock.patch.object(doctor_, 'repo', return_value=None):
            return doctor_.config()

    def test_doctor_offers_setup_until_a_user_file_exists(self):
        self.assertEqual(self.lines(), [
            {'name': 'config', 'level': 'ok', 'text': 'settings files without problems: none', 'fix': ''},
            {'name': 'config', 'level': 'ok', 'text': 'no settings file of your own yet, so the defaults apply',
             'fix': 'stampede setup asks your preferences and saves them'}])
        self.assertEqual(self.setup('--defaults')[0], 0)
        self.assertEqual(self.lines(), [{'name': 'config', 'level': 'ok', 'text': f'settings files without problems: {self.user}', 'fix': ''}])

    def test_a_problem_in_a_repo_file_is_not_hidden_by_the_offer(self):
        repo = self.home / 'repo'
        repo.mkdir()
        (repo / '.stampede.toml').write_text('bogus = 1\n')
        with mock.patch.object(doctor_, 'repo', return_value=str(repo)):
            lines = doctor_.config()
        self.assertEqual([line['level'] for line in lines], ['PROBLEM'])


if __name__ == '__main__':
    unittest.main()
