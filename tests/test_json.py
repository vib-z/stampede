"""--json on every command an agent runs (docs/CLI-JSON.md). Each play runs a whole job on one backend through the real
stampede command against the fakes, the steps of tests/clients_run.py plus the commands they leave out (MORE), twice: once
plain and once with --json on every command that takes it. Each --json step must print one object and nothing else on
stdout, exit as the plain step did, carry its status, and name the facts the plain line names."""
import json, re, shutil, sys, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clients_run  # noqa: E402
from clients_run import Job, check_process_tree, SHA  # noqa: E402
from test_clients import CLIENTS, WORKERS, HANDED  # noqa: E402
from test_gates import FAKE_GH  # noqa: E402
sys.path.insert(0, str(clients_run.ROOT / 'skills/herdr-fleet/scripts'))
from stampede import cli as cli_, out as out_  # noqa: E402

PLAYS = [(client, backend, False) for client in ('herdr-chat', 'claude-code', 'grokbot') for backend in ('tui', 'core', 'native')]
PLAYS += [('claude-code', backend, True) for backend in ('tui', 'native')]  # a front door: wait, approve, approve-gate
FACTS = ('agent', 'address', 'parent', 'lead', 'id', 'sha', 'pr', 'outbox', 'path', 'pane', 'running', 'cap', 'queued')


def normal(text):
    """What differs between two runs of the same play: the play's folder, question and gate ids, session ids, the minute."""
    text = re.sub(r'/(plain|json)/', '/<run>/', str(text))
    text = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', text)
    text = re.sub(r'\b[0-9a-f]{12}\b', '<id>', text)
    return re.sub(r'\d{4}-\d\d-\d\d \d\d:\d\d', '<minute>', text)


class Play(Job):
    """A Job that keeps each step's argv, runs every stampede command with --json when json is set, and plays MORE."""

    def __init__(self, client, backend, door, root, json_=False):
        super().__init__(client, CLIENTS[client], backend, root, WORKERS, HANDED, door=door)
        self.json, self.argv = json_, {}
        (self.bin / 'gh').write_text(FAKE_GH)
        (self.bin / 'gh').chmod(0o755)
        self.gh = self.root / 'gh.json'
        self.gh.write_text(json.dumps({'head': SHA, 'merge_commit': 'c' * 40}))
        self.base.update(GH_STATE=str(self.gh), GH_LOG=str(self.root / 'gh.log'))

    def run(self, step, argv, env, host=None):
        argv = [str(a) for a in argv]
        stampede = argv[0] == str(clients_run.STAMPEDE) and argv[1] in cli_.JSON
        if stampede and self.json:
            argv.insert(2, '--json')
        self.argv[step] = argv if stampede else None
        code, out, err = super().run(step, argv, env, host)
        if stampede and self.json and out.strip():
            got = json.loads(out)
            if got.get('status') == 'GATE':  # the play reads the gate's id from the plain line
                out = f'GATE {got["id"]} \n'
        return code, out, err

    def play(self):
        try:
            if self.door:
                return self.play_door()
            for step in (self.start, self.workers, self.question, self.gate, self.tell, self.more, self.finish):
                step()
        except Exception:
            import traceback
            self.error = traceback.format_exc()
        return self

    def more(self):
        """The commands the cross-client play leaves out, each with a refusal."""
        job = self.job
        self.lead('tell nobody', 'tell', job, 'nobody', 'hi')
        self.lead('tell no text', 'tell', job)
        self.lead('cancel nothing', 'cancel', job, 'ffffffffffff')
        self.lead('ask gate no sha', 'ask', job, '--gate', 'merge it')
        self.lead('start bad name', 'start', job, 'Bad_Name', '--kind', 'claude', '--brief', job / 'nope.md',
                  *(('--pane', f'{self.WS}:p2') if self.backend == 'tui' else ()))
        self.lead('approve no plan', 'approve', job, '--by', 'owner')
        (job / 'plan.md').write_text('One worker writes hello.\n')
        self.front('approve', 'approve', job, '--by', 'owner')
        self.front('wait items', 'wait', job, '--timeout', '0')
        self.front('wait timeout', 'wait', job, '--timeout', '0')
        report = job / 'review.md'
        report.write_text(f'# review\n\nStatus: PASS\nReviewed: {SHA}\n')
        self.lead('merge bad sha', 'merge', job, '3', '--sha', 'abc', '--review', report)
        self.lead('merge no gate', 'merge', job, '3', '--sha', SHA, '--review', report)
        self.lead('merge', 'merge', job, '3', '--sha', SHA, '--review', report, '--gate', self.ident)
        self.front('new no ask', 'new', '--file', self.root / 'nope.md')
        if (self.client, self.backend) == ('claude-code', 'native'):  # outside Herdr, no flag: backend auto picks Core
            self.front('new auto', 'new', '--file', self.root / 'ask.md', '--cwd', self.repo, '--name', 'xd')
        if self.backend == 'native':
            self.lead('next', 'next', job)
            self.lead('snapshot', 'snapshot', job)
            self.front('reopen', 'reopen', job)
            self.front('close worker', 'close', job, 'build-claude')
            self.front('close nobody', 'close', job, 'nobody')
        else:
            self.lead('next refused', 'next', job)


def play_all(root, json_):
    plays = [Play(c, b, d, root / ('json' if json_ else 'plain'), json_) for c, b, d in PLAYS]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(Play.play, plays))
    return plays


class Json(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp()).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        check_process_tree(cls.root)
        with ThreadPoolExecutor(2) as pool:
            cls.plain, cls.json = pool.map(lambda j: play_all(cls.root, j), (False, True))

    def test_every_command_gives_one_object_with_the_plain_facts(self):
        seen = set()
        for plain, got in zip(self.plain, self.json):
            self.assertFalse(plain.error or got.error, plain.error or got.error)
            for step, argv in got.argv.items():
                if not argv or step not in plain.steps:
                    continue
                with self.subTest(play=(got.client, got.backend, got.door), step=step):
                    code, out, err = got.steps[step]
                    pcode, pout, perr = plain.steps[step]
                    obj = json.loads(out)  # one object, nothing else on stdout
                    seen.add((argv[1], got.backend))
                    self.assertEqual(code, pcode, (out, err, pout, perr))
                    self.assertEqual((obj['ok'], obj['command']), (code == 0, argv[1]))
                    self.assertIn('status', obj)
                    plain_text = normal(pout + perr + ' '.join(plain.argv[step]))  # a fact is in its line or in what was asked
                    if 'error' in obj:
                        self.assertEqual(normal(obj['error']), normal(perr.splitlines()[-1] if obj['retry'] is None and
                                                                      'usage:' in perr else perr.splitlines()[0]))
                        self.assertEqual(normal(obj['retry'] or ''), normal(perr.splitlines()[1] if obj['retry'] else ''))
                        self.assertNotIn(obj['error'], err, 'the refusal is in the object, not on stderr')
                    results = obj.get('results', [obj])
                    for result in results:
                        if result.get('status') and (argv[1], result['status']) not in (('new', 'STARTED'), ('wait', 'ITEM')):
                            self.assertRegex(pout, r'(^|\n)' + re.escape(result['status']) + r'\b', 'its status starts a plain line')
                        for key in FACTS:
                            if result.get(key) not in (None, '', []) and (key, result['status']) != ('path', 'ITEM'):
                                self.assertIn(normal(result[key]), plain_text, key)
                    if argv[1] in out_.LISTS:
                        self.assertIsInstance(obj['results'], list)
        for command in cli_.JSON:
            self.assertTrue(any(c == command for c, _ in seen), f'{command} --json was never run')
        for command in ('start', 'tell', 'ask', 'post', 'finish', 'approve', 'gate-ok', 'cancel', 'merge', 'wait'):
            for backend in ('tui', 'core', 'native'):
                if backend == 'core' and command == 'wait':
                    continue
                self.assertIn((command, backend), seen)

    def test_the_facts_a_status_names(self):
        """A few objects in full: the shape an agent reads."""
        native = next(p for p in self.json if (p.client, p.backend, p.door) == ('claude-code', 'native', False))
        new = json.loads(native.steps['new'][1])
        self.assertEqual({k: new[k] for k in ('ok', 'command', 'status', 'agent', 'lead', 'job')},
                         {'ok': True, 'command': 'new', 'status': 'STARTED', 'agent': 'lead-xc', 'lead': 'lead-xc', 'job': str(native.job)})
        self.assertTrue(new['address'])
        self.assertEqual(new['backend'], 'native')
        auto = json.loads(native.steps['new auto'][1])
        self.assertEqual((auto['status'], auto['backend'], auto['lead']), ('STARTED', 'native', 'lead-xd'))
        self.assertIn('on Herdr Core (backend auto: not inside a Herdr pane)', auto['notes'])
        started = json.loads(native.steps['start claude'][1])
        self.assertEqual({k: started[k] for k in ('status', 'agent', 'kind', 'model', 'effort')},
                         {'status': 'STARTED', 'agent': 'build-claude', 'kind': 'claude', 'model': 'claude-opus-5-5', 'effort': 'medium'})  # roles.default
        self.assertEqual(json.loads(native.steps['start program'][1])['kind'], 'program')
        for play in self.json:
            if not play.door:
                self.assertEqual(json.loads(play.steps['new'][1])['backend'], {'core': 'core'}.get(play.backend, play.backend))
        gate = json.loads(native.steps['gate'][1])
        self.assertEqual((gate['status'], gate['sha'], gate['pr'], gate['kind']), ('GATE', SHA, 3, 'merge'))
        self.assertRegex(gate['id'], r'^[0-9a-f]{12}$')
        merged = json.loads(native.steps['merge'][1])
        self.assertEqual((merged['status'], merged['pr'], merged['sha'], merged['merge_commit']), ('MERGED', 3, SHA, 'c' * 40))
        refused = json.loads(native.steps['merge no gate'][1])
        self.assertEqual((refused['ok'], refused['status']), (False, None))
        self.assertTrue(refused['error'].startswith('stampede merge: the merge gate is on'))
        self.assertTrue(refused['retry'].startswith('stampede ask '))
        self.assertEqual(native.steps['merge no gate'][0], 2)
        usage = json.loads(native.steps['tell no text'][1])
        self.assertIn('the following arguments are required', usage['error'])
        self.assertEqual(json.loads(native.steps['wait timeout'][1])['results'][0]['status'], 'TIMEOUT')
        nxt = json.loads(native.steps['next'][1])
        self.assertEqual(nxt['status'], 'NOTHING QUEUED')
        tui = next(p for p in self.json if (p.client, p.backend, p.door) == ('claude-code', 'tui', False))
        items = json.loads(tui.steps['wait items'][1])['results']
        self.assertEqual([(i['status'], i['outbox'], i['kind']) for i in items], [('ITEM', '001', 'post')])
        self.assertIn('PLAN READY', items[0]['text'])


if __name__ == '__main__':
    unittest.main()
