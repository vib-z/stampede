"""--json on every command an agent runs (docs/CLI-JSON.md). Each play runs a whole job on one backend through the real
stampede command against the fakes, the steps of tests/clients_run.py plus the commands they leave out (MORE), twice: once
plain and once with --json on every command that takes it. Each --json step must print one object and nothing else on
stdout, exit as the plain step did, carry its status, and name the facts the plain line names."""
import ast, json, os, re, shutil, subprocess, sys, tempfile, threading, time, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clients_run  # noqa: E402
from clients_run import Job, check_process_tree, SHA  # noqa: E402
from test_clients import CLIENTS, WORKERS, HANDED  # noqa: E402
from test_gates import FAKE_GH  # noqa: E402
sys.path.insert(0, str(clients_run.ROOT / 'skills/herdr-fleet/scripts'))
from stampede import cli as cli_, out as out_, owner as owner_  # noqa: E402

PLAYS = [(client, backend, False) for client in ('herdr-chat', 'claude-code', 'grokbot') for backend in ('tui', 'core', 'native')]
PLAYS += [('claude-code', backend, True) for backend in ('tui', 'native')]  # a front door: wait, approve, approve-gate
FACTS = ('agent', 'address', 'parent', 'lead', 'id', 'sha', 'pr', 'outbox', 'path', 'pane', 'running', 'cap', 'queued')
DOC = (clients_run.ROOT / 'docs/CLI-JSON.md').read_text()


def rows(heading):
    """The cells of the table under '## <heading>' in docs/CLI-JSON.md, header and rule left out."""
    part = DOC.split('## ' + heading + '\n', 1)[1].split('\n## ', 1)[0]
    return [[c.strip() for c in line.strip('|').split('|')] for line in part.splitlines() if line.startswith('| `')]


def documented():
    """{command: statuses} from Per command: each backticked status word, None for null."""
    found = {}
    for command, statuses, _ in rows('Per command'):
        found.setdefault(command.strip('`').split()[0], set()).update(
            set(re.findall(r'`([A-Z][A-Z_ ]*[A-Z_])`', statuses)) | ({None} if 'null' in statuses else set()))
    return found


def always():
    """{(command, status or '*' or None): facts} from Always present, and the facts that may be null."""
    table = {}
    for command, status, facts in rows('Always present'):
        status = status.strip('`')
        table[(command.strip('`'), None if status == 'null' else status)] = re.findall(r'`([a-z_]+)`', facts)
    nullable = re.findall(r'`([a-z_]+)`', DOC.split('Null allowed:', 1)[1].split(';', 1)[0])
    return table, set(nullable)


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
            self.lead('start own flag', 'start', job, 'prog-own', '--', 'sleep', '60', '--json')  # plain: no flag; --json: after start
            self.lead('next', 'next', job)
            if self.json:  # a queued start that is no request: next crashes, and still prints one object
                (job / 'queue').mkdir(exist_ok=True)
                (job / 'queue' / '0001-bad.json').write_text('{"name": "bad"}')
                self.lead('next crash', 'next', job)
                (job / 'queue' / '0001-bad.json').unlink()
            self.lead('snapshot', 'snapshot', job)
            self.front('reopen', 'reopen', job)
            self.front('close worker', 'close', job, 'build-claude')
            self.front('close nobody', 'close', job, 'nobody')
            if self.json:  # the flag before the subcommand; the program keeps its own --json (last: it changes the tree)
                self.lead('start flag first', '--json', 'start', job, 'prog-first', '--', 'sleep', '60', '--json')
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
                    for line in pout.splitlines():  # a result line that names an address carries it as a fact
                        named = re.match(r'(SUBMITTED|STARTED|LIVE|CLOSED) (\S+) \((\S+)\)$', line)
                        if named:
                            self.assertIn(normal(named[3]), [normal(r.get('address') or r.get('pane')) for r in results], line)
                    if 'error' not in obj:
                        self.check_always(argv[1], obj)
        for command in cli_.JSON:
            self.assertTrue(any(c == command for c, _ in seen), f'{command} --json was never run')
        for command in ('start', 'tell', 'ask', 'post', 'finish', 'approve', 'gate-ok', 'cancel', 'merge', 'wait'):
            for backend in ('tui', 'core', 'native'):
                if backend == 'core' and command == 'wait':
                    continue
                self.assertIn((command, backend), seen)

    def check_always(self, command, obj):
        """Every fact the Always present table names for this command and status is in the object, and not null
        unless the table allows it."""
        table, nullable = always()
        checks = [(obj, table.get((command, '*'), []) + table.get((command, obj['status']), []))]
        if command in out_.LISTS:
            checks += [(r, table.get((command, r['status']), [])) for r in obj['results']]
        for where, facts in checks:
            for key in facts:
                self.assertIn(key, where, (command, where.get('status')))
                if key not in nullable:
                    self.assertIsNotNone(where[key], (command, where.get('status'), key))

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
        self.assertTrue(any(n.startswith('on Herdr Core (backend auto: not inside a Herdr pane), repo ') for n in auto['notes']), auto['notes'])
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
        plain_native = next(p for p in self.plain if (p.client, p.backend, p.door) == ('claude-code', 'native', False))
        self.assertTrue(plain_native.steps['start own flag'][1].startswith('STARTED prog-own'))
        for play, agent, step in ((plain_native, 'prog-own', 'start own flag'), (native, 'prog-own', 'start own flag'),
                                  (native, 'prog-first', 'start flag first')):
            run = next(r for r in play.calls('run') if play.labels(r).get('stampede.agent') == agent)
            self.assertEqual(play.program(run), ['sleep', '60', '--json'], (step, 'the program and its own flag arrive unchanged'))
            if play is native:
                got = json.loads(play.steps[step][1])
                self.assertEqual((got['status'], got['agent'], got['kind']), ('STARTED', agent, 'program'), step)
        code, out, err = native.steps['next crash']
        self.assertEqual((code, json.loads(out)['ok'], json.loads(out)['error'].split(':')[0]), (1, False, 'KeyError'))
        self.assertIn('Traceback', err)
        nxt = json.loads(native.steps['next'][1])
        self.assertEqual(nxt['status'], 'NOTHING QUEUED')
        tui = next(p for p in self.json if (p.client, p.backend, p.door) == ('claude-code', 'tui', False))
        items = json.loads(tui.steps['wait items'][1])['results']
        self.assertEqual([(i['status'], i['outbox'], i['kind']) for i in items], [('ITEM', '001', 'post')])
        self.assertIn('PLAN READY', items[0]['text'])


ENTRIES = {'new': ('cli.new',), 'start': ('cli.start',), 'tell': ('owner.tell',), 'ask': ('owner.ask', 'owner.ask_gate'),
           'post': ('owner.post',), 'wait': ('owner.wait',), 'finish': ('owner.finish',), 'next': ('native.next_',),
           'snapshot': ('native.snapshot',), 'reopen': ('native.reopen',), 'close': ('native.close',), 'approve': ('owner.approve',),
           'approve-gate': ('owner.approve_gate',), 'gate-ok': ('owner.gate_ok',), 'cancel': ('owner.cancel',),
           'merge': ('gates.merge',)}  # where run() sends each command
QUIET = {('merge', 'APPROVED')}  # merge runs gate-ok with stdout pointed elsewhere: never a result


def statuses():
    """{command: every status its code can print}: each out.emit status, and SUBMITTED and FAILED for out.said, in every
    function the command's entry can reach through the package (a reference to a function counts as a call)."""
    calls, emits = {}, {}
    for path in (clients_run.ROOT / 'skills/herdr-fleet/scripts/stampede').glob('*.py'):
        mod, tree = path.stem, ast.parse(path.read_text())
        alias = {a.asname or a.name: a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1 for a in n.names}
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            name = mod + '.' + fn.name
            calls[name], emits[name] = set(), set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias:
                    calls[name].add(alias[n.value.id] + '.' + n.attr)
                elif isinstance(n, ast.Name):
                    calls[name].add(mod + '.' + n.id)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                        and alias.get(n.func.value.id) == 'out' and n.func.attr in ('emit', 'said'):
                    first = n.args[0]
                    if n.func.attr == 'said':
                        emits[name] |= {'SUBMITTED', 'FAILED'}
                    else:
                        emits[name].add(first.value if isinstance(first, ast.Constant) else '<computed>')
    found = {}
    for command, entries in ENTRIES.items():
        todo, seen = list(entries), set()
        while todo:
            f = todo.pop()
            if f in calls and f not in seen:
                seen.add(f)
                todo += calls[f]
        found[command] = {s for f in seen for s in emits[f]} - {s for c, s in QUIET if c == command}
    return found


class Schema(unittest.TestCase):
    def test_every_status_the_code_can_print_is_in_the_schema(self):
        code, docs = statuses(), documented()
        self.assertEqual(set(code), set(cli_.JSON))
        for command, found in code.items():
            self.assertNotIn('<computed>', found, f'{command}: a status out.emit is given must be a literal')
            self.assertFalse(found - docs[command], f'{command} can print these, missing from docs/CLI-JSON.md')
        self.assertIn('DROPPED', code['reopen'])

    def test_a_line_from_another_program_carries_the_same_facts(self):
        cases = {'SUBMITTED build-codex (t4)': {'status': 'SUBMITTED', 'agent': 'build-codex', 'address': 't4'},
                 'SUBMITTED w9:p2 (pressed Enter again: the first was dropped)': {'status': 'SUBMITTED', 'agent': 'w9:p2', 'address': None},
                 'SUBMITTED lead-x': {'status': 'SUBMITTED', 'agent': 'lead-x', 'address': None},
                 'FAILED build-codex (it is working)': {'status': 'FAILED', 'agent': 'build-codex', 'reason': 'it is working'},
                 'FAILED w9:p2 focused: the owner is in that pane; retry later':
                     {'status': 'FAILED', 'agent': 'w9:p2', 'reason': 'focused: the owner is in that pane; retry later'},
                 'FAILED a (b (c) d)': {'status': 'FAILED', 'agent': 'a', 'reason': 'b (c) d'}}  # to the last )
        for line, want in cases.items():
            code, out, _ = call(['post', '--json'], lambda: out_.said(line + '\n', end='') or 0)
            self.assertEqual({k: out.get(k) for k in want}, want, line)

    def test_a_failure_s_reason_comes_from_the_code_that_knows_it(self):
        """send_core's FAILED line: the reason a slash command gets holds parentheses, and the object has it whole."""
        why = 'a slash command needs typed keys, which Core cannot guard: when hc get t4 shows idle, run hc keys t4 / r space ( a l l ) enter'
        line = out_.Line(f'FAILED build-codex ({why})', agent='build-codex', reason=why)
        code, out, _ = call(['tell', '--json'], lambda: out_.said(line) or 0)
        self.assertEqual((out['status'], out['agent'], out['reason']), ('FAILED', 'build-codex', why))
        self.assertEqual(str(line), f'FAILED build-codex ({why})')  # the plain line is the same text
        code, out, _ = call(['tell', '--json'], lambda: out_.said(out_.Line('FAILED a (as printed)', agent='a', reason='as known')) or 0)
        self.assertEqual(out['reason'], 'as known', 'a Line\'s own facts, never a parse of its text')


def call(argv, body=None):
    """cli.main(argv) in this process, or out.as_json(argv[0], body): (exit code, the object, stderr), fds 1 and 2 caught."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        sys.stdout.flush(), sys.stderr.flush()
        saved = os.dup(1), os.dup(2)
        os.dup2(out.fileno(), 1), os.dup2(err.fileno(), 2)
        try:
            code = cli_.main(argv) if body is None else out_.as_json(argv[0], body)
        finally:
            sys.stdout.flush(), sys.stderr.flush()
            os.dup2(saved[0], 1), os.dup2(saved[1], 2)
            os.close(saved[0]), os.close(saved[1])
        out.seek(0), err.seek(0)
        text = out.read().decode()
        return code, (json.loads(text) if text.strip() else text), err.read().decode()


class Calls(unittest.TestCase):
    """--json at its edges: where the flag stands, a crash or an interrupt, and calls one after another in one process."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.job = self.root / 'job'
        self.job.mkdir()
        (self.job / 'lead').write_text('lead-x\n')
        (self.job / 'ask.md').write_text('ask\n')
        env = {'HOME': str(self.root), 'HERDR_EVENTS_DIR': str(self.root / 'events'), 'FLEET_JOBS_ROOT': str(self.root),
               'STAMPEDE_NO_UPDATE_CHECK': '1'}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        for name in ('HERDR_EVENTS_OWNER', 'HERDR_WORKSPACE_ID', 'HERDR_ENV', 'HC_TERMINAL_ID', 'XDG_CONFIG_HOME'):
            os.environ.pop(name, None)

    def stampede(self, *argv):
        done = subprocess.run([str(clients_run.STAMPEDE), *map(str, argv)], capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout, done.stderr

    def test_the_flag_before_or_after_the_command_and_anywhere_in_its_arguments(self):
        for argv in (('--json', 'post', self.job, 'hi'), ('post', '--json', self.job, 'hi'), ('post', self.job, '--json', 'hi'),
                     ('post', self.job, 'hi', '--json'), ('--json', 'post', self.job, 'hi', '--json')):
            code, out, err = self.stampede(*argv)
            got = json.loads(out)
            self.assertEqual((code, got['command'], got['status'], err), (0, 'post', 'POSTED', ''), argv)
            self.assertNotIn('--json', got.get('notes', []))
        for argv in (('--json', 'tell'), ('tell', '--json'), ('--json', 'tell', self.job)):  # a usage error: one object, exit 2
            code, out, err = self.stampede(*argv)
            got = json.loads(out)
            self.assertEqual((code, got['ok'], err), (2, False, ''), argv)
            self.assertIn('the following arguments are required', got['error'])
        code, out, err = self.stampede('start', self.job, 'watch-ci', '--', 'sleep', '1', '--json')  # the program's flag
        self.assertEqual((code, out), (2, ''))  # plain: argparse's usage error on stderr
        self.assertIn('start: error: the following arguments are required', err)  # argparse names the prog its own way on 3.9
        attached = self.root / 'plan.md'
        attached.write_text('plan\n')
        for argv in (('ask', self.job, '--option', '--json', 'yes', 'Keep it?'), ('post', self.job, '--file', '--json', attached, 'hi'),
                     ('ask', self.job, '--option', 'a', '--option', '--json', 'Q'), ('post', '--json', self.job, '--file')):
            before = sorted(self.job.rglob('*'))
            code, out, err = self.stampede(*argv)  # argparse refuses an option whose value is --json; nothing is asked or posted
            got = json.loads(out)
            self.assertEqual((code, got['ok'], err), (2, False, ''), argv)
            self.assertIn('expected one argument', got['error'])
            self.assertEqual(sorted(self.job.rglob('*')), before, argv)
        code, out, err = self.stampede('post', self.job, '--', '--json', 'is', 'a', 'word')  # after --, the message's
        self.assertEqual((code, out.split()[0]), (0, 'POSTED'), err)
        self.assertIn('--json is a word', max((self.job / 'outbox').glob('*.md')).read_text())
        code, out, err = self.stampede('--json', 'config', 'show', '--job', self.job)  # the top level's flag reaches config show
        self.assertEqual((code, sorted(json.loads(out))[:2]), (0, ['environment', 'files']), err)

    def test_a_crash_or_an_interrupt_still_ends_in_one_object(self):
        def raises(error):
            def post(*args):
                raise error
            return post

        def in_finally(*args):
            try:
                return 0
            finally:
                raise RuntimeError('raised in a finally')
        cases = [(raises(RuntimeError('boom')), 1, 'RuntimeError: boom'), (raises(KeyError('name')), 1, "KeyError: 'name'"),
                 (in_finally, 1, 'RuntimeError: raised in a finally'),
                 (raises(KeyboardInterrupt()), 130, 'KeyboardInterrupt: interrupted'),
                 (raises(SystemExit('stopped here')), 1, 'stopped here')]  # Python's own exit 1 for a SystemExit with text
        for post, code, error in cases:
            with mock.patch.object(owner_, 'post', post):
                got_code, got, err = call(['post', str(self.job), 'hi', '--json'])
            self.assertEqual((got_code, got['ok'], got['command'], got['status']), (code, False, 'post', None), error)
            self.assertEqual((got['error'], got['retry']), (error, None))
            if error.startswith('RuntimeError') or error.startswith('KeyError'):
                self.assertIn('Traceback', err)
        self.assertIsNone(out_.RUN)

    def test_nothing_of_one_call_reaches_the_next(self):
        missing = self.root / 'nope'
        sequences = [
            (['tell', str(missing), 'lead', 'hi', '--json'], ['post', str(self.job), 'hi', '--json']),  # a refusal, then a success
            (['post', str(self.job), 'hi', '--json'], ['tell', '--help', '--json']),  # a success, then --help
            (['post', str(self.job), 'hi', '--json'], ['tell', '--json']),  # a success, then a usage error
        ]
        for first, second in sequences:
            call(first)
            code, got, _ = call(second)
            fresh = (code, got['command'])
            if second[1] == '--help':
                self.assertEqual((code, got['ok'], got['status']), (0, True, None))
                self.assertFalse({'error', 'job', 'agent', 'outbox'} & set(got), got)
            elif second[0] == 'post':
                self.assertEqual((code, got['status']), (0, 'POSTED'))
                self.assertNotIn('error', got)
            else:
                self.assertEqual((code, got['ok'], got['status']), (2, False, None))
                self.assertFalse({'outbox', 'path', 'job'} & set(got), got)
            self.assertEqual(fresh[1], second[0] if second[0] != '--json' else second[1])
        with mock.patch.object(owner_, 'post', side_effect=RuntimeError('boom')):  # an exception, then a success
            call(['post', str(self.job), 'hi', '--json'])
        code, got, _ = call(['post', str(self.job), 'again', '--json'])
        self.assertEqual((code, got['status']), (0, 'POSTED'))
        self.assertNotIn('error', got)
        self.assertIsNone(out_.RUN)

    def test_two_threads_at_once_each_get_their_own_object(self):
        jobs = [self.job, self.root / 'job2']
        jobs[1].mkdir()
        (jobs[1] / 'lead').write_text('lead-y\n')
        (jobs[1] / 'ask.md').write_text('ask\n')
        real_post, codes = owner_.post, {}

        def slow_post(*args):
            time.sleep(0.3)  # both calls overlap
            return real_post(*args)

        def one(job):
            codes[str(job)] = cli_.main(['post', str(job), 'hi from ' + job.name, '--json'])
        stdout, fd = sys.stdout, os.fstat(1).st_ino
        with tempfile.TemporaryFile() as out, mock.patch.object(owner_, 'post', slow_post):
            saved = os.dup(1)
            os.dup2(out.fileno(), 1)
            try:
                threads = [threading.Thread(target=one, args=(job,)) for job in jobs]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
            finally:
                os.dup2(saved, 1)
                os.close(saved)
            out.seek(0)
            objects = [json.loads(line) for line in out.read().decode().splitlines()]
        self.assertEqual(sorted(o['job'] for o in objects), sorted(str(j) for j in jobs))
        for o in objects:
            self.assertEqual((o['status'], o['path']), ('POSTED', o['job'] + '/outbox/001.md'))
            self.assertNotIn('results', o)
        self.assertEqual(set(codes.values()), {0})
        self.assertIs(sys.stdout, stdout)
        self.assertEqual(os.fstat(1).st_ino, fd)

    def test_a_failure_while_setting_up_leaves_nothing_behind(self):
        broken = open(os.devnull, 'w')
        broken.close()
        with mock.patch.object(sys, 'stdout', broken):
            with self.assertRaises(ValueError):  # the first flush, on a closed stdout
                cli_.main(['post', str(self.job), 'hi', '--json'])
        self.assertIsNone(out_.RUN)
        self.assertFalse(out_.LOCK.locked())
        code, text, err = call(['tell', str(self.root / 'nope'), 'lead', 'hi'])  # stdout repaired: a plain refusal as usual
        self.assertEqual((code, text), (2, ''))
        self.assertIn('stampede tell: job folder not found', err)
        code, got, _ = call(['post', str(self.job), 'hi', '--json'])
        self.assertEqual((code, got['status']), (0, 'POSTED'))

    def test_a_help_flag_before_the_command_runs_nothing(self):
        """-h or --help before the subcommand is the top-level help, as without --json, and nothing is dispatched: not
        update, not start's program, not the unknown-command check."""
        top = self.stampede('--help')
        self.assertEqual(top[0], 0)
        for argv in (('--help', 'update'), ('-h', 'update'), ('--help', 'start', self.job, 'x', '--', 'echo'), ('-h', 'nosuch'),
                     ('--help', 'tell', self.job, 'lead', 'hi')):
            self.assertEqual(self.stampede(*argv), top, argv)
        for argv in (('--json', '--help', 'update'), ('--help', '--json', 'tell'), ('--json', '-h', 'start', self.job, 'x', '--', 'echo')):
            code, out, err = self.stampede(*argv)
            got = json.loads(out)
            self.assertEqual((code, got['ok'], got['command'], err), (0, True, None, ''), argv)
            self.assertEqual('\n'.join(got['notes']), '\n'.join(l for l in top[1].splitlines() if l.strip()), argv)
        for argv in (['--help', 'update'], ['-h', 'update'], ['--json', '--help', 'update'], ['--help', 'start', str(self.job), 'x', '--', 'echo']):
            with mock.patch.object(cli_.subprocess, 'run') as ran, mock.patch.object(cli_, 'run') as dispatched:
                try:
                    call(argv)
                except SystemExit as stop:
                    self.assertEqual(stop.code, 0)
            self.assertFalse(ran.called or dispatched.called, argv)
        self.assertFalse((self.job / 'outbox').exists() or (self.job / 'inbox').exists())

    def test_a_reader_that_goes_away_leaves_no_traceback(self):
        done = subprocess.run(['bash', '-c', '"$0" post "$1" hi --json | true; echo "exit ${PIPESTATUS[0]}" >&2',
                               str(clients_run.STAMPEDE), str(self.job)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.stderr.strip().splitlines()[-1], 'exit 0')
        self.assertNotIn('Traceback', done.stderr)


if __name__ == '__main__':
    unittest.main()
