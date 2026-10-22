"""fleet-job: messages, background questions, approval and hooks, all with fakes."""
import json, os, stat, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/herdr-fleet/scripts'
sys.path.insert(0, str(SCRIPTS))
import fleet_job as fj


def job_with(agents):
    job = Path(tempfile.mkdtemp()) / '.herdr-demo'
    job.mkdir()
    rows = ['# herdr-reopen-snapshot: name\tkind\tsession\tbrief\targs']
    rows += [f'{name}\t{kind}\t-\t-\t-' for name, kind in agents]
    (job / 'agents.tsv').write_text('\n'.join(rows) + '\n')
    (job / 'lead').write_text(agents[0][0] + '\n')
    return job


def fake_herdr(cwd, status='idle', foreground='', start_error=None):
    """foreground: the pane's live shell folder; '' means the same as cwd, None leaves it out.
    start_error: an error code `agent start` answers with (exit 1), as Herdr does."""
    live = '' if foreground is None else ',"foreground_cwd":"' + str(cwd if foreground == '' else foreground) + '"'
    refuse = ('  "agent start") echo \'{"error":{"code":"' + start_error + '","message":"refused"}}\'; exit 1;;\n') if start_error else ''
    folder = Path(tempfile.mkdtemp())
    log = folder / 'herdr.log'
    script = folder / 'herdr'
    script.write_text('#!/bin/bash\necho "$*" >> ' + str(log) + '\ncase "$1 $2" in\n'
                      '  "pane list") echo \'{"result":{"panes":[{"cwd":"' + str(cwd) + '"}]}}\';;\n'
                      '  "pane get") echo \'{"result":{"pane":{"pane_id":"\'"$3"\'","cwd":"' + str(cwd) + '"' + live + ',"tab_id":"w9:t1"}}}\';;\n'
                      + refuse +
                      '  "tab create") echo \'{"result":{"root_pane":{"pane_id":"w9:p2"}}}\';;\n'
                      '  "agent wait") echo \'{"result":{"agent":{"agent_status":"' + status + '"}}}\';;\n'
                      '  *) echo \'{"result":{}}\';;\nesac\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script), log


def codex_home(*sessions):
    """A fake CODEX_HOME: one rollout file per (thread id, first-line payload)."""
    home = Path(tempfile.mkdtemp())
    folder = home / 'sessions/2026/10/21'
    folder.mkdir(parents=True)
    for thread, meta in sessions:
        (folder / ('rollout-2026-10-21T10-00-00-' + thread + '.jsonl')).write_text(
            json.dumps({'type': 'session_meta', 'payload': {'id': thread, **meta}}) + '\n')
    return str(home)


class Messages(unittest.TestCase):
    def test_tell_claude_appends_one_line_to_its_inbox(self):
        job = job_with([('lead-demo', 'claude'), ('build-api', 'claude')])
        fj.tell(job, 'build-api', 'first\nsecond')
        self.assertEqual((job / 'inbox/build-api.md').read_text(), 'first second\n')

    def test_tell_lead_resolves_the_lead(self):
        job = job_with([('lead-demo', 'claude')])
        fj.tell(job, 'lead', 'hello')
        self.assertEqual((job / 'inbox/lead-demo.md').read_text(), 'hello\n')

    def test_tell_refuses_an_agent_outside_the_job(self):
        job = job_with([('lead-demo', 'claude')])
        with self.assertRaises(ValueError):
            fj.tell(job, 'stranger', 'hi')


class Asks(unittest.TestCase):
    def fake_ask(self, body):
        folder = Path(tempfile.mkdtemp())
        script = folder / 'fake-ask'
        script.write_text('#!/bin/bash\n' + body + '\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return str(script)

    def test_answer_reaches_the_lead_inbox(self):
        job = job_with([('lead-demo', 'claude')])
        command = self.fake_ask('echo "Yes"')
        self.assertEqual(fj.ask_now(job, 'Go?', ['Yes', 'No'], command), 0)
        self.assertIn('ANSWER Go?: Yes', (job / 'inbox/lead-demo.md').read_text())

    def test_exit_3_is_reported_as_failed_with_its_code(self):
        job = job_with([('lead-demo', 'claude')])
        command = self.fake_ask('exit 3')
        fj.ask_now(job, 'Go?', ['Yes', 'No'], command)
        self.assertIn('ASK FAILED Go?: exit 3', (job / 'inbox/lead-demo.md').read_text())

    def test_cancel_stops_the_whole_ask_and_its_child(self):
        job = job_with([('lead-demo', 'claude')])
        marker = Path(tempfile.mkdtemp()) / 'sleep.pid'
        command = self.fake_ask('sleep 300 & echo $! > ' + str(marker) + '; wait')
        ident = fj.ask_background(job, 'Go?', ['Yes', 'No'], command)
        deadline = time.time() + 10
        while not (marker.is_file() and marker.read_text().strip()):
            self.assertLess(time.time(), deadline, 'the fake ask never started its child')
            time.sleep(0.05)
        child = int(marker.read_text())
        os.kill(child, 0)  # alive before the cancel
        fj.cancel(job, ident)
        deadline = time.time() + 10
        while True:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            self.assertLess(time.time(), deadline, 'the ask child survived cancel')
            time.sleep(0.05)
        self.assertNotIn('ASK FAILED', (job / 'inbox/lead-demo.md').read_text() if (job / 'inbox/lead-demo.md').exists() else '')


class Approval(unittest.TestCase):
    def test_a_plan_and_go_job_needs_no_approval(self):
        job = job_with([('lead-demo', 'claude')])
        fj.require_approval(job)  # no review file: no error

    def test_a_review_job_refuses_until_approved(self):
        job = job_with([('lead-demo', 'claude')])
        (job / 'review').write_text('owner asked to see the plan\n')
        (job / 'plan.md').write_text('# Plan: demo\n')
        with self.assertRaises(PermissionError):
            fj.require_approval(job)
        fj.approve(job, 'grokbot')
        fj.require_approval(job)
        self.assertIn('Approved by grokbot', (job / 'inbox/lead-demo.md').read_text())

    def test_a_changed_plan_needs_a_new_approval(self):
        job = job_with([('lead-demo', 'claude')])
        (job / 'review').write_text('x\n')
        (job / 'plan.md').write_text('v1\n')
        fj.approve(job, 'owner')
        (job / 'plan.md').write_text('v2\n')
        with self.assertRaises(PermissionError):
            fj.require_approval(job)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.job = job_with([('lead-demo', 'claude'), ('build-api', 'claude')])
        (self.job / 'hooks').mkdir()
        (self.job / 'hooks/build-api.json').write_text(json.dumps({'reports': ['reports/api.md']}))

    def stop(self, active=False):
        return fj.claude_stop(self.job, 'build-api', {'hook_event_name': 'Stop', 'stop_hook_active': active})

    def test_no_report_sends_the_worker_back_once(self):
        out = self.stop()
        self.assertEqual(json.loads(out)['decision'], 'block')
        self.assertEqual(self.stop(active=True), '')
        self.assertIn('TURN build-api ended without a report', (self.job / 'inbox.log').read_text())

    def test_a_done_report_is_announced_and_a_rewrite_again(self):
        report = self.job / 'reports/api.md'
        report.parent.mkdir()
        report.write_text('# api\nStatus: DONE\nfirst\n')
        self.stop()
        report.write_text('# api\nStatus: DONE\nfixed after review\n')
        self.stop()
        self.stop()
        log = (self.job / 'inbox.log').read_text()
        self.assertEqual(log.count('REPORT reports/api.md'), 2)

    def test_wake_returns_new_inbox_lines_once(self):
        fj.tell(self.job, 'lead', 'one')
        path = str(self.job / 'inbox/lead-demo.md')
        self.assertEqual(fj.wake(self.job, 'lead-demo', {'file_path': path}), ['one'])
        self.assertEqual(fj.wake(self.job, 'lead-demo', {'file_path': path}), [])

    def test_a_worker_question_becomes_a_file_and_a_line(self):
        out = fj.ask_lead(self.job, 'build-api', {'tool_input': {'questions': [{'question': 'Which DB?'}]}})
        self.assertEqual(json.loads(out)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('Which DB?', (self.job / 'questions/build-api.md').read_text())
        self.assertIn('QUESTION build-api: Which DB?', (self.job / 'inbox.log').read_text())

    def test_the_lead_may_ask_its_own_card(self):
        self.assertEqual(fj.ask_lead(self.job, 'lead-demo', {'tool_input': {'questions': []}}), '{}')

    def test_codex_and_cursor_turns_reach_the_lead(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'CODEX_HOME': codex_home(('t-main', {}))}):
            fj.codex_notify(self.job, 'build-api', {'type': 'agent-turn-complete', 'thread-id': 't-main', 'last-assistant-message': 'done'})
        fj.cursor_stop(self.job, 'build-api', {'status': 'completed'})
        log = (self.job / 'inbox.log').read_text()
        self.assertIn('TURN build-api done', log)
        self.assertEqual(log.count('TURN build-api'), 2)


class Start(unittest.TestCase):
    def test_claude_gets_auto_mode_and_its_hook_settings(self):
        job = job_with([('lead-demo', 'claude')])
        args = fj.cli_args(job, 'build-api', 'claude', 'claude-opus-5-5', 'xhigh', ['reports/api.md'])
        self.assertEqual(args[:2], ['--permission-mode', 'auto'])
        settings = json.loads(Path(args[args.index('--settings') + 1]).read_text())
        self.assertIn('Stop', settings['hooks'])
        self.assertIn('FileChanged', settings['hooks'])
        self.assertEqual(json.loads((job / 'hooks/build-api.json').read_text())['reports'], ['reports/api.md'])

    def test_the_lead_has_no_stop_hook(self):
        job = job_with([('lead-demo', 'claude')])
        args = fj.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True)
        settings = json.loads(Path(args[args.index('--settings') + 1]).read_text())
        self.assertNotIn('Stop', settings['hooks'])

    def test_codex_gets_approve_for_me_notify_and_the_job_dir(self):
        job = job_with([('lead-demo', 'claude')])
        args = fj.cli_args(job, 'build-ui', 'codex', 'gpt-6.1-sol', 'xhigh', [])
        self.assertIn('--approve-for-me', args)
        self.assertIn('--add-dir', args)
        self.assertTrue(any(a.startswith('notify=') for a in args))
        self.assertNotIn('--yolo', args)

    def test_yolo_only_in_a_linked_worktree(self):
        job = job_with([('lead-demo', 'claude')])
        repo = Path(tempfile.mkdtemp())
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'commit', '-q', '--allow-empty', '-m', 'base'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'})
        with self.assertRaises(PermissionError):
            fj.cli_args(job, 'build-api', 'codex', None, None, [], yolo_in=repo)
        tree = repo.parent / (repo.name + '-wt')
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', str(tree)], check=True)
        self.assertIn('--yolo', fj.cli_args(job, 'build-api', 'codex', None, None, [], yolo_in=tree))
        self.assertIn('--dangerously-skip-permissions', fj.cli_args(job, 'build-ui', 'claude', None, None, [], yolo_in=tree))
        with self.assertRaises(PermissionError):
            fj.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True, yolo_in=tree)

    def test_cursor_gets_auto_review_and_a_stop_plugin(self):
        job = job_with([('lead-demo', 'claude')])
        args = fj.cli_args(job, 'qa-ui', 'cursor', 'auto', None, [])
        self.assertIn('--auto-review', args)
        plugin = Path(args[args.index('--plugin-dir') + 1])
        self.assertIn('cursor-stop', (plugin / 'hooks/hooks.json').read_text())


class Command(unittest.TestCase):
    def test_hook_wake_exits_2_with_the_new_lines(self):
        job = job_with([('lead-demo', 'claude')])
        fj.tell(job, 'lead', 'REPORT reports/api.md')
        payload = json.dumps({'file_path': str(job / 'inbox/lead-demo.md')})
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'hook', 'wake', str(job), '--agent', 'lead-demo'],
                                input=payload, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('REPORT reports/api.md', result.stderr)

    def test_new_job_folder_name(self):
        self.assertEqual(fj.slug('Fix the login bug on the billing page, please'), 'fix-login-bug-billing')


class Fixes(unittest.TestCase):
    def run_new(self, status, env=(), start_error=None, **kw):
        import contextlib, io
        from unittest import mock
        repo = Path(tempfile.mkdtemp()) / 'repo'
        repo.mkdir()
        ask = repo.parent / 'ask.md'
        ask.write_text('Fix the login bug\n')
        herdr, log = fake_herdr(repo, status, start_error=start_error)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'HERDR': herdr, **dict(env)}), contextlib.redirect_stdout(out):
            fj.new(ask, 'w9', **kw)
        return out.getvalue(), repo / '.herdr-fix-login-bug', log.read_text()

    def test_new_starts_the_lead_on_the_table_model(self):
        _, _, log = self.run_new('idle')
        self.assertIn('--model claude-opus-5-5 --effort xhigh', log)
        _, _, log = self.run_new('idle', {'FLEET_LEAD_MODEL': 'claude-fable-5-1', 'FLEET_LEAD_EFFORT': 'max'})
        self.assertIn('--model claude-fable-5-1 --effort max', log)

    def test_new_holds_the_pointer_for_a_blocked_lead(self):
        out, job, _ = self.run_new('blocked')
        self.assertIn('BLOCKED lead-fix-login-bug: clear the startup dialog, then fleet-job tell ' + str(job) + ' lead "Read '
                      + str(job / 'briefs/lead-fix-login-bug.md') + '"', out)
        self.assertFalse((job / 'inbox/lead-fix-login-bug.md').exists())

    def test_command_errors_are_one_plain_line(self):
        job = job_with([('lead-demo', 'claude')])
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'approve', str(job), '--by', 'owner'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_a_worker_that_ends_reaches_the_lead_as_gone(self):
        job = job_with([('lead-demo', 'claude'), ('build-api', 'claude')])
        settings = lambda args: json.loads(Path(args[args.index('--settings') + 1]).read_text())
        worker = settings(fj.cli_args(job, 'build-api', 'claude', None, None, []))
        lead = settings(fj.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True))
        self.assertIn('SessionEnd', worker['hooks'])
        self.assertNotIn('SessionEnd', lead['hooks'])
        fj.session_end(job, 'build-api', {'reason': 'other'})
        fj.session_end(job, 'lead-demo', {'reason': 'other'})
        log = (job / 'inbox.log').read_text()
        self.assertIn('GONE build-api', log)
        self.assertNotIn('GONE lead-demo', log)


class ReviewRound1(unittest.TestCase):
    def worktree(self):
        repo = Path(tempfile.mkdtemp()) / 'repo'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'commit', '-q', '--allow-empty', '-m', 'base'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'})
        tree = repo.parent / 'repo-wt'
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', str(tree)], check=True)
        return repo, tree

    def start(self, job, agent, pane_cwd, foreground='', **kw):
        import contextlib, io
        from unittest import mock
        herdr, log = fake_herdr(pane_cwd, foreground=foreground)
        error = None
        with mock.patch.dict(os.environ, {'HERDR': herdr}), contextlib.redirect_stdout(io.StringIO()):
            try:
                fj.start(job, agent, 'claude', 'w9:p3', str(job / 'briefs' / (agent + '.md')), **kw)
            except PermissionError as refused:
                error = refused
        return error, log.read_text() if log.exists() else ''

    def test_r1_yolo_needs_the_pane_itself_in_a_linked_worktree(self):
        repo, tree = self.worktree()
        job = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        error, log = self.start(job, 'build-x', repo, yolo_in=str(tree))  # claims the worktree, pane sits in main
        self.assertIsInstance(error, PermissionError)
        self.assertNotIn('agent start', log)
        error, log = self.start(job, 'build-x', repo, yolo_in=str(repo))  # main checkout
        self.assertIsInstance(error, PermissionError)
        self.assertNotIn('agent start', log)
        error, log = self.start(job, 'build-x', tree, yolo_in=str(tree))
        self.assertIsNone(error)
        self.assertIn('--dangerously-skip-permissions', log)

    def test_r1_yolo_is_refused_for_the_lead_by_name(self):
        repo, tree = self.worktree()
        job = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        error, log = self.start(job, 'lead-demo', tree, yolo_in=str(tree))
        self.assertIsInstance(error, PermissionError)
        self.assertNotIn('agent start', log)

    def test_r1_restarting_the_lead_keeps_its_hooks(self):
        job = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        error, log = self.start(job, 'lead-demo', job.parent)
        self.assertIsNone(error)
        hooks = json.loads((job / 'hooks/lead-demo-claude.json').read_text())['hooks']
        self.assertNotIn('Stop', hooks)
        self.assertNotIn('SessionEnd', hooks)

    def test_r2_codex_notify_takes_its_payload_as_the_last_argument(self):
        job = job_with([('lead-demo', 'claude'), ('build-ui', 'codex')])
        args = fj.cli_args(job, 'build-ui', 'codex', None, None, [])
        notify = json.loads(next(a for a in args if a.startswith('notify='))[len('notify='):])
        payload = json.dumps({'type': 'agent-turn-complete', 'thread-id': 't-main', 'last-assistant-message': 'shipped'})
        result = subprocess.run(notify + [payload], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                env={**os.environ, 'CODEX_HOME': codex_home(('t-main', {}))})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('TURN build-ui shipped', (job / 'inbox.log').read_text())

    def test_r3_consuming_the_inbox_never_touches_it(self):
        job = job_with([('lead-demo', 'claude')])
        paths = fj.watch_paths(job, 'lead-demo', True)
        fj.tell(job, 'lead', 'one')
        before = [os.stat(path).st_mtime_ns for path in paths]
        time.sleep(0.05)
        self.assertEqual(fj.wake(job, 'lead-demo', {'file_path': paths[0]}), ['one'])
        self.assertEqual(fj.wake(job, 'lead-demo', {'file_path': paths[0]}), [])
        self.assertEqual(fj.watch_paths(job, 'lead-demo', True), paths)
        self.assertEqual([os.stat(path).st_mtime_ns for path in paths], before)

    def test_r6_every_cursor_stop_reaches_the_lead_with_its_status(self):
        job = job_with([('lead-demo', 'claude'), ('qa-ui', 'cursor')])
        args = fj.cli_args(job, 'qa-ui', 'cursor', None, None, [])
        plugin = Path(args[args.index('--plugin-dir') + 1])
        command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']['stop'][0]['command']
        for status in ('completed', 'error', 'aborted'):
            result = subprocess.run(command, shell=True, input=json.dumps({'status': status}), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        log = (job / 'inbox.log').read_text()
        for status in ('completed', 'error', 'aborted'):
            self.assertIn('TURN qa-ui ' + status, log)

    def test_r7_a_review_verdict_is_a_finished_report(self):
        job = job_with([('lead-demo', 'claude'), ('review-api', 'claude')])
        (job / 'hooks').mkdir()
        (job / 'hooks/review-api.json').write_text(json.dumps({'reports': ['reports/review.md']}))
        (job / 'reports').mkdir()
        for verdict in ('FINDINGS', 'PASS'):
            (job / 'reports/review.md').write_text('# review\nStatus: ' + verdict + '\n')
            self.assertEqual(fj.claude_stop(job, 'review-api', {'hook_event_name': 'Stop'}), '')
        self.assertEqual((job / 'inbox.log').read_text().count('REPORT reports/review.md'), 2)

    def test_r9_new_uses_a_given_empty_pane_and_renames_its_tab(self):
        out, job, log = Fixes.run_new(self, 'idle', pane='w9:p1')
        self.assertIn('tab rename w9:t1 lead', log)
        self.assertIn('agent start lead-fix-login-bug --kind claude --pane w9:p1 ', log)
        self.assertNotIn('tab create', log)

    def test_r9_new_without_a_pane_opens_a_lead_tab(self):
        out, job, log = Fixes.run_new(self, 'idle')
        self.assertIn('tab create --workspace w9', log)
        self.assertIn('--pane w9:p2 ', log)


class FinalFixes(unittest.TestCase):
    def test_k1_yolo_follows_the_shells_live_folder(self):
        repo, tree = ReviewRound1.worktree(self)
        job = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        error, log = ReviewRound1.start(self, job, 'build-x', tree, foreground=repo, yolo_in=str(tree))
        self.assertIsInstance(error, PermissionError)  # stored cwd in the worktree, live shell in main
        self.assertNotIn('agent start', log)
        error, log = ReviewRound1.start(self, job, 'build-x', tree, foreground=None, yolo_in=str(tree))
        self.assertIsInstance(error, PermissionError)  # no live folder: fail closed
        self.assertNotIn('agent start', log)
        error, log = ReviewRound1.start(self, job, 'build-x', tree, foreground=tree, yolo_in=str(tree))
        self.assertIsNone(error)
        self.assertIn('--dangerously-skip-permissions', log)


class LiveFixes(unittest.TestCase):
    def run_start(self, job, agent, start_error):
        import contextlib, io
        from unittest import mock
        herdr, log = fake_herdr(job.parent, start_error=start_error)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'HERDR': herdr}), contextlib.redirect_stdout(out):
            fj.start(job, agent, 'claude', 'w9:p3', str(job / 'briefs' / (agent + '.md')))
        return out.getvalue()

    def test_a_startup_dialog_at_start_is_blocked_not_a_crash(self):
        job = job_with([('lead-demo', 'claude')])
        out = self.run_start(job, 'build-x', 'agent_not_ready')
        self.assertIn('BLOCKED build-x: clear the startup dialog, then fleet-job tell ' + str(job) + ' build-x "Read '
                      + str(job / 'briefs/build-x.md') + '"', out)
        self.assertIn('build-x', fj.roster(job)[0])  # the reopen record was written
        self.assertFalse((job / 'inbox/build-x.md').exists())

    def test_a_startup_dialog_at_new_is_blocked_not_a_crash(self):
        out, job, log = Fixes.run_new(self, 'idle', start_error='agent_not_ready')
        self.assertIn('BLOCKED lead-fix-login-bug: clear the startup dialog, then fleet-job tell ' + str(job) + ' lead "Read '
                      + str(job / 'briefs/lead-fix-login-bug.md') + '"', out)
        self.assertIn('lead-fix-login-bug', fj.roster(job)[0])
        self.assertFalse((job / 'inbox/lead-fix-login-bug.md').exists())

    def test_any_other_herdr_error_still_fails(self):
        job = job_with([('lead-demo', 'claude')])
        with self.assertRaises(RuntimeError):
            self.run_start(job, 'build-x', 'agent_pane_not_found')
        self.assertNotIn('build-x', fj.roster(job)[0])

    def test_codex_background_turns_never_wake_the_lead(self):
        from unittest import mock
        job = job_with([('lead-demo', 'claude'), ('review-hello', 'codex')])
        home = codex_home(('t-main', {}), ('t-sub', {'source': {'subagent': 'thread_spawn'}}),
                          ('t-child', {'parent_thread_id': 't-main'}))
        turn = lambda thread, text, **extra: fj.codex_notify(job, 'review-hello', {
            'type': 'agent-turn-complete', 'thread-id': thread, 'last-assistant-message': text, **extra})
        with mock.patch.dict(os.environ, {'CODEX_HOME': home}):
            turn('t-sub', '{"title":"Review hello brief"}')
            turn('t-child', 'child done')
            turn('t-none', 'no session file')
            turn('t-main', 'side', parent_thread_id='t-main')
            turn('t-main', 'review done')
        self.assertEqual((job / 'inbox.log').read_text(), 'TURN review-hello review done\n')


class StampedeReview1(unittest.TestCase):
    """Fixes from the stampede review, round 1."""
    def cli(self, *args, path_herdr=None, drop=()):
        env = {k: v for k, v in os.environ.items() if k not in drop}
        if path_herdr:
            env['PATH'] = str(Path(path_herdr).parent) + ':' + env['PATH']
        return subprocess.run([str(SCRIPTS / 'fleet-job'), *args], capture_output=True, text=True, env=env)

    def test_r1_tell_to_a_focused_pane_is_one_plain_failure_and_sends_nothing(self):
        job = job_with([('lead-demo', 'claude'), ('build-ui', 'codex')])
        folder = Path(tempfile.mkdtemp())
        (folder / 'herdr').write_text('#!/bin/bash\necho "$*" >> ' + str(folder / 'calls') + '\n[ "$1 $2" = "agent get" ] && '
                                      'echo \'{"result":{"agent":{"agent_status":"idle","focused":true}}}\'\n')
        (folder / 'herdr').chmod(0o755)
        result = self.cli('tell', str(job), 'build-ui', 'hello', path_herdr=folder / 'herdr')
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (2, 'FAILED build-ui focused: the owner is in that pane; retry later\n', ''))
        self.assertEqual((folder / 'calls').read_text(), 'agent get build-ui\n')

    def test_r3_new_without_a_target_outside_herdr_is_a_usage_line(self):
        ask = Path(tempfile.mkdtemp()) / 'ask.md'
        ask.write_text('Fix the login bug\n')
        herdr, log = fake_herdr(ask.parent)
        result = self.cli('new', '--file', str(ask), drop=('HERDR_WORKSPACE_ID',), path_herdr=herdr)
        self.assertEqual((result.returncode, result.stderr.strip()),
                         (2, 'fleet-job new: new needs --workspace or --pane, or run it inside Herdr'))
        self.assertFalse(log.exists())

    def test_r6_the_references_start_agents_hooked_and_copy_no_env_file(self):
        refs = ROOT / 'skills/herdr-fleet/references'
        for name in ('worked-example.md', 'agents-and-models.md'):
            text = (refs / name).read_text()
            self.assertIn('fleet-job start "$B"', text, name)
            self.assertNotRegex(text, r'cp [^\n]*\.env', name)
            self.assertNotRegex(text, r'herdr agent prompt \S+ "You are', name)   # an unhooked start, then the brief by hand
        self.assertNotIn('Monitor tool', (refs / 'worked-example.md').read_text())
        self.assertNotIn('herdr agent start review-', (refs / 'agents-and-models.md').read_text())   # the takeover starts hooked too
