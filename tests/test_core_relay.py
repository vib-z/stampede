"""Herdr Core on the relay side: the owner's relay hooks, herdr-event-post, owner tags, the watchdog, herdr-doctor --core,
the core check that never starts a core, and the job's follower (herdr-event-core), replayed from fake streams."""
import importlib.util, json, os, socket, socketserver, subprocess, sys, tempfile, threading, time, unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase, FAKE_HC, ROOT

RELAY = ROOT / 'skills/grokbot-herdr/scripts'
FOLLOWER = RELAY / 'herdr-event-core'
KEY = 'hc-0123456789ab'


def follower_module():
    loader = SourceFileLoader('herdr_event_core', str(FOLLOWER))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class Hello(socketserver.StreamRequestHandler):
    def handle(self):
        request = json.loads(self.rfile.readline())
        self.wfile.write((json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': {'version': '0.1.13'}}) + '\n').encode())


def core_socket(folder):
    """A Unix socket that answers hello like a running core; returns its path."""
    path = Path(tempfile.mkdtemp(dir='/tmp')) / 'c.sock'
    server = socketserver.ThreadingUnixStreamServer(str(path), Hello)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return path, server


class Shell(unittest.TestCase):
    """The relay's shell scripts in a throwaway HOME, with a fake herdr-event-post that keeps what it is given."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.bin = self.home / '.local/bin'
        self.bin.mkdir(parents=True)
        self.events = self.home / 'events'
        for folder in ('owners', 'jobs', 'routes'):
            (self.events / folder).mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('HERDR_', 'HC_', 'STAMPEDE_', 'FLEET_'))}
        self.env.update(HOME=str(self.home), HERDR_EVENTS_DIR=str(self.events), HC=str(FAKE_HC),
                        FAKE_HC=str(self.home / 'core'), PATH=f'{self.bin}:/opt/homebrew/bin:/usr/bin:/bin',
                        HERDR_EVENTS_HOME=str(self.home / 'queue'))

    def fake(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o755)

    def link(self, *names):
        for name in names:
            (self.bin / name).symlink_to(RELAY / name)

    def run_script(self, name, *args, stdin='', **env):
        return subprocess.run([str(RELAY / name), *args], input=stdin, capture_output=True, text=True, timeout=30,
                              env={**self.env, **env})

    def posted(self):
        path = self.home / 'posted'
        return [json.loads(row) for row in path.read_text().splitlines() if row.strip()] if path.is_file() else []

    def log(self):
        path = self.home / 'Library/Logs/herdr-events.log'
        return path.read_text() if path.is_file() else ''


class CoreRelayHooks(Shell):
    """Build order 6: the owner's Claude and Codex relay hooks inside a Core terminal stampede started."""

    def setUp(self):
        super().setUp()
        self.fake('herdr-event-post', f'cat >> "{self.home}/posted"; echo >> "{self.home}/posted"\n')

    def test_claude_names_the_core_terminal_and_the_key(self):
        stop = json.dumps({'hook_event_name': 'Stop', 'session_id': 's1', 'cwd': '/repo'})
        self.run_script('herdr-event-claude-hook', stdin=stop, HC_TERMINAL_ID='t3', STAMPEDE_JOB_KEY=KEY)
        self.run_script('herdr-event-claude-hook', stdin=stop, HC_TERMINAL_ID='t3')  # a Core terminal stampede did not start
        first, second = self.posted()
        self.assertEqual((first['pane'], first['workspace']), (f'hc:{KEY}/t3', KEY))
        self.assertNotIn('pane', second)
        self.assertNotIn('workspace', second)

    def test_codex_no_longer_drops_a_core_turn(self):
        turn = json.dumps({'type': 'agent-turn-complete', 'last-assistant-message': 'done'})
        self.run_script('herdr-event-codex-notify', turn, HC_TERMINAL_ID='t4', STAMPEDE_JOB_KEY=KEY)
        self.run_script('herdr-event-codex-notify', turn, HC_TERMINAL_ID='t4')
        (event,) = self.posted()
        self.assertEqual((event['source'], event['pane'], event['workspace']), ('codex', f'hc:{KEY}/t4', KEY))
        self.assertIn('skip: codex turn with no herdr pane', self.log())


class CoreEventPost(Shell):
    """Build order 6: herdr-event-post reads the key from an hc: pane and keeps a Core job's plain turn ends home."""

    def setUp(self):
        super().setUp()
        (self.events / 'routes/alpha').write_text('URL=http://127.0.0.1:9/never\n')
        (self.events / 'owners' / KEY).write_text('owner=alpha\n')

    def post(self, **event):
        return self.run_script('herdr-event-post', json.dumps(event), HERDR_EVENTS_ROUTES_DIR=str(self.events / 'routes'))

    def queued(self):
        return [json.loads(p.read_text()) for p in sorted((self.home / 'queue/queue').glob('*.json'))] \
            if (self.home / 'queue/queue').is_dir() else []

    def test_an_hc_pane_gives_the_key_and_its_owner_route(self):
        self.post(source='hc', state='blocked', pane=f'hc:{KEY}/t3', agent='build-api')
        (item,) = self.queued()
        self.assertEqual((item['route'], item['payload']['workspace'], item['payload']['owner']), ('alpha', KEY, 'alpha'))

    def test_plain_core_turn_ends_stay_home_while_the_job_is_open(self):
        (self.events / 'jobs' / KEY).write_text('/repo/.herdr-demo\n')
        for state in ('done', 'idle'):
            self.post(source='hc', state=state, pane=f'hc:{KEY}/t3')
        self.assertEqual(self.queued(), [])
        self.assertEqual(self.log().count('job-skip'), 2)
        self.post(source='hc', state='dead', pane=f'hc:{KEY}/t3')
        self.assertEqual([q['payload']['state'] for q in self.queued()], ['dead'])

    def test_a_malformed_hc_pane_names_no_workspace(self):
        for pane in ('hc:../owners/x/t3', 'hc:hc-XYZ/t3', 'hc:hc-0123456789abc/t3', f'hc:{KEY}/t3'):
            self.post(source='hc', state='blocked', pane=pane)
        self.assertEqual([q['payload']['pane'] for q in self.queued()], [f'hc:{KEY}/t3'])
        self.assertEqual(self.log().count('logged-only (no route URL)'), 3)


class CoreOwnerTags(Shell):
    """Build order 6: herdr-events-owner, the watchdog and the doctor take a Core key."""

    def setUp(self):
        super().setUp()
        self.fake('herdr', f'echo "$*" >> "{self.home}/herdr-calls"\ncase "$1 $2" in\n'
                           '  "agent list") echo \'{"result":{"agents":[]}}\';;\n'
                           '  "workspace list") echo \'{"result":{"workspaces":[{"workspace_id":"w1"}]}}\';;\n'
                           '  "workspace get") [ "$3" = w1 ];;\nesac\n')

    def test_owner_shows_sets_and_clears_a_key_without_herdr(self):
        self.assertIn('owner=(none', self.run_script('herdr-events-owner', KEY).stdout)
        refused = self.run_script('herdr-events-owner', KEY, 'alpha')
        self.assertEqual(refused.returncode, 2)
        self.assertIn('no open Core job', refused.stderr)
        (self.events / 'jobs' / KEY).write_text('/repo/.herdr-demo\n')
        self.assertEqual(self.run_script('herdr-events-owner', KEY, 'alpha').returncode, 0)
        self.assertEqual((self.events / 'owners' / KEY).read_text(), 'owner=alpha\n')
        self.assertEqual(self.run_script('herdr-events-owner', KEY, '--clear').returncode, 0)
        self.assertFalse((self.events / 'owners' / KEY).exists())
        self.assertFalse((self.home / 'herdr-calls').exists())
        for bad in ('hc-0123', 'hc-0123456789AB', 'hc-../x'):
            self.assertEqual(self.run_script('herdr-events-owner', bad, 'alpha').returncode, 2, bad)

    def test_the_watchdog_keeps_a_core_tag_while_its_job_is_open_or_core_is_unknown(self):
        self.link('herdr-event-post', 'herdr-event-core')
        open_key, unknown = KEY, 'hc-ba9876543210'
        for name in ('w1', open_key, unknown, 'junk'):
            (self.events / 'owners' / name).write_text('owner=alpha\n')
        (self.events / 'jobs' / open_key).write_text('/repo/.herdr-demo\n')
        result = self.run_script('herdr-event-watchdog', HC_SOCKET=str(self.home / 'no.sock'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in (self.events / 'owners').iterdir()), sorted(['w1', open_key, unknown]))
        self.assertFalse((self.home / 'core/calls').exists(), 'the watchdog never asks a core it could not reach')

    def test_the_doctor_accepts_a_core_tag(self):
        subprocess.run(['bash', str(ROOT / 'install.sh')], env={**self.env, 'STAMPEDE_NO_UPDATE_CHECK': '1'},
                       check=True, capture_output=True, timeout=30)
        (self.events / 'owners' / KEY).write_text('owner=alpha\n')
        (self.events / 'jobs' / KEY).write_text('/repo/.herdr-demo\n')
        result = subprocess.run([str(self.bin / 'herdr-doctor')], capture_output=True, text=True, timeout=30,
                                env={**self.env, 'STAMPEDE_NO_UPDATE_CHECK': '1'})
        self.assertNotIn('malformed owner tag', result.stdout)
        (self.events / 'jobs' / KEY).unlink()
        result = subprocess.run([str(self.bin / 'herdr-doctor')], capture_output=True, text=True, timeout=30,
                                env={**self.env, 'STAMPEDE_NO_UPDATE_CHECK': '1'})
        self.assertIn(f'warn owner tag {KEY} (alpha) for a finished Core job: herdr-events-owner {KEY} --clear', result.stdout)


class CoreAlive(Shell):
    """Build order 6: whether the selected core is up, asked of its socket; never by an hc command that would start one."""

    def test_no_socket_is_down_even_with_a_core_process_around(self):
        fake = self.home / 'herdr-core'
        fake.symlink_to('/bin/sleep')
        unrelated = subprocess.Popen([str(fake), '30'])
        self.addCleanup(unrelated.kill)
        result = self.run_script('herdr-event-core', '--alive', HC_SOCKET=str(self.home / 'none.sock'))
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.home / 'core/calls').exists())

    def test_a_socket_that_answers_hello_is_up(self):
        path, server = core_socket(self.home)
        self.addCleanup(server.shutdown)
        self.assertEqual(self.run_script('herdr-event-core', '--alive', HC_SOCKET=str(path)).returncode, 0)

    def test_the_socket_is_found_as_core_finds_it(self):
        core = follower_module()
        home = Path('/h')
        self.assertEqual(core.socket_path({'HOME': '/h'}), home / '.local/state/herdr-core/default/default.sock')
        self.assertEqual(core.socket_path({'HOME': '/h', 'HC_SESSION': ' smoke ', 'XDG_STATE_HOME': '/s'}),
                         Path('/s/herdr-core/smoke/smoke.sock'))
        self.assertEqual(core.socket_path({'HOME': '/h', 'XDG_RUNTIME_DIR': '/r'}), Path('/r/herdr-core/default.sock'))
        self.assertEqual(core.socket_path({'HOME': '/h', 'HC_SOCKET': '/x.sock', 'XDG_RUNTIME_DIR': '/r'}), Path('/x.sock'))
        config = self.home / 'config/herdr-core'
        config.mkdir(parents=True)
        (config / 'config.toml').write_text('notes = true\nsocket = "/from/config.sock"\n')
        self.assertEqual(core.socket_path({'HOME': '/h', 'XDG_CONFIG_HOME': str(self.home / 'config')}), Path('/from/config.sock'))


class CoreDoctor(Shell):
    """Build order 7: herdr-doctor --core, read-only."""

    def setUp(self):
        super().setUp()
        for app in ('.claude', '.codex'):
            (self.home / app).mkdir()
        self.env['STAMPEDE_NO_UPDATE_CHECK'] = '1'
        del self.env['HC']  # the doctor runs hc --version itself, through the fake on its PATH
        (self.events / 'routes').rmdir()  # no relay installed: a routes folder would turn its checks on
        subprocess.run(['bash', str(ROOT / 'install.sh')], env=self.env, check=True, capture_output=True, timeout=30)
        self.fake('hc', 'echo "hc ${TEST_HC_VERSION:-0.1.13}"\n')
        self.fake('claude', 'echo "${TEST_CLAUDE_VERSION:-2.1.312} (Claude Code)"\n')
        self.fake('codex', 'echo "      --no-daemon"\n')
        self.fake('df', "printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999999 0 52428800 0%% /\\n'\n")
        self.socket, server = core_socket(self.home)
        self.addCleanup(server.shutdown)

    def doctor(self, **env):
        return subprocess.run([str(self.bin / 'herdr-doctor'), '--core'], capture_output=True, text=True, timeout=30,
                              env={**self.env, 'HC_SOCKET': str(self.socket), **env})

    def test_a_ready_machine(self):
        result = self.doctor()
        for line in ('ok hc 0.1.13', 'ok Herdr Core answers', 'ok claude 2.1.312 reports its status', 'ok codex runs with --no-daemon'):
            self.assertIn(line, result.stdout)
        self.assertNotIn('herdr server', result.stdout)
        self.assertNotIn('PROBLEM', result.stdout, result.stdout)

    def test_each_core_gap_is_named(self):
        cases = [({'TEST_HC_VERSION': '0.1.12'}, 'PROBLEM hc 0.1.12 is older than 0.1.13'),
                 ({'HC_SOCKET': str(self.home / 'none.sock')}, 'PROBLEM Herdr Core not running'),
                 ({'TEST_CLAUDE_VERSION': '2.1.200'}, 'PROBLEM claude 2.1.200 reports no status')]
        for env, line in cases:
            result = self.doctor(**env)
            self.assertEqual(result.returncode, 1)
            self.assertIn(line, result.stdout)
        self.fake('codex', 'echo "--yolo"\n')
        self.assertIn('PROBLEM codex has no --no-daemon', self.doctor().stdout)
        self.fake('cursor-agent', 'exit 0\n')
        self.assertIn('warn cursor-agent runs on the TUI only', self.doctor().stdout)
        (self.bin / 'hc').unlink()
        self.assertIn('PROBLEM hc not on PATH', self.doctor().stdout)

    def test_never_starts_a_core(self):
        self.fake('hc', f'echo "$*" >> "{self.home}/hc-calls"; echo "hc 0.1.13"\n')
        self.doctor(HC_SOCKET=str(self.home / 'none.sock'))
        self.assertEqual((self.home / 'hc-calls').read_text().split(), ['--version'])


def ev(kind, terminal, data, seq=0):
    return {'jsonrpc': '2.0', 'method': 'event', 'params': {'seq': seq, 'type': kind, 'terminal': terminal, 'data': data}}


def status(terminal, word, seq=0, **fields):
    return ev('status', terminal, {'status': {'state': word, **fields} if word else None, 'records': {}, 'reported': True}, seq)


def turn(terminal, n, word, seq=0):
    return ev('turn', terminal, {'turn': n, 'state': word}, seq)


def finished(terminal, code=0, reason='exited', seq=0, signal=None):
    return ev('finished', terminal, {'reason': reason, 'exit_code': code, 'signal': signal, 'finished_ms': 1}, seq)


class Follower(CoreCase):
    """Build order 6: herdr-event-core, the lifecycle authority for a Core job, from fake streams and snapshots."""

    def setUp(self):
        super().setUp()
        self.job_dir, self.key = self.core_job(workers=[('build-api', 'claude'), ('review-api', 'codex')], owner='alpha')
        self.roles = {'t1': ('lead-demo', 'lead'), 't2': ('relay-' + self.key[3:], 'relay'),
                      't3': ('build-api', 'worker'), 't4': ('review-api', 'worker')}
        (self.job_dir / 'core.json').write_text(json.dumps(
            {agent: {'state': 'live', 'address': address, 'role': role} for address, (agent, role) in self.roles.items()}))
        for address, (agent, role) in self.roles.items():
            self.add_terminal(address, name=agent, screen='last lines of ' + agent,
                              labels={'stampede.job': self.key, 'stampede.agent': agent, 'stampede.role': role})
        self.posts = []

    def follower(self):
        core = follower_module()
        patch = mock.patch.object(core.Follower, 'post', lambda follower, fields: self.posts.append(fields))
        patch.start()
        self.addCleanup(patch.stop)
        return core, core.Follower(self.job_dir)

    def record(self, address, word=None, turn_n=0, state='live', **fields):
        agent, role = self.roles.get(address, ('wait-ci', 'wait'))
        return {'address': address, 'name': agent, 'state': state, 'turn': turn_n, 'reported': word is not None,
                'status': {'state': word, **fields} if word else None,
                'labels': {'stampede.job': self.key, 'stampede.role': role, **({} if role == 'wait' else {'stampede.agent': agent})}}

    def snap(self, *records, seq=1):
        return {'channel': None, 'seq': seq, 'terminals': list(records)}

    def inbox(self):
        path = self.job_dir / 'inbox.log'
        return path.read_text().splitlines() if path.is_file() else []

    def sent(self):
        return [(p['state'], p['agent']) for p in self.posts]

    def feed(self, follower, *rows):
        for row in rows:
            follower.line(row)

    def test_a_snapshot_seeds_without_telling_anyone(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t1', 'working'), self.record('t3', 'working', 2), self.record('t4', 'idle', 1)))
        self.assertEqual((self.inbox(), self.posts), ([], []))

    def test_working_then_null_then_finished_is_dead_and_gone(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t3', 'working')), status('t3', None), finished('t3', 0))
        self.assertEqual(self.inbox(), ['GONE build-api exited exit 0'])
        self.assertEqual(self.sent(), [('dead', 'build-api')])
        self.assertEqual(self.posts[0]['last_state'], 'working')
        self.assertEqual(self.posts[0]['pane'], f'hc:{self.key}/t3')
        self.assertEqual(self.posts[0]['workspace'], self.key)
        self.assertEqual(self.posts[0]['source'], 'hc')
        self.assertIn('last lines of build-api', self.posts[0]['output_tail'])

    def test_blocked_then_finished_on_one_turn_is_two_notifications(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t4', 'working')), status('t4', 'blocked', kind='permission', msg='Approve deploy?'),
                  turn('t4', 1, 'blocked'), status('t4', None), finished('t4', None, 'killed', signal=1))
        self.assertEqual(self.inbox(), ['BLOCKED review-api permission', 'GONE review-api killed exit -'])
        self.assertEqual(self.sent(), [('blocked', 'review-api'), ('dead', 'review-api')])
        self.assertEqual((self.posts[0]['kind'], self.posts[0]['msg']), ('permission', 'Approve deploy?'))

    def test_a_normal_end_reaches_the_lead_but_not_the_bot(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t3', 'working')), status('t3', 'done'), turn('t3', 1, 'done'),
                  finished('t3', 0), status('t4', 'idle'), finished('t4', 0))
        self.assertEqual(self.inbox(), ['GONE build-api exited exit 0', 'GONE review-api exited exit 0'])
        self.assertEqual(self.sent(), [('done', 'build-api')])

    def test_killed_workers_with_no_hook_are_gone_once_each(self):
        _, f = self.follower()
        rows = [self.snap(self.record('t3', 'working'), self.record('t4', 'working')),
                status('t3', None), finished('t3', None, 'killed', signal=9), status('t4', None), finished('t4', None, 'killed', signal=9)]
        self.feed(f, *rows, *rows[1:])
        self.assertEqual(self.inbox(), ['GONE build-api killed exit -', 'GONE review-api killed exit -'])
        self.assertEqual(self.sent(), [('dead', 'build-api'), ('dead', 'review-api')])

    def test_the_lead_and_the_relay_never_write_to_the_lead(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t1', 'working'), self.record('t2')), status('t1', 'blocked', kind='question'),
                  status('t2', 'blocked'), finished('t2', 1), status('t1', None), finished('t1', 1))
        self.assertEqual(self.inbox(), [])
        self.assertEqual(self.sent(), [('blocked', 'lead-demo'), ('dead', 'lead-demo')])

    def test_a_wait_terminal_ends_with_waited(self):
        _, f = self.follower()
        created = ev('created', 't5', self.record('t5'))
        self.feed(f, self.snap(), created, finished('t5', 1))
        self.assertEqual(self.inbox(), ['WAITED wait-ci exit 1'])
        self.assertEqual(self.posts, [])

    def test_errors_and_turn_zero_blocks_fire_once_in_a_stream_and_in_a_first_snapshot(self):
        _, f = self.follower()
        rows = [self.snap(self.record('t3'), self.record('t4', 'idle', 2)),
                status('t3', 'blocked', kind='auth'), status('t4', 'error', msg='rate limited')]
        self.feed(f, *rows, *rows[1:])
        self.assertEqual(self.inbox(), ['BLOCKED build-api auth', 'ERROR review-api rate limited'])
        self.posts.clear()
        (self.job_dir / 'inbox.log').unlink()
        (self.job_dir / 'relay-state.json').unlink()
        _, f = self.follower()
        first = self.snap(self.record('t3', 'blocked', 0, kind='auth'), self.record('t4', 'error', 2, msg='rate limited'))
        self.feed(f, first, first)
        self.assertEqual(self.inbox(), ['BLOCKED build-api auth', 'ERROR review-api rate limited'])
        self.assertEqual(self.sent(), [('blocked', 'build-api'), ('error', 'review-api')])

    def test_a_new_episode_on_a_later_turn_after_a_gap_fires_once(self):
        for word, line in (('blocked', 'BLOCKED build-api permission'), ('error', 'ERROR build-api boom')):
            (self.job_dir / 'relay-state.json').unlink(missing_ok=True)
            (self.job_dir / 'inbox.log').unlink(missing_ok=True)
            _, f = self.follower()
            fields = {'kind': 'permission'} if word == 'blocked' else {'msg': 'boom'}
            self.feed(f, self.snap(self.record('t3', 'working', 2)), status('t3', word, **fields), turn('t3', 3, word))
            later = self.snap(self.record('t3', word, 4, **fields), seq=1)  # working and the same state again, while away
            self.feed(f, later, later)
            self.assertEqual(self.inbox(), [line, line])
            _, again = self.follower()  # restarted from relay-state.json
            self.feed(again, later)
            self.assertEqual(self.inbox(), [line, line])

    def test_a_death_and_a_wait_end_while_away_are_reported_once_after_reconnect(self):
        _, f = self.follower()
        self.feed(f, self.snap(self.record('t3', 'working', 1), self.record('t4', 'idle'), self.record('t5')))
        self.terminal('t3', state='finished', status=None, exit_code=None, reason='holder_lost')
        self.add_terminal('t5', name='wait-ci', state='finished', exit_code=0, reason='exited', status=None,
                          labels={'stampede.job': self.key, 'stampede.role': 'wait'})
        state = self.state()
        del state['terminals']['t4']  # its record is gone too
        (self.core / 'state.json').write_text(json.dumps(state))
        after = self.snap(seq=1)
        self.feed(f, after, after)
        self.assertEqual(sorted(self.inbox()), ['GONE build-api holder_lost exit -', 'LOST review-api', 'WAITED wait-ci exit 0'])
        self.assertEqual(sorted(self.sent()), [('dead', 'build-api'), ('dead', 'review-api')])

    def test_missed_reconciles_and_drops_older_events(self):
        _, f = self.follower()
        missed = {'jsonrpc': '2.0', 'method': 'missed', 'params': {'seq': 50, 'terminals': [self.record('t3', 'blocked', 1, kind='permission')]}}
        self.feed(f, self.snap(self.record('t3', 'working')), missed, status('t3', 'error', seq=49), status('t3', 'error', seq=51, msg='x'))
        self.assertEqual(self.inbox(), ['BLOCKED build-api permission', 'ERROR build-api x'])

    def run_follow(self, core, f, streams, alive=lambda: True, give_up=600):
        """follow() over the fake hc's event streams, one per connection, with a clock that sleep() moves."""
        self.shape(streams=streams)
        clock = [0.0]
        with mock.patch.object(core, 'alive', alive), mock.patch.object(core, 'GIVE_UP', give_up), \
                mock.patch.object(core, 'clock', lambda: clock[0]), \
                mock.patch.object(core, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s)):
            return f.follow(), clock[0]

    def test_eof_reconnects_to_a_new_core_generation(self):
        core, f = self.follower()
        first = [self.snap(self.record('t3', 'working'), seq=900), status('t3', 'blocked', seq=901, kind='permission')]
        second = [self.snap(self.record('t3', 'working', 1), seq=3), status('t3', None, seq=4), finished('t3', 2, seq=5)]
        third = [self.snap(seq=1)]
        code, _ = self.run_follow(core, f, [first, second, third], give_up=5)
        self.assertEqual(self.inbox()[:2], ['BLOCKED build-api permission', 'GONE build-api exited exit 2'])
        self.assertEqual(self.inbox()[-1], 'RELAY DOWN stream ended')
        self.assertEqual(code, 1)

    def test_a_core_that_stays_down_ends_in_relay_down(self):
        core, f = self.follower()
        code, waited = self.run_follow(core, f, [], alive=lambda: False)
        self.assertEqual(code, 1)
        self.assertEqual(self.inbox(), ['RELAY DOWN core not reachable'])
        self.assertEqual(self.sent(), [('relay_down', 'relay-' + self.key[3:])])
        self.assertGreaterEqual(waited, 600)
        self.assertLess(waited, 700)
        self.assertFalse((self.core / 'calls').exists(), 'never an hc command against a core that is down')

    def test_finish_or_start_failed_ends_it_even_on_a_busy_stream(self):
        for stamp in ('finished', 'start-failed'):
            (self.core / 'state.json').unlink(missing_ok=True)
            core, f = self.follower()
            busy = [self.snap(self.record('t3', 'working'))] + [status('t3', 'working' if n % 2 else 'idle', seq=n) for n in range(2, 200)]
            seen = []
            real = f.event

            def event(params, real=real):
                seen.append(params)
                if len(seen) == 3:
                    (self.job_dir / stamp).write_text('x\n')
                return real(params)
            f.event = event
            code, _ = self.run_follow(core, f, [busy])
            self.assertEqual(code, 0)
            self.assertLessEqual(len(seen), 4)
            (self.job_dir / stamp).unlink()

    def test_the_command_exits_at_once_for_a_job_that_never_started(self):
        self.shape(streams=[[self.snap(self.record('t3', 'working')), status('t3', 'blocked', kind='question')]])
        (self.job_dir / 'start-failed').write_text('x\n')
        result = subprocess.run([str(FOLLOWER), str(self.job_dir)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [], 'it exits before connecting when the job never started')


if __name__ == '__main__':
    unittest.main()
