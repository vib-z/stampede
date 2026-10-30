"""Mixed jobs: a Herdr Core job hands the agents Core cannot run (Cursor, Hermes, Kimi) to Herdr TUI panes. Every Core call
goes to tests/fake_hc.py and every Herdr call to tests/fake_herdr.py; nothing here starts a program or touches a real
core or Herdr."""
import contextlib, io, json, os, shlex, subprocess, sys, threading, time, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, LEAD, ROOT, SCRIPTS, SHA, fj, git
from test_core_relay import RELAY, Shell, follower_module, status

FAKE_HERDR = ROOT / 'tests/fake_herdr.py'
PANE = 'w9:p3'


class MixedCase(CoreCase):
    """A Core job beside a fake Herdr TUI with one empty pane at its shell prompt, w9:p3."""

    def setUp(self):
        super().setUp()
        self.tui = self.root / 'herdr'
        (self.bin / 'herdr').symlink_to(FAKE_HERDR)
        patch = mock.patch.dict(os.environ, {'HERDR': str(self.bin / 'herdr'), 'FAKE_HERDR': str(self.tui)})
        patch.start()
        self.addCleanup(patch.stop)
        self.job_dir, self.key = self.core_job()
        self.add_pane(PANE)

    def herdr_state(self):
        path = self.tui / 'state.json'
        return json.loads(path.read_text()) if path.is_file() else {'panes': {}}

    def herdr_shape(self, **fields):
        self.tui.mkdir(exist_ok=True)
        (self.tui / 'state.json').write_text(json.dumps({**self.herdr_state(), **fields}))

    def add_pane(self, pane, **fields):
        state = self.herdr_state()
        state['panes'][pane] = {'cwd': str(self.repo), 'agent': None, 'screen': '❯ ', **fields}
        self.herdr_shape(**state)

    def agent(self, pane=PANE, **fields):
        """Change the agent in a pane, as Herdr would: a turn that ends (working or blocked to idle or done) adds one to
        completion_seq to a Herdr-wide counter. agent=None empties the pane (it exited); gone=True closes the pane."""
        state = self.herdr_state()
        if fields.get('gone'):
            del state['panes'][pane]
        elif 'agent' in fields and fields['agent'] is None:
            state['panes'][pane]['agent'] = None
        else:
            agent = state['panes'][pane]['agent']
            if (agent['agent_status'] in ('working', 'blocked') and fields.get('agent_status') in ('idle', 'done')
                    and 'completion_seq' not in fields):
                state['seq'] = fields['completion_seq'] = state.get('seq', 1000) + 1  # Herdr-wide, as live
            agent.update(fields)
        self.herdr_shape(**state)

    def herdr_calls(self, verb=None):
        path = self.tui / 'calls'
        rows = [json.loads(row) for row in path.read_text().splitlines()] if path.is_file() else []
        return [row for row in rows if verb is None or ' '.join(row[:2]) == verb]

    def hand(self, agent='build-ui', kind='hermes', pane=PANE, job=None, **kw):
        job = job or self.job_dir
        return self.quiet(fj.start, job, agent, kind, pane, str(self.brief(job, agent)), **kw)

    def mark(self, pane=PANE):
        """The job a pane's handed mark names, else None."""
        path = self.events / 'handed' / pane
        return path.read_text().splitlines()[0] if path.is_file() else None

    def settled(self):
        """The job finished, its lead live: a reopen then looks only at the agents."""
        (self.job_dir / 'finished').write_text('x\n')
        self.add_terminal('t1', name='lead-demo', labels={'stampede.job': self.key, 'stampede.agent': 'lead-demo'})
        fj.bind(self.job_dir, 'lead-demo', {'state': 'live', 'address': 't1', 'role': 'lead'})


class MixedStart(MixedCase):
    """Design item 1 and A1: start with --pane on a Core job, its launch written before Herdr starts it."""

    def test_each_kind_core_cannot_run_starts_in_its_pane(self):
        for n, kind in enumerate(('cursor', 'hermes', 'kimi')):
            pane, agent = f'w9:p{4 + n}', f'build-{kind}'
            self.add_pane(pane)
            code, out = self.hand(agent, kind, pane)
            self.assertEqual((code, out.strip()), (0, f'STARTED {agent} (pane {pane})'))
            entry = self.entries(self.job_dir)[agent]
            self.assertEqual({k: entry[k] for k in ('state', 'role', 'backend', 'pane', 'kind', 'completion', 'briefed')},
                             {'state': 'live', 'role': 'worker', 'backend': 'tui', 'pane': pane, 'kind': kind,
                              'completion': None, 'briefed': True})
            self.assertRegex(entry['launch'], r'^[0-9a-f]{12}$')
            self.assertEqual(fj.agent_rows(self.job_dir)[agent]['kind'], kind)
            self.assertEqual((self.events / 'handed' / pane).read_text(), f'{self.job_dir}\n{entry["launch"]}\n')
            started = self.herdr_state()['panes'][pane]
            self.assertEqual((started['label'], started['agent']['agent']), (agent, kind))
            brief = self.job_dir / 'briefs' / (agent + '.md')
            self.assertEqual(started['agent']['prompts'], [f'You are {agent} in a herdr fleet. Read {brief} and do everything it says.'])
        self.assertEqual(self.calls('run'), [], 'nothing handed runs in a Core terminal')
        self.assertEqual(self.herdr_calls('agent send-keys'), [], 'never a key')
        self.assertIn('build-hermes', (self.job_dir / 'REOPEN.md').read_text())

    def test_core_kinds_a_pane_with_cwd_and_a_bad_pane_are_refused(self):
        for kind in ('claude', 'codex'):
            with self.assertRaises(ValueError) as refused:
                self.hand('build-api', kind)
            self.assertIn('--cwd', str(refused.exception))
        with self.assertRaises(ValueError) as refused:
            self.hand('build-ui', 'hermes', cwd=str(self.repo))
        self.assertIn('--pane', str(refused.exception))
        for kind, pane in (('gemini', PANE), ('hermes', '../../x')):
            with self.assertRaises(ValueError):
                self.hand('build-ui', kind, pane)
        self.assertEqual((self.herdr_calls(), self.calls('run'), self.entries(self.job_dir)), ([], [], {}))

    def test_kinds_core_cannot_run_need_a_pane_and_hermes_and_kimi_need_core(self):
        for kind in ('cursor', 'hermes', 'kimi'):
            with self.assertRaises(ValueError) as refused:
                self.hand('build-ui', kind, pane=None)
            self.assertIn(f'{kind.capitalize()} reports no OSC 7501 status, so Herdr Core cannot run it', str(refused.exception))
            self.assertIn('--pane', str(refused.exception))
        tui = self.repo / '.herdr-tui'
        (tui / 'briefs').mkdir(parents=True)
        (tui / 'lead').write_text('lead-tui\n')
        for kind in ('hermes', 'kimi'):
            with self.assertRaises(ValueError) as refused:
                self.hand('build-ui', kind, job=tui)
            self.assertIn('Herdr Core', str(refused.exception))
        self.assertEqual((self.herdr_calls(), self.calls('run')), ([], []))

    def test_one_live_launch_per_agent_across_core_and_the_tui(self):
        with fj.launching(self.job_dir, 'build-ui'), self.assertRaises(ValueError) as refused:
            self.hand()
        self.assertIn('being started by another caller', str(refused.exception))
        self.assertEqual(self.hand()[0], 0)
        self.add_pane('w9:p4')
        with self.assertRaises(ValueError) as refused:
            self.hand(pane='w9:p4')
        self.assertIn(f'build-ui is already running in pane {PANE}', str(refused.exception))
        with self.assertRaises(ValueError) as refused:  # a Core start of that name
            self.quiet(fj.start, self.job_dir, 'build-ui', 'claude', None, str(self.brief(self.job_dir, 'build-ui')))
        self.assertIn(f'already running in pane {PANE}', str(refused.exception))
        self.agent(agent='cursor')  # its name runs in its pane, but not as this launch
        with self.assertRaises(ValueError) as refused:
            self.hand(pane='w9:p4')
        self.assertIn('not as the launch this job recorded', str(refused.exception))
        self.agent(agent=None)  # it exited: its pane is a shell again
        self.assertEqual(self.hand(pane='w9:p4')[0], 0)
        self.assertEqual(self.entries(self.job_dir)['build-ui']['pane'], 'w9:p4')
        labels = {'stampede.job': self.key, 'stampede.agent': 'review-ui', 'stampede.role': 'worker'}
        self.add_terminal('t1', name='review-ui', labels=labels)
        with self.assertRaises(ValueError) as refused:  # a Core terminal of the job runs that name
            self.hand('review-ui')
        self.assertIn('already running at t1', str(refused.exception))
        self.assertEqual(len(self.herdr_calls('agent start')), 2)

    def test_a_startup_dialog_is_blocked_and_a_failed_start_is_failed(self):
        self.herdr_shape(start_error={'build-ui': 'agent_not_ready', 'build-db': 'pane_not_at_prompt'})
        code, out = self.hand()
        self.assertEqual(code, 1)
        self.assertIn(f'BLOCKED build-ui: clear the startup dialog in pane {PANE}', out)
        self.assertEqual((self.entries(self.job_dir)['build-ui']['state'], self.mark()), ('live', str(self.job_dir)))
        self.add_pane('w9:p4')
        code, out = self.hand('build-db', pane='w9:p4')
        self.assertEqual(code, 1)
        self.assertIn('FAILED build-db (herdr agent start', out)
        self.assertEqual((self.entries(self.job_dir)['build-db']['state'], self.mark('w9:p4')), ('failed', None))

    def test_the_start_pointer_never_goes_into_a_busy_agent(self):  # owner check 2
        self.herdr_shape(on_start={'build-ui': {'agent_status': 'working'}}, start_error={'build-db': 'agent_not_ready'})
        code, out = self.hand()
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith('NOT READY build-ui: working: tell it after its turn'), out)
        self.add_pane('w9:p4')
        code, out = self.hand('build-db', pane='w9:p4')
        self.assertEqual(code, 1)
        self.assertIn('BLOCKED build-db', out)
        self.assertEqual((self.herdr_calls('agent prompt'), self.herdr_calls('agent send-keys')), ([], []))
        self.assertEqual([self.entries(self.job_dir)[a]['state'] for a in ('build-ui', 'build-db')], ['live', 'live'])

    def test_a_lost_answer_is_adopted_or_kept_unknown_and_never_launched_twice(self):
        self.herdr_shape(start_error={'build-ui': 'timeout', 'build-db': 'timeout'}, spawns=['build-ui', 'build-db'])
        self.assertEqual(self.hand(), (0, f'STARTED build-ui (pane {PANE})\n'), 'it started all the same: adopted')
        self.add_pane('w9:p4')
        self.herdr_shape(list_error='server_down')
        code, out = self.hand('build-db', pane='w9:p4')
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith('UNKNOWN build-db: herdr agent start'), out)
        self.assertEqual((self.entries(self.job_dir)['build-db']['state'], self.mark('w9:p4')), ('starting', str(self.job_dir)))
        with self.assertRaises(ValueError) as refused:
            self.hand('build-db', pane='w9:p4')
        self.assertIn('Herdr did not answer', str(refused.exception))
        self.herdr_shape(list_error=None)
        with self.assertRaises(ValueError) as refused:
            self.hand('build-db', pane='w9:p4')
        self.assertIn('already running in pane w9:p4', str(refused.exception))
        self.assertEqual(len(self.herdr_calls('agent start')), 2)
        self.settled()
        code, out = self.quiet(fj.reopen, self.job_dir)  # R1-8: settled live, but never briefed: no success, and no typing
        self.assertIn('NOT BRIEFED build-db (pane w9:p4): it runs, but its brief was never confirmed sent', out)
        self.assertEqual((code, self.entries(self.job_dir)['build-db']['state']), (1, 'live'))
        self.assertEqual(self.herdr_state()['panes']['w9:p4']['agent']['prompts'], [])
        tell = shlex.split(out.split('only if it has not got it: ')[1].splitlines()[0])
        self.assertEqual(tell[:4], ['fleet-job', 'tell', str(self.job_dir), 'build-db'])
        self.quiet(fj.tell, self.job_dir, 'build-db', tell[4])
        code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertIn('LIVE build-db (pane w9:p4)', out)
        self.assertEqual(code, 0)

    def test_the_core_lead_brief_and_help_teach_the_handed_start(self):
        self.new_core()
        brief = (self.job / 'briefs' / (LEAD + '.md')).read_text()
        self.assertIn(f'fleet-job start {self.job} <agent> --kind cursor|hermes|kimi --pane <pane> --brief <file>', brief)
        self.assertIn('--kind claude|codex --brief <file> [--cwd <dir>]', brief)
        self.assertIn('gate-ok', brief)
        self.assertNotIn('typed in your pane', brief)
        help_text = subprocess.run([str(SCRIPTS / 'fleet-job'), 'start', '--help'], capture_output=True, text=True).stdout
        self.assertIn('hermes', help_text)


class MixedKinds(MixedCase):
    """Design item 2: cli_args knows Hermes and Kimi: auto mode by default, their unattended flags only with --yolo-in."""

    def test_hermes_and_kimi_flags(self):
        self.assertEqual(fj.cli_args(self.job_dir, 'a', 'hermes', 'm1', 'high', []), ['-m', 'm1', '--reasoning', 'high'])
        self.assertEqual(fj.cli_args(self.job_dir, 'b', 'kimi', 'k2', None, []), ['-y', '-m', 'k2'])
        git('init', '-q', '.', cwd=self.repo)
        git('commit', '-q', '--allow-empty', '-m', 'base', cwd=self.repo)
        tree = self.root / 'code/repo-wt'
        git('worktree', 'add', '-q', str(tree), cwd=self.repo)
        self.assertEqual(fj.cli_args(self.job_dir, 'a', 'hermes', None, None, [], yolo_in=tree), ['--yolo'])
        self.assertEqual(fj.cli_args(self.job_dir, 'b', 'kimi', None, None, [], yolo_in=tree), ['-y'])
        self.assertEqual(sorted(p.name for p in (self.job_dir / 'hooks').iterdir()), ['a.json', 'b.json'])


class FollowerCase(MixedCase):
    """A follower of the job, its bot posts kept, its clocks the test's; one look is one Herdr read, applied."""

    def setUp(self):
        super().setUp()
        (self.job_dir / 'owner').write_text('alpha\n')
        self.posts, self.now = [], [0.0]
        for name in ('FLEET_WATCH_NOTIFY', 'HERDR_EVENTS_STALE_MINUTES'):
            os.environ.pop(name, None)

    def follower(self):
        core = follower_module()
        for patch in (mock.patch.object(core.Follower, 'post', lambda follower, event: self.posts.append(event)),
                      mock.patch.object(core, 'POLL_EVERY', 0), mock.patch.object(core, 'STALL_EVERY', 0),
                      mock.patch.object(core, 'wall', lambda: self.now[0])):
            patch.start()
            self.addCleanup(patch.stop)
        return core.Follower(self.job_dir)

    def inbox(self):
        path = self.job_dir / 'inbox.log'
        return path.read_text().splitlines() if path.is_file() else []

    def look(self, follower):
        """One Herdr read on the reader's thread, then applied on this one: a poll starts it, the next applies it."""
        follower.poll()
        if getattr(follower, 'reader', None):
            follower.reader.join(10)
        follower.poll()

    def steps(self, follower, *statuses, pane=PANE):
        for word in statuses:
            if word == 'exit':
                self.agent(pane, agent=None)
            elif word == 'close':
                self.agent(pane, gone=True)
            else:
                self.agent(pane, agent_status=word)
            self.look(follower)

    def sent(self):
        return [(e['state'], e.get('turn') or e.get('kind') or e.get('last_state')) for e in self.posts]


class MixedFollower(FollowerCase):
    """Design item 3, A1 to A3: the follower looks at handed agents and tells the lead and the bot as for a Core worker."""

    def test_turns_blocks_and_an_exit_of_a_hermes_worker(self):
        self.hand('build-ui', 'hermes')  # working on its brief pointer
        f = self.follower()
        self.steps(f, 'done', 'working', 'blocked', 'working', 'idle', 'exit')
        self.assertEqual(self.inbox(), ['TURN build-ui', 'BLOCKED build-ui dialog', 'TURN build-ui', 'GONE build-ui exited'])
        self.assertEqual(self.sent(), [('done', 1001), ('blocked', 'dialog'), ('idle', 1002)])
        launch = self.entries(self.job_dir)['build-ui']['launch']
        event = self.posts[1]
        self.assertEqual((event['source'], event['workspace'], event['pane'], event['agent'], event['owner']),
                         ('hc', self.key, PANE, 'build-ui', 'alpha'))
        self.assertEqual(event['event_id'], f'{self.key}/tui:{PANE}|{launch}|blocked|1')
        self.assertEqual(self.posts[0]['event_id'], f'{self.key}/tui:{PANE}|{launch}|completion|1001')
        self.assertIn('output_tail', event)
        self.look(f)
        self.assertEqual(len(self.inbox()), 4, 'GONE once')
        self.assertEqual(self.mark(), str(self.job_dir), 'a GONE keeps its mark until finish')

    def test_a_turn_between_looks_or_while_the_follower_was_down_is_told_once(self):
        self.hand()
        first = self.follower()
        self.look(first)
        self.agent(agent_status='idle', completion_seq=1)  # worked and finished between two looks
        self.look(first)
        self.look(first)
        self.agent(agent_status='done', completion_seq=2)  # and again while no follower ran
        self.look(self.follower())
        self.look(self.follower())
        self.assertEqual(self.inbox(), ['TURN build-ui', 'TURN build-ui'])
        self.assertEqual(self.sent(), [('idle', 1), ('done', 2)])

    def test_kimi_turns_and_cursor_leaves_its_turn_line_to_its_own_hook(self):
        self.hand('build-k', 'kimi')
        self.add_pane('w9:p4')
        self.hand('build-c', 'cursor', 'w9:p4')
        f = self.follower()
        for pane in (PANE, 'w9:p4'):
            self.agent(pane, agent_status='done')
        self.look(f)
        self.assertEqual(self.inbox(), ['TURN build-k'])
        self.assertEqual(sorted((e['agent'], e['state']) for e in self.posts), [('build-c', 'done'), ('build-k', 'done')])

    def test_dead_when_it_ends_working_and_the_pane_is_named_when_it_closed(self):
        self.hand()
        f = self.follower()
        self.steps(f, 'working', 'close')
        self.look(f)
        self.assertEqual(self.inbox(), ['GONE build-ui pane closed'])
        self.assertEqual(self.sent(), [('dead', 'working')])

    def test_stale_once_per_stall(self):
        self.hand()
        f = self.follower()
        for minute in (0, 29, 31, 40):
            self.now[0] = minute * 60
            self.look(f)
            f.stalls()
        self.assertEqual(self.inbox(), ['STALE build-ui no new output for 31m'])
        self.assertEqual([(e['state'], e['minutes_unchanged'], e['pane']) for e in self.posts], [('stale', 31, PANE)])

    def test_one_event_each_across_a_follower_restart(self):
        self.hand()
        self.steps(self.follower(), 'blocked')
        self.steps(self.follower(), 'blocked', 'working')  # a restarted follower resumes from relay-state.json
        self.steps(self.follower(), 'done', 'done')
        self.assertEqual(self.inbox(), ['BLOCKED build-ui dialog', 'TURN build-ui'])
        self.assertEqual(self.sent(), [('blocked', 'dialog'), ('done', 1001)])

    def test_a_restart_in_its_pane_is_a_new_launch_and_herdr_down_is_no_news(self):
        self.hand()
        f = self.follower()
        self.steps(f, 'done', 'exit')
        self.hand()
        self.herdr_shape(list_error='server_down')
        self.steps(f, 'done')
        self.agent(agent=None)
        self.look(f)
        self.herdr_shape(list_error=None)
        self.agent(agent=None)
        self.assertEqual(self.inbox(), ['TURN build-ui', 'GONE build-ui exited'], 'Herdr down: no TURN, and never GONE')
        self.hand()
        self.steps(f, 'done')
        self.assertEqual(self.inbox(), ['TURN build-ui', 'GONE build-ui exited', 'TURN build-ui'])

    def test_a_same_name_replacement_is_gone_and_a_start_not_yet_live_is_never_gone(self):
        self.hand()
        f = self.follower()
        self.look(f)
        self.agent(agent_session={'kind': 'id', 'value': 's1'})
        self.look(f)
        self.agent(agent_session={'kind': 'id', 'value': 's2'})  # a new process under its name
        self.look(f)
        self.assertEqual(self.inbox(), ['GONE build-ui replaced'])
        fj.bind(self.job_dir, 'build-db', {'state': 'starting', 'backend': 'tui', 'pane': 'w9:p8', 'kind': 'kimi',
                                           'launch': 'a' * 12}, fresh=True)
        self.look(f)
        self.assertEqual(len(self.inbox()), 1)

    def test_the_follower_and_reopen_never_type_into_a_pane(self):  # owner check 2
        self.hand()
        self.add_pane('w9:p4')
        self.hand('build-k', 'kimi', 'w9:p4')
        typed = len(self.herdr_calls('agent prompt'))  # the two start pointers
        f = self.follower()
        for minute, word in ((0, 'working'), (1, 'blocked'), (2, 'working'), (40, 'working'), (41, 'done'), (42, 'idle')):
            self.now[0] = minute * 60
            self.agent(agent_status=word)
            self.look(f)
            f.stalls()
        self.settled()
        self.quiet(fj.reopen, self.job_dir)  # LIVE for both
        self.agent(agent=None)
        self.look(f)
        self.quiet(fj.reopen, self.job_dir)  # NOT RUNNING for build-ui
        self.assertEqual(self.inbox()[-1], 'GONE build-ui exited')
        self.assertIn('STALE build-ui no new output for 38m', self.inbox())
        self.assertEqual((len(self.herdr_calls('agent prompt')), self.herdr_calls('agent send-keys')), (typed, []))
        self.assertEqual(self.calls('send') + self.calls('keys'), [])

    def test_a_core_only_job_never_calls_herdr(self):
        f = self.follower()
        f.line({'channel': None, 'seq': 1, 'terminals': []})
        self.look(f)
        self.assertEqual(self.herdr_calls(), [])

    def test_it_ticks_while_the_core_stream_is_quiet(self):
        self.hand()
        core = follower_module()
        self.shape(streams=[[{'channel': None, 'seq': 1, 'terminals': []}]], hold=[60])
        with mock.patch.object(core.Follower, 'post', lambda follower, event: None), \
                mock.patch.object(core, 'POLL_EVERY', 0.05), mock.patch.object(core, 'TICK', 0.05), \
                mock.patch.object(core, 'alive', lambda: True):
            follower, result = core.Follower(self.job_dir), []
            thread = threading.Thread(target=lambda: result.append(follower.follow()), daemon=True)
            thread.start()
            deadline = time.time() + 20
            while not any(r.get('status') == 'working' for r in list(follower.terminals.values())):
                self.assertLess(time.time(), deadline, 'no tick while the stream was quiet')
                time.sleep(0.05)
            self.agent(agent_status='done')
            while self.inbox() != ['TURN build-ui']:
                self.assertLess(time.time(), deadline, 'no TURN while the stream was quiet')
                time.sleep(0.05)
            (self.job_dir / 'finished').write_text('x\n')
            thread.join(timeout=20)
        self.assertEqual(result, [0])


class MixedMarks(MixedCase):
    """Design item 4 and A4: every event about a marked pane but the follower's stays home, until finish."""

    def post(self, **event):
        return subprocess.run([str(RELAY / 'herdr-event-post'), json.dumps(event)], capture_output=True, text=True, timeout=30)

    def queued(self):
        return sorted((e['source'], e['pane']) for e in
                      (json.loads(p.read_text())['payload'] for p in (self.root / 'queue/queue').glob('*.json')))

    def test_only_the_followers_events_about_a_marked_pane_leave(self):
        (self.root / 'routes/default').write_text('URL=http://127.0.0.1:9/never\n')
        self.hand()
        for source, state in (('herdr', 'blocked'), ('herdr', 'done'), ('herdr-watchdog', 'dead'), ('claude', 'Notification')):
            self.assertEqual(self.post(source=source, pane=PANE, workspace='w9', state=state).returncode, 0)
        self.assertEqual(self.queued(), [])
        self.assertIn('handed-skip', (self.root / 'home/Library/Logs/herdr-events.log').read_text())
        self.post(source='hc', pane=PANE, workspace=self.key, state='blocked', kind='dialog', event_id=self.key + '/x|blocked|1')
        self.post(source='herdr', pane='w9:p8', workspace='w9', state='blocked')
        self.assertEqual(self.queued(), [('hc', PANE), ('herdr', 'w9:p8')])

    def test_finish_clears_only_this_jobs_marks(self):
        self.hand()
        (self.events / 'handed/w9:p8').write_text('/another/job\nffffffffffff\n')
        self.quiet(fj.finish, self.job_dir, 'shipped')
        self.assertEqual((self.mark(), self.mark('w9:p8')), (None, '/another/job'))


class MixedWatchdog(Shell):
    """A4: the TUI watchdog never tracks a handed pane, so neither stale nor dead, even for one it saw before its mark."""

    def test_a_marked_pane_is_never_stale_or_dead(self):
        (self.events / 'handed').mkdir()
        (self.events / 'handed/w9:p3').write_text('/repo/.herdr-demo\naaaaaaaaaaaa\n')
        (self.home / 'Library/Logs').mkdir(parents=True)
        agents = self.home / 'agents.json'
        self.fake('herdr', f'case "$1 $2" in\n  "agent list") cat "{agents}";;\n  "pane read") echo same;;\n'
                           '  "workspace list") echo \'{"result":{"workspaces":[]}}\';;\nesac\n')
        self.fake('herdr-event-post', f'cat >> "{self.home}/posted"; echo >> "{self.home}/posted"\n')
        state = self.home / '.local/state/herdr-events/watchdog'
        working = {'agent_status': 'working', 'agent': 'hermes', 'workspace_id': 'w9', 'tab_id': 'w9:t1'}
        listed = lambda *panes: agents.write_text(json.dumps({'result': {'agents': [{**working, 'pane_id': p} for p in panes]}}))
        listed('w9:p3', 'w9:p4', 'w9:p5')
        path = f'{self.bin}:/usr/bin:/bin:/sbin'  # md5 is in /sbin
        self.assertEqual(self.run_script('herdr-event-watchdog', PATH=path).returncode, 0)
        self.assertEqual(self.posted(), [])
        self.assertFalse((state / 'w9_p3').exists())
        for pane in ('w9_p4', 'w9_p5'):
            (state / pane).write_text(f'{(state / pane).read_text().split()[0]} 0 0\n')  # unchanged since long ago
        (self.events / 'handed/w9:p5').write_text('/repo/.herdr-demo\nbbbbbbbbbbbb\n')  # handed after the watchdog saw it
        self.run_script('herdr-event-watchdog', PATH=path)
        listed()
        self.run_script('herdr-event-watchdog', PATH=path)
        self.assertEqual(sorted((p['state'], p['pane']) for p in self.posted()), [('dead', 'w9:p4'), ('stale', 'w9:p4')])


class MixedTell(MixedCase):
    """Design item 5 and A5: tell prompts a handed agent only as this launch, idle or done, unfocused, with an empty prompt."""

    def told(self, text='Fix the nit'):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                fj.tell(self.job_dir, 'build-ui', text)
                code = 0
            except SystemExit as stop:
                code = stop.code
        return out.getvalue().strip(), code

    def test_refusals_and_the_idle_path(self):
        self.hand()
        pointer = self.herdr_state()['panes'][PANE]['agent']['prompts']
        for fields, why in (({'agent_status': 'working'}, 'working: tell it after its turn'),
                            ({'agent_status': 'blocked'}, f'blocked: read it with herdr agent read {PANE}'),
                            ({'agent_status': 'idle', 'focused': True}, 'focused: the owner is in that pane; retry later'),
                            ({'focused': False, 'name': 'someone-else'}, f'pane {PANE} runs someone-else, not build-ui'),
                            ({'name': 'build-ui', 'agent_session': {'kind': 'id', 'value': 's2'}},
                             f'pane {PANE} runs build-ui, but not as the launch this job recorded')):
            fj.bind(self.job_dir, 'build-ui', {'session': 's1'})
            self.agent(**fields)
            self.assertEqual(self.told(), (f'FAILED build-ui ({why})', 2))
        self.agent(agent_session={'kind': 'id', 'value': 's1'})
        self.add_pane(PANE, agent=self.herdr_state()['panes'][PANE]['agent'], screen='❯ half a sentence')
        out, code = self.told()
        self.assertEqual(code, 2)
        self.assertIn('text may be typed in its prompt', out)
        self.add_pane(PANE, agent=self.herdr_state()['panes'][PANE]['agent'])
        for word in ('idle', 'done'):
            self.agent(agent_status=word)
            self.assertEqual(self.told(), (f'SUBMITTED build-ui (pane {PANE})', 0))
        self.assertEqual(self.herdr_state()['panes'][PANE]['agent']['prompts'], pointer + ['Fix the nit', 'Fix the nit'])
        self.assertEqual(self.herdr_calls('agent prompt')[-1][4:], ['--wait', '--until', 'working', '--until', 'blocked', '--timeout', '15000'])
        fj.bind(self.job_dir, 'build-ui', {'state': 'starting'})
        self.assertIn('its start is not settled', self.told()[0])
        fj.bind(self.job_dir, 'build-ui', {'state': 'live'})
        self.agent(agent=None)
        out, code = self.told()
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith(f'FAILED build-ui (not running in pane {PANE}'), out)
        self.assertEqual((self.calls('send'), self.herdr_calls('agent send-keys')), ([], []), 'never hc send, never a key')


    def test_a_claude_worker_of_a_mixed_job_reads_only_its_inbox(self):  # owner check 2
        self.hand()
        with open(self.job_dir / 'agents.tsv', 'a') as rows:
            rows.write('build-api\tclaude\t\t\t\n')
        before = (len(self.herdr_calls()), len(self.calls()))
        self.assertEqual(self.quiet(fj.tell, self.job_dir, 'build-api', 'hello')[1], 'DELIVERED build-api (inbox file)\n')
        self.assertEqual((self.job_dir / 'inbox/build-api.md').read_text(), 'hello\n')
        self.assertEqual((len(self.herdr_calls()), len(self.calls())), before)


class MixedGates(MixedCase):
    """Design item 6: a Core job with a handed agent still counts only the recorded yes, and a handed pane cannot record it."""

    def test_only_the_recorded_yes_and_never_from_a_handed_pane(self):
        self.hand()
        (self.job_dir / 'owner').write_text('alpha\n')
        gate = {'gate': '0123456789ab', 'action': 'Merge PR #3', 'pr': 3, 'sha': SHA, 'route': 'alpha', 'asked': 'now'}
        (self.job_dir / 'gates').mkdir()
        (self.job_dir / 'gates/0123456789ab.json').write_text(json.dumps(gate))
        for text in ('yes', 'GATE 0123456789ab APPROVED by owner'):
            self.quiet(fj.tell, self.job_dir, 'lead', text)
        with self.assertRaises(PermissionError) as refused:
            fj.gate_ok(self.job_dir, '0123456789ab', SHA)
        self.assertNotIn('typed in your pane', str(refused.exception))
        pane_env = {**os.environ, 'HERDR_ENV': '1', 'HERDR_PANE_ID': PANE, 'HERDR_WORKSPACE_ID': 'w9'}
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'approve-gate', str(self.job_dir), '0123456789ab', '--sha', SHA,
                                 '--by', 'build-ui'], capture_output=True, text=True, env=pane_env, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn('approve-gate runs only outside Herdr and Herdr Core', result.stderr)
        self.assertFalse((self.job_dir / 'gates/0123456789ab.approved').exists())
        with mock.patch.object(fj, 'inside_herdr', return_value=False):
            self.quiet(fj.approve_gate, self.job_dir, '0123456789ab', SHA, 'owner in alpha chat')
        self.assertIn('APPROVED 0123456789ab', self.quiet(fj.gate_ok, self.job_dir, '0123456789ab', SHA)[1])


class MixedFingerprints(MixedCase):
    """Owner check 3: on a mixed job a gate is bound to its id and exact commit, a gate changed while asked is not
    recorded, and the plan digest refuses a handed start after the plan changed until approved again."""

    def setUp(self):
        super().setUp()
        self.hand()

    def gate(self, action, owner=True):
        if owner:
            (self.job_dir / 'owner').write_text('alpha\n')
        with mock.patch.object(fj, 'ask_background'):
            self.quiet(fj.ask_gate, self.job_dir, action, SHA, 3)
        return max((self.job_dir / 'gates').glob('*.json'), key=lambda p: p.stat().st_mtime_ns).stem

    def approve(self, ident, sha):
        with mock.patch.object(fj, 'inside_herdr', return_value=False):
            return self.quiet(fj.approve_gate, self.job_dir, ident, sha, 'owner in alpha chat')

    def test_gate_ok_with_another_commit_refuses(self):
        ident = self.gate('Merge PR #3 into main')
        with self.assertRaises(PermissionError):
            self.approve(ident, 'b' * 40)  # a yes for another commit is never recorded
        self.assertFalse((self.job_dir / 'gates' / (ident + '.approved')).exists())
        self.approve(ident, SHA)
        self.assertIn('APPROVED ' + ident, self.quiet(fj.gate_ok, self.job_dir, ident, SHA)[1])
        with self.assertRaises(PermissionError) as refused:
            fj.gate_ok(self.job_dir, ident, 'c' * 40)  # a push after the yes withdraws it
        self.assertIn('a push after the yes withdraws it', str(refused.exception))

    def test_a_yes_for_one_gate_never_passes_another(self):
        first = self.gate('Merge PR #3 into main')
        time.sleep(0.01)
        second = self.gate('Deploy to production')
        self.approve(first, SHA)
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job_dir, second, SHA)
        (self.job_dir / 'gates' / (second + '.approved')).write_text((self.job_dir / 'gates' / (first + '.approved')).read_text())
        with self.assertRaises(PermissionError) as refused:
            fj.gate_ok(self.job_dir, second, SHA)
        self.assertIn(f'is for gate {first}', str(refused.exception))

    def test_a_gate_changed_while_asked_is_not_recorded(self):
        ident = self.gate('Merge PR #3 into main', owner=False)  # a local job: the phone card records the yes
        record = self.job_dir / 'gates' / (ident + '.json')
        swap = json.dumps({**fj.load_gate(self.job_dir, ident), 'action': 'Deploy to production'})
        ask = self.root / 'swap-ask'
        ask.write_text(f"#!/bin/bash\nprintf '%s' '{swap}' > '{record}'\necho yes\n")
        ask.chmod(0o755)
        with mock.patch.object(fj, 'ASK_CMD', str(ask)):
            fj.ask_now(self.job_dir, '', [], None, ident)
        self.assertFalse((self.job_dir / 'gates' / (ident + '.approved')).exists())
        self.assertIn('GATE NOT RECORDED', (self.job_dir / 'inbox/lead-demo.md').read_text())
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job_dir, ident, SHA)

    def test_a_handed_start_waits_for_approval_of_the_plan_as_it_stands(self):
        (self.job_dir / 'review').write_text('The owner asked to see the plan before any pane opens.\n')
        (self.job_dir / 'plan.md').write_text('# Plan v1\n')
        self.add_pane('w9:p4')
        with self.assertRaises(PermissionError):
            self.hand('build-k', 'kimi', 'w9:p4')
        fj.approve(self.job_dir, 'owner')
        self.assertEqual(self.hand('build-k', 'kimi', 'w9:p4')[0], 0)
        self.add_pane('w9:p5')
        for name in ('plan.md', 'fleet-plan.md'):
            (self.job_dir / name).write_text('# changed after the yes\n')
            with self.assertRaises(PermissionError) as refused:
                self.hand('build-c', 'cursor', 'w9:p5')
            self.assertIn('again after any change to the plan', str(refused.exception))
            fj.approve(self.job_dir, 'owner')
        self.assertEqual(self.hand('build-c', 'cursor', 'w9:p5')[0], 0)
        self.assertEqual(len(self.herdr_calls('agent start')), 3, 'no Herdr start while the plan waited')


class MixedReopen(MixedCase):
    """Design item 7 and A7: reopen never runs a handed agent in a Core terminal: LIVE, the exact start, or UNKNOWN."""

    def test_live_missing_or_unknown(self):
        git('init', '-q', '.', cwd=self.repo)
        git('commit', '-q', '--allow-empty', '-m', 'base', cwd=self.repo)
        tree = self.root / 'code/repo-wt'
        git('worktree', 'add', '-q', str(tree), cwd=self.repo)
        self.add_pane(PANE, cwd=str(tree))
        self.hand(model='m1', effort='high', reports=['reports/ui.md'], yolo_in=str(tree))
        self.settled()
        code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertEqual((code, out.splitlines()[0]), (0, f'LIVE build-ui (pane {PANE})'))
        self.agent(agent=None)
        code, out = self.quiet(fj.reopen, self.job_dir)
        brief = self.job_dir / 'briefs/build-ui.md'
        self.assertEqual(code, 1)
        self.assertIn(f'NOT RUNNING build-ui (pane {PANE}): start it again in a pane at its shell prompt: fleet-job start '
                      f'{self.job_dir} build-ui --kind hermes --pane {PANE} --brief {brief} --model m1 --effort high '
                      f'--report reports/ui.md --yolo-in {tree}', out)
        self.herdr_shape(list_error='server_down')
        code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertEqual(code, 1)
        self.assertIn('UNKNOWN build-ui: Herdr did not show clearly whether pane w9:p3 runs it', out)
        self.assertEqual(self.calls('run'), [], 'never in a Core terminal')
        self.assertIn(f'pane {PANE}', (self.job_dir / 'REOPEN.md').read_text())


class Round1Start(MixedCase):
    """Review round 1: the reopen race (R1-1), identity (R1-2), whole lists (R1-3), pane claims (R1-4), briefing (R1-8)."""

    def racing(self, during):
        """fj.launching that first runs `during`, once, when reopen comes for build-ui's lock: a start that slips in
        after reopen looked at the job and before it holds the lock."""
        real, ran = fj.launching, []

        @contextlib.contextmanager
        def launching(job, agent):
            if agent == 'build-ui' and not ran:
                ran.append(agent)
                during()
            with real(job, agent):
                yield
        return mock.patch.object(fj, 'launching', launching)

    def core_worker_gone(self):
        """build-ui as the job's Codex worker on Core, its terminal finished; the lead live, the job finished."""
        with open(self.job_dir / 'agents.tsv', 'a') as rows:
            rows.write('build-ui\tcodex\t\t' + str(self.brief(self.job_dir, 'build-ui')) + '\t--approve-for-me\n')
        self.add_terminal('t5', name='build-ui', state='finished', labels={'stampede.job': self.key, 'stampede.agent': 'build-ui'})
        fj.bind(self.job_dir, 'build-ui', {'state': 'live', 'address': 't5', 'role': 'worker'}, fresh=True)
        self.settled()

    def test_r1_1_a_hand_off_after_reopen_looked_is_never_started_on_core(self):
        self.core_worker_gone()
        with self.racing(lambda: self.hand('build-ui', 'hermes')):
            code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertEqual(self.calls('run'), [], 'no Codex on Core beside the handed Hermes')
        self.assertIn(f'LIVE build-ui (pane {PANE})', out)
        self.assertEqual((code, self.entries(self.job_dir)['build-ui']['backend']), (0, 'tui'))

    def test_r1_1_a_core_start_after_reopen_looked_is_not_called_missing(self):
        self.hand()
        self.agent(agent=None)
        self.settled()
        brief = str(self.brief(self.job_dir, 'build-ui'))
        with self.racing(lambda: self.quiet(fj.start, self.job_dir, 'build-ui', 'codex', None, brief)):
            code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertEqual([self.labels(run)['stampede.agent'] for run in self.calls('run')], ['build-ui'], 'started once, by start')
        self.assertNotIn('NOT RUNNING', out)
        self.assertEqual((code, self.entries(self.job_dir)['build-ui'].get('backend')), (0, None))

    def test_r1_2_a_start_herdr_shows_no_identity_for_is_never_started(self):
        for n, (error, answer) in enumerate((('server_down', None), (None, {}), (None, {'agent': {'pane_id': 'w9:p99', 'name': 'x'}}),
                                             (None, {'agent': {'pane_id': '?', 'completion_seq': None}}),
                                             (None, {'agent': {'name': '?', 'completion_seq': 'one'}}))):
            pane, agent = f'w9:p{4 + n}', f'build-{n}'
            self.add_pane(pane)
            if answer and 'agent' in answer:
                answer['agent'].update({k: v for k, v in (('pane_id', pane), ('name', agent)) if answer['agent'].get(k) == '?'})
            self.herdr_shape(get_error={pane: error} if error else {}, get_answer={pane: answer} if answer is not None else {})
            code, out = self.hand(agent, pane=pane)
            self.assertEqual(code, 1, out)
            self.assertTrue(out.startswith(f'UNKNOWN {agent}: '), out)
            self.assertEqual(self.entries(self.job_dir)[agent]['state'], 'starting')
            self.assertEqual(self.herdr_state()['panes'][pane]['agent']['prompts'], [], 'no brief to an unsettled launch')

    def test_r1_2_an_absent_null_or_malformed_identity_never_matches(self):
        self.hand()
        self.settled()
        fj.bind(self.job_dir, 'build-ui', {'session': 's1', 'completion': 1001})  # what this launch showed
        for fields in ({'agent_session': {'kind': 'id', 'value': 's2'}}, {'completion_seq': None}, {'name': None}):
            state = self.herdr_state()
            agent = state['panes'][PANE]['agent']
            agent.update({'name': 'build-ui', 'agent_session': {'kind': 'id', 'value': 's1'}, 'completion_seq': 1001,
                          'agent_status': 'idle', **fields})
            self.herdr_shape(**state)
            out, code = MixedTell.told(self)
            self.assertEqual(code, 2, (fields, out))
            code, out = self.quiet(fj.reopen, self.job_dir)
            self.assertIn('UNKNOWN build-ui', out, fields)
            with self.assertRaises(ValueError):
                self.quiet(fj.start, self.job_dir, 'build-ui', 'claude', None, str(self.brief(self.job_dir, 'build-ui')))
        self.assertEqual(self.herdr_state()['panes'][PANE]['agent']['prompts'][1:], [], 'nothing typed')
        self.assertEqual(self.calls('run'), [])

    def test_r1_3_a_malformed_list_is_no_evidence_of_absence(self):
        self.hand()
        self.settled()
        brief = str(self.brief(self.job_dir, 'build-ui'))
        for answer in ({}, {'agents': 'none'}, {'agents': [{}]}, {'agents': [{'pane_id': PANE, 'name': None, 'agent': 'hermes'}]}):
            self.herdr_shape(list_answer=answer)
            with self.assertRaises(ValueError) as refused:
                self.quiet(fj.start, self.job_dir, 'build-ui', 'claude', None, brief)
            self.assertIn('Herdr did not answer clearly', str(refused.exception), answer)
            code, out = self.quiet(fj.reopen, self.job_dir)
            self.assertIn('UNKNOWN build-ui', out, answer)
        self.assertEqual(self.calls('run'), [])

    def test_r1_4_a_pane_is_claimed_once(self):
        self.hand()
        launch = self.entries(self.job_dir)['build-ui']['launch']
        self.herdr_shape(start_error={'review-ui': 'pane_not_at_prompt'})
        with self.assertRaises(ValueError) as refused:
            self.hand('review-ui', 'kimi')
        self.assertIn(f'pane {PANE} is handed to build-ui of {self.job_dir}', str(refused.exception))
        other = self.repo / '.herdr-other'
        (other / 'briefs').mkdir(parents=True)
        (other / 'backend').write_text('core\n')
        (other / 'workspace').write_text(fj.job_key(other) + '\n')
        (other / 'lead').write_text('lead-other\n')
        with self.assertRaises(ValueError) as refused:
            self.hand('build-x', 'cursor', job=other)
        self.assertIn(f'is handed to build-ui of {self.job_dir}', str(refused.exception))
        self.assertEqual((self.events / 'handed' / PANE).read_text(), f'{self.job_dir}\n{launch}\n')
        self.assertEqual(len(self.herdr_calls('agent start')), 1, 'refused before any start')
        self.assertNotIn('review-ui', self.entries(self.job_dir))
        self.agent(agent=None)  # build-ui left: its mark is stale, and the pane can be claimed again
        self.herdr_shape(start_error={})
        self.assertEqual(self.hand('review-ui', 'kimi')[0], 0)
        self.assertEqual(self.mark(), str(self.job_dir))
        results = []

        def claim(agent):
            try:
                fj.claim_pane(self.job_dir, agent, 'w9:p7', {'state': 'starting', 'backend': 'tui', 'pane': 'w9:p7',
                                                             'launch': agent * 4})
                results.append('claimed')
            except ValueError:
                results.append('refused')
        threads = [threading.Thread(target=claim, args=(name,)) for name in ('aaa', 'bbb')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), ['claimed', 'refused'])

    def test_r1_8_a_live_but_unbriefed_agent_is_no_success(self):
        self.herdr_shape(on_start={'build-ui': {'focused': True}})  # the owner is in the pane: the pointer waits
        code, out = self.hand()
        self.assertTrue(out.startswith('NOT READY build-ui: focused'), out)
        self.settled()
        code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertEqual(code, 1)
        self.assertIn(f'NOT BRIEFED build-ui (pane {PANE})', out)
        self.assertEqual(self.herdr_state()['panes'][PANE]['agent']['prompts'], [], 'reopen never types')
        self.agent(focused=False)
        self.quiet(fj.tell, self.job_dir, 'build-ui', shlex.split(out.split('only if it has not got it: ')[1])[4])
        self.assertEqual(self.quiet(fj.reopen, self.job_dir), (0, f'LIVE build-ui (pane {PANE})\nLIVE {self.key}: no agent to restart\n'))


class Round1Follower(FollowerCase):
    """Review round 1: no unverified identity or screen (R1-2, R1-5), one completion once (R1-6), Herdr never holds up
    Core (R1-7), and a malformed list is no news (R1-3)."""

    def test_r1_2_and_r1_3_unclear_answers_change_nothing(self):
        self.hand()
        f = self.follower()
        self.look(f)
        self.agent(agent_status='done')  # a turn ended, but the next answers do not show it clearly
        row = {k: v for k, v in self.herdr_state()['panes'][PANE]['agent'].items() if k not in ('args', 'prompts')}
        for answer in ({}, {'agents': 'none'}, {'agents': [{}]}, {'agents': [{**row, 'pane_id': PANE, 'name': None}]},
                       {'agents': [{k: v for k, v in {**row, 'pane_id': PANE}.items() if k != 'completion_seq'}]}):
            self.herdr_shape(list_answer=answer)
            self.look(f)
        self.assertEqual((self.inbox(), [e['state'] for e in self.posts]), ([], []))
        self.herdr_shape(list_answer=None)
        self.look(f)
        self.assertEqual(self.inbox(), ['TURN build-ui'])

    def test_r1_5_a_replacements_screen_never_reaches_the_old_owner(self):
        self.hand()  # alpha's job; its pane is then taken over by another job's agent (owner beta) under the same name
        f = self.follower()
        self.agent(agent_status='working', agent_session={'kind': 'id', 'value': 's1'})
        self.look(f)
        self.add_pane(PANE, agent={**self.herdr_state()['panes'][PANE]['agent'], 'agent_session': {'kind': 'id', 'value': 's2'}},
                      screen='OTHER_JOB_PRIVATE_SENTINEL')
        self.look(f)
        self.add_pane('w9:p4')
        self.hand('review-ui', 'kimi', 'w9:p4')
        self.agent('w9:p4', agent_status='working')
        self.look(f)
        self.add_pane('w9:p4', agent={**self.herdr_state()['panes']['w9:p4']['agent'], 'name': 'beta-agent'},
                      screen='OTHER_JOB_PRIVATE_SENTINEL')
        self.look(f)
        self.assertNotIn('OTHER_JOB_PRIVATE_SENTINEL', json.dumps(self.posts))
        self.assertTrue(all('output_tail' not in e for e in self.posts if e['state'] == 'dead'))
        self.assertEqual(self.inbox(), ['GONE build-ui replaced', 'GONE review-ui exited'])
        self.assertEqual([(e['state'], e['owner']) for e in self.posts], [('dead', 'alpha'), ('dead', 'alpha')])

    def test_r1_6_a_restart_at_the_save_boundary_tells_one_completion_once(self):
        self.herdr_shape(on_start={'build-ui': {'completion_seq': 1000}})  # a counted baseline, as after an earlier turn
        self.hand()
        first = self.follower()
        self.look(first)

        def killed(*args, **kw):
            raise RuntimeError('the follower died here')
        first.observe = killed  # it dies after the turn's notification was saved, before the poll's own save
        self.agent(agent_status='done')
        with self.assertRaises(RuntimeError):
            self.look(first)
        self.look(self.follower())
        self.assertEqual(self.inbox(), ['TURN build-ui'])
        self.assertEqual(len(self.posts), 1, 'one completion, one bot event')

    def core_beside(self, stream, hang):
        """build-api, a Core worker at t3, beside the handed build-ui; Herdr hangs `hang` seconds on every call."""
        self.hand()
        self.add_terminal('t3', name='build-api', status={'state': 'working'},
                          labels={'stampede.job': self.key, 'stampede.agent': 'build-api', 'stampede.role': 'worker'})
        fj.bind(self.job_dir, 'build-api', {'state': 'live', 'address': 't3', 'role': 'worker'}, fresh=True)
        self.shape(streams=[stream], hold=[30])
        self.herdr_shape(hang=hang)
        core = follower_module()
        for patch in (mock.patch.object(core.Follower, 'post', lambda follower, event: self.posts.append(event)),
                      mock.patch.object(core, 'alive', lambda: True)):
            patch.start()
            self.addCleanup(patch.stop)
        follower, result = core.Follower(self.job_dir), []
        thread = threading.Thread(target=lambda: result.append(follower.follow()), daemon=True)
        return follower, thread, result

    def finish_follow(self, follower, thread, result):
        began = time.time()
        (self.job_dir / 'finished').write_text('x\n')
        thread.join(timeout=30)
        took = time.time() - began
        if getattr(follower, 'reader', None):
            follower.reader.join(30)  # the hung read ends on its own, later
        return took, result

    def test_r1_7_a_hung_herdr_never_holds_up_a_busy_core_stream(self):
        record = {'address': 't3', 'name': 'build-api', 'state': 'live', 'turn': 0, 'status': {'state': 'working'},
                  'labels': {'stampede.job': self.key, 'stampede.agent': 'build-api', 'stampede.role': 'worker'}}
        stream = [{'channel': None, 'seq': 1, 'terminals': [record]}, status('t3', 'blocked', seq=2, kind='permission')]
        follower, thread, result = self.core_beside(stream, hang=4)
        began = time.time()
        thread.start()
        while 'BLOCKED build-api permission' not in self.inbox():
            self.assertLess(time.time() - began, 2, 'a Core event waited for Herdr')
            time.sleep(0.02)
        took, result = self.finish_follow(follower, thread, result)
        self.assertEqual(result, [0])
        self.assertLess(took, 2.5)

    def test_r1_7_a_hung_herdr_never_holds_up_a_quiet_core_stream(self):
        follower, thread, result = self.core_beside([{'channel': None, 'seq': 1, 'terminals': []}], hang=4)
        thread.start()
        deadline = time.time() + 5
        while not (getattr(follower, 'reader', None) and follower.reader.is_alive()):
            self.assertLess(time.time(), deadline, 'no Herdr read began')
            time.sleep(0.02)
        took, result = self.finish_follow(follower, thread, result)
        self.assertEqual(result, [0])
        self.assertLess(took, 2.5, 'the quiet stream kept ticking while Herdr hung')


class LiveFacts(FollowerCase):
    """The live run on Herdr 0.9.5 (LT6 to LT9): Cursor's empty prompt, a null completion_seq on a fresh agent, an agent
    Herdr does not detect, and a terminal id that belongs to the pane."""

    def test_lt6_cursors_empty_prompt_takes_a_tell_and_an_unknown_one_fails_closed(self):
        self.hand('build-c', 'cursor')
        self.agent(agent_status='idle')
        self.add_pane(PANE, agent=self.herdr_state()['panes'][PANE]['agent'], screen='\u2192 Plan, search, build anything\n')
        self.assertEqual(self.quiet(fj.tell, self.job_dir, 'build-c', 'Fix the nit')[1], f'SUBMITTED build-c (pane {PANE})\n')
        self.add_pane('w9:p4', screen='\u276f Plan a feature, then build it st\u2026')  # Hermes, with its rotating placeholder
        self.hand('build-h', 'hermes', 'w9:p4')
        self.agent('w9:p4', agent_status='idle')
        with self.assertRaises(SystemExit):
            self.quiet(fj.tell, self.job_dir, 'build-h', 'Fix the nit')

    def test_lt7_the_first_turn_from_a_null_baseline_is_told(self):
        self.hand('build-h', 'hermes')
        self.add_pane('w9:p4')
        self.hand('build-c', 'cursor', 'w9:p4')
        self.assertEqual([self.entries(self.job_dir)[a]['completion'] for a in ('build-h', 'build-c')], [None, None])
        f = self.follower()
        for pane in (PANE, 'w9:p4'):
            self.agent(pane, agent_status='done')  # the brief's turn ends before the follower first looks
        self.look(f)
        self.assertEqual(self.inbox(), ['TURN build-h'])
        self.assertEqual(sorted((e['agent'], e['state']) for e in self.posts), [('build-c', 'done'), ('build-h', 'done')])

    def test_lt8_an_agent_herdr_never_detects_is_failed_with_how_to_end_it(self):
        self.herdr_shape(start_error={'build-h': 'timeout'})  # its CLI runs in the pane, but Herdr shows no agent there
        code, out = self.hand('build-h', 'hermes')
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith('FAILED build-h (herdr agent start: '), out)
        self.assertIn(f'): Herdr did not see hermes start in pane {PANE}, but its CLI '
                      f'may still run there: read it with herdr pane read {PANE} --source visible --lines 30, and end it there '
                      'with /exit', out)
        self.assertEqual((self.entries(self.job_dir)['build-h']['state'], self.mark()), ('failed', None))

    def test_lt9_a_restart_in_the_same_pane_is_told_apart_without_the_terminal_id(self):
        self.hand()
        f = self.follower()
        self.steps(f, 'done')  # its first turn: completion_seq is now a number
        terminal = self.herdr_state()['panes'][PANE]['agent']['terminal_id']
        self.add_pane(PANE, agent={**self.herdr_state()['panes'][PANE]['agent'], 'completion_seq': None, 'agent_status': 'idle'})
        self.assertEqual(self.herdr_state()['panes'][PANE]['agent']['terminal_id'], terminal, 'the pane keeps its terminal id')
        self.look(f)
        self.assertEqual(self.inbox(), ['TURN build-ui', 'GONE build-ui replaced'])


if __name__ == '__main__':
    unittest.main()
