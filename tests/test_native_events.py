"""A Core-native job on the relay side: herdr-event-sweep (the lead's blocked, error, stale and dead, once each),
the watchdog that runs it, flush's UNDELIVERED line through fleet-job tell, and herdr-reopen-snapshot's hand-over.
Every script runs for real, against the fake hc and a socket that answers hello like a running core."""
import contextlib, io, json, os, shutil, subprocess, sys, time, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, ROOT
from test_core_relay import core_socket
from stampede import hcapi as hcapi_, native as native_  # noqa: E402
from shlex import quote as shlex_quote  # noqa: E402

RELAY = ROOT / 'skills/grokbot-herdr/scripts'


class NativeCase(CoreCase):
    def setUp(self):
        super().setUp()
        self.socket, server = core_socket(self.root)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.local = self.root / 'home/.local/bin'  # the scripts put $HOME/.local/bin first on PATH
        self.local.mkdir(parents=True)
        self.stand_in('herdr', 'exit 127')  # no Herdr TUI on this machine
        self.jd, self.key = self.native_job('job-a', 'hc-0123456789ab')

    def stand_in(self, name, body):
        path = self.local / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def native_job(self, name, key, backend='native', socket=None):
        job = self.root / 'jobs' / name
        job.mkdir(parents=True)
        for file, text in (('workspace', key), ('lead', 'lead-x'), ('owner', 'alpha')):
            (job / file).write_text(text + '\n')
        if backend:
            (job / 'backend').write_text(backend + '\n')
        (job / 'endpoint').write_text(json.dumps({'session': '', 'socket': str(socket or self.socket)}))
        (self.events / 'jobs').mkdir(exist_ok=True)
        (self.events / 'jobs' / key).write_text(str(job) + '\n')
        return job, key

    def lead(self, address='t1', key=None, **fields):
        key = key or self.key
        state = self.state()
        state['terminals'][address] = {
            'address': address, 'name': 'lead-x', 'state': 'live', 'turn': 0, 'status': {'state': 'working'},
            'argv': ['env', f'STAMPEDE_JOB_KEY={key}', 'claude'], 'exit_code': None, 'reason': None, 'parent': None,
            'labels': {'stampede.job': key, 'stampede.role': 'lead', 'stampede.agent': 'lead-x'}, 'screen': 'thinking', **fields}
        self.shape(**state)

    def sweep(self):
        (self.root / 'home/.local/state/herdr-events/dedupe.tsv').unlink(missing_ok=True)  # the sweep's own memory only
        result = subprocess.run([str(RELAY / 'herdr-event-sweep')], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def queued(self):
        rows = sorted((self.root / 'queue/queue').glob('*.json')) if (self.root / 'queue/queue').is_dir() else []
        return [json.loads(p.read_text())['payload'] for p in rows]

    def ids(self):
        return [e['event_id'] for e in self.queued()]

    def sweep_state(self, job=None):
        return json.loads(((job or self.jd) / 'sweep-state.json').read_text())


class Sweep(NativeCase):
    def test_a_blocked_lead_posts_once_with_the_follower_fields(self):
        self.lead(status={'state': 'blocked', 'kind': 'permission', 'msg': 'run rm?'}, screen='Allow rm? y/n')
        self.sweep()
        self.sweep()
        [event] = self.queued()
        self.assertEqual({k: event[k] for k in ('source', 'state', 'pane', 'workspace', 'agent', 'kind', 'msg', 'output_tail',
                                                'event_id', 'job', 'owner')},
                         {'source': 'hc', 'state': 'blocked', 'pane': f'hc:{self.key}/t1', 'workspace': self.key, 'agent': 'lead-x',
                          'kind': 'permission', 'msg': 'run rm?', 'output_tail': 'Allow rm? y/n',
                          'event_id': f'{self.key}/t1|blocked|1', 'job': str(self.jd), 'owner': 'alpha'})

    def test_the_follower_still_answers_the_sweep_and_the_probes_for_one_release(self):
        self.lead(status={'state': 'blocked', 'kind': 'permission'})
        old = subprocess.run([str(RELAY / 'herdr-event-core'), '--sweep'], capture_output=True, text=True, timeout=60)
        self.assertEqual(old.returncode, 0, old.stderr)
        self.sweep()  # the new script takes over the same state: nothing twice
        self.assertEqual(self.ids(), [f'{self.key}/t1|blocked|1'])
        for script in ('herdr-event-core', 'herdr-event-sweep'):
            for socket, code in ((self.socket, 0), (self.root / 'none.sock', 1)):
                alive = subprocess.run([str(RELAY / script), '--alive'], env={**os.environ, 'HC_SOCKET': str(socket)},
                                       capture_output=True, text=True, timeout=30)
                self.assertEqual((alive.returncode, alive.stdout), (code, ''), script)
        shown = subprocess.run([str(RELAY / 'herdr-event-sweep'), '--help'], capture_output=True, text=True, timeout=30)
        self.assertEqual(shown.returncode, 0)
        self.assertIn('herdr-event-sweep --alive', shown.stdout)

    def test_a_second_episode_posts_again(self):
        self.lead(status={'state': 'blocked', 'kind': 'permission'})
        self.sweep()
        self.lead(status={'state': 'working'})
        self.sweep()
        self.lead(status={'state': 'blocked', 'kind': 'question'})
        self.sweep()
        self.assertEqual(self.ids(), [f'{self.key}/t1|blocked|1', f'{self.key}/t1|blocked|2'])

    def test_an_error_posts_once(self):
        self.lead(status={'state': 'error', 'msg': 'rate limited'})
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['msg'], e['event_id']) for e in self.queued()],
                         [('error', 'rate limited', f'{self.key}/t1|error|1')])

    def test_a_stall_only_after_the_limit_and_once(self):
        self.lead()
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])

        def age(minutes):
            state = self.sweep_state()
            state['terminals']['t1']['stall']['since'] -= minutes * 60
            (self.jd / 'sweep-state.json').write_text(json.dumps(state))
        age(29)
        self.sweep()
        self.assertEqual(self.queued(), [], 'under 30 minutes is no stall')
        age(2)
        self.sweep()
        age(60)
        self.sweep()
        [event] = self.queued()
        self.assertEqual((event['state'], event['event_id']), ('stale', f'{self.key}/t1|stale|1'))
        self.assertGreaterEqual(event['minutes_unchanged'], 31)
        self.lead(screen='new output')
        self.sweep()
        self.assertFalse(self.sweep_state()['terminals']['t1']['stall']['told'], 'new output starts a new stall clock')

    def test_a_lead_with_no_terminal_is_dead_once(self):
        self.lead()
        self.sweep()
        self.shape(terminals={})
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['reason'], e['last_state'], e['event_id']) for e in self.queued()],
                         [('dead', 'lost', 'working', f'{self.key}/t1|finished')])

    def test_a_shell_in_the_leads_place_is_dead_once(self):
        self.lead()
        self.sweep()
        self.lead(argv=['/bin/zsh', '-l'], status=None)
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['reason']) for e in self.queued()], [('dead', 'lost')])

    def test_a_killed_lead_never_seen_live_is_dead(self):
        self.lead(state='finished', status=None, exit_code=None, reason='killed')
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['reason']) for e in self.queued()], [('dead', 'killed')])

    def test_a_lead_lost_before_any_pass_is_dead_once(self):
        """R4: new, kill and hc rm before the first pass: Core has no row, tree.json has the lead's address."""
        from stampede import hcapi as hcapi_, native as native_, cli as cli_
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        with mock.patch.dict(os.environ, {'HC_SOCKET': str(self.socket)}):
            code, out = self.quiet(cli_.new, str(ask), None, core=True, cwd=str(self.repo))
            self.assertEqual(code, 0, out)
            hcapi_.hc('kill', 't1')
            hcapi_.hc('rm', 't1')
        (self.job / 'owner').write_text('alpha\n')  # a route of its own, so the post is queued
        key = (self.job / 'workspace').read_text().strip()
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['reason'], e['pane'], e['event_id']) for e in self.queued()],
                         [('dead', 'lost', f'hc:{key}/t1', f'{key}/t1|finished')])

    def test_a_lead_saved_as_exited_0_then_removed_is_no_dead(self):
        """R6: the lead left by itself with exit 0, a snapshot saved it, then its record was removed: no alarm."""
        from stampede import hcapi as hcapi_, native as native_, cli as cli_
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        with mock.patch.dict(os.environ, {'HC_SOCKET': str(self.socket)}):
            code, out = self.quiet(cli_.new, str(ask), None, core=True, cwd=str(self.repo))
            self.assertEqual(code, 0, out)
            self.terminal('t1', state='finished', status=None, exit_code=0, reason='exited')
            self.quiet(native_.snapshot, self.job)
            hcapi_.hc('rm', 't1')
        (self.job / 'owner').write_text('alpha\n')
        node = next(n for n in json.loads((self.job / 'tree.json').read_text())['nodes'].values() if n.get('role') == 'lead')
        self.assertEqual((node.get('state'), node.get('exit_code'), node.get('reason')), ('finished', 0, 'exited'))
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])

    def test_a_lead_with_no_address_in_tree_json_is_no_news(self):
        (self.jd / 'tree.json').write_text(json.dumps({'nodes': {'lead-x': {'name': 'lead-x', 'role': 'lead', 'state': 'starting'}}}))
        self.sweep()
        (self.jd / 'tree.json').write_text('{not json')
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertFalse((self.jd / 'sweep-state.json').is_file() and self.sweep_state()['terminals'])

    def test_its_own_exit_0_is_no_dead(self):
        self.lead()
        self.sweep()
        self.lead(state='finished', status=None, exit_code=0, reason='exited')
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertTrue(self.sweep_state()['terminals']['t1']['finished'])

    def test_a_finished_job_and_a_relay_job_are_skipped(self):
        relay, relay_key = self.native_job('job-r', 'hc-0000000000aa', backend='core')
        plain, plain_key = self.native_job('job-p', 'hc-0000000000bb', backend=None)
        for key in (relay_key, plain_key, self.key):
            self.lead(address='t-' + key[-2:], key=key, status={'state': 'blocked', 'kind': 'permission'})
        (self.jd / 'finished').write_text('')
        self.sweep()
        self.assertEqual(self.queued(), [])
        for job in (self.jd, relay, plain):
            self.assertFalse((job / 'sweep-state.json').exists())

    def test_a_closed_job_is_no_alarm_until_it_is_reopened(self):
        self.lead()
        self.sweep()
        (self.jd / 'closed').write_text('')
        self.shape(terminals={})
        self.sweep()
        self.assertEqual(self.queued(), [], 'closed on purpose: no dead')
        (self.jd / 'closed').unlink()
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['event_id']) for e in self.queued()], [('dead', f'{self.key}/t1|finished')])

    def test_a_core_that_does_not_answer_is_no_news(self):
        (self.jd / 'endpoint').write_text(json.dumps({'session': '', 'socket': str(self.root / 'none.sock')}))
        self.lead(status={'state': 'blocked', 'kind': 'permission'})
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertFalse((self.core / 'calls').exists(), 'no hc call, so no core is started')

    def test_an_event_the_post_refused_goes_out_on_the_next_pass(self):
        (self.root / 'queue').write_text('a file where the queue folder should be')
        self.lead(status={'state': 'blocked', 'kind': 'permission'})
        self.sweep()
        self.assertEqual(list(self.sweep_state()['unsent']), ['t1|blocked|1'])
        (self.root / 'queue').unlink()
        self.sweep()
        self.sweep()
        self.assertEqual(self.ids(), [f'{self.key}/t1|blocked|1'])
        self.assertEqual(self.sweep_state()['unsent'], {})

    def test_helpers_are_not_the_sweeps(self):
        self.lead()
        state = self.state()
        state['terminals']['t2'] = {**state['terminals']['t1'], 'address': 't2', 'status': {'state': 'blocked', 'kind': 'permission'},
                                    'labels': {'stampede.job': self.key, 'stampede.role': 'helper', 'stampede.agent': 'h1'}}
        self.shape(**state)
        self.sweep()
        self.assertEqual(self.queued(), [])


class Helpers(NativeCase):
    """alerts.helpers on (<job>/settings.json): each helper gets the lead's blocked, error, stale and dead, with agent its
    own name; a plain child, a helper closed by stampede close or ended with its parent's branch never; off: only the lead."""

    def setUp(self):
        super().setUp()
        self.setting(True)
        self.lead(status={'state': 'idle'})

    def setting(self, on):
        (self.jd / 'settings.json').write_text(json.dumps({'values': {'alerts.helpers': on}}))

    def helper(self, address='t2', name='h1', role='helper', parent='t1', **fields):
        state = self.state()
        labels = {'stampede.job': self.key, 'stampede.agent': name, **({'stampede.role': role} if role else {})}
        state['terminals'][address] = {**state['terminals']['t1'], 'address': address, 'name': name, 'parent': parent,
                                       'status': {'state': 'working'}, 'labels': labels, 'screen': 'building',
                                       'die_with_parent': True, **fields}
        self.shape(**state)

    def posted(self):
        return [(e['state'], e['agent'], e['event_id']) for e in self.queued()]

    def test_blocked_and_error_once_per_episode_with_the_lead_s_shape(self):
        self.helper(status={'state': 'blocked', 'kind': 'permission', 'msg': 'run rm?'}, screen='Allow rm?')
        self.sweep()
        self.sweep()
        [event] = self.queued()
        self.assertEqual({k: event[k] for k in ('source', 'state', 'pane', 'workspace', 'agent', 'kind', 'msg', 'output_tail', 'event_id',
                                                'owner')},
                         {'source': 'hc', 'state': 'blocked', 'pane': f'hc:{self.key}/t2', 'workspace': self.key, 'agent': 'h1',
                          'kind': 'permission', 'msg': 'run rm?', 'output_tail': 'Allow rm?', 'event_id': f'{self.key}/t2|blocked|1',
                          'owner': 'alpha'})
        self.helper(status={'state': 'working'})
        self.sweep()
        self.helper(status={'state': 'error', 'msg': 'rate limited'})
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('blocked', 'h1', f'{self.key}/t2|blocked|1'), ('error', 'h1', f'{self.key}/t2|error|1')])
        self.assertFalse((self.jd / 'inbox.log').exists(), 'a native job has no inbox')

    def test_stale_after_the_limit(self):
        self.helper()
        self.sweep()
        self.sweep()
        state = self.sweep_state()
        state['terminals']['t2']['stall']['since'] -= 31 * 60
        (self.jd / 'sweep-state.json').write_text(json.dumps(state))
        self.sweep()
        self.sweep()
        [event] = self.queued()
        self.assertEqual((event['state'], event['agent'], event['event_id']), ('stale', 'h1', f'{self.key}/t2|stale|1'))
        self.assertGreaterEqual(event['minutes_unchanged'], 31)

    def test_dead_when_it_ended_working_or_blocked_or_a_shell_took_its_place(self):
        self.helper()
        self.helper('t3', 'h2', status={'state': 'blocked', 'kind': 'question'})
        self.helper('t4', 'h3')
        self.sweep()
        self.terminal('t2', state='finished', status=None, exit_code=None, reason='killed')
        self.terminal('t3', state='finished', status=None, exit_code=1, reason='exited')
        self.terminal('t4', argv=['/bin/zsh', '-l'], status=None)
        self.sweep()
        self.sweep()
        dead = [(e['agent'], e['reason'], e['last_state'], e['event_id']) for e in self.queued() if e['state'] == 'dead']
        self.assertEqual(sorted(dead), [('h1', 'killed', 'working', f'{self.key}/t2|finished'),
                                        ('h2', 'exited', 'blocked', f'{self.key}/t3|finished'),
                                        ('h3', 'lost', 'working', f'{self.key}/t4|finished')])

    def test_removed_from_core_by_anything_but_stampede_close_is_lost(self):
        self.helper()
        self.helper('t3', 'h2', status={'state': 'idle'})
        self.sweep()
        state = self.state()
        del state['terminals']['t2'], state['terminals']['t3']
        self.shape(**state)
        self.sweep()
        self.sweep()
        self.assertEqual(sorted((e['state'], e['agent'], e['reason']) for e in self.queued()), [('dead', 'h1', 'lost'), ('dead', 'h2', 'lost')])

    def test_no_dead_for_its_own_exit_0_a_close_or_its_parent_s_end(self):
        self.helper()
        self.helper('t3', 'h2')
        self.helper('t4', 'h3', parent='t3')
        self.sweep()
        self.terminal('t2', state='finished', status=None, exit_code=0, reason='exited')
        closed = {'name': 'h2', 'role': 'helper', 'state': 'closed', 'address': 't3'}  # stampede close h2: its subtree
        (self.jd / 'tree.json').write_text(json.dumps({'nodes': {'h2': closed, 'h3': {**closed, 'name': 'h3', 'address': 't4'}}}))
        state = self.state()
        del state['terminals']['t3'], state['terminals']['t4']
        self.shape(**state)
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertTrue(all(r['finished'] for a, r in self.sweep_state()['terminals'].items() if a != 't1'))

    def test_the_lead_s_end_takes_its_branch_with_it(self):
        self.helper()
        self.sweep()
        self.terminal('t1', state='finished', status=None, exit_code=None, reason='killed', finished_ms=1000)
        self.terminal('t2', state='finished', status=None, exit_code=None, reason='killed', finished_ms=1000)
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'lead-x', f'{self.key}/t1|finished')])
        self.assertTrue(self.sweep_state()['terminals']['t2']['finished'], 'quiet: judged, not pending')

    def test_b1_a_helper_that_outlives_its_parent_still_reports_its_own_death(self):
        self.helper(die_with_parent=False)
        self.helper('t3', 'h2')
        self.sweep()
        self.terminal('t1', state='finished', status=None, exit_code=None, reason='killed', finished_ms=1000)
        self.terminal('t3', state='finished', status=None, exit_code=None, reason='killed', finished_ms=1001)  # its branch
        self.sweep()  # t2 outlived it and still works
        self.terminal('t2', state='finished', status=None, exit_code=1, reason='exited')
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'lead-x', f'{self.key}/t1|finished'), ('dead', 'h1', f'{self.key}/t2|finished')])

    def test_b1_a_helper_under_a_live_plain_child_is_no_branch_end(self):
        self.helper('t2', 'ci-wait', role=None)
        self.helper('t3', 'h2', parent='t2')
        self.sweep()
        self.terminal('t3', state='finished', status=None, exit_code=None, reason='killed')
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h2', f'{self.key}/t3|finished')])

    def test_b2_off_after_on_posts_no_helper_event_and_keeps_no_stall_clock(self):
        self.helper()
        self.sweep()
        self.sweep()
        state = self.sweep_state()
        state['terminals']['t2']['stall']['since'] -= 31 * 60  # saved while on
        (self.jd / 'sweep-state.json').write_text(json.dumps(state))
        self.setting(False)
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [], 'off: no helper event of any kind')
        self.assertNotIn('stall', self.sweep_state()['terminals']['t2'])
        self.setting(True)
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [], 'on again: the unwatched time is no stall')
        self.assertFalse(self.sweep_state()['terminals']['t2']['stall']['told'])

    def test_b3_a_helper_that_failed_between_two_passes_is_dead_once_and_its_exit_0_is_not(self):
        self.sweep()  # a pass with no helper yet
        now = int(time.time() * 1000)
        self.helper(state='finished', status=None, exit_code=1, reason='exited', finished_ms=now)
        self.helper('t3', 'h2', state='finished', status=None, exit_code=None, reason='killed')
        self.helper('t4', 'h3', state='finished', status=None, exit_code=0, reason='exited')
        self.helper('t5', 'h4', state='finished', status=None, exit_code=1, reason='exited')
        (self.jd / 'tree.json').write_text(json.dumps({'nodes': {'h4': {'name': 'h4', 'role': 'helper', 'state': 'closed', 'address': 't5'}}}))
        self.sweep()
        self.sweep()
        dead = sorted((e['agent'], e['reason'], e.get('last_state'), e['event_id']) for e in self.queued())
        self.assertEqual(dead, [('h1', 'exited', None, f'{self.key}/t2|finished'), ('h2', 'killed', None, f'{self.key}/t3|finished')])

    def test_b3_one_that_failed_before_the_job_s_first_pass_is_dead(self):
        self.helper(state='finished', status=None, exit_code=1, reason='exited', finished_ms=1)  # on from the start
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])

    def test_b3_one_that_ended_while_alerts_were_off_is_not(self):
        self.setting(False)
        self.sweep()
        self.helper(state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000) - 1000)
        self.setting(True)
        self.helper('t3', 'h2', state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000) + 1000)
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h2', f'{self.key}/t3|finished')])

    def test_r1_off_and_on_again_a_new_blocked_episode_is_news(self):
        self.helper(status={'state': 'blocked', 'kind': 'permission', 'msg': 'first question'})
        self.sweep()
        self.setting(False)
        self.sweep()
        self.terminal('t2', status={'state': 'working'})
        self.sweep()
        self.setting(True)
        self.sweep()
        self.terminal('t2', status={'state': 'blocked', 'kind': 'permission', 'msg': 'second question'})
        self.sweep()
        self.sweep()
        self.assertEqual([(e['msg'], e['event_id']) for e in self.queued()],
                         [('first question', f'{self.key}/t2|blocked|1'), ('second question', f'{self.key}/t2|blocked|2')])

    def test_r1_off_and_on_again_a_new_stall_is_news(self):
        self.helper()
        self.sweep()
        self.stall()
        self.sweep()
        self.setting(False)
        self.sweep()
        self.setting(True)
        self.sweep()
        self.stall()
        self.sweep()
        self.assertEqual([e['event_id'] for e in self.queued()], [f'{self.key}/t2|stale|1', f'{self.key}/t2|stale|2'])

    def stall(self):
        state = self.sweep_state()
        state['terminals']['t2']['stall']['since'] -= 31 * 60
        (self.jd / 'sweep-state.json').write_text(json.dumps(state))

    def test_r2_its_own_failure_is_dead_though_its_parent_then_exits_0(self):
        self.helper()
        self.sweep()
        ended = int(time.time() * 1000)
        self.terminal('t2', state='finished', status=None, exit_code=1, reason='exited', finished_ms=ended)
        self.terminal('t1', state='finished', status=None, exit_code=0, reason='exited', finished_ms=ended + 100)
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])

    def test_r2_a_kill_before_its_parent_ended_is_no_branch_end(self):
        self.helper()
        self.sweep()
        ended = int(time.time() * 1000)
        self.terminal('t2', state='finished', status=None, reason='killed', finished_ms=ended)
        self.terminal('t1', state='finished', status=None, exit_code=0, reason='exited', finished_ms=ended + 100)
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])

    def test_r3_a_parent_lookup_that_fails_leaves_the_helper_pending(self):
        self.helper('t2', 'plain-parent', role=None)
        self.helper('t3', 'child', parent='t2')
        self.sweep()
        self.terminal('t3', state='finished', status=None, reason='killed')
        self.shape(get_error={'t2': 'unavailable'})
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertFalse(self.sweep_state()['terminals']['t3']['finished'], 'pending, not finished')
        self.shape(get_error={})
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'child', f'{self.key}/t3|finished')])

    def test_r4_rewriting_unchanged_settings_loses_no_failure(self):
        self.sweep()
        self.helper(state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000))
        time.sleep(0.03)
        path = self.jd / 'settings.json'
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])

    def bad_hc(self, script):
        """Run the sweep's hc through a wrapper: script (sh) may answer first; otherwise the fake answers."""
        wrapper = self.root / 'bad-hc'
        wrapper.write_text(f'#!/bin/sh\n{script}\nexec {shlex_quote(os.environ["HC"])} "$@"\n')
        wrapper.chmod(0o755)
        return mock.patch.dict(os.environ, {'HC': str(wrapper)})

    def node(self, name='h1', address='t2', **fields):
        tree = json.loads((self.jd / 'tree.json').read_text()) if (self.jd / 'tree.json').is_file() else {'nodes': {}}
        tree['nodes'][name] = {'name': name, 'role': 'helper', 'state': 'live', 'address': address, **fields}
        (self.jd / 'tree.json').write_text(json.dumps(tree))

    def gone_from_core(self, *addresses):
        state = self.state()
        for address in addresses:
            del state['terminals'][address]
        self.shape(**state)

    def test_a1_a_failed_helper_list_on_the_first_on_pass_keeps_when_alerts_began(self):
        self.setting(False)
        self.sweep()
        self.setting(True)
        with self.bad_hc('case "$1 $*" in "ls "*stampede.role=helper*) exit 1;; esac'):
            self.sweep()
        began = self.sweep_state()['alerts']['since']
        self.assertGreater(began, 0)
        self.helper(state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000))
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])
        self.assertEqual(self.sweep_state()['alerts']['since'], began)

    def test_a1_so_does_a_failed_lead_list(self):
        self.setting(False)
        self.sweep()
        self.setting(True)
        with self.bad_hc('[ "$1" = ls ] && exit 1'):
            self.sweep()
        self.assertGreater(self.sweep_state()['alerts']['since'], 0)

    def test_a2_a_sweep_during_stampede_close_raises_no_alarm(self):
        self.helper()
        self.helper('t3', 'h2', parent='t2')
        self.node()
        self.node('h2', 't3', parent='h1')
        self.sweep()
        real = hcapi_.hc

        def interleaved(*args, **kw):
            result = real(*args, **kw)
            if args[0] in ('kill', 'rm'):
                self.sweep()  # a watchdog pass between close's kill or rm and its closed mark
            return result
        with mock.patch.object(hcapi_, 'hc', side_effect=interleaved), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(native_.close(self.jd, 'h1'), 0)
        self.assertIn('CLOSED h1 (t2)', out.getvalue())
        self.sweep()
        self.assertEqual(self.queued(), [])

    def test_a2_close_s_intent_holds_when_its_last_write_never_came(self):
        self.helper()
        self.node()
        self.sweep()
        (self.jd / 'close-intent.log').write_text('t2\n')  # close got that far, then the tree write failed
        self.gone_from_core('t2')
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])

    def test_a3_an_incomplete_get_is_no_answer(self):
        self.helper()
        self.sweep()
        for answer in ('{}', '{"address": "t9", "state": "finished", "reason": "exited", "exit_code": 1}',
                       '{"address": "t2", "reason": "exited", "exit_code": 1}', 'not json'):
            with self.bad_hc(f'[ "$1" = get ] && [ "$3" = t2 ] && {{ printf "%s\\n" {shlex_quote(answer)}; exit 0; }}'):
                self.sweep()
            self.assertEqual(self.queued(), [], answer)
            self.assertFalse(self.sweep_state()['terminals']['t2']['finished'], answer)
        self.terminal('t2', state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000))
        self.sweep()
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'h1', f'{self.key}/t2|finished')])

    def test_a4_a_helper_whose_end_is_pending_is_never_stale(self):
        self.helper('t9', 'plain', role=None)
        self.helper('t2', 'child', parent='t9')
        self.sweep()
        self.stall()
        self.terminal('t2', state='finished', status=None, reason='killed', finished_ms=1234)
        self.shape(get_error={'t9': 'unavailable'})
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])
        self.assertNotIn('stall', self.sweep_state()['terminals']['t2'])
        self.shape(get_error={})
        self.sweep()
        self.assertEqual(self.posted(), [('dead', 'child', f'{self.key}/t2|finished')], 'its parent is live: no branch end')

    def test_a5_a_helper_killed_and_removed_between_passes_is_dead(self):
        self.sweep()
        self.helper()
        self.node()
        self.gone_from_core('t2')
        self.sweep()
        self.sweep()
        self.assertEqual([(e['state'], e['agent'], e['reason']) for e in self.queued()], [('dead', 'h1', 'lost')])

    def test_a5_but_not_one_gone_before_alerts_began(self):
        self.setting(False)
        self.node(state='gone')
        self.sweep()
        self.setting(True)
        self.sweep()
        self.sweep()
        self.assertEqual(self.queued(), [])

    def test_a6_a_branch_end_needs_both_times(self):
        for child, parent in ((None, 1000), (1000, None)):
            self.setUp()
            self.helper()
            self.sweep()
            self.terminal('t2', state='finished', status=None, reason='killed', finished_ms=child)
            self.terminal('t1', state='finished', status=None, reason='killed', finished_ms=parent)
            self.sweep()
            self.assertEqual(self.posted(), [('dead', 'lead-x', f'{self.key}/t1|finished')], (child, parent))
            self.assertFalse(self.sweep_state()['terminals']['t2']['finished'], 'the order is unknown: pending')
            self.gone_from_core('t1')
            self.sweep()
            self.assertEqual(self.posted()[1:], [('dead', 'h1', f'{self.key}/t2|finished')], 'Core no longer knows the parent')

    def test_a_plain_child_is_never_reported(self):
        self.helper('t5', 'ci-wait', role=None, status={'state': 'blocked', 'kind': 'permission'})
        self.sweep()
        self.terminal('t5', state='finished', status=None, exit_code=1, reason='exited')
        self.sweep()
        self.assertEqual(self.queued(), [])

    def test_off_posts_exactly_what_it_posts_today(self):
        for value in (False, None):
            self.setUp()
            if value is None:
                (self.jd / 'settings.json').unlink()
            else:
                self.setting(value)
            self.lead(status={'state': 'blocked', 'kind': 'permission'})
            self.helper(status={'state': 'blocked', 'kind': 'permission'})
            self.sweep()
            self.terminal('t2', state='finished', status=None, exit_code=None, reason='killed')
            self.sweep()
            self.assertEqual(self.posted(), [('blocked', 'lead-x', f'{self.key}/t1|blocked|1')], value)
            self.assertEqual(list(self.sweep_state()['terminals']), ['t1'], 'no helper tracked')
            self.assertFalse([c for c in self.calls('ls') if 'stampede.role=helper' in c], 'no helper listing')


class EndToEnd(NativeCase):
    def test_new_saves_alerts_helpers_and_the_sweep_reports_a_failed_helper(self):
        fleet = ROOT / 'skills/herdr-fleet/scripts/fleet-job'
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        made = subprocess.run([str(fleet), 'new', '--core', '--file', str(ask), '--cwd', str(self.repo), '--name', 'login',
                               '--set', 'alerts.helpers=true'], capture_output=True, text=True, timeout=60,
                              env={**os.environ, 'HERDR_EVENTS_OWNER': 'alpha'})  # a bot's job: its events are queued for it
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        job = Path(made.stdout.split()[-1])
        self.assertNotIn(self.repo, job.parents, 'the job folder is under the jobs root, not in the repo')
        self.assertEqual((job / 'workdir').read_text().strip(), str(self.repo))
        self.assertEqual((self.events / 'jobs' / (job / 'workspace').read_text().strip()).read_text().strip(), str(job))
        self.assertIs(json.loads((job / 'settings.json').read_text())['values']['alerts.helpers'], True)
        point = json.loads((job / 'endpoint').read_text())
        (job / 'endpoint').write_text(json.dumps({**point, 'socket': str(self.socket)}))  # the fake core's hello socket
        started = subprocess.run([str(fleet), 'start', str(job), 'build-api', '--', 'false'], capture_output=True, text=True,
                                 timeout=60, env={**os.environ, 'HC_TERMINAL_ID': ''})
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        address = next(a for a, t in self.state()['terminals'].items() if t['labels'].get('stampede.agent') == 'build-api')
        self.sweep()
        self.terminal(address, state='finished', status=None, exit_code=1, reason='exited', finished_ms=int(time.time() * 1000))
        self.sweep()
        self.assertEqual([(e['state'], e['agent'], e['exit_code']) for e in self.queued()], [('dead', 'build-api', 1)])


class Watchdog(NativeCase):
    def test_the_watchdog_runs_the_sweep_with_no_herdr_tui(self):
        self.lead(status={'state': 'blocked', 'kind': 'permission'})
        result = subprocess.run([str(RELAY / 'herdr-event-watchdog')], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ids(), [f'{self.key}/t1|blocked|1'])


class Flush(NativeCase):
    def held(self, job):
        queue = self.root / 'queue/queue'
        queue.mkdir(parents=True, exist_ok=True)
        payload = {'source': 'stampede', 'state': 'question', 'ask': 'q1', 'owner': 'beta', 'job': str(job), 'pane': f'hc:{job.name}'}
        (queue / f'20261113T000000Z-{job.name}.json').write_text(json.dumps({'route': 'beta', 'payload': payload}))

    def test_an_undelivered_line_of_a_native_job_goes_to_fleet_job_tell(self):
        record = self.root / 'told'
        self.stand_in('fleet-job', f'printf "%s\\n" "$@" >> {record}')
        relay, _ = self.native_job('job-r', 'hc-0000000000aa', backend='core')
        self.held(self.jd)
        self.held(relay)
        result = subprocess.run([str(RELAY / 'herdr-event-flush')], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = record.read_text().splitlines()
        self.assertEqual(calls[:3], ['tell', str(self.jd), 'lead'])
        self.assertTrue(calls[3].startswith('UNDELIVERED question q1 for beta held: route beta has no URL'), calls[3])
        self.assertFalse((self.jd / 'inbox.log').exists())
        self.assertIn('UNDELIVERED question q1 for beta', (relay / 'inbox.log').read_text(), 'a relay job is unchanged')
        self.assertEqual(calls[4:], ['_wake', str(relay)])


class ReopenSnapshot(NativeCase):
    def test_a_native_job_hands_over_to_fleet_job_snapshot(self):
        tree = self.root / 'checkout/skills'
        (tree / 'grokbot-herdr/scripts').mkdir(parents=True)
        (tree / 'herdr-fleet/scripts').mkdir(parents=True)
        shutil.copy(RELAY / 'herdr-reopen-snapshot', tree / 'grokbot-herdr/scripts')
        fleet = tree / 'herdr-fleet/scripts/fleet-job'
        fleet.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {self.root / "snap"}\nexit 7\n')
        fleet.chmod(0o755)
        result = subprocess.run([sys.executable, str(tree / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), self.key, str(self.jd)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual((self.root / 'snap').read_text().splitlines(), ['snapshot', str(self.jd)])
        self.assertFalse((self.jd / 'REOPEN.md').exists())


if __name__ == '__main__':
    unittest.main()
