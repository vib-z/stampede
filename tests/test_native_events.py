"""A Core-native job on the relay side: herdr-event-core --sweep (the lead's blocked, error, stale and dead, once each),
the watchdog that runs it, flush's UNDELIVERED line through fleet-job tell, and herdr-reopen-snapshot's hand-over.
Every script runs for real, against the fake hc and a socket that answers hello like a running core."""
import json, os, shutil, subprocess, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, ROOT
from test_core_relay import core_socket

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
        result = subprocess.run([str(RELAY / 'herdr-event-core'), '--sweep'], capture_output=True, text=True, timeout=60)
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
