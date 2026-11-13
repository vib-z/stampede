"""A Core-native job (stampede new --core, docs/CORE-NATIVE.md): the lead as a root, helpers as Core children, the cap
and its queue, the tabs, the tree, tell, and the shared commands. Every Core call goes to tests/fake_hc.py through HC."""
import json, os, subprocess, sys, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, SCRIPTS, SHA, LEAD, fj  # noqa: E402

FLEET = SCRIPTS / 'fleet-job'


class NativeCase(CoreCase):
    def new(self, **kw):
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        return self.quiet(fj.new, str(ask), None, core=True, cwd=str(self.repo), **kw)

    def started(self, **kw):
        code, out = self.new(**kw)
        self.assertEqual(code, 0, out)
        return self.job

    def start(self, name, *program, kind='claude', **kw):
        brief = None if program else str(self.brief(self.job, name))
        return self.quiet(fj.start, self.job, name, None if program else kind, None, brief, program=program, **kw)

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
        key = fj.job_key(job)
        self.assertEqual({k: tags[k] for k in ('stampede.job', 'stampede.role', 'stampede.agent', 'stampede.space', 'stampede.kind',
                                               'herdr.space', 'herdr.tab')},
                         {'stampede.job': key, 'stampede.role': 'lead', 'stampede.agent': LEAD, 'stampede.space': 'fix-login-bug',
                          'stampede.kind': 'claude', 'herdr.space': 'fix-login-bug', 'herdr.tab': 'main'})
        self.assertEqual(tags['stampede.session'], self.option(run, '--session-id'))
        self.assertNotIn('--settings', run)
        self.assertEqual(fj.backend(job), 'native')
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
        self.assertEqual((job / 'space').read_text().strip(), 'fix-login-bug-' + fj.job_key(job)[3:7])
        self.setUp()
        job = self.started(space='login', max_helpers=3)
        self.assertEqual((job / 'space').read_text().strip(), 'login')
        self.assertEqual((job / 'max-helpers').read_text().strip(), '3')
        self.assertEqual(self.labels(self.runs()[0])['herdr.space'], 'login')

    def test_relay_makes_the_earlier_kind_and_space_needs_native(self):
        with mock.patch.object(fj, 'new_core', return_value=0) as core:
            self.new(relay=True)
        core.assert_called_once()
        with self.assertRaises(ValueError):
            self.new(relay=True, space='x')

    def test_a_lead_that_ends_at_once_is_failed_and_taken_back(self):
        self.shape(on_run={LEAD: {'state': 'finished', 'exit_code': 1, 'reason': 'exited'}})
        code, out = self.new()
        self.assertEqual(code, 1)
        self.assertIn(f'FAILED {LEAD}', out)
        self.assertFalse((self.events / 'jobs' / fj.job_key(self.job)).exists())


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
                self.quiet(fj.start, self.job, args.pop('agent'), args.pop('kind'), args.pop('pane'), args.pop('brief'), **args)
            self.assertIn(said, str(refused.exception))
        self.assertEqual(len(self.runs()), 2)

    def test_the_cli_refuses_pane_in_one_line(self):
        result = self.cli('start', self.job, 'x', '--kind', 'cursor', '--pane', 'w1:p1', '--brief', self.brief(self.job, 'x'))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)
        self.assertIn('run that CLI as a program', result.stderr)


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
        self.assertEqual(self.quiet(fj.native().next_, self.job)[1].strip(), 'WAITING 2 queued (12 running, cap 12)')
        self.terminal(self.addresses()['h0'], status={'state': 'done'})
        code, out = self.quiet(fj.native().next_, self.job)
        self.assertEqual(out.splitlines()[0], f'STARTED h12 (t{14}) under {LEAD}')   # oldest first
        self.terminal(self.addresses()['h1'], status={'state': 'idle'}, turn=1)
        fj.hc('kill', self.addresses()['h2'])
        _, out = self.quiet(fj.native().next_, self.job)
        self.assertIn('STARTED h13', out)
        self.assertEqual(self.quiet(fj.native().next_, self.job)[1].strip(), 'NOTHING QUEUED')

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
            self.assertIn('STARTED h1', self.quiet(fj.native().next_, self.job)[1])

    def test_a_queued_start_whose_parent_is_gone_is_dropped(self):
        (self.job / 'max-helpers').write_text('1\n')
        self.start('h0')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            self.start('child')
        fj.hc('kill', 't2')
        _, out = self.quiet(fj.native().next_, self.job)
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


class TreeTell(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_tree_text_and_json_with_an_unlabelled_child(self):
        self.start('build-api')
        self.add_terminal('t3', name='ci-wait', parent='t2', labels={}, status=None)
        (self.job / 'max-helpers').write_text('1\n')
        self.start('later')
        code, out = self.quiet(fj.native().tree, self.job)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ['space fix-login-bug (' + fj.job_key(self.job) + ')',
                                            f'  {LEAD} (t1) lead claude idle tab main', '    build-api (t2) helper claude idle tab main',
                                            '      ci-wait (t3) plain - live tab -', f'  queued later under {LEAD} (claude)'])
        shown = json.loads(self.quiet(fj.native().tree, self.job, True)[1])
        self.assertEqual([(n['name'], n['depth'], n['parent']) for n in shown['nodes']], [(LEAD, 0, None), ('build-api', 1, 't1'), ('ci-wait', 2, 't2')])
        self.assertEqual(shown['queue'][0]['name'], 'later')

    def test_tell_sends_and_a_refusal_is_failed_exit_2(self):
        self.start('build-api')
        code, out = self.quiet(fj.tell, self.job, 'build-api', 'Use the v2 endpoint')
        self.assertEqual((code, out.strip()), (0, 'SUBMITTED build-api (t2)'))
        self.assertEqual(self.state()['terminals']['t2']['sent'], ['Use the v2 endpoint'])
        self.assertFalse([c for c in self.calls('send') if '--force' in c])
        self.quiet(fj.tell, self.job, 'lead', 'the owner says hi')
        self.assertEqual(self.state()['terminals']['t1']['sent'], ['the owner says hi'])
        self.shape(send_error={'t2': 'cancelled'})
        code, out = self.quiet(fj.tell, self.job, 'build-api', 'again')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith('FAILED build-api ('))
        result = self.cli('tell', self.job, 'nobody', 'x')
        self.assertEqual((result.returncode, result.stdout.strip()), (2, 'FAILED nobody (no live terminal of this job is nobody)'))

    def test_notify_lead_types_into_the_lead_and_never_raises(self):
        self.quiet(fj.notify_lead, self.job, 'TURN build-api')
        self.assertEqual(self.state()['terminals']['t1']['sent'], ['TURN build-api'])
        self.shape(ls_error='unavailable')
        self.quiet(fj.notify_lead, self.job, 'lost')


class Shared(NativeCase):
    def setUp(self):
        super().setUp()
        self.started()

    def test_ask_gate_ok_and_approve_gate(self):
        self.assertFalse(fj.pane_yes(self.job))
        with mock.patch.object(fj, 'ASK_CMD', 'true'):
            self.assertEqual(self.quiet(fj.ask_now, self.job, 'Which db?', [], 'echo postgres')[0], 0)
        self.assertIn('ANSWER Which db?: postgres', self.state()['terminals']['t1']['sent'][-1])
        with mock.patch.object(fj, 'ask_background'):
            self.quiet(fj.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        gate = next((self.job / 'gates').glob('*.json')).stem
        with self.assertRaises(PermissionError) as refused:
            fj.gate_ok(self.job, gate, SHA)
        self.assertNotIn('typed in your pane', str(refused.exception))
        self.quiet(fj.tell, self.job, 'lead', 'yes')
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job, gate, SHA)
        with mock.patch.object(fj, 'ASK_CMD', 'true'):
            self.quiet(fj.ask_now, self.job, 'q', [], None, gate)
        self.assertIn('APPROVED', self.quiet(fj.gate_ok, self.job, gate, SHA)[1])

    def test_approve_gate_for_a_bot_and_post_and_finish(self):
        (self.job / 'owner').write_text('alpha\n')
        self.quiet(fj.ask_gate, self.job, 'Merge PR #3', SHA, 3)
        gate = json.loads(next((self.job / 'gates').glob('*.json')).read_text())
        with mock.patch.object(fj, 'inside_herdr', return_value=True), self.assertRaises(PermissionError) as refused:
            fj.approve_gate(self.job, gate['gate'], SHA, 'owner', fj.gate_digest(gate))
        self.assertIn('Herdr Core', str(refused.exception))
        with mock.patch.object(fj, 'inside_herdr', return_value=False):
            self.assertIn('APPROVED', self.quiet(fj.approve_gate, self.job, gate['gate'], SHA, 'owner in chat', fj.gate_digest(gate))[1])
        self.assertIn('APPROVED', self.quiet(fj.gate_ok, self.job, gate['gate'], SHA)[1])
        self.assertIn('POSTED 001 to alpha', self.quiet(fj.post, self.job, 'PLAN READY')[1])
        self.assertIn('FINISHED', self.quiet(fj.finish, self.job, 'done')[1])
        events = [json.loads(p.read_text())['payload'] for p in (self.root / 'queue/queue').glob('*') if not p.name.startswith('.')]
        self.assertTrue(events)
        key = fj.job_key(self.job)
        for event in events:
            self.assertEqual((event['workspace'], event['lead_pane']), (key, f'hc:{key}/t1'))
        self.assertFalse((self.events / 'jobs' / key).exists())

    def test_the_cli_routes(self):
        for verb in ('hook', '_deliver', '_wake'):
            args = ('hook', 'claude-stop', self.job, '--agent', 'x') if verb == 'hook' else (verb, self.job)
            self.assertEqual(self.cli(*args).returncode, 0, verb)
        result = self.cli('snapshot', self.job)
        self.assertEqual((result.returncode, result.stderr.strip()), (2, 'fleet-job snapshot: snapshot on a native job is not built yet'))
        relay, _ = self.core_job()
        for verb in ('next', 'tree', 'snapshot', 'reopen', 'close'):
            result = self.cli(verb, relay)
            self.assertEqual(result.returncode, 2, verb)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1, verb)
        self.assertEqual(self.cli('tree', self.job).returncode, 0)


class Fake(CoreCase):
    def test_a_parent_from_parent_or_the_caller_and_its_end_ends_its_branch(self):
        fj.hc('run', '--bg', '--no-parent', '--name', 'a', '--', 'x')
        fj.hc('run', '--bg', '--parent', 'a', '--name', 'b', '--', 'x')
        with mock.patch.dict(os.environ, {'HC_TERMINAL_ID': 't2'}):
            fj.hc('run', '--bg', '--name', 'c', '--', 'x')
            fj.hc('run', '--bg', '--outlive-parent', '--name', 'd', '--', 'x')
        self.assertEqual([fj.hc('get', t)['parent'] for t in ('t1', 't2', 't3', 't4')], [None, 't1', 't2', 't2'])
        fj.hc('kill', 't1')
        self.assertEqual([fj.hc('get', t)['state'] for t in ('t1', 't2', 't3', 't4')], ['finished', 'finished', 'finished', 'live'])
        self.assertEqual({t['address'] for t in fj.native().listing()}, {'t1', 't2', 't3', 't4'})


if __name__ == '__main__':
    unittest.main()
