"""The cross-client suite: stampede driven from every client it claims, with like-for-like outcomes (docs/CLIENTS.md).

CLIENTS is the one list the suite runs over, and WORKERS the one list of worker kinds. A front door added to README's
table, or a client added here, fails ClientsInSync until both docs/CLIENTS.md and this table name it. Outcomes plays
one job per client and backend against the repo's fakes (tests/clients_run.py) and asserts each outcome's command
contract, O1 to O9, as subtests named "<client>/<backend> <outcome>". A gap between clients is a finding: a test
marked as an expected failure, named after it. Stdlib only; nothing leaves the machine.
"""
import re, shutil, sys, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

# name: README front-door row (None: not a README front door yet), where it runs (inside Herdr, outside it, or over ssh),
# the backends it can start. A bot also names its slug (its route, and the owner of its jobs) and how it makes a TUI job
# its own: the workspace's owner tag (grokbot-herdr, Step 3) or HERDR_EVENTS_OWNER at new. On Core there is no workspace
# to tag, so every bot sets HERDR_EVENTS_OWNER there.
CLIENTS = {
    'herdr-chat': {'readme': 'a chat in Herdr', 'where': 'inside', 'backends': ('tui', 'core')},
    'claude-code': {'readme': 'Claude desktop or the Claude app', 'where': 'outside', 'backends': ('tui', 'core')},
    'codex': {'readme': 'Codex desktop or the ChatGPT app', 'where': 'outside', 'backends': ('tui', 'core')},
    'cursor': {'readme': 'Cursor', 'where': 'outside', 'backends': ('tui', 'core')},
    'hermes': {'readme': None, 'where': 'outside', 'backends': ('tui', 'core')},
    'grokbot': {'readme': 'Grok Bot', 'where': 'ssh', 'backends': ('tui', 'core'), 'bot': 'grokbot', 'owner_from': 'tag'},
    'other-bot': {'readme': 'any other bot', 'where': 'ssh', 'backends': ('tui', 'core'), 'bot': 'other-bot', 'owner_from': 'env'},
    'remote-computer': {'readme': 'a whole remote computer', 'where': 'inside', 'backends': ('tui', 'core')},
}
WORKERS = {'tui': ('claude', 'codex', 'cursor'), 'core': ('claude', 'codex')}  # the one worker registry: what start takes
KINDS = tuple(dict.fromkeys(kind for kinds in WORKERS.values() for kind in kinds))  # O3 starts each on every backend
REFUSED = {'cursor': 'Cursor reports no OSC 7501 status'}  # why a backend that does not take a kind refuses it
OUTCOMES = {
    'O1': 'health', 'O2': 'start', 'O3': 'workers', 'O4': 'question', 'O5': 'gate',
    'O6': 'tell', 'O7': 'finish', 'O8': 'reopen-safe', 'O9': 'no-poll',
}

from clients_run import ANSWER, BOT_SCRIPTS, GATE, LEAD_MODEL, OTHER_SHA, QUESTION, SHA, STAMPEDE, SUMMARY, Job, check_process_tree  # noqa: E402  (after CLIENTS: it imports fleet_job)
from test_core import FAKE_HC  # noqa: E402
from test_fleet_job import fake_herdr, valid_brief  # noqa: E402
import test_doctor  # noqa: E402

SAY_SO = "an agent's own say-so never counts"


def table_rows(text, heading):
    """First cells of the first table under a heading, with bold and parentheses removed."""
    section = text.split('\n' + heading + '\n', 1)[1].split('\n## ', 1)[0]
    rows = [line for line in section.splitlines() if line.startswith('|')][2:]
    return [re.sub(r'\*\*|\s*\(.*?\)', '', row.split('|')[1]).strip() for row in rows]


class ClientsInSync(unittest.TestCase):
    def test_every_readme_front_door_is_a_client(self):
        named = {c['readme'] for c in CLIENTS.values()}
        for door in table_rows((ROOT / 'README.md').read_text(), '## Front doors'):
            self.assertIn(door, named, f'README front door {door!r} has no CLIENTS row in tests/test_clients.py')

    def test_every_client_has_a_docs_row(self):
        rows = table_rows((ROOT / 'docs/CLIENTS.md').read_text(), '## Clients')
        self.assertEqual(sorted(r.strip('`') for r in rows), sorted(CLIENTS))

    def test_every_outcome_is_documented(self):
        text = (ROOT / 'docs/CLIENTS.md').read_text()
        for oid, name in OUTCOMES.items():
            self.assertIn(f'**{oid} {name}**', text)

    def test_every_row_is_complete(self):
        for name, row in CLIENTS.items():
            self.assertIn(row['where'], ('inside', 'outside', 'ssh'), name)
            self.assertTrue(set(row['backends']) <= set(WORKERS), name)
            self.assertTrue(row['backends'], f'{name}: no backend, so no job would test it')
            self.assertEqual(len(set(row['backends'])), len(row['backends']), f'{name}: a backend twice')
            self.assertEqual(row['where'] == 'ssh', bool(row.get('bot')), f'{name}: a client over ssh is a bot, and only it')
            if row.get('bot'):
                self.assertIn(row['owner_from'], ('tag', 'env'), name)

    def test_every_kind_a_backend_does_not_take_says_why(self):
        for backend, kinds in WORKERS.items():
            for kind in set(KINDS) - set(kinds):
                self.assertIn(kind, REFUSED, f'{backend} does not take {kind}: REFUSED needs the reason start gives')


class Outcomes(unittest.TestCase):
    """Every client, on every backend it claims, passes the command contract of O1 to O9 (O9 for bots) against the fakes.
    No agent runs: the agents' own work (plan.md, the worker's file, the commit) is for the live runs (docs/CLIENTS.md)."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp()).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        check_process_tree(cls.root)  # fails the class at once, with why, where ps is denied
        cls.doctor = test_doctor.Doctor('test_clean_core_is_read_only_and_never_calls_launchctl')
        cls.addClassCleanup(cls.doctor.doCleanups)
        cls.doctor.setUp()  # an installed scratch HOME with a fake herdr, launchctl and df
        cls.doctor.fake('claude', 'echo "2.1.312 (Claude Code)"')  # never a real agent CLI
        cls.doctor.fake('codex', 'echo "--no-daemon"')
        cls.jobs = [Job(name, row, backend, cls.root, WORKERS) for name, row in CLIENTS.items() for backend in row['backends']]
        with ThreadPoolExecutor(8) as pool:  # each job has its own folders, fakes and environment
            cls.health = dict(zip([(j.client, j.backend) for j in cls.jobs], pool.map(cls.health_check, cls.jobs)))
            cls.reference = dict(zip(('tui', 'tui-bot', 'core'), pool.map(lambda f: cls.run_doctor(f, {}), ('tui', 'tui-bot', 'core'))))
            list(pool.map(Job.play, cls.jobs))

    @classmethod
    def doctor_flags(cls, job):
        return 'core' if job.backend == 'core' else 'tui-bot' if job.bot else 'tui'

    @classmethod
    def run_doctor(cls, flags, env):
        """herdr-doctor as each guide runs it: --core on Core, --relay for a bot on the TUI. The fake hc answers --version;
        its socket is a scratch path, so no real core is asked."""
        argv = {'tui': (), 'tui-bot': ('--relay',), 'core': ('--core',)}[flags]
        core = {'HC': str(FAKE_HC), 'FAKE_HC': str(cls.root / 'doctor-core'), 'HC_SOCKET': str(cls.root / 'none.sock')}
        result = cls.doctor.doctor(*argv, **core, **env)
        return result.returncode, result.stdout

    @classmethod
    def health_check(cls, job):
        ids = {k: v for k, v in job.client_env().items() if k.startswith('HERDR_') and k not in job.base}
        return cls.run_doctor(cls.doctor_flags(job), ids)

    def test_every_declared_pair_played_to_the_end(self):
        declared = sorted((name, backend) for name, row in CLIENTS.items() for backend in row['backends'])
        played = sorted((job.client, job.backend) for job in self.jobs if not job.error and 'finish again' in job.steps)
        self.assertEqual(played, declared)

    # each outcome, for every client and backend
    def outcome(self, oid, check):
        for job in self.jobs:
            with self.subTest(f'{job.client}/{job.backend} {oid}'):
                check(job)

    def step(self, job, name):
        if name not in job.steps:
            self.fail(f'{name} never ran: {job.error or "an earlier step stopped it"}')
        return job.steps[name]

    def ok(self, job, name, *says):
        code, out, err = self.step(job, name)
        self.assertEqual(code, 0, f'{name}: {out}{err}')
        for text in says:
            self.assertIn(text, out, name)
        return out

    def refused(self, job, name, *says):
        code, out, err = self.step(job, name)
        self.assertEqual(code, 2, f'{name}: {out}{err}')
        for text in says:
            self.assertIn(text, out + err, name)

    def events(self, job, state):
        return [q for q in job.queued() if q['payload'].get('state') == state]

    def test_o1_health(self):
        def check(job):
            code, out = self.health[(job.client, job.backend)]
            self.assertEqual((code, out), self.reference[self.doctor_flags(job)], 'the doctor reads the machine, not the client')
            self.assertIn('ok hc 0.1.13' if job.backend == 'core' else 'ok herdr on PATH', out)
        self.outcome('O1', check)

    def test_o2_start(self):
        def check(job):
            out = self.ok(job, 'new')
            self.assertEqual(out.strip().splitlines()[-1], f'{Job.LEAD} {job.job}')
            self.assertIn('plan.md', (job.job / 'briefs' / (Job.LEAD + '.md')).read_text())
            self.assertEqual(job.marked, str(job.job), 'the job is marked open until finish')
            owner = job.job / 'owner'
            self.assertEqual(owner.read_text().strip() if owner.is_file() else None, job.bot, 'the job is its starter\'s')
            pointer = f'You are {Job.LEAD}. Read {job.job / "briefs" / (Job.LEAD + ".md")}'
            if job.backend == 'core':
                (lead,) = [r for r in job.calls('run') if job.labels(r).get('stampede.role') == 'lead']
                self.assertTrue(lead[-1].startswith(pointer), 'the brief pointer is the first prompt')
                lead = ' '.join(lead)
            else:
                (lead,) = [c for c in job.herdr_calls() if c.startswith(f'agent start {Job.LEAD} --kind claude')]
                self.assertIn(pointer, job.inbox())
            self.assertIn(f'--model {LEAD_MODEL} --effort low', lead, 'the front door\'s FLEET_LEAD_MODEL and EFFORT')
        self.outcome('O2', check)

    def test_o3_workers(self):
        def check(job):
            runs = {job.labels(r).get('stampede.agent'): r for r in job.calls('run')}
            for kind in KINDS:
                agent = 'build-' + kind
                if kind not in WORKERS[job.backend]:
                    self.refused(job, 'start ' + kind, REFUSED[kind])
                    self.assertNotIn(agent, runs)
                elif job.backend == 'core':
                    self.ok(job, 'start ' + kind, f'STARTED {agent} (t')
                    self.assertEqual(Path(job.program(runs[agent])[0]).name, kind)
                else:
                    self.ok(job, 'start ' + kind, 'DELIVERED' if kind == 'claude' else 'SUBMITTED ' + agent)
                    self.assertTrue(any(c.startswith(f'agent start {agent} --kind {kind}') for c in job.herdr_calls()))
        self.outcome('O3', check)

    def test_o4_question(self):
        def check(job):
            out = self.ok(job, 'ask', 'ASKED ')
            if job.bot:
                self.assertIn('sent to ' + job.bot, out)
                (event,) = self.events(job, 'question')
                self.assertEqual((event['route'], event['payload']['owner']), (job.bot, job.bot))
                self.assertEqual((event['payload']['question'], event['payload']['options']), (QUESTION, [ANSWER, 'no']))
                self.ok(job, 'answer', 'DELIVERED')
                self.assertIn(f'ANSWER {event["payload"]["ask"]} {QUESTION}: {ANSWER}', job.inbox())
                self.assertEqual(job.asked(), '', 'no phone card in a bot\'s job')
            else:
                self.assertIn(f'--option {ANSWER} --option no -- {QUESTION}', job.asked())
                self.assertIn(f'ANSWER {QUESTION}: {ANSWER}', job.inbox())
                self.assertEqual(self.events(job, 'question'), [])
            self.assertEqual(job.moshi(), '', 'no card went to the real phone command')
        self.outcome('O4', check)

    def test_o5_gate(self):
        def check(job):
            self.ok(job, 'gate', 'GATE ' + job.ident)
            refused = ['approve other commit', 'approve inside Herdr', 'approve in a Core terminal'] + ([] if job.bot else ['approve'])
            self.assertEqual(list(job.closed), ['the ask'] + refused)
            for after, (code, recorded) in job.closed.items():  # no yes yet: the gate stays shut
                self.assertEqual((code, recorded), (2, False), f'the gate opened after {after}')
                self.refused(job, 'gate-ok after ' + after, 'has no recorded yes')
            self.refused(job, 'approve inside Herdr', SAY_SO)
            self.refused(job, 'approve in a Core terminal', SAY_SO)
            self.refused(job, 'approve other commit')
            self.refused(job, 'gate-ok other commit', 'a push after the yes withdraws it')
            if job.bot:
                (event,) = self.events(job, 'gate')
                self.assertEqual((event['route'], event['payload']['sha'], event['payload']['action']), (job.bot, SHA, GATE))
                self.assertIn(f'approve-gate {job.job} {job.ident} --sha {SHA}', event['payload']['approve'])
                self.refused(job, 'approve other commit', 'a stale yes')
                self.ok(job, 'approve', f'APPROVED {job.ident} at {SHA}')
                self.ok(job, 'gate-ok', f'APPROVED {job.ident} by owner in {job.bot} chat')
            else:
                self.assertIn(f'Gate {job.ident}: {GATE} (PR #3) at {SHA[:12]}?', job.asked())
                self.refused(job, 'approve', SAY_SO if job.row['where'] == 'inside' else 'belongs to a job started locally')
                self.ok(job, 'gate-ok', f'APPROVED {job.ident} by owner, through ask')
                self.assertEqual(self.events(job, 'gate'), [])
        self.outcome('O5', check)

    def test_o6_tell(self):
        def check(job):
            self.ok(job, 'tell lead', f'DELIVERED {Job.LEAD} (inbox file)')
            self.assertIn('Use the repo root', job.inbox())
            if job.backend == 'core':
                address = job.address(job.worker)
                self.ok(job, 'tell worker', f'SUBMITTED {job.worker} ({address})')
                self.refused(job, 'tell working worker', f'FAILED {job.worker} (working: tell it after its turn)')
                self.ok(job, 'tell done worker', f'SUBMITTED {job.worker} ({address})')
                self.assertEqual(job.state()['terminals'][address]['sent'], ['Check the path', 'And the docs'])
                idle, done = job.calls('send')  # the idle send is guarded; a done worker takes it at once
                self.assertEqual((idle[-5:-2], '--if' in done), (['--if', 'idle', '--'], False))
            else:
                self.ok(job, 'tell worker', 'SUBMITTED ' + job.worker)
                self.assertTrue(any(c.startswith(f'agent prompt {job.worker} Check the path') for c in job.herdr_calls()))
        self.outcome('O6', check)

    def test_o7_finish(self):
        def check(job):
            self.ok(job, 'finish', f'FINISHED {job.job}')
            self.ok(job, 'finish again', f'FINISHED {job.job}')
            self.assertFalse(job.marker.exists(), 'finish cleared the marker')
            self.assertEqual((job.job / 'finished').read_text().strip(), SUMMARY)
            done = self.events(job, 'done')
            if job.bot:
                self.assertEqual(len(done), 1, 'one done event')
                self.assertEqual((done[0]['route'], done[0]['payload']['summary']), (job.bot, SUMMARY))
            else:  # the ordinary relay: no route of the client's own, so the event is logged once
                self.assertEqual(done, [])
                self.assertEqual(job.relay_log().count('stampede pane=- state=done'), 1)
        self.outcome('O7', check)

    def test_o8_reopen_safe(self):
        def check(job):
            runs, herdr = job.before_reopen
            if job.backend == 'core':
                self.ok(job, 'reopen', f'LIVE {job.key}: no agent to restart')
                self.assertEqual(len(job.calls('run')), runs, 'nothing started')
            else:
                self.ok(job, 'snapshot')
                self.refused(job, 'reopen', 'a workspace labelled xc is already open')
                started = [c for c in job.herdr_calls()[herdr:] if c.startswith(('workspace create', 'agent start', 'tab create'))]
                self.assertEqual(started, [], 'nothing started')
        self.outcome('O8', check)

    def test_o9_no_poll(self):
        def check(job):
            if not job.bot:
                self.skipTest('a local client is woken by its own pane or card; O9 is for a bot')
            self.ok(job, 'turn end')
            self.assertEqual(job.queue_after_turn_end, job.queue_before, 'a plain turn end of an open job never wakes the bot')
            self.assertIn('job-skip', job.relay_log())
            asked = [q['payload'] for q in job.queued() if q['payload'].get('source') == 'stampede']
            self.assertEqual(sorted(e['state'] for e in asked), ['done', 'gate', 'question'])
            for event in asked:  # each carries what the bot does next, so it never reads the job to find out
                self.assertTrue(event.get('answer') or event.get('approve') or event.get('summary'), event)
            if job.backend == 'tui' and job.row['owner_from'] == 'env':
                return  # finding F2: the lead's block never reaches this bot (test_f2_an_owner_set_by_env_hears_its_panes)
            self.assertEqual([(q['route'], q['payload']['state']) for q in job.queued() if q['payload'].get('source') != 'stampede'],
                             [(job.bot, 'blocked')], 'the lead\'s block wakes the bot')
        self.outcome('O9', check)

    # findings: where a client does worse than another, each with its proof; a fix makes its test an unexpected success

    @unittest.expectedFailure
    def test_f1_a_bots_core_start_names_its_owner(self):
        """F1: over ssh a bot has no workspace on Core, so only HERDR_EVENTS_OWNER makes the job its own. The bot guides'
        Core start leaves it out; run as written, the job is local: its questions and gates go to the phone and its
        finish to the default route, and the bot never hears them."""
        bot = next(name for name, row in CLIENTS.items() if row.get('bot'))
        job = Job(bot, CLIENTS[bot], 'core', self.root / 'f1', WORKERS)
        (job.root / 'ask.md').write_text('Write hello.txt\n')
        env = {k: v for k, v in job.client_env().items() if k != 'HERDR_EVENTS_OWNER'}  # the guide's command as written
        code, out, err = job.run('new', (ROOT / 'scripts/stampede', 'new', '--core', '--file', job.root / 'ask.md', '--cwd',
                                         job.repo, '--name', Job.NAME), env, 'sshd')
        self.assertEqual(code, 0, out + err)
        self.assertFalse((job.job / 'owner').is_file(), 'proof: run as written, the job is local')
        for doc in ('remote/grokbot/herdr.md', 'remote/other.md'):
            for line in (ROOT / doc).read_text().splitlines():
                if 'stampede new --core' in line:
                    self.assertIn('HERDR_EVENTS_OWNER', line, doc)

    @unittest.expectedFailure
    def test_f2_an_owner_set_by_env_hears_its_panes(self):
        """F2: on the TUI, a bot that names itself with HERDR_EVENTS_OWNER at new (README, Safety) owns the job's
        questions, gates and finish, but new does not tag the workspace, so the panes' own blocked, permission, stale and
        dead events go to the default route. On Core, new tags the job's key, so the follower's do reach it."""
        for job in self.jobs:
            if job.bot and job.backend == 'tui' and job.row['owner_from'] == 'env':
                self.assertEqual((job.events / 'owners' / job.WS).read_text().strip() if (job.events / 'owners' / job.WS).is_file()
                                 else '', 'owner=' + job.bot, 'new tags the workspace with the job\'s bot')
                blocked = [q for q in job.queued() if q['payload'].get('state') == 'blocked']
                self.assertEqual([q['route'] for q in blocked], [job.bot])


    # findings of the live runs (docs/CLIENTS.md, "Found by the live runs") that the fakes can show
    def fresh(self, name, backend, where='outside'):
        """A new job of its own for a finding, started by the first client that runs where it says."""
        client = next(c for c, row in CLIENTS.items() if row['where'] == where)
        job = Job(client, CLIENTS[client], backend, self.root / name, WORKERS)
        job.start()
        self.assertEqual(job.steps['new'][0], 0, job.steps['new'])
        return job

    def card_from_a_tui_pane(self):
        """A local TUI job's lead asks with its pane's environment, which holds no FLEET_ASK_CMD of the front door's.
        One job, for F5 and F6."""
        if getattr(type(self), 'card_job', None):
            return type(self).card_job
        type(self).card_job = job = self.fresh('card', 'tui')
        pane = {k: v for k, v in job.lead_env().items() if k != 'FLEET_ASK_CMD'}
        code, out, err = job.run('ask from the pane', (STAMPEDE, 'ask', job.job, QUESTION, '--option', ANSWER), pane)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(job.until(lambda: job.asked() or job.moshi()), 'no card at all')
        return job

    @unittest.expectedFailure
    def test_f4_a_herdr_refusal_at_start_is_one_line(self):
        """F4: on the TUI, a Herdr refusal at start, such as a worker name a pane of another job already holds (Herdr's
        agent names are global), ends in a Python traceback: main() catches HcError, not HerdrError. On Core, one line."""
        job = self.fresh('f4', 'tui')
        herdr, _ = fake_herdr(job.repo, start_error='agent_name_taken')
        self.addCleanup(shutil.rmtree, Path(herdr).parent, True)
        argv = (STAMPEDE, 'start', job.job, 'build-taken', '--kind', 'codex', '--pane', 'w9:p9', '--brief', valid_brief(job.job, 'build-taken'))
        code, out, err = job.run('start a taken name', argv, {**job.lead_env(), 'HERDR': herdr})
        self.assertNotEqual(code, 0)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertTrue(err.startswith('fleet-job start: herdr agent start'), err)

    @unittest.expectedFailure
    def test_f5_a_tui_lead_asks_through_the_front_doors_command(self):
        """F5: a TUI lead runs with its pane's environment, so of the front door's settings only FLEET_LEAD_MODEL and
        FLEET_LEAD_EFFORT (which new reads itself) reach it: its cards go to Moshi, not to the front door's
        FLEET_ASK_CMD. On Core, launch_env carries every setting. Fixed when a lead with its pane's environment asks
        through the front door's FLEET_ASK_CMD, and nothing reaches Moshi."""
        job = self.card_from_a_tui_pane()
        self.assertEqual(job.moshi(), '', 'the card went to Moshi')
        self.assertIn(QUESTION, job.asked(), 'the front door\'s FLEET_ASK_CMD asked it')

    @unittest.expectedFailure
    def test_f6_a_phone_card_names_its_job(self):
        """F6: a card on the phone carries the question and --source herdr-fleet, but no job, so with several jobs open
        the owner tells their cards apart by the question alone."""
        job = self.card_from_a_tui_pane()
        self.assertRegex(job.asked() or job.moshi(), rf'\b{Job.NAME}\b', 'the card names its job')

    @unittest.expectedFailure
    def test_f7_a_kind_a_backend_does_not_take_is_refused_before_its_brief(self):
        """F7: start checks the brief before the kind, so a cursor start on Core with an incomplete brief names the
        missing sections, not why Core takes no Cursor. Either way nothing starts."""
        job = self.fresh('f7', 'core')
        brief = job.job / 'briefs/probe.md'
        brief.write_text('## Goal\nProbe.\n')
        for kind in set(KINDS) - set(WORKERS['core']):
            code, out, err = job.run('start ' + kind, (STAMPEDE, 'start', job.job, 'probe-' + kind, '--kind', kind, '--brief', brief),
                                     job.lead_env())
            self.assertEqual(code, 2, out + err)
            self.assertIn(REFUSED[kind], err)


    @unittest.expectedFailure
    def test_f10_a_bot_fills_the_answer_by_its_placeholder(self):
        """F10: a question's `answer` and a gate's `deny` hold `<the owner's words>` shell-quoted, so the plain replace
        a bot makes (remote/events.md shows the placeholder as is) misses it, and the lead gets the placeholder."""
        for job in self.jobs:
            for event in [q['payload'] for q in job.queued() if q['payload'].get('state') in ('question', 'gate')]:
                command = event.get('answer') or event['deny']
                self.assertNotEqual(command.replace("<the owner's words>", ANSWER), command, f'{job.client}/{job.backend}')

    @unittest.expectedFailure
    def test_f11_the_finishing_turn_wakes_no_bot(self):
        """F11: finish removes the job's marker before the lead's turn ends, so that turn's own Stop is no longer a turn
        end of an open job: it reaches the bot as one more event after done."""
        job = self.fresh('f11', 'core', where='ssh')
        self.assertEqual(job.lead('finish', 'finish', job.job, SUMMARY)[0], 0)

        def stop(step, address):  # a Claude Stop from a terminal of the job, as its hook posts it; how many it queued
            before = len(job.queued())
            code, out, err = job.run(step, (BOT_SCRIPTS / 'herdr-event-post', 'source=claude', 'state=Stop',
                                            f'pane=hc:{job.key}/{address}'), job.base)
            self.assertEqual(code, 0, out + err)
            return len(job.queued()) - before
        finishing = stop('the finishing turn', job.address(Job.LEAD))
        self.assertEqual(stop('a later turn', 't9'), 1, 'control: a Stop in the closed job still reaches the bot')
        self.assertEqual(finishing, 0, 'the bot heard the finishing turn after its done')


if __name__ == '__main__':
    unittest.main()
