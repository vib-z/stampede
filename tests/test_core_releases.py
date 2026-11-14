"""What Herdr Core 0.1.18 to 0.1.20 and the Herdr app changed for a stampede job, against tests/fake_hc.py: a send held
by a person's draft, hc calls that end, a kept terminal whose program was lost (a shell in its place), the app's space
and tab labels as an opt-in, the follower's lost, restarted, keep, labels and heartbeat, and a Codex lead on Core.
Each behaviour here was first measured on a real hc 0.1.20 in a scratch session; the live evals C13 to C16 repeat it."""
import contextlib, io, json, os, subprocess, sys, time, unittest, uuid
from pathlib import Path
from unittest import mock

try:
    import tomllib  # noqa: F401: only to know whether this Python reads TOML
    TOML = True
except ImportError:  # Python 3.9 and 3.10: stampede cannot read draft_wait and says so; these tests need it read
    TOML = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import CoreCase
from stampede import base as base_, job as job_, hcapi as hcapi_, owner as owner_, hooks as hooks_, tui as tui_, relay as relay_, handed as handed_, cli as cli_
from test_core_relay import core_socket, ev, finished, follower_module, status, turn

SHELL = ['/bin/sh', '-l']  # what Core's restarted event leaves as a kept terminal's argv


class Told(CoreCase):
    """A Core job with one Codex worker at t1, and tell's line and exit code."""

    def setUp(self):
        super().setUp()
        self.job_dir, self.key = self.core_job(workers=[('review-api', 'codex')])
        (self.job_dir / 'core.json').write_text(json.dumps({'review-api': {'state': 'live', 'address': 't1'}}))
        self.add_terminal('t1', name='review-api', argv=['/usr/bin/env', 'STAMPEDE_JOB_KEY=' + self.key, 'codex'],
                          labels={'stampede.job': self.key, 'stampede.agent': 'review-api'})

    def told(self, text='Fix the nit'):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                owner_.tell(self.job_dir, 'review-api', text)
                code = 0
            except SystemExit as stop:
                code = stop.code
        return out.getvalue().strip(), code, self.state()['terminals']['t1']['sent']


class DraftHold(Told):
    """Core 0.1.20 holds a send while a person is typing in the terminal. stampede waits for it, never types over it,
    and says one line whatever comes of it."""

    def test_a_person_typing_holds_the_tell_then_it_goes_in_alone(self):
        self.terminal('t1', person={'draft': 'half a thought', 'then': 'clear', 'after': 0.3})
        started = time.monotonic()
        self.assertEqual(self.told(), ('SUBMITTED review-api (t1)', 0, ['Fix the nit']))
        self.assertGreaterEqual(time.monotonic() - started, 0.3)

    def test_a_person_who_sends_their_own_message_first_keeps_it_apart(self):
        self.terminal('t1', person={'draft': 'my own question', 'then': 'send'})
        self.assertEqual(self.told(), ('SUBMITTED review-api (t1)', 0, ['my own question', 'Fix the nit']))

    def test_a_send_core_cancelled_is_one_failed_line(self):
        self.shape(send_error={'t1': 'cancelled'})
        self.assertEqual(self.told(), ('FAILED review-api (Herdr Core cancelled the send before it typed anything: tell again if '
                                       'still needed)', 2, []))

    def test_a_hung_hc_ends_within_the_limit_and_types_nothing(self):
        self.shape(send_slow={'t1': 30})
        started = time.monotonic()
        with mock.patch.object(hcapi_, 'send_limit', lambda seconds=None: 1):
            out, code, sent = self.told()
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual((code, sent), (2, []))
        self.assertTrue(out.startswith('FAILED review-api (hc send: no answer in 1 s, so it was stopped; a send still held by a draft '
                                       'types nothing once stopped, but read it with hc read t1 before any resend)'), out)

    def test_a_send_that_did_not_start_a_turn_says_so(self):
        self.shape(send_started={'t1': False})
        out, code, sent = self.told()
        self.assertEqual((code, sent), (0, ['Fix the nit']))
        self.assertEqual(out, 'SUBMITTED review-api (t1); it has not gone working yet: read it with hc read t1 before any resend')
        self.shape(send_started={'t1': None})  # a program that reports no status: nobody can tell, so no warning
        self.assertEqual(self.told()[0], 'SUBMITTED review-api (t1)')

    @unittest.skipUnless(TOML, 'reading draft_wait needs tomllib, Python 3.11 and later')
    def test_a_send_is_stopped_before_core_s_hold_could_run_out(self):
        """Core types after a draft only once its hold (draft_wait since the person's last key) is over. stampede's
        send ends SEND_MARGIN seconds before that could happen, so it never goes in after a draft someone left."""
        config = self.root / 'home/.config/herdr-core'
        config.mkdir(parents=True)
        for text, wait, limit in (('notes = true\n', 60.0, 50.0), ('draft_wait = 100\n', 100.0, 90.0), ('  draft_wait=20.5 # short\n', 20.5, 15),
                                  ('draft_wait = 5\n', 5.0, 15), ('draft_wait = -3\n', 0.0, 15)):
            (config / 'config.toml').write_text(text)
            self.assertEqual((hcapi_.core_hold()[0], hcapi_.send_limit()), (wait, limit), text)
        (config / 'config.toml').write_text('draft_wait = 100\n')
        limits = []
        real = subprocess.run

        def run(argv, *args, **kw):
            if argv[1:2] == ['send']:
                limits.append(kw.get('timeout'))
            return real(argv, *args, **kw)
        with mock.patch.object(subprocess, 'run', run):
            self.told()
        self.assertEqual(limits, [90.0])

    def test_a_draft_begun_after_the_look_and_then_left_is_never_submitted_with_the_tell(self):
        """review-codex R3: the person starts typing after stampede read an empty prompt, and leaves the draft. Core
        would type the tell after it once its hold ran out; the send is stopped before that, and nothing is typed."""
        self.shape(draft_wait=4)  # the fake holds a draft that stays this long
        self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay'})
        with mock.patch.object(hcapi_, 'core_hold', lambda: (4.0, 'in a test')), mock.patch.object(hcapi_, 'SEND_MARGIN', 3), mock.patch.object(hcapi_, 'SEND_FLOOR', 0.5):
            out, code, sent = self.told()
        self.assertEqual((code, sent), (2, []))
        self.assertIn('no answer in 1 s, so it was stopped', out)
        self.assertEqual(self.state()['terminals']['t1']['person']['draft'], 'unfinished owner instruction ', 'the draft is untouched')

    def test_a_failure_core_does_not_name_is_not_taken_for_nothing_typed(self):
        self.shape(send_error={'t1': 'boom'})  # not one of hc send's own kinds: nobody can tell what was typed
        self.assertEqual(relay_.send_core(self.job_dir, 'review-api', 'x')[0], None)
        for kind in relay_.SEND_REFUSED:
            self.shape(send_error={'t1': kind})
            self.assertIs(relay_.send_core(self.job_dir, 'review-api', 'x')[0], False, kind)
        import hc_contract
        kinds = {e['data']['kind'] for m in hc_contract.snapshot()['methods'] if m['name'] == 'terminal.send' for e in m['errors']}
        self.assertEqual(set(relay_.SEND_REFUSED), kinds, 'every error kind hc send has, and no other, means nothing was typed')

    def test_text_typed_by_keys_is_still_refused_first(self):
        """Core holds only for a person's live typing: text already in the prompt is stampede's own check, as before."""
        self.terminal('t1', draft='zzz', screen='› zzz\n  ? for help')
        out, code, sent = self.told()
        self.assertEqual((code, sent), (2, []))
        self.assertIn('text is already typed in its prompt', out)
        self.assertEqual(self.calls('send'), [])


class LostUnderKeep(Told):
    """A terminal the Herdr app shows is kept: when its program is lost, Core puts a shell at the same address, with the
    same name and labels. That shell is not the agent."""

    def shell(self):
        self.terminal('t1', keep=True, argv=SHELL, status=None, reported=False)

    def test_tell_names_the_shell_and_types_nothing(self):
        self.shell()
        out, code, sent = self.told()
        self.assertEqual((code, sent), (2, []))
        self.assertEqual(out, f'FAILED review-api (its program was lost and Herdr Core put a shell in its place at t1: start it '
                              f'again with bash {self.job_dir / "reopen.sh"})')
        self.assertEqual(self.calls('send'), [])

    def test_a_live_agent_under_keep_is_still_the_agent(self):
        self.terminal('t1', keep=True)
        self.assertEqual(self.told()[:2], ('SUBMITTED review-api (t1)', 0))
        self.assertEqual(handed_.live_terminal(self.job_dir, 'review-api')['address'], 't1')

    def test_start_and_reopen_see_no_live_agent_and_start_one(self):
        self.shell()
        self.assertIsNone(handed_.live_terminal(self.job_dir, 'review-api'))
        brief = self.brief(self.job_dir, 'review-api')
        (self.job_dir / 'agents.tsv').write_text((self.job_dir / 'agents.tsv').read_text().replace(
            'review-api\tcodex\t\t\t', f'review-api\tcodex\t\t{brief}\t'))
        with job_.launching(self.job_dir, 'review-api'):
            outcome, out = self.quiet(relay_.reopen_agent, self.job_dir, 'review-api', job_.agent_rows(self.job_dir)['review-api'], True, False)
        self.assertEqual(outcome, 'started', out)
        run = self.calls('run')[-1]
        self.assertEqual(self.option(run, '--name'), 'review-api-' + self.key[3:7], 'the shell still holds the name')
        self.assertEqual(self.entries(self.job_dir)['review-api']['address'], 't2')
        self.assertEqual(handed_.live_terminal(self.job_dir, 'review-api')['address'], 't2', 'the shell is never adopted by its labels')

    def test_a_shell_is_a_shell_whether_keep_is_still_on_or_not(self):
        """review-codex R4: hc keep --off after the loss does not bring the agent back, so the shell is still no agent."""
        self.shell()
        self.terminal('t1', keep=False)
        self.assertTrue(hcapi_.shelled(self.state()['terminals']['t1']))
        self.assertIsNone(handed_.live_terminal(self.job_dir, 'review-api'))
        self.assertIn('put a shell in its place at t1', self.told()[0])
        self.assertFalse(hcapi_.shelled({'keep': True}), 'a record with no argv is not judged')
        self.assertFalse(hcapi_.shelled({'keep': True, 'argv': ['/usr/bin/env', 'STAMPEDE_JOB_KEY=hc-0123456789ab', 'claude']}))
        self.assertFalse(hcapi_.shelled({'keep': False, 'argv': ['/usr/bin/env', 'STAMPEDE_JOB_KEY=hc-0123456789ab', 'claude']}))

    def test_a_second_loss_gets_a_third_name_and_never_adopts_a_shell(self):
        """review-codex R2: the first shell holds the agent's name and the second the spare. The third start takes a
        free name, and a lost answer is looked up by that launch's own label, so no older terminal is adopted."""
        self.shell()
        brief = self.brief(self.job_dir, 'review-api')
        self.assertEqual(self.quiet(cli_.start, self.job_dir, 'review-api', 'codex', None, str(brief))[0], 0)
        self.assertEqual(self.entries(self.job_dir)['review-api']['address'], 't2')
        self.terminal('t2', keep=True, argv=SHELL, status=None, reported=False)   # lost again: a second shell
        code, out = self.quiet(cli_.start, self.job_dir, 'review-api', 'codex', None, str(brief))
        self.assertEqual((code, self.entries(self.job_dir)['review-api']['address']), (0, 't3'), out)
        third = self.calls('run')[-1]
        self.assertRegex(self.option(third, '--name'), r'^review-api-[0-9a-f]{8}$')
        self.assertEqual(handed_.live_terminal(self.job_dir, 'review-api')['address'], 't3')
        self.terminal('t3', keep=True, argv=SHELL, status=None, reported=False)   # and a start whose answer is lost
        self.shape(run_error={name: 'unavailable' for name in ('review-api', 'review-api-' + self.key[3:7])})
        with mock.patch.object(uuid, 'uuid4', lambda: mock.Mock(hex='feedc0de' * 4)):
            self.shape(run_error={'review-api-feedc0de': 'unavailable'})
            code, out = self.quiet(cli_.start, self.job_dir, 'review-api', 'codex', None, str(brief))
        self.assertEqual(code, 1, out)
        self.assertIn('FAILED review-api', out)
        self.assertEqual(self.entries(self.job_dir)['review-api']['state'], 'failed', 'no shell stands in for the launch that never ran')
        lookup = self.calls('ls')[-1]
        self.assertIn('stampede.launch=feedc0de', lookup)


class AppSpace(CoreCase):
    """D1: a Core job shows in the Herdr app only when asked. The labels are Herdr's own (herdr.space, herdr.tab)."""

    def runs(self):
        return {self.labels(run).get('stampede.role'): self.labels(run) for run in self.calls('run')}

    def test_off_by_default(self):
        code, _ = self.new_core()
        self.assertEqual(code, 0)
        for labels in self.runs().values():
            self.assertEqual([k for k in labels if k.startswith('herdr.')], [])
        self.assertFalse((self.job / 'app-space').exists())

    def test_the_lead_and_workers_carry_the_labels_and_the_follower_does_not(self):
        code, _ = self.new_core(app=True)
        self.assertEqual(code, 0)
        key = (self.job / 'workspace').read_text().strip()
        space = 'stampede-' + key[3:]
        self.assertEqual((self.job / 'app-space').read_text().strip(), space)
        runs = self.runs()
        self.assertEqual((runs['lead']['herdr.space'], runs['lead']['herdr.tab']), (space, 'lead-fix-login-bug'))
        self.assertEqual([k for k in runs['relay'] if k.startswith('herdr.')], [])
        self.shape(on_run={'build-api': {'title': '✳ ~/code/x'}})  # a title that is a folder never names a tab
        self.quiet(cli_.start, self.job, 'build-api', 'claude', None, str(self.brief(self.job, 'build-api')))
        worker = self.runs()['worker']
        self.assertEqual((worker['herdr.space'], worker['herdr.tab'], worker['stampede.agent']), (space, 'build-api', 'build-api'))

    def test_the_standing_choice_and_the_flag_s_place(self):
        with mock.patch.dict(os.environ, {'STAMPEDE_APP_SPACE': '1'}):
            self.assertEqual(self.new_core()[0], 0)
        self.assertTrue((self.job / 'app-space').is_file())
        with self.assertRaises(ValueError) as refused:
            cli_.new('ask.md', 'w1', app=True)
        self.assertIn('--app-space is for new --core', str(refused.exception))

    def test_a_lost_answer_is_still_adopted_by_the_job_s_own_labels(self):
        self.new_core(app=True)
        self.shape(run_error={'build-api': 'unavailable'}, spawn_also=True)
        _, out = self.quiet(cli_.start, self.job, 'build-api', 'claude', None, str(self.brief(self.job, 'build-api')))
        self.assertIn('STARTED build-api', out)
        lookup = self.calls('ls')[-1]
        self.assertNotIn('herdr.space', ' '.join(lookup), 'the lookup names the job, the agent and the session only')


class CodexLeadOnCore(CoreCase):
    """D3: a Core job takes a Codex lead. Core's own guards stand where the TUI needed herdr-send: hc send --if idle,
    and the hold while a person types."""

    def lead_job(self, status='idle'):
        job, key = self.core_job(workers=[('build-api', 'claude')])
        (job / 'agents.tsv').write_text((job / 'agents.tsv').read_text().replace('lead-demo\tclaude', 'lead-demo\tcodex'))
        (job / 'core.json').write_text(json.dumps({'lead-demo': {'state': 'live', 'address': 't1', 'role': 'lead'}}))
        (job / 'hooks').mkdir()  # as cli_args leaves it at the lead's start
        self.add_terminal('t1', name='lead-demo', status={'state': status} if status else None,
                          argv=['/usr/bin/env', 'STAMPEDE_JOB_KEY=' + key, 'codex'],
                          labels={'stampede.job': key, 'stampede.agent': 'lead-demo', 'stampede.role': 'lead'})
        return job, key

    def deliver(self, job, wait=0.4):
        with mock.patch.object(tui_, 'DELIVER_FOR', wait), mock.patch.object(tui_, 'DELIVER_EVERY', 0.05):
            return self.quiet(tui_.deliver, job)

    @unittest.skipUnless(TOML, 'reading draft_wait needs tomllib, Python 3.11 and later')
    def test_a_codex_lead_needs_core_s_draft_hold(self):
        """review-codex R3: its inbox is typed into its terminal with nobody watching, and only Core's hold keeps a
        person's typing apart from that. With no hold (before 0.1.20), or one too short to end a send inside, a Codex
        lead is refused before anything is made, and a deliverer types nothing."""
        self.shape(version='0.1.19')
        with self.assertRaises(ValueError) as refused:
            self.new_core(kind='codex')
        self.assertIn('a Codex lead on Herdr Core gets its inbox typed into its terminal, and Herdr Core 0.1.19 does not hold a message',
                      str(refused.exception))
        self.assertFalse(self.job.exists())
        self.shape(version='0.1.20')
        path, server = core_socket(self.root)   # the core that runs says 0.1.13 in its hello, whatever hc on PATH is
        self.addCleanup(server.shutdown)
        with mock.patch.dict(os.environ, {'HC_SOCKET': str(path)}), self.assertRaises(ValueError) as refused:
            self.new_core(kind='codex')
        self.assertIn('Herdr Core 0.1.13 does not hold a message', str(refused.exception))
        self.assertFalse(self.job.exists())
        config = self.root / 'home/.config/herdr-core'
        config.mkdir(parents=True)
        (config / 'config.toml').write_text('draft_wait = 10\n')
        with self.assertRaises(ValueError) as refused:
            self.new_core(kind='codex')
        self.assertIn('draft_wait is 10 s', str(refused.exception))
        self.assertEqual(self.new_core()[0], 0, 'a Claude lead reads its inbox file, so it needs no hold')
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        code, out = self.deliver(job)
        self.assertEqual(code, 6)
        self.assertIn('NOT TYPED: draft_wait is 10 s', out)
        self.assertEqual(self.calls('send'), [])
        with self.assertRaises(ValueError):   # nor is a lead restarted on Codex there
            self.quiet(cli_.start, job, 'lead-demo', 'codex', None, str(job / 'briefs/lead-demo.md'))

    def test_a_delivery_with_no_answer_is_never_typed_twice(self):
        """review-codex R1: hc send reached the lead, then its answer was lost. The lines are not typed again: their
        offsets move, and the lead is told once where to read them itself."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'REPORT reports/build-api.md')
        base_.append(job / 'inbox.log', 'TURN build-api')
        real, lost = hcapi_.hc, []

        def hc(*args, **kw):
            answer = real(*args, **kw)
            if args[0] == 'send' and not lost:
                lost.append(args)
                raise hcapi_.HcError('hc send: no answer in 50 s, so it was stopped', 'timeout', 124)
            return answer
        with mock.patch.object(hcapi_, 'hc', hc):
            code, out = self.deliver(job, wait=10)
        self.assertEqual(code, 7, out)   # held: nothing more goes into that terminal until it has taken a turn
        self.assertIn('HELD: a send to lead-demo got no answer', out)
        (lines,) = self.state()['terminals']['t1']['sent']
        self.assertIn('inbox.log: REPORT reports/build-api.md | TURN build-api', lines)
        self.assertEqual(tui_.unread(job, 'lead-demo'), [], 'the lines are not waiting to be typed again')
        self.assertEqual(self.deliver(job)[0], 7, 'nor does a later deliverer type anything while the hold stands')
        self.assertEqual(len(self.calls('send')), 1)
        self.terminal('t1', turn=1)   # the lead took a turn: whatever was in its prompt was submitted
        self.assertEqual(self.deliver(job)[0], 0)
        lines, pointer = self.state()['terminals']['t1']['sent']
        self.assertEqual(pointer, f'[fleet-job inbox for lead-demo, not typed by the owner] Herdr Core gave no answer to a delivery, so these '
                                  f'lines may not have reached you. Read them yourself, each once: lines 1 to 2 of {job / "inbox.log"}')
        self.assertEqual((relay_.owed(job), tui_.unread(job, 'lead-demo')), ([], []))
        self.assertFalse((job / 'hooks/deliver-held.json').exists())
        base_.append(job / 'inbox.log', 'GONE build-api exited exit 0')
        self.assertEqual(self.deliver(job)[0], 0)
        self.assertEqual(len(self.state()['terminals']['t1']['sent']), 3, 'later lines are typed as ever, once')
        held = [q for q in (self.root / 'queue/queue').glob('*.json') if json.loads(q.read_text())['payload'].get('kind') == 'held']
        self.assertEqual(len(held), 0, 'no owner here, so the hold is logged on the machine only')

    def test_a_pointer_that_is_owed_is_sent_until_it_goes_in_and_the_lines_never_again(self):
        job, _ = self.lead_job()
        base_.append(job / 'inbox' / 'lead-demo.md', 'ANSWER: yes, the root')
        self.shape(send_error={'t1': 'boom'})   # a failure Core does not name: nobody can tell
        code, out = self.deliver(job, wait=10)
        self.assertEqual(code, 7, out)
        self.assertEqual(self.state()['terminals']['t1']['sent'], [])
        self.assertEqual(relay_.owed(job), [[str(job / 'inbox' / 'lead-demo.md'), 1, 1]])
        self.assertEqual(tui_.unread(job, 'lead-demo'), [], 'the line is not waiting to be typed again')
        self.terminal('t1', turn=4)   # a turn: the hold ends, and the pointer is tried, with no answer again
        self.assertEqual(self.deliver(job, wait=10)[0], 7)
        self.assertEqual(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'], 4, 'held again, from this turn')
        self.assertEqual(len(self.calls('send')), 2, 'one try of the lines, one of the pointer')
        self.shape(send_error={})
        self.assertEqual(self.deliver(job)[0], 7, 'no turn since: still held, though a send would now work')
        self.terminal('t1', turn=5)
        self.assertEqual(self.deliver(job)[0], 0)
        (pointer,) = self.state()['terminals']['t1']['sent']
        self.assertIn('lines 1 to 1 of ' + str(job / 'inbox' / 'lead-demo.md'), pointer)
        self.assertNotIn('ANSWER: yes', pointer)

    def test_a_hold_ends_with_a_turn_another_terminal_or_a_hand_and_the_owner_hears_of_it(self):
        job, key = self.lead_job()
        (job / 'owner').write_text('alpha\n')
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(send_error={'t1': 'boom'})
        self.assertEqual(self.deliver(job, wait=10)[0], 7)
        (event,) = [json.loads(q.read_text())['payload'] for q in sorted((self.root / 'queue/queue').glob('*.json'))]
        self.assertEqual((event['state'], event['kind'], event['agent'], event['pane'], event['owner']),
                         ('blocked', 'held', 'lead-demo', f'hc:{key}/t1', 'alpha'))
        self.assertIn('text may be left typed in its terminal (t1)', event['msg'])
        self.shape(send_error={})
        (job / 'hooks/deliver-held.json').unlink()   # someone looked at the prompt and cleared the hold by hand
        self.assertEqual(self.deliver(job)[0], 0)
        self.assertIn('lines 1 to 1 of', self.state()['terminals']['t1']['sent'][0])
        relay_.hold(job, 'lead-demo', 't1')
        self.assertFalse(relay_.held(job, {'address': 't7', 'turn': 0}), 'a restarted lead is another terminal, with another prompt')

    def test_a_draft_the_owner_leaves_in_the_lead_s_terminal_is_never_submitted_with_a_line(self):
        """review-codex R3, for the lead: the owner starts typing after the look and leaves it. Nothing is typed."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(draft_wait=30)
        self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay'})
        with mock.patch.object(hcapi_, 'send_limit', lambda seconds=None: 0.5):
            code, out = self.deliver(job, wait=10)   # the deadline is not what is tested: room for a slow machine
        self.assertEqual(code, 7, out)
        terminal = self.state()['terminals']['t1']
        self.assertEqual((terminal['sent'], terminal['person']['draft']), ([], 'unfinished owner instruction '))

    def test_a_draft_s_hold_runs_out_once_however_often_a_deliverer_comes_back(self):
        """review-codex R3, round 2: Core counts its hold from the person's last key, not from each send. The first send
        is stopped in time; a second one, begun while that same draft sits there, would meet the end of the hold. So
        after a send with no answer nothing is typed until the terminal has taken a turn, whatever the screen shows."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        real, born = hcapi_.hc, []

        def hc(*args, **kw):   # one last key, just after stampede's first look at the (empty) prompt
            if args[0] == 'send':
                born.append(time.monotonic()) if not born else None
                self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay',
                                            'after': max(0, born[0] + 3 - time.monotonic())})
            return real(*args, **kw)
        with mock.patch.object(hcapi_, 'hc', hc), mock.patch.object(hcapi_, 'send_limit', lambda seconds=None: 2):
            first = self.deliver(job, wait=15)[0]
            time.sleep(max(0, born[0] + 3.2 - time.monotonic()))   # the hold has run out: a send now would go in after the draft
            later = [self.deliver(job, wait=10)[0] for _ in range(2)]
        self.assertEqual((first, later), (7, [7, 7]))
        self.assertEqual(len(self.calls('send')), 1, 'one send, stopped in time; none after it')
        self.assertEqual(self.state()['terminals']['t1']['sent'], [])

    def test_new_starts_a_codex_lead_in_a_core_terminal(self):
        code, out = self.new_core(kind='codex')
        self.assertEqual(code, 0, out)
        (lead,) = [run for run in self.calls('run') if self.labels(run).get('stampede.role') == 'lead']
        program = self.program(lead)
        self.assertTrue(program[0].endswith('/codex'))
        self.assertIn('--no-daemon', program)
        self.assertNotIn('--session-id', program)
        brief = self.job / 'briefs/lead-fix-login-bug.md'
        self.assertEqual(program[-1], f'You are lead-fix-login-bug. Read {brief} and do everything it says.')
        text = brief.read_text()
        for said in ('fleet-job types each new line of', 'into this terminal', 'prints APPROVED', 'A typed yes does not count on Core'):
            self.assertIn(said, text)
        self.assertNotIn('typed in your pane', text)
        self.assertEqual(job_.lead_kind(self.job), 'codex')
        self.assertEqual(job_.agent_rows(self.job)['lead-fix-login-bug']['session'], '', 'Codex names its own session')

    def test_a_standing_codex_choice_is_the_lead_of_a_core_job_and_a_fork_still_refuses_it(self):
        with mock.patch.dict(os.environ, {'FLEET_LEAD_KIND': 'codex'}):
            self.assertEqual(self.new_core()[0], 0)
            self.assertEqual(job_.lead_kind(self.job), 'codex')
            with self.assertRaises(ValueError) as refused:
                self.new_core(fork='0b5f1c2e-7d3a-4e8b-9c41-2a6f8e9d1b37')
            self.assertIn('--fork forks a Claude chat', str(refused.exception))

    def test_its_inbox_is_typed_with_hc_send_only_while_it_is_idle(self):
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'GONE build-api killed exit -')
        base_.append(job / 'inbox' / 'lead-demo.md', 'ANSWER: yes, the root')
        code, out = self.deliver(job)
        self.assertEqual(code, 0, out)
        (text,) = self.state()['terminals']['t1']['sent']
        self.assertTrue(text.startswith('[fleet-job inbox for lead-demo, not typed by the owner] '), text)
        self.assertIn('lead-demo.md: ANSWER: yes, the root', text)
        self.assertIn('inbox.log: GONE build-api killed exit -', text)
        (send,) = self.calls('send')
        self.assertEqual(send[2:4], ['--if', 'idle'])
        self.assertEqual(self.calls('keys'), [], 'never a key')
        self.assertEqual(self.deliver(job)[0], 0)
        self.assertEqual(len(self.calls('send')), 1, 'each line once')

    def test_it_waits_while_the_lead_works_is_blocked_or_is_a_shell(self):
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        for change in ({'status': {'state': 'working'}}, {'status': {'state': 'blocked', 'kind': 'permission'}},
                       {'status': None, 'keep': True, 'argv': SHELL}, {'status': {'state': 'idle'}, 'state': 'finished'}):
            with self.subTest(change=change):
                self.terminal('t1', **change)
                code, out = self.deliver(job, wait=0.3)
                self.assertEqual(code, 3, out)
                self.assertEqual(self.calls('send'), [])
                self.assertEqual(len(tui_.unread(job, 'lead-demo')), 1, 'the line stays unread')

    def test_a_draft_in_its_prompt_or_a_person_typing_is_never_typed_over(self):
        job, _ = self.lead_job()
        self.terminal('t1', draft='zzz', screen='› zzz\n  ? for help')
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.assertEqual(self.deliver(job, wait=0.3)[0], 3)
        self.assertEqual(self.state()['terminals']['t1']['sent'], [])
        self.terminal('t1', draft='', screen='› ', person={'draft': 'the owner is typing', 'then': 'send'})
        self.assertEqual(self.deliver(job)[0], 0)
        sent = self.state()['terminals']['t1']['sent']
        self.assertEqual(sent[0], 'the owner is typing')
        self.assertTrue(sent[1].startswith('[fleet-job inbox for lead-demo'))

    def test_a_core_that_does_not_answer_leaves_the_line_for_the_next_deliverer(self):
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(get_error={'t1': 'unavailable'})
        code, out = self.deliver(job)
        self.assertEqual(code, 4)
        self.assertIn('CANNOT REACH HERDR', out)

    def test_tell_and_the_follower_wake_its_deliverer(self):
        job, _ = self.lead_job()
        with mock.patch.object(tui_, 'deliver_soon') as kicked:
            _, out = self.quiet(owner_.tell, job, 'lead', 'GATE 0123456789ab APPROVED')
        self.assertEqual(out.strip(), 'DELIVERED lead-demo (inbox file; typed into its terminal once it is idle)')
        kicked.assert_called_once()
        core = follower_module()
        with mock.patch.object(core.subprocess, 'Popen') as woke:
            follower = core.Follower(job)
            follower.tell('GONE build-api killed exit -')
        self.assertEqual(woke.call_args.args[0], [str(core.FLEET_JOB), '_wake', str(job)])
        (job / 'agents.tsv').write_text((job / 'agents.tsv').read_text().replace('lead-demo\tcodex', 'lead-demo\tclaude'))
        with mock.patch.object(core.subprocess, 'Popen') as woke:
            core.Follower(job).tell('GONE build-api killed exit -')
        woke.assert_not_called()  # a Claude lead's file hook sees the line
        self.assertEqual((job / 'inbox.log').read_text().count('GONE build-api killed exit -'), 2)

    def test_its_own_turn_end_names_its_session_and_reopen_resumes_it(self):
        job, _ = self.lead_job()
        thread = '019a0000-0000-7000-8000-00000000abcd'
        rollout = self.root / 'codex/sessions/2026/11/11'
        rollout.mkdir(parents=True)
        (rollout / f'rollout-2026-11-11T00-00-00-{thread}.jsonl').write_text(json.dumps({'payload': {}}) + '\n')
        payload = {'type': 'agent-turn-complete', 'thread-id': thread, 'last-assistant-message': 'planned'}
        with mock.patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'codex')}), mock.patch.object(hooks_, 'RELAY_CODEX', '/usr/bin/true'), \
                mock.patch.object(tui_, 'deliver_soon') as kicked:
            hooks_.codex_notify(job, 'lead-demo', payload)
            hooks_.codex_notify(job, 'lead-demo', {**payload, 'thread-id': 'a-sub-agent-thread-with-no-file'})
        self.assertEqual(kicked.call_count, 2)
        self.assertEqual(job_.agent_rows(job)['lead-demo']['session'], thread)
        self.assertFalse((job / 'inbox.log').exists(), 'the lead\'s own turn never goes to its own inbox.log')
        self.terminal('t1', state='finished')
        with job_.launching(job, 'lead-demo'):
            outcome, out = self.quiet(relay_.reopen_agent, job, 'lead-demo', job_.agent_rows(job)['lead-demo'], False, True)
        self.assertEqual(outcome, 'started', out)
        program = self.program(self.calls('run')[-1])
        self.assertEqual((program[1], program[-1]), ('resume', thread))

    def test_a_codex_lead_that_never_ended_a_turn_reopens_with_its_brief(self):
        job, _ = self.lead_job()
        brief = job / 'briefs/lead-demo.md'
        brief.write_text('the brief\n')
        (job / 'agents.tsv').write_text((job / 'agents.tsv').read_text().replace('lead-demo\tcodex\t\t\t', f'lead-demo\tcodex\t\t{brief}\t'))
        self.terminal('t1', state='finished')
        with job_.launching(job, 'lead-demo'):
            self.quiet(relay_.reopen_agent, job, 'lead-demo', job_.agent_rows(job)['lead-demo'], False, True)
        self.assertEqual(self.program(self.calls('run')[-1])[-1], f'You are lead-demo in a herdr fleet. Read {brief} and do everything it says.')

    def test_a_reopened_codex_lead_acknowledges_through_its_deliverer(self):
        job, _ = self.lead_job()
        (job / 'hooks').mkdir(exist_ok=True)

        def typed(folder):  # the deliverer, played at once: what fleet-job _deliver does once the lead is idle
            self.deliver(folder)
        with mock.patch.object(tui_, 'deliver_soon', typed), mock.patch.object(relay_, 'REOPEN_DEADLINE', 5), mock.patch.object(relay_, 'REOPEN_EVERY', 0.3):
            code, out = self.quiet(relay_.acknowledged, job, 'lead-demo')
        self.assertEqual(code, 0, out)
        self.assertIn('ACKNOWLEDGED lead-demo', out)
        self.assertIn('REOPENED lead-demo', self.state()['terminals']['t1']['sent'][0])

    def test_a_hold_counts_turns_from_a_look_after_the_send_with_the_terminal_at_rest(self):
        """review-codex R10: a prompt finishes between the deliverer's look and the send's own, and the owner then starts
        a draft. The stopped send's hold must not be ended by that earlier turn: its count is read after the send."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        real, seen, born = hcapi_.hc, [], []

        def hc(*args, **kw):
            answer = real(*args, **kw)
            if args[0] == 'get' and not seen:
                seen.append(answer.get('turn'))
                self.terminal('t1', turn=1)   # a turn ends right after the deliverer's own look
            if args[0] == 'read' and not born:
                born.append(time.monotonic())   # the owner starts typing right after the look at the prompt
                self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay', 'after': 3})
            return answer
        with mock.patch.object(hcapi_, 'hc', hc), mock.patch.object(hcapi_, 'send_limit', lambda seconds=None: 2):
            first = self.deliver(job, wait=15)[0]
            time.sleep(max(0, born[0] + 3.2 - time.monotonic()))
            self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay', 'after': 0})   # the hold has run out
            later = [self.deliver(job, wait=10)[0] for _ in range(2)]
        self.assertEqual((seen, first, later), ([0], 7, [7, 7]))
        self.assertEqual(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'], 1, 'counted from after the send')
        self.assertEqual(len(self.calls('send')), 1)
        self.assertEqual(self.state()['terminals']['t1']['sent'], [])

    def test_a_hold_begun_while_a_turn_is_under_way_waits_for_a_turn_begun_after_it(self):
        """A turn that was already running when the send got no answer may end with the left text still in the prompt:
        the hold takes its count only once the terminal is at rest, and ends with a turn after that."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(send_error={'t1': 'boom'})
        self.terminal('t1', status={'state': 'done'}, turn=3)
        real = hcapi_.hc

        def hc(*args, **kw):
            if args[0] == 'send':   # the lead turns working under the send, which then gets no answer
                self.terminal('t1', status={'state': 'working'})
            return real(*args, **kw)
        with mock.patch.object(hcapi_, 'hc', hc):
            self.assertEqual(self.deliver(job, wait=4)[0], 3, 'no answer, and the lead is working: it is waited for')
        self.assertIsNone(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'], 'no count yet: a turn was under way')
        self.shape(send_error={})
        self.terminal('t1', status={'state': 'done'}, turn=4)   # that turn ended: it began before the hold
        self.assertEqual(self.deliver(job, wait=10)[0], 7)
        self.assertEqual(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'], 4)
        self.assertEqual(self.deliver(job, wait=10)[0], 7)
        self.terminal('t1', turn=5)   # a prompt submitted since
        self.assertEqual(self.deliver(job, wait=10)[0], 0)
        self.assertEqual(len(self.state()['terminals']['t1']['sent']), 1, 'the pointer, once')

    def test_a_hold_from_the_core_s_environment_also_limits_the_send(self):
        """review-codex R9: with no draft_wait in the config, Core's hold is HC_DRAFT_MS from its own environment. The
        value that lets a Codex lead be typed to is the value its sends are stopped by."""
        job, _ = self.lead_job()
        self.shape(core_env={'HC_DRAFT_MS': '30000'})
        self.assertEqual((hcapi_.typing_guard(), hcapi_.send_limit()), (('', 30.0), 20.0))
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(core_env={'HC_DRAFT_MS': '9000'}, draft_wait=9)   # the same, in small: a 9 s hold, sends stopped after 6
        real = hcapi_.hc

        def hc(*args, **kw):
            answer = real(*args, **kw)
            if args[0] == 'read':   # the owner starts typing right after the look at the prompt, and leaves it
                self.terminal('t1', person={'draft': 'unfinished owner instruction ', 'then': 'stay'})
            return answer
        started = time.monotonic()
        with mock.patch.object(hcapi_, 'hc', hc), mock.patch.object(hcapi_, 'SEND_MARGIN', 3), mock.patch.object(hcapi_, 'SEND_FLOOR', 0.5):
            self.assertEqual(hcapi_.typing_guard(), ('', 9.0))
            code, out = self.deliver(job, wait=12)
        self.assertEqual(code, 7, out)
        self.assertLess(time.monotonic() - started, 8.5, 'stopped before the 9 s hold ran out')
        self.assertIn('no answer in 6 s', out)
        self.assertEqual(self.state()['terminals']['t1']['sent'], [])

    def test_a_count_taken_just_as_a_turn_ended_does_not_start_a_hold(self):
        """A turn that ended moments before the look may not show in the count yet: the hold takes its count only from
        a terminal that has been at rest for a few seconds by Core's own clock."""
        now = time.time() * 1000
        rest = {'state': 'live', 'status': {'state': 'done'}, 'turn': 6}
        self.assertEqual(relay_.settled({**rest, 'status_ms': now - 60_000}), 6)
        self.assertIsNone(relay_.settled({**rest, 'status_ms': now - 1_000}))
        self.assertIsNone(relay_.settled(rest), 'no clock, no count')
        self.assertIsNone(relay_.settled({**rest, 'status': {'state': 'working'}, 'status_ms': now - 60_000}))
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(send_error={'t1': 'boom'})
        recent = now + 3_600_000   # a status change that stays "only just now" for the whole test
        self.terminal('t1', status_ms=recent, turn=6)
        self.assertEqual(self.deliver(job, wait=2)[0], 3, 'it stays for a settled look, and none comes')
        self.assertIsNone(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'])
        self.shape(send_error={})
        self.terminal('t1', turn=7)   # the count of that turn shows a moment later: no hold may end by it
        self.assertEqual(self.deliver(job, wait=2)[0], 3)
        self.assertEqual((len(self.calls('send')), relay_.hold_count(job)), (1, None))
        self.terminal('t1', status_ms=now - 60_000)
        self.assertEqual(self.deliver(job, wait=10)[0], 7)
        self.assertEqual(json.loads((job / 'hooks/deliver-held.json').read_text())['turn'], 7)
        self.terminal('t1', turn=8)
        self.assertEqual(self.deliver(job, wait=10)[0], 0)

    def test_a_hold_gets_its_count_though_every_wake_up_comes_right_at_a_turn_s_end(self):
        """review-codex R11: a deliverer woken by a turn's end sees a status only just changed. It stays the few seconds
        a settled look takes, so the hold gets its count, and the next turn ends it."""
        job, _ = self.lead_job()
        base_.append(job / 'inbox.log', 'TURN build-api')
        self.shape(send_error={'t1': 'boom'})
        self.terminal('t1', status={'state': 'done'}, turn=6, status_ms=time.time() * 1000)
        with mock.patch.object(relay_, 'HOLD_SETTLE', 0.6):
            self.assertEqual(self.deliver(job, wait=10)[0], 7)
            self.assertEqual(relay_.hold_count(job), 6, 'taken by the same deliverer, once the terminal had settled')
            self.shape(send_error={})
            self.terminal('t1', turn=7, status_ms=time.time() * 1000)   # the next wake-up, again right at a turn's end
            self.assertEqual(self.deliver(job, wait=10)[0], 0)
        (pointer,) = self.state()['terminals']['t1']['sent']
        self.assertIn('may not have reached you', pointer)

    def test_a_send_with_no_answer_never_acknowledges_a_reopen(self):
        """review-codex R7: the REOPENED lines may not have reached the lead, so their offsets move without the
        acknowledgement a delivery gives, and reopen keeps asking."""
        job, _ = self.lead_job()
        self.shape(send_error={'t1': 'boom'})
        with mock.patch.object(tui_, 'deliver_soon', lambda folder: self.deliver(folder, wait=10)), \
                mock.patch.object(relay_, 'REOPEN_DEADLINE', 1.5), mock.patch.object(relay_, 'REOPEN_EVERY', 0.2):
            code, out = self.quiet(relay_.acknowledged, job, 'lead-demo')
        self.assertEqual(code, 3, out)
        self.assertIn('NOT ACKNOWLEDGED', out)
        self.assertNotIn('ACKNOWLEDGED lead-demo: its wake delivered', out)
        self.assertFalse((job / 'hooks/ack-lead-demo.json').exists())
        self.assertTrue(relay_.owed(job), 'the lead is still owed the lines')

    @unittest.skipUnless(TOML, 'reading draft_wait needs tomllib, Python 3.11 and later')
    def test_core_s_draft_wait_is_read_as_core_reads_it(self):
        """review-codex R8: the hold decides whether lines may be typed unattended, so it is Core's own reading of its
        config.toml (TOML numbers and keys, defaults for a file that is no TOML), and unknown is a refusal."""
        config = self.root / 'home/.config/herdr-core'
        config.mkdir(parents=True)
        cases = (('draft_wait = 30e-2\n', ('set', 0.3)), ('"draft_wait" = 0.1\n', ('set', 0.1)), ('draft_wait = 1_0\n', ('set', 10.0)),
                 ('draft_wait = -3\n', ('set', 0.0)), ('draft_wait = 600\n[broken\n', ('default', 60.0)), ('notes = true\n', ('default', 60.0)),
                 ('[other]\ndraft_wait = 1\n', ('default', 60.0)), ('draft_wait = "long"\n', ('unknown', None)),
                 ('draft_wait = inf\n', ('unknown', None)), ('draft_wait = true\n', ('unknown', None)), ('draft_wait = 1e300\n', ('unknown', None)))
        for text, want in cases:
            (config / 'config.toml').write_text(text)
            self.assertEqual(hcapi_.draft_config(), want, text)
        import builtins
        real = builtins.__import__
        with mock.patch.object(builtins, '__import__', lambda name, *a, **kw: (_ for _ in ()).throw(ImportError(name)) if name == 'tomllib' else real(name, *a, **kw)):
            (config / 'config.toml').write_text('draft_wait = 45\n')   # a Python before 3.11 cannot read TOML
            self.assertEqual(hcapi_.draft_config(), ('unknown', None))
            (config / 'config.toml').write_text('notes = true\n')
            self.assertEqual(hcapi_.draft_config(), ('default', 60.0))
        for text, said in (('draft_wait = 30e-2\n', 'draft_wait is 0.3 s in Herdr Core\'s config.toml'), ('"draft_wait" = 0.1\n', 'draft_wait is 0.1 s'),
                           ('draft_wait = "long"\n', 'cannot be read here as Core reads it')):
            (config / 'config.toml').write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError) as refused:
                self.new_core(kind='codex')
            self.assertIn(said, str(refused.exception))
            self.assertFalse(self.job.exists())
        (config / 'config.toml').write_text('draft_wait = "long"\n')
        self.assertEqual(hcapi_.send_limit(), hcapi_.SEND_FLOOR, 'a tell by hand gets the shortest limit when the hold is not known')
        (config / 'config.toml').unlink()
        self.shape(core_env={'HC_DRAFT_MS': '8000'})   # Core's fallback when its config sets nothing
        with self.assertRaises(ValueError) as refused:
            self.new_core(kind='codex')
        self.assertIn('draft_wait is 8 s by HC_DRAFT_MS in the running core\'s environment', str(refused.exception))
        (config / 'config.toml').write_text('draft_wait = 60\n')   # the config wins over that fallback, as in Core
        self.assertEqual(hcapi_.typing_unsafe(), '')
        (config / 'config.toml').unlink()
        self.shape(core_env={}, exec_error='unavailable')
        self.assertIn('environment cannot be read', hcapi_.typing_unsafe())
        self.assertEqual(hcapi_.send_limit(), hcapi_.SEND_FLOOR)
        self.shape(exec_error='')
        self.assertEqual(hcapi_.typing_unsafe(), '')
        elsewhere = self.root / 'core-home/.config/herdr-core'   # the core reads its own config, wherever this shell's is
        elsewhere.mkdir(parents=True)
        (elsewhere / 'config.toml').write_text('draft_wait = 12\n')
        (config / 'config.toml').write_text('draft_wait = 90\n')
        self.shape(core_env={'HOME': str(self.root / 'core-home')})
        self.assertEqual(hcapi_.core_hold()[0], 12.0)
        self.assertIn('draft_wait is 12 s', hcapi_.typing_unsafe())
        self.shape(core_env={'HOME': str(self.root / 'core-home'), 'XDG_CONFIG_HOME': str(self.root / 'home/.config')})
        self.assertEqual((hcapi_.core_hold()[0], hcapi_.typing_unsafe()), (90.0, ''))

    def test_a_lead_restarted_on_the_other_cli_gets_its_brief_for_it(self):
        self.new_core()
        lead, brief = 'lead-fix-login-bug', self.job / 'briefs/lead-fix-login-bug.md'
        self.assertNotIn('fleet-job types each new line of', brief.read_text())
        address = self.entries(self.job)[lead]['address']
        self.terminal(address, state='finished')
        _, out = self.quiet(cli_.start, self.job, lead, 'codex', None, str(brief))
        self.assertIn('STARTED ' + lead, out)
        self.assertIn('fleet-job types each new line of', brief.read_text())
        self.assertIn('into this terminal', brief.read_text())
        self.assertIn('--no-daemon', self.program(self.calls('run')[-1]))


class FollowerEvents(CoreCase):
    """The follower on Core's lost, restarted, keep, labels and heartbeat (hc 0.1.20's events.subscribe)."""

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
        self.core = follower_module()
        patch = mock.patch.object(self.core.Follower, 'post', lambda follower, fields: self.posts.append(fields))
        patch.start()
        self.addCleanup(patch.stop)
        self.f = self.core.Follower(self.job_dir)

    def record(self, address, word=None, keep=False, argv=None, state='live'):
        agent, role = self.roles[address]
        return {'address': address, 'name': agent, 'state': state, 'turn': 0, 'reported': word is not None, 'keep': keep,
                'argv': argv or ['/usr/bin/env', 'STAMPEDE_JOB_KEY=' + self.key, 'claude'],
                'status': {'state': word} if word else None,
                'labels': {'stampede.job': self.key, 'stampede.role': role, 'stampede.agent': agent}}

    def snap(self, *records, seq=1):
        return {'channel': None, 'seq': seq, 'terminals': list(records)}

    def feed(self, *rows):
        for row in rows:
            self.f.line(row)

    def inbox(self):
        path = self.job_dir / 'inbox.log'
        return path.read_text().splitlines() if path.is_file() else []

    def lost(self, terminal, signal=9):
        return ev('lost', terminal, {'exit_code': None, 'finished_ms': None, 'reason': 'signaled', 'signal': signal})

    def restarted(self, terminal):
        return ev('restarted', terminal, self.record(terminal, keep=True, argv=SHELL))

    def shell_line(self, agent, address, reason):
        return f'GONE {agent} {reason} exit - (a shell is in its place at {address}: restart the agent with bash {self.job_dir / "reopen.sh"})'

    def test_lost_then_restarted_under_keep_is_gone_once_and_never_idle(self):
        """As measured on hc 0.1.20: status null, lost (signaled), restarted (a shell), then whatever the shell does."""
        self.feed(self.snap(self.record('t3', 'working')), ev('keep', 't3', {'keep': True}), status('t3', None), self.lost('t3'),
                  self.restarted('t3'), ev('foreground', 't3', {'argv': SHELL, 'name': 'bash'}),
                  status('t3', 'idle'), turn('t3', 1, 'idle'), status('t3', 'blocked', kind='permission'), finished('t3', 0))
        self.assertEqual(self.inbox(), [self.shell_line('build-api', 't3', 'signaled')])
        self.assertEqual([(p['state'], p['agent'], p.get('reason')) for p in self.posts], [('dead', 'build-api', 'signaled')])
        self.assertEqual(self.posts[0]['last_state'], 'working')

    def test_lost_without_keep_is_gone_with_core_s_reason_and_no_shell(self):
        self.feed(self.snap(self.record('t4', 'idle')), status('t4', None), self.lost('t4'), finished('t4', None, 'signaled', signal=9))
        self.assertEqual(self.inbox(), ['GONE review-api signaled exit -'])
        self.assertEqual(self.posts, [], 'an idle agent that is lost is told to the lead, with no alarm for the bot, as an idle exit is')

    def test_restarted_alone_is_still_gone(self):
        self.feed(self.snap(self.record('t3', 'working')), self.restarted('t3'), status('t3', 'idle'))
        self.assertEqual(self.inbox(), [self.shell_line('build-api', 't3', 'lost')])
        self.assertEqual([(p['state'], p['agent']) for p in self.posts], [('dead', 'build-api')])

    def test_a_shell_found_at_reconnect_is_gone_and_a_kept_agent_is_not(self):
        """A reboot: kept terminals come back as shells while the follower was away. One still running its agent stays."""
        self.feed(self.snap(self.record('t3', keep=True, argv=SHELL), self.record('t4', 'idle', keep=True)))
        self.assertEqual(self.inbox(), [self.shell_line('build-api', 't3', 'lost')])
        self.feed(self.snap(self.record('t3', keep=True, argv=SHELL), self.record('t4', 'idle', keep=True)))
        self.assertEqual(len(self.inbox()), 1, 'once')

    def test_the_lead_s_own_loss_reaches_the_bot_and_not_its_own_inbox(self):
        self.feed(self.snap(self.record('t1', 'working', keep=True)), status('t1', None), self.lost('t1'), self.restarted('t1'))
        self.assertEqual(self.inbox(), [])
        self.assertEqual([(p['state'], p['agent']) for p in self.posts], [('dead', 'lead-demo')])

    def test_a_shell_found_at_reconnect_with_keep_turned_off_is_still_gone(self):
        """review-codex R4: keep on, a loss, a shell, then hc keep --off, all while the follower was away."""
        self.feed(self.snap(self.record('t3', keep=False, argv=SHELL), self.record('t4', 'idle', keep=False)))
        self.assertEqual(self.inbox(), [self.shell_line('build-api', 't3', 'lost')])

    def test_a_terminal_only_adopted_by_its_labels_is_never_judged_by_its_argv(self):
        """A wait terminal, or one the lead started by hand with the job's labels, never names STAMPEDE_JOB_KEY."""
        wait = {'address': 't9', 'name': 'wait-ci', 'state': 'live', 'turn': 0, 'keep': True, 'argv': ['gh', 'run', 'watch'],
                'status': None, 'labels': {'stampede.job': self.key, 'stampede.role': 'wait'}}
        hand = {**wait, 'address': 't8', 'name': 'helper', 'labels': {'stampede.job': self.key, 'stampede.agent': 'helper'}}
        self.feed(self.snap(wait, hand))
        self.assertEqual(self.inbox(), [])
        self.feed(ev('labels', 't8', {'labels': {'stampede.job': self.key, 'stampede.agent': 'helper-2', 'stampede.role': 'wait'}}),
                  finished('t8', 0))
        self.assertEqual(self.inbox(), ['WAITED helper-2 exit 0'], 'an adopted terminal is who its labels say')
        self.feed(ev('labels', 't3', {'labels': {'stampede.job': self.key, 'stampede.agent': 'someone-else'}}), finished('t3', 1))
        self.assertEqual(self.inbox()[-1], 'GONE build-api exited exit 1', 'a bound agent is who core.json says')

    def test_the_types_with_no_news_change_nothing(self):
        self.feed(self.snap(self.record('t3', 'working')))
        before = json.dumps(self.f.terminals, sort_keys=True)
        for kind in self.core.IGNORED:
            self.feed(ev(kind, 't3', {'title': '✳ ~/code/x', 'cols': 80, 'rows': 24, 'argv': SHELL, 'name': 'bash'}))
        self.feed({'jsonrpc': '2.0', 'method': 'heartbeat', 'params': {'seq': 9}})
        self.assertEqual(json.dumps(self.f.terminals, sort_keys=True), before)
        self.assertEqual((self.inbox(), self.posts), ([], []))

    def test_a_stream_that_goes_silent_after_a_heartbeat_is_reopened(self):
        """Core sends a heartbeat every 15 s. A stream that sent one and then nothing is hung: the follower ends it and
        connects again, where the snapshot reconciles. A stream that never sent one (an older core) is left alone."""
        beat = {'jsonrpc': '2.0', 'method': 'heartbeat', 'params': {'seq': 1}}
        fake = self.root / 'core'
        state = json.loads((fake / 'state.json').read_text())
        (fake / 'state.json').write_text(json.dumps({**state, 'streams': [[self.snap(), beat]], 'hold': [30]}))
        clock = [0.0]
        with mock.patch.object(self.core, 'clock', lambda: clock[0]), mock.patch.object(self.core, 'TICK', 0.05):
            rows, started = [], time.monotonic()
            for row in self.f.stream():
                rows.append(row)
                if row.get('method') == 'heartbeat':
                    clock[0] += self.core.BEAT_LOST + 1  # a minute passes with nothing more
            self.assertLess(time.monotonic() - started, 10, 'ended long before the fake closes the connection')
        self.assertIn(beat, rows)
        state = json.loads((fake / 'state.json').read_text())
        (fake / 'state.json').write_text(json.dumps({**state, 'connections': 0, 'streams': [[self.snap()]], 'hold': [0.6]}))
        clock[0] = 0.0
        with mock.patch.object(self.core, 'clock', lambda: clock.__setitem__(0, clock[0] + 100) or clock[0]), \
                mock.patch.object(self.core, 'TICK', 0.05):
            started = time.monotonic()
            list(self.f.stream())
        self.assertGreaterEqual(time.monotonic() - started, 0.5, 'no heartbeat seen: it waits for the stream itself to end')


if __name__ == '__main__':
    unittest.main()
