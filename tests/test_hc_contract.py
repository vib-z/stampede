"""Herdr Core's API as stampede uses it: the committed `hc schema` snapshot holds everything the product calls, the
follower decides on every event type Core sends, and tests/fake_hc.py answers as that schema says. A bundled copy of
someone else's API drifts quietly; this is the test that says so."""
import importlib.machinery, importlib.util, json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import hc_contract  # noqa: E402

FAKE_HC = ROOT / 'tests/fake_hc.py'
PRODUCT = [ROOT / 'skills/herdr-fleet/scripts/fleet_job.py', ROOT / 'skills/grokbot-herdr/scripts/herdr-event-core',
           ROOT / 'skills/grokbot-herdr/scripts/herdr-event-sweep',
           ROOT / 'skills/grokbot-herdr/scripts/herdr-event-watchdog', ROOT / 'skills/herdr-fleet/scripts/core_native.py']


def follower():
    path = ROOT / 'skills/grokbot-herdr/scripts/herdr-event-core'
    spec = importlib.util.spec_from_loader('herdr_event_core', importlib.machinery.SourceFileLoader('herdr_event_core', str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.schema = hc_contract.snapshot()
        self.view = hc_contract.view(self.schema)

    def test_the_snapshot_holds_everything_stampede_uses(self):
        self.assertNotIn('missing:', json.dumps(self.view), 'the snapshot lacks a method, parameter, error kind or field stampede uses')

    def test_the_snapshot_is_the_version_its_name_says(self):
        self.assertIn(self.schema['info']['version'], hc_contract.SNAPSHOT.name)

    def test_every_hc_command_the_product_runs_is_in_the_contract(self):
        called = set()
        for path in PRODUCT:
            text = path.read_text()
            called |= set(re.findall(r"\bhc\('([a-z]+)'", text))  # hc('get', ...)
            called |= set(re.findall(r"or 'hc', '([a-z]+)'", text))  # [os.environ.get('HC') or 'hc', 'events', ...]
            called |= set(re.findall(r'"\$\{HC:-hc\}" ([a-z]+)', text))  # "${HC:-hc}" ls
            called |= {'kill', 'rm'} if "for verb in ('kill', 'rm')" in text else set()
        self.assertGreaterEqual(called, {'run', 'ls', 'get', 'send', 'wait', 'read', 'events', 'kill', 'rm'})
        self.assertEqual(called - set(hc_contract.USES), set(), 'a hc command the product runs is not in hc_contract.USES')

    def test_the_follower_decides_on_every_event_type_core_sends(self):
        core = follower()
        decided = set(core.EVENTS) | set(core.IGNORED)
        self.assertEqual(set(self.view['event types']) - decided, set(), 'an event type with no decision in herdr-event-core')
        self.assertFalse(set(core.EVENTS) & set(core.IGNORED))
        for kind in ('lost', 'restarted', 'keep', 'labels'):
            self.assertIn(kind, core.EVENTS)
        self.assertTrue(self.view['heartbeat'])

    def test_the_send_error_kinds_stampede_tells_apart_are_core_s(self):
        text = PRODUCT[0].read_text()
        self.assertIn("'cancelled'", text)
        self.assertIn('cancelled', self.view['send']['errors'])


class Fake(unittest.TestCase):
    """The fake answers each command the contract names, with fields and error kinds the schema has."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.schema = hc_contract.snapshot()
        self.methods = {m['name']: m for m in self.schema['methods']}

    def hc(self, *args, input=''):
        env = {k: v for k, v in os.environ.items() if k not in ('HC_SESSION', 'HC_SOCKET', 'HC_TERMINAL_ID')}
        return subprocess.run([sys.executable, str(FAKE_HC), *args], capture_output=True, text=True, input=input,
                              env={**env, 'FAKE_HC': str(self.home)})

    def state(self, **fields):
        path = self.home / 'state.json'
        state = {'next': 1, 'terminals': {}, **(json.loads(path.read_text()) if path.is_file() else {})}
        for address, change in fields.pop('terminals', {}).items():
            state['terminals'][address].update(change)
        path.write_text(json.dumps({**state, **fields}))

    def sent(self, address='t1'):
        return json.loads((self.home / 'state.json').read_text())['terminals'][address]['sent']

    def run_one(self):
        ran = self.hc('run', '--bg', '--no-parent', '--no-notify', '--name', 'w', '--cwd', '/tmp', '--label', 'a=b', '--json', '--', 'prog')
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return json.loads(ran.stdout)

    def test_the_fake_has_every_command_of_the_contract(self):
        self.run_one()
        calls = {'ls': ['ls'], 'get': ['get', 't1'], 'send': ['send', '--', 't1', 'x'], 'wait': ['wait', 't1'], 'read': ['read', 't1'],
                 'keep': ['keep', 't1'], 'label': ['label', 't1', 'k=v'], 'keys': ['keys', 't1', 'a'], 'events': ['events'],
                 'exec': ['exec', '--', '/usr/bin/env'], 'kill': ['kill', 't1'], 'rm': ['rm', 't1'], 'connect': ['connect']}
        self.assertEqual(set(calls) | {'run'}, set(hc_contract.USES))
        for command, argv in calls.items():
            done = self.hc(*argv, '--json')
            self.assertNotIn('the fake hc has no', done.stderr, command)
            self.assertEqual(done.returncode, 0, f'{command}: {done.stderr}')

    def test_the_fake_s_answers_hold_only_fields_the_schema_has(self):
        shown = self.run_one()
        extra = {'sent'}  # the fake's own record of what arrived
        self.assertEqual(set(shown) - hc_contract.fields(self.schema, self.methods['terminal.run']) - extra, set())
        self.assertEqual(set(json.loads(self.hc('get', 't1').stdout)) - hc_contract.fields(self.schema, self.methods['terminal.get']) - extra, set())
        sent = json.loads(self.hc('send', '--if', 'idle', '--', 't1', 'hello').stdout)
        self.assertEqual(set(sent) - hc_contract.fields(self.schema, self.methods['terminal.send']), set())
        self.assertIn('started', sent)
        self.assertEqual(set(json.loads(self.hc('read', 't1').stdout)) - hc_contract.fields(self.schema, self.methods['terminal.read']), set())
        listed = json.loads(self.hc('connect', input='{"jsonrpc":"2.0","id":1,"method":"terminal.list","params":{"all":true}}\n').stdout)
        self.assertEqual(set(listed['result']) - hc_contract.fields(self.schema, self.methods['terminal.list']), set())
        self.assertEqual(set(listed['result']['terminals'][0]) - hc_contract.fields(self.schema, self.methods['terminal.get']), set())

    def test_the_fake_s_error_kinds_are_the_schema_s(self):
        self.run_one()
        kinds = {e['data']['kind'] for e in self.methods['terminal.send'].get('errors', [])}
        for kind, shape in (('cancelled', {'send_error': {'t1': 'cancelled'}}), ('blocked', {'terminals': {'t1': {'status': {'state': 'blocked'}}}})):
            self.state(**shape)
            failed = self.hc('send', '--', 't1', 'x')
            self.assertEqual(json.loads(failed.stderr)['error']['kind'], kind)
            self.assertIn(kind, kinds)
            self.state(send_error={}, terminals={'t1': {'status': {'state': 'idle'}}})
        self.assertEqual(json.loads(self.hc('send', '--if', 'working', '--', 't1', 'x').stderr)['error']['kind'], 'status_mismatch')
        self.assertEqual(json.loads(self.hc('get', 't9').stderr)['error']['kind'], 'not_found')
        self.assertIn('not_found', {e['data']['kind'] for e in self.methods['terminal.get']['errors']})

    def test_a_person_s_draft_holds_a_send_and_is_never_sent_with_it(self):
        """Core 0.1.20: a send waits for a person's unsent draft; cleared or sent, the message goes in alone. The fake
        of before pasted every message after whatever was typed, which this fails."""
        self.run_one()
        self.state(terminals={'t1': {'person': {'draft': 'half a thought', 'then': 'clear'}}})
        self.assertEqual(self.hc('send', '--', 't1', 'the message').returncode, 0)
        self.assertEqual(self.sent(), ['the message'])
        self.state(terminals={'t1': {'person': {'draft': 'my own question', 'then': 'send'}}})
        self.hc('send', '--', 't1', 'the second')
        self.assertEqual(self.sent(), ['the message', 'my own question', 'the second'])

    def test_a_draft_left_past_the_limit_and_text_typed_with_keys_still_get_the_message_after_them(self):
        """Measured on hc 0.1.20: after draft_wait the send goes in after the draft; hc keys text is no person's draft."""
        self.run_one()
        self.state(terminals={'t1': {'person': {'draft': 'left alone ', 'then': 'stay', 'after': 0}}})  # the limit has passed
        self.hc('send', '--', 't1', 'the message')
        self.hc('keys', 't1', 'a', 'b')
        self.hc('send', '--', 't1', 'again')
        self.assertEqual(self.sent(), ['left alone the message', 'abagain'])

    def test_keep_and_label_change_the_terminal(self):
        self.run_one()
        self.hc('keep', 't1')
        self.hc('label', 't1', 'herdr.space=s1', 'a=')
        shown = json.loads(self.hc('get', 't1').stdout)
        self.assertTrue(shown['keep'])
        self.assertEqual(shown['labels'], {'herdr.space': 's1'})
        self.hc('keep', 't1', '--off')
        self.assertFalse(json.loads(self.hc('get', 't1').stdout)['keep'])


if __name__ == '__main__':
    unittest.main()
