"""A Core-native job (stampede new --core, docs/CORE-NATIVE.md): the lead as a root, helpers as Core children, the cap
and its queue, the tabs, the tree, tell, and the shared commands. Every Core call goes to tests/fake_hc.py through HC."""
import json, os, shlex, subprocess, sys, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, SCRIPTS, SHA, LEAD  # noqa: E402
from stampede import job as job_, hcapi as hcapi_, herdrapi as herdrapi_, owner as owner_, relay as relay_, native as native_, cli as cli_

FLEET = SCRIPTS / 'fleet-job'


class NativeCase(CoreCase):
    def new(self, **kw):
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        return self.quiet(cli_.new, str(ask), None, core=True, cwd=str(self.repo), **kw)

    def started(self, **kw):
        code, out = self.new(**kw)
        self.assertEqual(code, 0, out)
        return self.job

    def start(self, name, *program, kind='claude', **kw):
        brief = None if program else str(self.brief(self.job, name))
        return self.quiet(cli_.start, self.job, name, None if program else kind, None, brief, program=program, **kw)

    def runs(self):
        return self.calls('run')

    def addresses(self):
        return {t['labels'].get('stampede.agent'): a for a, t in self.state()['terminals'].items() if t['labels'].get('stampede.agent')}

    def cli(self, *args, env=None):
        return subprocess.run([str(FLEET), *map(str, args)], capture_output=True, text=True, env={**os.environ, **(env or {})})


class New(NativeCase):
    def test_the_lead_is_a_root_with_the_space_labels_and_no_follower(self):
        job = self.started()
        self.assertEqual(len(self.runs()), 1)
        run = self.runs()[0]
        self.assertIn('--no-parent', run)
        tags = self.labels(run)
        key = job_.job_key(job)
        self.assertEqual({k: tags[k] for k in ('stampede.job', 'stampede.role', 'stampede.agent', 'stampede.space', 'stampede.kind',
                                               'herdr.space', 'herdr.tab')},
                         {'stampede.job': key, 'stampede.role': 'lead', 'stampede.agent': LEAD, 'stampede.space': 'fix-login-bug',
                          'stampede.kind': 'claude', 'herdr.space': 'fix-login-bug', 'herdr.tab': 'main'})
        self.assertEqual(tags['stampede.session'], self.option(run, '--session-id'))
        self.assertNotIn('--settings', run)
        self.assertEqual(job_.backend(job), 'native')
        for name in ('backend', 'endpoint', 'workspace', 'lead', 'space', 'tree.json', 'briefs/' + LEAD + '.md'):
            self.assertTrue((job / name).is_file(), name)
        for name in ('inbox', 'inbox.log', 'hooks', 'core.json', 'agents.tsv', 'relay-state.json', 'max-helpers'):
            self.assertFalse((job / name).exists(), name)
        self.assertEqual((self.events / 'jobs' / key).read_text().strip(), str(job))
        node = json.loads((job / 'tree.json').read_text())['nodes'][LEAD]
        self.assertEqual((node['role'], node['address'], node['state'], node['tab']), ('lead', 't1', 'live', 'main'))
        self.assertTrue(self.program(run)[-1].startswith(f'You are {LEAD}. Read {job / "briefs" / LEAD}.md'))

    def test_the_lead_brief_names_the_native_commands_and_only_the_recorded_yes(self):
        brief = (self.started() / 'briefs' / (LEAD + '.md')).read_text()
        for said in ('hc wait --children any', 'next', 'tree', 'hc send', 'reports', 'hc run --bg', 'At most 12 helpers',
                     'Only the owner', 'gate-ok', 'A typed yes does not count on Core', 'finish'):
            self.assertIn(said, brief)
        self.assertFalse({chr(0x2013), chr(0x2014)} & set(brief))

    def test_the_space_is_the_slug_or_space_and_gets_a_suffix_on_a_clash(self):
        self.add_terminal('t1', labels={'stampede.job': 'hc-000000000000', 'stampede.space': 'fix-login-bug'})
        job = self.started()
        self.assertEqual((job / 'space').read_text().strip(), 'fix-login-bug-' + job_.job_key(job)[3:7])
        self.setUp()
        job = self.started(space='login', max_helpers=3)
        self.assertEqual((job / 'space').read_text().strip(), 'login')
        self.assertEqual((job / 'max-helpers').read_text().strip(), '3')
        self.assertEqual(self.labels(self.runs()[0])['herdr.space'], 'login')

    def test_b4_set_beats_max_helpers_in_the_cap_file(self):
        from stampede import settings as settings_
        with mock.patch.object(settings_, 'SETS', ['helpers.max=6']):
            job = self.started(max_helpers=3)
        self.assertEqual(((job / 'max-helpers').read_text().strip(), native_.cap(job)), ('6', 6))
        (job / 'max-helpers').write_text('2\n')  # a later edit of the file still wins
        self.assertEqual(native_.cap(job), 2)
        self.setUp()
        with mock.patch.object(settings_, 'SETS', ['helpers.max=5']):
            job = self.started()
        self.assertEqual(((job / 'max-helpers').exists(), native_.cap(job)), (False, 5), 'a --set alone: the saved cap')

    def test_b2_a_start_reads_the_brief_sections_the_job_saved(self):
        from stampede import settings as settings_
        job = self.started()
        saved = json.loads((job / 'settings.json').read_text())
        saved['values']['brief.sections'], saved['sources']['brief.sections'] = ['Goal'], 'repo'
        (job / 'settings.json').write_text(json.dumps(saved))
        brief = job / 'briefs' / 'goal-only.md'
        brief.write_text('## Goal\nShip it.\n')
        code, out = self.quiet(cli_.start, job, 'goal-only', 'claude', None, str(brief))
        self.assertIn('STARTED goal-only', out)
        self.assertEqual(settings_.current().get('brief.sections')[:2], ['Goal', 'Why'], 'the live layers keep seven')

    def test_relay_makes_the_earlier_kind_and_space_needs_native(self):
        with mock.patch.object(relay_, 'new_core', return_value=0) as core:
            self.new(relay=True)
        core.assert_called_once()
        with self.assertRaises(ValueError):
            self.new(relay=True, space='x')

    def test_a_lead_that_ends_at_once_is_failed_and_taken_back(self):
        self.shape(on_run={LEAD: {'state': 'finished', 'exit_code': 1, 'reason': 'exited'}})
        code, out = self.new()
        self.assertEqual(code, 1)
        self.assertIn(f'FAILED {LEAD}', out)
        self.assertFalse((self.events / 'jobs' / job_.job_key(self.job)).exists())


class Start(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_a_helper_is_a_child_of_the_lead_by_default_with_its_labels_and_prompt(self):
        code, out = self.start('build-api')
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip(), f'STARTED build-api (t2) under {LEAD}')
        run = self.runs()[-1]
        self.assertEqual(self.option(run, '--parent'), 't1')
        tags = self.labels(run)
        self.assertEqual((tags['stampede.role'], tags['stampede.agent'], tags['stampede.kind'], tags['herdr.tab'], tags['herdr.space']),
                         ('helper', 'build-api', 'claude', 'main', 'fix-login-bug'))
        self.assertNotIn('stampede.space', tags)
        prompt = self.program(run)[-1]
        report = self.job / 'reports/build-api.md'
        for said in ('You are build-api', f'Your parent is {LEAD} at t1', str(self.job / 'briefs/build-api.md'), str(report),
                     f'hc send t1 "build-api: <one line> {report}"', 'hc get $HC_TERMINAL_ID'):
            self.assertIn(said, prompt)
        self.assertEqual(self.state()['terminals']['t2']['parent'], 't1')
        node = json.loads((self.job / 'tree.json').read_text())['nodes']['build-api']
        self.assertEqual((node['parent'], node['session'], node['report']), (LEAD, tags['stampede.session'], str(report)))

    def test_codex_runs_without_its_daemon_and_with_no_hooks(self):
        self.start('build-ui', kind='codex')
        run = self.runs()[-1]
        self.assertIn('--no-daemon', run)
        self.assertFalse([a for a in run if 'notify=' in a])
        self.assertFalse((self.job / 'hooks').exists())

    def test_the_caller_is_the_parent_and_parent_names_another(self):
        self.start('build-api')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('test-api')
        self.assertEqual(self.option(self.runs()[-1], '--parent'), 't2')
        self.start('test-ui', parent='build-api', outlive=True)
        self.assertEqual(self.option(self.runs()[-1], '--parent'), 't2')
        self.assertIn('--outlive-parent', self.runs()[-1])
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't99'}):
            _, out = self.start('docs-api')
        self.assertIn(f'under {LEAD}', out)

    def test_a_program_after_dashes_runs_as_kind_program(self):
        code, out = self.start('watch-ci', 'sleep', '60')
        self.assertEqual(code, 0, out)
        run = self.runs()[-1]
        self.assertEqual(self.program(run), ['sleep', '60'])
        self.assertEqual(self.labels(run)['stampede.kind'], 'program')

    def test_refusals(self):
        self.start('build-api')
        bad = self.job / 'briefs/bad.md'
        bad.write_text('## Goal\nx\n')
        for kw, said in (({'agent': 'build-api'}, 'is taken'), ({'agent': LEAD}, 'is taken'), ({'pane': 'w1:p1'}, 'as a program'),
                         ({'brief': str(bad)}, 'is missing'), ({'kind': 'cursor'}, 'as a program'), ({'parent': 'nobody'}, 'no agent nobody')):
            args = {'agent': 'other', 'kind': 'claude', 'pane': None, 'brief': str(self.brief(self.job, 'other')), **kw}
            with self.subTest(kw=kw), self.assertRaises(ValueError) as refused:
                self.quiet(cli_.start, self.job, args.pop('agent'), args.pop('kind'), args.pop('pane'), args.pop('brief'), **args)
            self.assertIn(said, str(refused.exception))
        self.assertEqual(len(self.runs()), 2)

    def test_the_cli_refuses_pane_in_one_line(self):
        result = self.cli('start', self.job, 'x', '--kind', 'cursor', '--pane', 'w1:p1', '--brief', self.brief(self.job, 'x'))
        self.assertEqual(result.returncode, 2)
        refusal, command = result.stderr.strip().splitlines()   # one line, then the command to run, quoted as built
        self.assertIn('run that CLI as a program', refusal)
        self.assertEqual(shlex.split(command)[:4], ['stampede', 'start', str(self.job), 'x'])

    def test_the_cli_takes_flags_before_the_program(self):
        """argparse before 3.13 loses a program after -- once a flag stands before it: the CLI cuts at -- itself."""
        result = self.cli('start', self.job, 'watch-ci', '--tab', 'ci', '--outlive-parent', '--', 'sleep', '--', '60')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = self.runs()[-1]
        self.assertEqual(self.program(run), ['sleep', '--', '60'])
        self.assertEqual(self.labels(run)['herdr.tab'], 'ci')
        self.assertIn('--outlive-parent', run)


class Cap(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_the_thirteenth_queues_and_next_starts_it_once_one_is_done(self):
        for n in range(12):
            self.start(f'h{n}')
        code, out = self.start('h12')
        self.assertEqual((code, out.strip()), (0, 'QUEUED h12 (12 running, cap 12)'))
        code, out = self.start('h13')
        self.assertIn('QUEUED h13 (12 running, cap 12)', out)
        self.assertEqual(self.quiet(native_.next_, self.job)[1].strip(), 'WAITING 2 queued (12 running, cap 12)')
        self.terminal(self.addresses()['h0'], status={'state': 'done'})
        code, out = self.quiet(native_.next_, self.job)
        self.assertEqual(out.splitlines()[0], f'STARTED h12 (t{14}) under {LEAD}')   # oldest first
        self.terminal(self.addresses()['h1'], status={'state': 'idle'}, turn=1)
        hcapi_.hc('kill', self.addresses()['h2'])
        _, out = self.quiet(native_.next_, self.job)
        self.assertIn('STARTED h13', out)
        self.assertEqual(self.quiet(native_.next_, self.job)[1].strip(), 'NOTHING QUEUED')

    def test_depth_two_counts_and_the_lead_and_plain_children_do_not(self):
        for n in range(2):
            self.start(f'h{n}')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('deep')
        self.add_terminal('t9', parent='t1', labels={})   # a bare hc run of the lead's: no stampede label
        (self.job / 'max-helpers').write_text('3\n')
        _, out = self.start('more')
        self.assertIn('QUEUED more (3 running, cap 3)', out)

    def test_the_setting_and_the_file(self):
        with mock.patch.dict(os.environ, {'STAMPEDE_MAX_HELPERS': '1'}):
            self.start('h0')
            self.assertIn('cap 1', self.start('h1')[1])
            (self.job / 'max-helpers').write_text('2\n')
            self.assertIn('STARTED h1', self.quiet(native_.next_, self.job)[1])

    def test_a_queued_start_whose_parent_is_gone_is_dropped(self):
        (self.job / 'max-helpers').write_text('1\n')
        self.start('h0')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('child')
        hcapi_.hc('kill', 't2')
        _, out = self.quiet(native_.next_, self.job)
        self.assertIn('DROPPED child: its parent h0 is gone', out)
        self.assertTrue(list((self.job / 'queue/dropped').glob('*-child.json')))


class Tabs(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def tab(self, name):
        return self.state()['terminals'][self.addresses()[name]]['labels']['herdr.tab']

    def test_four_per_tab_then_the_next_and_tab_names_a_workstream(self):
        for n in range(4):
            self.start(f'h{n}')
        self.assertEqual([self.tab(f'h{n}') for n in range(4)], ['main', 'main', 'main', 'main-2'])
        for n in range(5):
            self.start(f'w{n}', tab='docs')
        self.assertEqual([self.tab(f'w{n}') for n in range(5)], ['docs'] * 4 + ['docs-2'])

    def test_the_setting(self):
        with mock.patch.dict(os.environ, {'STAMPEDE_TAB_PANES': '2'}):
            self.start('h0')
            self.start('h1')
        self.assertEqual((self.tab('h0'), self.tab('h1')), ('main', 'main-2'))


class Layout(NativeCase):
    """The owner's split order: the lead top left, then right of it, down of that, down of the lead; 4 a tab."""
    def setUp(self):
        super().setUp()
        self.started()

    def places(self, *names):
        tags = {t['labels'].get('stampede.agent'): t['labels'] for t in self.state()['terminals'].values() if t['state'] == 'live'}
        return [(tags[n]['herdr.tab'], tags[n]['stampede.pane'], tags[n].get('stampede.split'), tags[n].get('stampede.beside'))
                for n in names]

    def test_the_lead_and_three_helpers_then_four_a_tab(self):
        for n in range(1, 8):
            self.start(f'h{n}')
        self.assertEqual(self.places(LEAD, 'h1', 'h2', 'h3'), [('main', '1', None, None), ('main', '2', 'right', LEAD),
                                                              ('main', '3', 'down', 'h1'), ('main', '4', 'down', LEAD)])
        self.assertEqual(self.places('h4', 'h5', 'h6', 'h7'), [('main-2', '1', None, None), ('main-2', '2', 'right', 'h4'),
                                                              ('main-2', '3', 'down', 'h5'), ('main-2', '4', 'down', 'h4')])

    def test_a_workstream_tab_and_a_nested_level(self):
        for n in range(1, 4):
            self.start(f'w{n}', tab='ci')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': self.addresses()['w1']}):
            self.start('w1-sub', tab='ci')
            self.start('deep')
        self.assertEqual(self.places('w1', 'w2', 'w3', 'w1-sub', 'deep'),
                         [('ci', '1', None, None), ('ci', '2', 'right', 'w1'), ('ci', '3', 'down', 'w2'), ('ci', '4', 'down', 'w1'),
                          ('main', '2', 'right', LEAD)])

    def test_a_freed_place_is_taken_again_lowest_first_with_the_fall_back(self):
        for n in range(1, 4):
            self.start(f'h{n}')
        hcapi_.hc('kill', self.addresses()['h1'])
        hcapi_.hc('kill', self.addresses()['h2'])
        self.start('a')
        self.start('b')
        self.assertEqual(self.places('a', 'b'), [('main', '2', 'right', LEAD), ('main', '3', 'down', 'a')])
        hcapi_.hc('kill', self.addresses()['a'])
        self.start('c')   # pane 2 again; then pane 3's split target gone: it would split the lead right
        hcapi_.hc('kill', self.addresses()['c'])
        hcapi_.hc('kill', self.addresses()['b'])
        self.start('d')
        self.start('e')
        self.assertEqual(self.places('d', 'e'), [('main', '2', 'right', LEAD), ('main', '3', 'down', 'd')])
        hcapi_.hc('kill', self.addresses()['d'])
        self.terminal(self.addresses()['e'], labels={**self.state()['terminals'][self.addresses()['e']]['labels'], 'stampede.pane': '9'})
        self.start('f')
        self.assertEqual(self.places('f'), [('main', '2', 'right', LEAD)])

    def test_the_fall_back_when_the_split_target_is_free(self):
        self.start('h1')
        self.start('h2')
        hcapi_.hc('kill', self.addresses()['h1'])
        self.terminal(self.addresses()['h2'], labels={**self.state()['terminals'][self.addresses()['h2']]['labels'], 'stampede.pane': '3'})
        self.start('h3')
        self.start('h4')
        self.assertEqual(self.places('h3', 'h4'), [('main', '2', 'right', LEAD), ('main', '4', 'down', LEAD)])
        state = self.state()
        state['terminals']['t1']['labels'].pop('stampede.pane')
        (self.core / 'state.json').write_text(json.dumps(state))
        hcapi_.hc('kill', self.addresses()['h3'])
        self.start('h5')   # the lead holds a place but no number: pane 1 is free, so no split
        self.assertEqual(self.places('h5'), [('main', '1', None, None)])

    def test_the_setting_at_6(self):
        with mock.patch.dict(os.environ, {'STAMPEDE_TAB_PANES': '6'}):
            for n in range(1, 7):
                self.start(f'h{n}')
        self.assertEqual([p[1:] for p in self.places('h4', 'h5', 'h6')], [('5', 'right', 'h3'), ('6', 'right', 'h4'), ('1', None, None)])
        self.assertEqual(self.places('h6')[0][0], 'main-2')

    def test_a_second_job_has_its_own_main(self):
        ask = self.root / 'ask2.md'
        ask.write_text('Another job\n')
        code, out = self.quiet(cli_.new, str(ask), None, name='other', core=True, cwd=str(self.repo))
        self.assertEqual(code, 0, out)
        other = job_.job_key(self.repo / '.herdr-other')
        lead = next(t for t in self.state()['terminals'].values() if t['labels'].get('stampede.job') == other)
        self.assertEqual((lead['labels']['herdr.tab'], lead['labels']['stampede.pane']), ('main', '1'))

    def test_reopen_keeps_places_and_tree_shows_them(self):
        for n in range(1, 4):
            self.start(f'h{n}', kind='codex')
        hcapi_.hc('kill', 't1')
        self.quiet(native_.reopen, self.job, True, False, False)
        self.assertEqual(self.places(LEAD, 'h1', 'h2', 'h3'), [('main', '1', None, None), ('main', '2', 'right', LEAD),
                                                              ('main', '3', 'down', 'h1'), ('main', '4', 'down', LEAD)])
        nodes = json.loads((self.job / 'tree.json').read_text())['nodes']
        self.assertEqual((nodes['h2']['pane'], nodes['h2']['split'], nodes['h2']['beside']), (3, 'down', 'h1'))
        _, out = self.quiet(native_.tree, self.job)
        self.assertIn('h3 (t', out)
        self.assertTrue(any(line.endswith('tab main pane 4') and 'h3' in line for line in out.splitlines()), out)
        _, out = self.quiet(native_.tree, self.job, True)
        row = next(r for r in json.loads(out)['nodes'] if r['name'] == 'h1')
        self.assertEqual((row['tab'], row['pane'], row['split'], row['beside']), ('main', 2, 'right', LEAD))


class TreeTell(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_tree_text_and_json_with_an_unlabelled_child(self):
        self.start('build-api')
        self.add_terminal('t3', name='ci-wait', parent='t2', labels={}, status=None)
        (self.job / 'max-helpers').write_text('1\n')
        self.start('later')
        code, out = self.quiet(native_.tree, self.job)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ['space fix-login-bug (' + job_.job_key(self.job) + ')',
                                            f'  {LEAD} (t1) lead claude idle tab main pane 1', '    build-api (t2) helper claude idle tab main pane 2',
                                            '      ci-wait (t3) plain - live tab -', f'  queued later under {LEAD} (claude)'])
        shown = json.loads(self.quiet(native_.tree, self.job, True)[1])
        self.assertEqual([(n['name'], n['depth'], n['parent']) for n in shown['nodes']], [(LEAD, 0, None), ('build-api', 1, 't1'), ('ci-wait', 2, 't2')])
        self.assertEqual(shown['queue'][0]['name'], 'later')

    def test_tell_sends_and_a_refusal_is_failed_exit_2(self):
        self.start('build-api')
        code, out = self.quiet(owner_.tell, self.job, 'build-api', 'Use the v2 endpoint')
        self.assertEqual((code, out.strip()), (0, 'SUBMITTED build-api (t2)'))
        self.assertEqual(self.state()['terminals']['t2']['sent'], ['Use the v2 endpoint'])
        self.assertFalse([c for c in self.calls('send') if '--force' in c])
        self.quiet(owner_.tell, self.job, 'lead', 'the owner says hi')
        self.assertEqual(self.state()['terminals']['t1']['sent'], ['the owner says hi'])
        self.shape(send_error={'t2': 'cancelled'})
        code, out = self.quiet(owner_.tell, self.job, 'build-api', 'again')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith('FAILED build-api ('))
        result = self.cli('tell', self.job, 'nobody', 'x')
        self.assertEqual(result.returncode, 2)   # the names it has, as tell on the other backends gives them
        self.assertRegex(result.stdout.strip(), r'^FAILED nobody \(no live terminal of this job is nobody; it has: lead, build-api(, [a-z-]+)*\)$')

    def test_notify_lead_types_into_the_lead_and_never_raises(self):
        self.quiet(owner_.notify_lead, self.job, 'TURN build-api')
        self.assertEqual(self.state()['terminals']['t1']['sent'], ['TURN build-api'])
        self.shape(ls_error='unavailable')
        self.quiet(owner_.notify_lead, self.job, 'lost')


class Shared(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_ask_gate_ok_and_approve_gate(self):
        self.assertFalse(owner_.pane_yes(self.job))
        with mock.patch.object(owner_, 'ASK_CMD', 'true'):
            self.assertEqual(self.quiet(owner_.ask_now, self.job, 'Which db?', [], 'echo postgres')[0], 0)
        self.assertIn('ANSWER Which db?: postgres', self.state()['terminals']['t1']['sent'][-1])
        with mock.patch.object(owner_, 'ask_background'):
            self.quiet(owner_.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        gate = next((self.job / 'gates').glob('*.json')).stem
        with self.assertRaises(PermissionError) as refused:
            owner_.gate_ok(self.job, gate, SHA)
        self.assertNotIn('typed in your pane', str(refused.exception))
        self.quiet(owner_.tell, self.job, 'lead', 'yes')
        with self.assertRaises(PermissionError):
            owner_.gate_ok(self.job, gate, SHA)
        with mock.patch.object(owner_, 'ASK_CMD', 'true'):
            self.quiet(owner_.ask_now, self.job, 'q', [], None, gate)
        self.assertIn('APPROVED', self.quiet(owner_.gate_ok, self.job, gate, SHA)[1])

    def test_approve_gate_for_a_bot_and_post_and_finish(self):
        (self.job / 'owner').write_text('alpha\n')
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        gate = json.loads(next((self.job / 'gates').glob('*.json')).read_text())
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=True), self.assertRaises(PermissionError) as refused:
            owner_.approve_gate(self.job, gate['gate'], SHA, 'owner', owner_.gate_digest(gate))
        self.assertIn('Herdr Core', str(refused.exception))
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            self.assertIn('APPROVED', self.quiet(owner_.approve_gate, self.job, gate['gate'], SHA, 'owner in chat', owner_.gate_digest(gate))[1])
        self.assertIn('APPROVED', self.quiet(owner_.gate_ok, self.job, gate['gate'], SHA)[1])
        self.assertIn('POSTED 001 to alpha', self.quiet(owner_.post, self.job, 'PLAN READY')[1])
        self.assertIn('FINISHED', self.quiet(owner_.finish, self.job, 'done')[1])
        events = [json.loads(p.read_text())['payload'] for p in (self.root / 'queue/queue').glob('*') if not p.name.startswith('.')]
        self.assertTrue(events)
        key = job_.job_key(self.job)
        for event in events:
            self.assertEqual((event['workspace'], event['lead_pane']), (key, f'hc:{key}/t1'))
        self.assertFalse((self.events / 'jobs' / key).exists())

    def test_the_cli_routes(self):
        for verb in ('hook', '_deliver', '_wake'):
            args = ('hook', 'claude-stop', self.job, '--agent', 'x') if verb == 'hook' else (verb, self.job)
            self.assertEqual(self.cli(*args).returncode, 0, verb)
        relay, _ = self.core_job()
        for verb in ('next', 'tree', 'snapshot', 'reopen', 'close'):
            result = self.cli(verb, relay)
            self.assertEqual(result.returncode, 2, verb)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1, verb)
        self.assertEqual(self.cli('tree', self.job).returncode, 0)


class FrontDoor(NativeCase):
    """new --core --front-door: a chat outside Herdr and Core is the owner's only contact. The lead posts to
    <job>/outbox, stampede wait hands each item to the chat, and answers, approve and approve-gate reach the lead
    through Core (hc send), never an inbox file."""

    def setUp(self):
        super().setUp()
        self.started(front=True, review=True)

    def item(self, n):
        return (self.job / 'outbox' / f'{n:03d}.md').read_text()

    def answer_line(self, n):
        """The command an outbox item says to run, as the chat runs it (shlex), without the trailing no line."""
        return shlex.split(self.item(n).split('Answer with: ', 1)[1].split('   (a no:', 1)[0])

    def heard(self):
        return self.state()['terminals']['t1']['sent']

    def test_new_writes_the_file_and_a_brief_with_no_card_and_the_plan_posted(self):
        self.assertTrue((self.job / 'front-door').is_file())
        brief = (self.job / 'briefs' / (LEAD + '.md')).read_text()
        for said in ('talks only to the chat that started this job', f'post {self.job} "PLAN READY: <one line>" --file',
                     'reaches no one from a Core terminal', 'Core types the answer into this terminal',
                     'posted to the chat with its approve line', 'Post your report first', 'gate-ok'):
            self.assertIn(said, brief)
        self.assertFalse({chr(0x2013), chr(0x2014)} & set(brief))

    def test_new_refuses_it_with_relay_and_for_a_bot(self):
        for kw, env, says in (({'relay': True}, {}, 'drop --relay'), ({}, {'HERDR_EVENTS_OWNER': 'alpha'}, 'a bot relays its own jobs')):
            super().setUp()  # a fresh scratch each
            with mock.patch.dict(os.environ, env), self.assertRaises(ValueError) as refused:
                self.new(front=True, **kw)
            self.assertIn(says, str(refused.exception))
            self.assertFalse(self.job.exists(), 'nothing is made')
            self.assertEqual(self.runs(), [])
        result = self.cli('new', '--core', '--relay', '--front-door', '--file', self.root / 'ask.md', '--cwd', self.repo)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_post_ask_gate_and_finish_write_outbox_items_and_wait_hands_them_on(self):
        self.assertIn('POSTED 001 for the front door to relay', self.quiet(owner_.post, self.job, 'PLAN READY: two helpers')[1])
        ident, out = self.quiet(owner_.ask, self.job, 'Which db?', ['postgres', 'sqlite'])
        self.assertIn('posted to the front door as outbox 002', out)
        self.assertIn('Core types the answer into your terminal', out)
        self.assertNotIn('inbox', out)
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        self.assertFalse((self.job / 'asks').exists(), 'no phone card')
        code, out = self.quiet(owner_.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        for said in ('# 001 post', '# 002 question', '- postgres', '# 003 gate', 'approve-gate'):
            self.assertIn(said, out)
        self.assertEqual(self.quiet(owner_.wait, self.job, 0, 0)[0], 3, 'each item once, then a timeout')
        self.assertIn('TIMEOUT', self.quiet(owner_.wait, self.job, 0, 0)[1])
        self.quiet(owner_.finish, self.job, 'all done')
        self.assertIn('# 004 done', self.item(4))
        self.assertEqual(self.queue_events(), [], 'no bot hears a front-door job')

    def queue_events(self):
        return list((self.root / 'queue/queue').glob('*.json')) if (self.root / 'queue/queue').is_dir() else []

    def test_an_answer_and_approve_reach_the_lead_through_core(self):
        ident, _ = self.quiet(owner_.ask, self.job, 'Which db?', [])
        argv = self.answer_line(1)
        self.assertEqual(argv[:4], ['fleet-job', 'tell', str(self.job), 'lead'])
        code, out = self.quiet(owner_.tell, self.job, 'lead', argv[4].replace('<their words>', 'postgres'))
        self.assertEqual((code, out.strip()), (0, f'SUBMITTED {LEAD} (t1)'))
        self.assertEqual(self.heard()[-1], f'ANSWER {ident} Which db?: postgres')
        self.assertFalse((self.job / 'inbox').exists(), 'no inbox file on Core')
        (self.job / 'plan.md').write_text('two helpers\n')
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False), self.assertRaises(PermissionError):
            owner_.approve(self.job, 'owner')  # not posted yet
        self.quiet(owner_.post, self.job, 'PLAN READY', [str(self.job / 'plan.md')])
        self.quiet(owner_.wait, self.job, 5, 0)
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=True), self.assertRaises(PermissionError):
            owner_.approve(self.job, 'owner')  # the lead's own approve
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            self.quiet(owner_.approve, self.job, "owner in desktop chat: 'go'")
        self.assertIn('Start the helpers the plan names', self.heard()[-1])
        self.assertEqual(self.quiet(owner_.require_approval, self.job)[0], None)

    def test_the_gate_loop_opens_only_on_the_chat_s_approve_gate(self):
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        ident = next((self.job / 'gates').glob('*.json')).stem
        self.assertEqual(owner_.load_gate(self.job, ident)['route'], 'front-door')
        self.quiet(owner_.wait, self.job, 5, 0)
        argv = self.answer_line(1)
        self.assertEqual(argv[1:3], ['approve-gate', str(self.job)])
        self.quiet(owner_.tell, self.job, 'lead', 'yes')  # typed into the lead: never a yes
        with self.assertRaises(PermissionError):
            owner_.gate_ok(self.job, ident, SHA)
        by = argv[-1].replace('<chat>: <their exact words>', "desktop chat: 'merge it'")
        inside = self.cli(*argv[1:-1], by, env={'HC_TERMINAL_ID': 't9'})  # from a Core terminal
        self.assertEqual(inside.returncode, 2)
        self.assertIn("an agent's own say-so never counts", inside.stderr)
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            flags = dict(zip(argv[4::2], argv[5::2]))
            self.assertIn('APPROVED', self.quiet(owner_.approve_gate, self.job, ident, flags['--sha'], by, flags['--digest'])[1])
        self.assertIn(f'GATE {ident} APPROVED by owner in desktop chat', self.heard()[-1])
        self.assertIn('APPROVED', self.quiet(owner_.gate_ok, self.job, ident, SHA)[1])

    def test_wait_says_blocked_with_the_screen_and_lead_gone(self):
        self.terminal('t1', status={'state': 'blocked', 'kind': 'permission'}, screen='Allow this command?\n  1. Yes\n')
        code, out = self.quiet(owner_.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(f'BLOCKED {LEAD}: permission. Core says it waits at a dialog in its terminal t1'), out)
        self.assertIn('Allow this command?', out)
        self.assertNotIn('BLOCKED_ON_CARD', out)
        self.terminal('t1', status={'state': 'idle'})
        self.assertEqual(self.quiet(owner_.wait, self.job, 0, 0)[0], 3)
        self.terminal('t1', state='finished', reason='killed', status=None)
        code, out = self.quiet(owner_.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(f'LEAD_GONE {LEAD}: Herdr Core holds no live lead'), out)
        self.shape(ls_error='unavailable')  # Core does not answer: no news, not gone
        self.assertEqual(self.quiet(owner_.wait, self.job, 0, 0)[0], 3)


class Fake(CoreCase):
    def test_a_parent_from_parent_or_the_caller_and_its_end_ends_its_branch(self):
        hcapi_.hc('run', '--bg', '--no-parent', '--name', 'a', '--', 'x')
        hcapi_.hc('run', '--bg', '--parent', 'a', '--name', 'b', '--', 'x')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            hcapi_.hc('run', '--bg', '--name', 'c', '--', 'x')
            hcapi_.hc('run', '--bg', '--outlive-parent', '--name', 'd', '--', 'x')
        self.assertEqual([hcapi_.hc('get', t)['parent'] for t in ('t1', 't2', 't3', 't4')], [None, 't1', 't2', 't2'])
        hcapi_.hc('kill', 't1')
        self.assertEqual([hcapi_.hc('get', t)['state'] for t in ('t1', 't2', 't3', 't4')], ['finished', 'finished', 'finished', 'live'])
        self.assertEqual({t['address'] for t in native_.listing()}, {'t1', 't2', 't3', 't4'})


class Record(NativeCase):
    def nodes(self):
        return json.loads((self.job / 'tree.json').read_text())['nodes']

    def test_the_record_s_three_files_at_new_and_after_a_start(self):
        job = self.started()
        for name in ('tree.json', 'REOPEN.md', 'reopen.sh'):
            self.assertTrue((job / name).is_file(), name)
        self.assertTrue(os.access(job / 'reopen.sh', os.X_OK))
        self.assertIn(f'reopen {job}', (job / 'reopen.sh').read_text())
        self.assertNotIn('build-api', (job / 'REOPEN.md').read_text())
        self.start('build-api')
        self.assertIn('| build-api | helper | ' + LEAD + ' | claude |', (job / 'REOPEN.md').read_text())

    def test_a_fork_s_record_is_what_a_reopen_needs(self):
        sid = '12345678-1234-1234-1234-123456789abc'
        self.started(fork=sid)
        self.assertIn('--fork-session', self.runs()[0])
        argv = self.nodes()[LEAD]['argv']
        self.assertNotIn('--fork-session', argv)
        self.assertNotIn(sid, argv)
        self.assertIn('--session-id', argv)

    def test_a_snapshot_with_a_plain_child_a_finished_node_and_a_gone_node(self):
        self.started()
        self.start('build-api')
        self.start('watch-ci', 'make', 'watch')
        self.add_terminal('t4', name='ci-wait', parent='t2', labels={}, status=None, argv=['make', 'test'])
        self.terminal('t3', state='finished', exit_code=3, reason='exited', status=None)
        self.terminal('t2', labels={**self.state()['terminals']['t2']['labels'], 'stampede.kind': 'codex'})
        native_.record(self.job, 'old-one', role='helper', kind='claude', state='live')
        session = self.nodes()['build-api']['session']
        code, out = self.quiet(native_.snapshot, self.job)
        self.assertEqual((code, out.strip()), (0, str(self.job / 'tree.json')))
        nodes = self.nodes()
        self.assertEqual((nodes['ci-wait']['role'], nodes['ci-wait']['argv'], nodes['ci-wait']['parent']), ('plain', ['make', 'test'], 'build-api'))
        self.assertEqual((nodes['watch-ci']['state'], nodes['watch-ci']['exit_code'], nodes['watch-ci']['reason']), ('finished', 3, 'exited'))
        self.assertEqual(nodes['old-one']['state'], 'gone')
        self.assertEqual((nodes['build-api']['kind'], nodes['build-api']['session'], nodes['build-api']['address']), ('claude', session, 't2'))
        self.assertIn('ci-wait', (self.job / 'REOPEN.md').read_text())
        self.shape(ls_error='unavailable')
        self.assertEqual(self.cli('snapshot', self.job).returncode, 1)

    def test_herdr_reopen_snapshot_hands_a_native_job_to_fleet_job_snapshot(self):
        self.started()
        self.start('build-api')
        hcapi_.hc('kill', 't2')
        script = SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'
        done = subprocess.run([str(script), job_.job_key(self.job), str(self.job)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.nodes()['build-api']['state'], 'finished')
        self.shape(ls_error='unavailable')
        self.assertNotEqual(subprocess.run([str(script), job_.job_key(self.job), str(self.job)], capture_output=True).returncode, 0)

    def test_finish_refreshes_the_record_and_never_fails_for_it(self):
        self.started()
        self.start('build-api')
        hcapi_.hc('kill', 't2')
        self.quiet(owner_.finish, self.job, 'done')
        self.assertEqual(self.nodes()['build-api']['state'], 'finished')
        self.shape(ls_error='unavailable')
        (self.job / 'finished').unlink()
        self.assertIn('FINISHED', self.quiet(owner_.finish, self.job, 'done again')[1])


class Reopen(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()
        self.start('build-api')                       # t2, claude, its session file exists
        self.start('build-ui', kind='codex')          # t3
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('deep')                        # t4, under build-api
        self.start('watch-ci', 'make', 'watch')       # t5, a program
        self.add_terminal('t6', name='ci-wait', parent='t1', labels={}, status=None, argv=['make', 'test'], die_with_parent=True)
        self.quiet(native_.snapshot, self.job)
        self.nodes = json.loads((self.job / 'tree.json').read_text())['nodes']
        folder = self.root / 'home/.claude/projects/x'
        folder.mkdir(parents=True)
        (folder / (self.nodes['build-api']['session'] + '.jsonl')).write_text('{}\n')
        hcapi_.hc('kill', 't1')                           # the whole tree ends with the lead
        self.before = len(self.runs())

    def reopen(self, *flags):
        return self.quiet(native_.reopen, self.job, '--fresh' in flags, '--prompt' in flags, '--rerun-programs' in flags)

    def run_of(self, name):
        return next(r for r in self.runs()[self.before:] if self.labels(r).get('stampede.agent') == name)

    def test_parents_first_each_under_its_parent_s_new_address(self):
        code, out = self.reopen()
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), [f'STARTED {LEAD} (t7)', f'STARTED build-api (t8) under {LEAD}',
                                            'SKIPPED build-ui (codex keeps no session to resume: --fresh starts it again with its brief)',
                                            'SKIPPED watch-ci (a program: --rerun-programs runs it again)',
                                            'SKIPPED ci-wait (a plain child: run it again if still needed: make test)',
                                            'STARTED deep (t9) under build-api'])   # its session never ran: through the queue, after the walk
        lead, api, deep = (self.run_of(n) for n in (LEAD, 'build-api', 'deep'))
        self.assertIn('--no-parent', lead)
        self.assertEqual(self.option(lead, '--session-id'), self.nodes[LEAD]['session'])   # no session file: it never ran
        self.assertTrue(self.program(lead)[-1].startswith(f'You are {LEAD}.'))
        self.assertEqual((self.option(api, '--parent'), self.option(api, '--resume')), ('t7', self.nodes['build-api']['session']))
        self.assertNotIn('--session-id', api)
        self.assertNotIn('You are', self.program(api)[-1])
        self.assertEqual(self.labels(api)['stampede.resumed'], '1')
        self.assertEqual(self.option(deep, '--parent'), 't8')
        self.assertIn('Your parent is build-api at t8', self.program(deep)[-1])
        self.assertEqual(self.labels(deep)['herdr.tab'], self.nodes['deep']['tab'])
        self.assertIn('You were reopened', self.state()['terminals']['t7']['sent'][-1])
        self.assertEqual(self.state()['terminals']['t8']['sent'], [])
        code, out = self.reopen()
        self.assertEqual(len(self.runs()), self.before + 3)
        self.assertEqual(sorted(row.split()[0] for row in out.splitlines()), ['LIVE'] * 3 + ['SKIPPED'] * 3)

    def test_prompt_and_fresh(self):
        self.reopen('--prompt')
        self.assertIn(f'Your parent is {LEAD} at t7', self.state()['terminals']['t8']['sent'][-1])
        self.setUp()
        self.reopen('--fresh')
        api = self.run_of('build-api')
        self.assertNotIn('--resume', api)
        self.assertNotEqual(self.option(api, '--session-id'), self.nodes['build-api']['session'])

    def test_programs_run_again_only_with_the_flag_and_never_after_exit_0(self):
        self.assertIn('STARTED watch-ci', self.reopen('--rerun-programs')[1])
        self.assertEqual(self.program(self.run_of('watch-ci')), ['make', 'watch'])
        self.setUp()
        native_.record(self.job, 'watch-ci', state='finished', exit_code=0)
        self.assertIn('DONE watch-ci (exited 0)', self.reopen('--rerun-programs')[1])

    def test_a_failed_parent_s_children_are_skipped(self):
        self.shape(run_error={'build-api': 'spawn_failed'})
        code, out = self.reopen()
        self.assertEqual(code, 1)
        self.assertIn('FAILED build-api (', out)
        self.assertIn('SKIPPED deep: its parent build-api is not running', out)

    def test_the_marker_and_tag_come_back_and_closed_goes_and_a_finished_job_gets_neither(self):
        key = job_.job_key(self.job)
        (self.job / 'owner').write_text('alpha\n')
        (self.events / 'jobs' / key).unlink()
        (self.job / 'closed').write_text('x\n')
        self.reopen()
        self.assertTrue((self.events / 'jobs' / key).is_file())
        self.assertIn('owner=alpha', (self.events / 'owners' / key).read_text())
        self.assertFalse((self.job / 'closed').exists())
        self.setUp()
        key = job_.job_key(self.job)
        (self.job / 'finished').write_text('done\n')
        (self.events / 'jobs' / key).unlink()
        self.reopen()
        self.assertFalse((self.events / 'jobs' / key).exists())

    def test_a_resumed_idle_agent_holds_no_place_under_the_cap(self):
        self.reopen()
        (self.job / 'max-helpers').write_text('1\n')   # build-api (resumed, idle) does not count; deep does
        self.assertIn('QUEUED', self.start('more')[1])
        (self.job / 'max-helpers').write_text('2\n')
        self.assertIn('STARTED more', self.quiet(native_.next_, self.job)[1])


class NoWorkByItself(NativeCase):
    """A reopen never hands out work by itself (R1, R3), and an uncertain start is never lost or doubled (R2)."""
    def running(self):
        return sum(native_.running(t) for t in self.state()['terminals'].values())

    def waiting(self):
        return [r['name'] for _, r in native_.queued(self.job)]

    def reopen(self, *flags):
        return self.quiet(native_.reopen, self.job, '--fresh' in flags, '--prompt' in flags, '--rerun-programs' in flags)

    def test_r1_reopen_keeps_the_cap(self):
        self.started(max_helpers=1)
        self.start('a', kind='codex')
        self.terminal('t2', status={'state': 'done'}, turn=1)
        self.start('b', kind='codex')
        hcapi_.hc('kill', 't1')
        code, out = self.reopen()
        self.assertIn('SKIPPED a (codex keeps no session to resume: --fresh starts it again with its brief)', out)
        self.assertEqual((self.running(), self.waiting()), (0, []))
        code, out = self.reopen('--fresh')
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[1:], [f'STARTED a (t5) under {LEAD}', 'QUEUED b (1 running, cap 1)'])
        self.assertEqual((self.running(), self.waiting()), (1, ['b']))
        self.assertIn(f'Your parent is {LEAD} at t4', self.program(self.runs()[-1])[-1])

    def test_r2_a_start_that_timed_out_but_began_is_adopted_and_holds_its_place(self):
        self.started(max_helpers=1)
        for name in ('a', 'b', 'c'):
            self.start(name)
        self.terminal('t2', status={'state': 'done'}, turn=1)
        self.shape(run_error={'b': 'timeout'}, spawn_also=True)
        code, out = self.quiet(native_.next_, self.job)
        self.assertEqual(out.splitlines(), [f'STARTED b (t3) under {LEAD}', 'WAITING 1 queued (1 running, cap 1)'])
        self.assertEqual((code, self.running(), self.waiting()), (0, 1, ['c']))
        node = json.loads((self.job / 'tree.json').read_text())['nodes']['b']
        self.assertEqual((node['address'], node['session']), ('t3', self.state()['terminals']['t3']['labels']['stampede.session']))

    def test_r3_a_finished_job_reopens_for_reading_only(self):
        self.started(max_helpers=1)
        self.start('a', kind='codex')
        self.quiet(owner_.finish, self.job, 'accepted')
        hcapi_.hc('kill', 't1')
        before = len(self.runs())
        code, out = self.reopen()
        self.assertEqual(len(self.runs()), before)
        self.assertIn(f'SKIPPED {LEAD} (the job is finished, and its Claude session never ran', out)
        self.assertIn(f'SKIPPED a: its parent {LEAD} is not running', out)
        folder = self.root / 'home/.claude/projects/x'
        folder.mkdir(parents=True)
        session = json.loads((self.job / 'tree.json').read_text())['nodes'][LEAD]['session']
        (folder / (session + '.jsonl')).write_text('{}\n')
        code, out = self.reopen('--prompt')
        lead = self.runs()[-1]
        self.assertEqual((len(self.runs()), self.option(lead, '--resume')), (before + 1, session))
        self.assertNotIn('Read ', self.program(lead)[-1])
        self.assertIn('SKIPPED a (the job is finished, and codex keeps no session to resume)', out)
        self.assertIn('reopened for reading: the job is finished', self.state()['terminals']['t3']['sent'][-1])
        self.assertEqual(self.waiting(), [])

    def test_the_refusals_on_a_finished_job(self):
        self.started()
        (self.job / 'finished').write_text('done\n')
        for flag in ('--fresh', '--rerun-programs'):
            done = self.cli('reopen', self.job, flag)
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn('reopens for reading only', done.stderr)

    def test_r5_a_finished_job_never_runs_its_queue(self):
        self.started(max_helpers=1)
        self.start('a', kind='codex')
        self.start('b', kind='codex')
        self.quiet(owner_.finish, self.job, 'accepted')
        self.terminal('t2', status={'state': 'done'}, turn=1)
        before = len(self.runs())
        code, out = self.reopen()
        self.assertEqual((code, len(self.runs()), self.waiting()), (0, before, ['b']))
        self.assertEqual(out.splitlines(), ['SKIPPED b (the job is finished: its queued start stays in the queue)',
                                            f'LIVE {LEAD} (t1)', 'LIVE a (t2)'])
        for verb in (('next', self.job), ('start', self.job, 'c', '--kind', 'claude')):
            done = self.cli(*verb)
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn('the job is finished: it starts no helper', done.stderr)
        self.assertEqual((len(self.runs()), self.waiting()), (before, ['b']))

    def test_fresh_and_rerun_programs_go_through_the_cap(self):
        self.started()
        self.start('build-api')
        self.start('build-ui', kind='codex')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('deep')
        self.start('watch-ci', 'make', 'watch')
        (self.job / 'max-helpers').write_text('1\n')
        hcapi_.hc('kill', 't1')
        code, out = self.reopen('--fresh', '--rerun-programs')
        self.assertEqual(out.splitlines(), [f'STARTED {LEAD} (t6)', f'STARTED build-api (t7) under {LEAD}',
                                            'QUEUED build-ui (1 running, cap 1)', 'QUEUED deep (1 running, cap 1)',
                                            'QUEUED watch-ci (1 running, cap 1)'])
        self.terminal('t7', status={'state': 'done'}, turn=1)
        self.assertIn('STARTED build-ui (t8) under', self.quiet(native_.next_, self.job)[1])
        self.terminal('t8', status={'state': 'done'}, turn=1)
        _, out = self.quiet(native_.next_, self.job)
        self.assertIn('STARTED deep (t9) under build-api', out)
        self.assertIn('Your parent is build-api at t7', self.program(self.runs()[-1])[-1])

    def test_a_child_whose_parent_still_waits_is_left_waiting_then_started_after_it(self):
        self.started()
        queue = self.job / 'queue'
        queue.mkdir(exist_ok=True)
        for stamp, name, parent in ((1, 'child', 'p'), (2, 'p', LEAD)):
            request = dict(name=name, kind='claude', brief=str(self.brief(self.job, name)), model=None, effort=None, cwd=str(self.repo),
                           tab=None, parent=parent, outlive=False, program=[], yolo=False, report=str(self.job / 'reports' / name))
            (queue / f'{stamp}-{name}.json').write_text(json.dumps(request))
        _, out = self.quiet(native_.next_, self.job)
        self.assertEqual(out.splitlines(), [f'STARTED p (t2) under {LEAD}', 'WAITING 1 queued (1 running, cap 12)'])
        self.assertEqual(self.quiet(native_.next_, self.job)[1].strip(), 'STARTED child (t3) under p')

    def test_a_request_whose_terminal_already_lives_is_adopted(self):
        self.started()
        (self.job / 'max-helpers').write_text('1\n')
        self.start('h0')
        self.start('h1')
        self.terminal('t2', status={'state': 'done'}, turn=1)
        self.add_terminal('t9', parent='t1', labels={'stampede.job': job_.job_key(self.job), 'stampede.role': 'helper',
                                                     'stampede.agent': 'h1', 'stampede.kind': 'claude', 'herdr.tab': 'main'})
        before = len(self.runs())
        _, out = self.quiet(native_.next_, self.job)
        self.assertEqual(out.strip(), f'STARTED h1 (t9) under {LEAD}')
        self.assertEqual((len(self.runs()), self.waiting()), (before, []))

    def test_core_silent_after_a_failed_run_keeps_the_request(self):
        self.started()
        (self.job / 'max-helpers').write_text('1\n')
        self.start('h0')
        self.start('h1')
        self.start('h2')
        self.terminal('t2', status={'state': 'done'}, turn=1)
        self.shape(run_error={'h1': 'timeout'}, lookup_error='timeout')
        code, out = self.quiet(native_.next_, self.job)
        self.assertEqual(code, 1)
        self.assertIn('UNKNOWN h1: ', out)
        self.assertIn('run stampede next once Herdr Core answers', out)
        self.assertNotIn('h2', out)
        self.assertEqual(self.waiting(), ['h1', 'h2'])


class Close(NativeCase):
    def setUp(self):
        super().setUp()
        self.shape(on_run={'build-api': {'leaves': 1}, 'deep': {'status': {'state': 'working'}}})
        patch = mock.patch.object(native_, 'LEAVE_FOR', 3)   # the lead stays idle: it is killed after this long
        patch.start()
        self.addCleanup(patch.stop)
        self.started()
        self.start('build-api')                                    # t2, idle, leaves 1 s after /exit
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('deep', kind='codex')                       # t3, working
        self.add_terminal('t4', name='ci-wait', parent='t3', labels={}, status=None, die_with_parent=True)

    def test_the_whole_job_closes_deepest_first_politely_when_idle(self):
        code, out = self.quiet(native_.close, self.job)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), ['CLOSED ci-wait (t4)', 'CLOSED deep (t3)', 'CLOSED build-api (t2)', f'CLOSED {LEAD} (t1)'])
        self.assertEqual([c[-1] for c in self.calls('rm')], ['t4', 't3', 't2', 't1'])
        killed = [c[-1] for c in self.calls('kill')]
        self.assertNotIn('t2', killed)                             # it was given its time and left on /exit
        self.assertEqual((self.state()['terminals'].get('t2'), [c for c in self.calls('get') if c[-1] == 't2'] != []), (None, True))
        self.assertIn('t3', killed)                                # working: killed
        self.assertIn('t1', killed)                                # idle but stayed: killed after the wait
        self.assertEqual(self.calls('keys')[0][2:], ['t2', '/', 'e', 'x', 'i', 't', 'enter'])
        self.assertTrue((self.job / 'closed').is_file())
        nodes = json.loads((self.job / 'tree.json').read_text())['nodes']
        self.assertFalse({nodes[n]['state'] for n in (LEAD, 'build-api', 'deep')} & {'closed'})   # put away, not closed for good

    def test_an_idle_agent_leaves_by_itself_with_exit_0(self):
        self.terminal('t3', status={'state': 'idle'}, leaves=1)
        self.quiet(native_.close, self.job, 'deep')
        self.assertNotIn('t3', [c[-1] for c in self.calls('kill')])

    def test_a_helper_closed_by_name_stays_closed_at_reopen_and_a_whole_close_does_not(self):
        self.quiet(native_.close, self.job, 'build-api')
        nodes = json.loads((self.job / 'tree.json').read_text())['nodes']
        self.assertEqual((nodes['build-api']['state'], nodes['deep']['state']), ('closed', 'closed'))
        hcapi_.hc('kill', 't1')
        before = len(self.calls('run'))
        code, out = self.quiet(native_.reopen, self.job)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), [f'STARTED {LEAD} (t5)', 'DONE build-api (closed)', 'DONE deep (closed)'])
        self.assertEqual(len(self.calls('run')), before + 1)
        self.quiet(native_.close, self.job)
        _, out = self.quiet(native_.reopen, self.job)
        self.assertIn(f'STARTED {LEAD}', out)
        self.assertIn('DONE build-api (closed)', out)

    def test_a_helper_s_subtree_and_the_refusal_from_inside(self):
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't3'}), self.assertRaises(ValueError):
            native_.close(self.job, 'build-api')
        result = self.cli('close', self.job, 'lead', env={'HC_TERMINAL_ID': 't1'})
        self.assertEqual((result.returncode, len(result.stderr.strip().splitlines())), (2, 1))
        _, out = self.quiet(native_.close, self.job, 'build-api')
        self.assertEqual(out.splitlines(), ['CLOSED ci-wait (t4)', 'CLOSED deep (t3)', 'CLOSED build-api (t2)'])
        self.assertFalse((self.job / 'closed').exists())
        self.assertEqual(self.state()['terminals']['t1']['state'], 'live')

    def test_a_terminal_core_refuses_is_failed_and_the_rest_go_on(self):
        self.shape(get_error={'t3': 'unavailable'})
        code, out = self.quiet(native_.close, self.job)
        self.assertEqual(code, 1)
        self.assertIn('FAILED deep (', out)
        self.assertIn(f'CLOSED {LEAD} (t1)', out)



class Outlived(NativeCase):
    """A terminal that outlived a dead lead (Core sets parent once) is still the job's."""

    def setUp(self):
        super().setUp()
        self.started()
        self.start('keeper', 'sleep', '900', outlive=True)        # t2, under t1, outlives it
        self.add_terminal('t3', name='keeper-log', parent='t2', labels={}, status=None)
        hcapi_.hc('kill', 't1')
        self.quiet(native_.reopen, self.job)                  # the lead is t4; keeper still names t1

    def test_tree_snapshot_the_cap_and_close_take_it(self):
        self.assertEqual(self.state()['terminals']['t2']['parent'], 't1')
        _, out = self.quiet(native_.tree, self.job)
        self.assertIn(f'    keeper (t2) helper program idle tab main pane 2 outlived {LEAD}', out.splitlines())
        self.assertIn('      keeper-log (t3) plain - live tab -', out.splitlines())
        shown = json.loads(self.quiet(native_.tree, self.job, True)[1])
        self.assertEqual([(n['name'], n['depth'], n['outlived']) for n in shown['nodes']][1:],
                         [('keeper', 1, LEAD), ('keeper-log', 2, None)])
        self.quiet(native_.snapshot, self.job)
        nodes = json.loads((self.job / 'tree.json').read_text())['nodes']
        self.assertEqual((nodes['keeper']['state'], nodes['keeper']['address']), ('live', 't2'))
        (self.job / 'max-helpers').write_text('1\n')
        self.assertIn('QUEUED more (1 running, cap 1)', self.start('more', 'sleep', '1')[1])
        (self.job / 'queue').joinpath('dropped').mkdir(exist_ok=True)
        for path in (self.job / 'queue').glob('*.json'):
            path.unlink()
        _, out = self.quiet(native_.close, self.job)
        self.assertEqual(out.splitlines(), ['CLOSED keeper-log (t3)', 'CLOSED keeper (t2)', f'CLOSED {LEAD} (t4)'])


class Wording(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_a_helper_named_lead_is_refused_with_its_reason(self):
        with self.assertRaises(ValueError) as refused:
            self.start('lead')
        self.assertIn("lead names the job's lead", str(refused.exception))

    def test_ask_says_core_types_the_answer_into_the_terminal(self):
        with mock.patch.object(subprocess, 'Popen') as spawned:
            spawned.return_value.pid = 1
            _, out = self.quiet(owner_.ask, self.job, 'Which db?', [])
        self.assertNotIn('inbox', out)
        self.assertIn("Core types the answer into the lead's terminal", out)
        (self.job / 'owner').write_text('alpha\n')
        _, out = self.quiet(owner_.ask, self.job, 'Which db?', [])
        self.assertNotIn('inbox', out)
        self.assertIn('Core types the answer into your terminal', out)


if __name__ == '__main__':
    unittest.main()
