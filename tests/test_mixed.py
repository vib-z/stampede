"""Mixed jobs: a Herdr Core job hands the agents Core cannot run (Cursor, Hermes, Kimi) to Herdr TUI panes. Every Core call
goes to tests/fake_hc.py and every Herdr call to tests/fake_herdr.py; nothing here starts a program or touches a real
core or Herdr."""
import contextlib, io, json, os, subprocess, sys, threading, time, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, LEAD, ROOT, SCRIPTS, SHA, fj, git
from test_core_relay import RELAY, Shell, follower_module

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
        its completion_seq. agent=None empties the pane (it exited); gone=True closes the pane."""
        state = self.herdr_state()
        if fields.get('gone'):
            del state['panes'][pane]
        elif 'agent' in fields and fields['agent'] is None:
            state['panes'][pane]['agent'] = None
        else:
            agent = state['panes'][pane]['agent']
            if (agent['agent_status'] in ('working', 'blocked') and fields.get('agent_status') in ('idle', 'done')
                    and 'completion_seq' not in fields):
                fields['completion_seq'] = agent['completion_seq'] + 1
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
            self.assertEqual({k: entry[k] for k in ('state', 'role', 'backend', 'pane', 'kind', 'terminal', 'completion')},
                             {'state': 'live', 'role': 'worker', 'backend': 'tui', 'pane': pane, 'kind': kind,
                              'terminal': f'term{n + 1}', 'completion': 0})
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
        self.agent(terminal_id='term99')  # its name runs in its pane, but not as this launch
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
        code, out = self.quiet(fj.reopen, self.job_dir)
        self.assertIn('LIVE build-db (pane w9:p4)', out)
        self.assertEqual((code, self.entries(self.job_dir)['build-db']['state']), (0, 'live'))

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


class MixedFollower(MixedCase):
    """Design item 3, A1 to A3: the follower looks at handed agents and tells the lead and the bot as for a Core worker."""

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

    def steps(self, follower, *statuses, pane=PANE):
        for word in statuses:
            if word == 'exit':
                self.agent(pane, agent=None)
            elif word == 'close':
                self.agent(pane, gone=True)
            else:
                self.agent(pane, agent_status=word)
            follower.poll()

    def sent(self):
        return [(e['state'], e.get('turn') or e.get('kind') or e.get('last_state')) for e in self.posts]

    def test_turns_blocks_and_an_exit_of_a_hermes_worker(self):
        self.hand('build-ui', 'hermes')  # working on its brief pointer
        f = self.follower()
        self.steps(f, 'done', 'working', 'blocked', 'working', 'idle', 'exit')
        self.assertEqual(self.inbox(), ['TURN build-ui', 'BLOCKED build-ui dialog', 'TURN build-ui', 'GONE build-ui exited'])
        self.assertEqual(self.sent(), [('done', 1), ('blocked', 'dialog'), ('idle', 2)])
        launch = self.entries(self.job_dir)['build-ui']['launch']
        event = self.posts[1]
        self.assertEqual((event['source'], event['workspace'], event['pane'], event['agent'], event['owner']),
                         ('hc', self.key, PANE, 'build-ui', 'alpha'))
        self.assertEqual(event['event_id'], f'{self.key}/tui:{PANE}|{launch}|blocked|1')
        self.assertEqual(self.posts[0]['event_id'], f'{self.key}/tui:{PANE}|{launch}|turn|1')
        self.assertIn('output_tail', event)
        f.poll()
        self.assertEqual(len(self.inbox()), 4, 'GONE once')
        self.assertEqual(self.mark(), str(self.job_dir), 'a GONE keeps its mark until finish')

    def test_a_turn_between_looks_or_while_the_follower_was_down_is_told_once(self):
        self.hand()
        first = self.follower()
        first.poll()
        self.agent(agent_status='idle', completion_seq=1)  # worked and finished between two looks
        first.poll()
        first.poll()
        self.agent(agent_status='done', completion_seq=2)  # and again while no follower ran
        self.follower().poll()
        self.follower().poll()
        self.assertEqual(self.inbox(), ['TURN build-ui', 'TURN build-ui'])
        self.assertEqual(self.sent(), [('idle', 1), ('done', 2)])

    def test_kimi_turns_and_cursor_leaves_its_turn_line_to_its_own_hook(self):
        self.hand('build-k', 'kimi')
        self.add_pane('w9:p4')
        self.hand('build-c', 'cursor', 'w9:p4')
        f = self.follower()
        for pane in (PANE, 'w9:p4'):
            self.agent(pane, agent_status='done')
        f.poll()
        self.assertEqual(self.inbox(), ['TURN build-k'])
        self.assertEqual(sorted((e['agent'], e['state']) for e in self.posts), [('build-c', 'done'), ('build-k', 'done')])

    def test_dead_when_it_ends_working_and_the_pane_is_named_when_it_closed(self):
        self.hand()
        f = self.follower()
        self.steps(f, 'working', 'close')
        f.poll()
        self.assertEqual(self.inbox(), ['GONE build-ui pane closed'])
        self.assertEqual(self.sent(), [('dead', 'working')])

    def test_stale_once_per_stall(self):
        self.hand()
        f = self.follower()
        for minute in (0, 29, 31, 40):
            self.now[0] = minute * 60
            f.poll()
            f.stalls()
        self.assertEqual(self.inbox(), ['STALE build-ui no new output for 31m'])
        self.assertEqual([(e['state'], e['minutes_unchanged'], e['pane']) for e in self.posts], [('stale', 31, PANE)])

    def test_one_event_each_across_a_follower_restart(self):
        self.hand()
        self.steps(self.follower(), 'blocked')
        self.steps(self.follower(), 'blocked', 'working')  # a restarted follower resumes from relay-state.json
        self.steps(self.follower(), 'done', 'done')
        self.assertEqual(self.inbox(), ['BLOCKED build-ui dialog', 'TURN build-ui'])
        self.assertEqual(self.sent(), [('blocked', 'dialog'), ('done', 1)])

    def test_a_restart_in_its_pane_is_a_new_launch_and_herdr_down_is_no_news(self):
        self.hand()
        f = self.follower()
        self.steps(f, 'done', 'exit')
        self.hand()
        self.herdr_shape(list_error='server_down')
        self.steps(f, 'done')
        self.agent(agent=None)
        f.poll()
        self.herdr_shape(list_error=None)
        self.agent(agent=None)
        self.assertEqual(self.inbox(), ['TURN build-ui', 'GONE build-ui exited'], 'Herdr down: no TURN, and never GONE')
        self.hand()
        self.steps(f, 'done')
        self.assertEqual(self.inbox(), ['TURN build-ui', 'GONE build-ui exited', 'TURN build-ui'])

    def test_a_same_name_replacement_is_gone_and_a_start_not_yet_live_is_never_gone(self):
        self.hand()
        f = self.follower()
        f.poll()
        self.agent(terminal_id='term99')
        f.poll()
        self.assertEqual(self.inbox(), ['GONE build-ui replaced'])
        fj.bind(self.job_dir, 'build-db', {'state': 'starting', 'backend': 'tui', 'pane': 'w9:p8', 'kind': 'kimi',
                                           'launch': 'a' * 12}, fresh=True)
        f.poll()
        self.assertEqual(len(self.inbox()), 1)

    def test_a_core_only_job_never_calls_herdr(self):
        f = self.follower()
        f.line({'channel': None, 'seq': 1, 'terminals': []})
        f.poll()
        self.assertEqual(self.herdr_calls(), [])

    def test_it_ticks_while_the_core_stream_is_quiet(self):
        self.hand()
        core = follower_module()
        self.shape(streams=[[{'channel': None, 'seq': 1, 'terminals': []}]], hold=[60])
        with mock.patch.object(core.Follower, 'post', lambda follower, event: None), \
                mock.patch.object(core, 'POLL_EVERY', 0.05), mock.patch.object(core, 'alive', lambda: True):
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
                            ({'name': 'build-ui', 'terminal_id': 'term99'}, f'pane {PANE} runs build-ui, but not as the launch this job recorded')):
            self.agent(**fields)
            self.assertEqual(self.told(), (f'FAILED build-ui ({why})', 2))
        self.agent(terminal_id='term1')
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
        self.assertIn('UNKNOWN build-ui: Herdr did not answer', out)
        self.assertEqual(self.calls('run'), [], 'never in a Core terminal')
        self.assertIn(f'pane {PANE}', (self.job_dir / 'REOPEN.md').read_text())


if __name__ == '__main__':
    unittest.main()
