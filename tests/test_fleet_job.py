"""fleet-job: messages, background questions, approval and hooks, all with fakes."""
import json, os, shlex, stat, subprocess, sys, tempfile, time, unittest
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


def valid_brief(job, agent='build-x', omit=()):
    brief = job / 'briefs' / (agent + '.md')
    brief.parent.mkdir(exist_ok=True)
    brief.write_text('\n'.join('## ' + name + '\nDo the assigned work.\n'
                              for name in fj.BRIEF_SECTIONS if name not in omit))
    return brief


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


class Briefs(unittest.TestCase):
    def test_missing_sections_refuse_before_hooks_herdr_or_roster_writes(self):
        import contextlib, io
        from unittest import mock
        for kind in ('claude', 'codex', 'cursor'):
            with self.subTest(kind=kind):
                job = job_with([('lead-demo', 'claude')])
                brief = valid_brief(job, omit=('Goal', 'Done when'))
                before = (job / 'agents.tsv').read_bytes()
                herdr, log = fake_herdr(job.parent)
                message = (f'brief {brief} is missing: Goal, Done when; '
                           'fill them in on skills/herdr-fleet/references/brief.md and start again')
                argv = ['start', str(job), 'build-x', '--kind', kind, '--pane', 'w9:p3', '--brief', str(brief)]
                with mock.patch.dict(os.environ, {'HERDR': herdr}):
                    with self.assertRaises(ValueError) as refused:
                        fj.start(job, 'build-x', kind, 'w9:p3', brief, yolo_in=job.parent)
                    self.assertEqual(str(refused.exception), message)
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(fj.main(argv), 2)
                self.assertEqual(stderr.getvalue(), 'fleet-job start: ' + message + '\n')
                self.assertFalse(log.exists(), 'not even a Herdr read should run')
                self.assertFalse((job / 'hooks').exists())
                self.assertEqual((job / 'agents.tsv').read_bytes(), before)
                self.assertNotIn('build-x', fj.roster(job)[0])

    def test_stampede_start_missing_done_when_exits_2_and_starts_nothing(self):
        job = job_with([('lead-demo', 'claude')])
        brief = valid_brief(job, omit=('Done when',))
        herdr, log = fake_herdr(job.parent)
        result = subprocess.run([str(ROOT / 'scripts/stampede'), 'start', str(job), 'build-x', '--kind', 'claude',
                                 '--pane', 'w9:p3', '--brief', str(brief)], capture_output=True, text=True,
                                env={**os.environ, 'HERDR': herdr})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, f'fleet-job start: brief {brief} is missing: Done when; '
                         'fill them in on skills/herdr-fleet/references/brief.md and start again\n')
        self.assertFalse(log.exists())
        self.assertFalse((job / 'hooks/build-x.json').exists())
        self.assertNotIn('build-x', fj.roster(job)[0])

    def test_an_empty_section_is_missing_before_any_level_heading(self):
        job = job_with([('lead-demo', 'claude')])
        text = valid_brief(job).read_text()
        for next_heading in ('# Notes', '###### Notes'):
            with self.subTest(next_heading=next_heading):
                empty = text.replace('## Goal\nDo the assigned work.\n', '## Goal\n \t\n' + next_heading + '\nOther context.\n')
                self.assertEqual(fj.missing_sections(empty), ['Goal'])
        self.assertEqual(fj.missing_sections(text.replace('## If blocked\nDo the assigned work.\n', '## If blocked\n \t\n')),
                         ['If blocked'])

    def test_heading_levels_case_and_title_suffixes_are_accepted(self):
        job = job_with([('lead-demo', 'claude')])
        text = valid_brief(job).read_text().replace('## Constraints', '## Constraints and anti-goals')
        for level in range(1, 7):
            with self.subTest(level=level):
                self.assertEqual(fj.missing_sections(text.replace('## ', '#' * level + ' ').upper()), [])
        self.assertEqual(fj.missing_sections(text.replace('## Goal', '####### Goal')), ['Goal'])
        self.assertEqual(fj.missing_sections(text.replace('## Goal', 'Goal:')), ['Goal'])

    def test_a_missing_brief_file_is_refused_without_side_effects(self):
        from unittest import mock
        job = job_with([('lead-demo', 'claude')])
        brief = job / 'briefs/missing.md'
        before = (job / 'agents.tsv').read_bytes()
        herdr, log = fake_herdr(job.parent)
        with mock.patch.dict(os.environ, {'HERDR': herdr}), self.assertRaises(ValueError) as refused:
            fj.start(job, 'build-x', 'claude', 'w9:p3', brief)
        self.assertEqual(str(refused.exception), f'brief {brief} does not exist')
        self.assertFalse(log.exists())
        self.assertFalse((job / 'hooks').exists())
        self.assertEqual((job / 'agents.tsv').read_bytes(), before)

    def test_a_restarted_lead_accepts_its_generated_one_paragraph_brief(self):
        out, job, _ = Fixes.run_new(self, 'idle')
        lead = fj.roster(job)[1]
        brief = job / 'briefs' / (lead + '.md')
        self.assertEqual(fj.missing_sections(brief.read_text()), list(fj.BRIEF_SECTIONS))
        error, log = ReviewRound1.start(self, job, lead, job.parent)
        self.assertIsNone(error)
        self.assertIn('agent start ' + lead, log)
        self.assertIn('Read ' + str(brief), (job / 'inbox' / (lead + '.md')).read_text())

    def test_the_template_matches_the_required_sections_and_is_complete(self):
        import re
        template = (SCRIPTS.parent / 'references/brief.md').read_text()
        self.assertEqual(tuple(re.findall(r'^## (.+)$', template, re.M)), fj.BRIEF_SECTIONS)
        self.assertEqual(fj.missing_sections(template), [])


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
        extra = dict(env)
        # new writes ~/.config/herdr-events/jobs/<workspace>; keep that off a real home
        if 'HOME' not in extra and not os.environ.get('HOME', '').startswith(tempfile.gettempdir()):
            extra['HOME'] = tempfile.mkdtemp()
        root = Path(extra.get('FLEET_JOBS_ROOT', repo.parent / 'herdr-jobs'))
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'HERDR': herdr, 'FLEET_JOBS_ROOT': str(root), **extra}), contextlib.redirect_stdout(out):
            fj.new(ask, 'w9', **kw)
        return out.getvalue(), max((root / 'jobs').iterdir(), key=lambda j: j.stat().st_mtime_ns), log.read_text()

    def test_new_puts_the_job_under_the_jobs_root_and_keeps_the_repo_as_cwd(self):
        from datetime import date
        out, job, log = self.run_new('idle')
        repo = job.parents[2] / 'repo'
        self.assertEqual(job, job.parents[2] / 'herdr-jobs/jobs' / (date.today().isoformat() + '-local-fix-login-bug'))
        self.assertEqual((job / 'workdir').read_text(), str(repo) + '\n')
        self.assertEqual(list(repo.iterdir()), [])                       # nothing Herdr-related lands in the repo
        self.assertIn('tab create --workspace w9 --cwd ' + str(repo) + ' ', log)
        self.assertIn('--add-dir ' + str(job) + ' ', log)               # the lead may write its job folder outside its cwd
        self.assertTrue(out.endswith('lead-fix-login-bug ' + str(job) + '\n'))

    def test_the_jobs_root_defaults_to_code_herdr_jobs(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'FLEET_JOBS_ROOT': ''}):
            self.assertEqual(fj.jobs_root(), Path.home() / 'code/herdr-jobs')
        with mock.patch.dict(os.environ, {'FLEET_JOBS_ROOT': '~/elsewhere'}):
            self.assertEqual(fj.jobs_root(), Path.home() / 'elsewhere')

    def test_the_same_ask_twice_the_same_day_gets_its_own_job_and_a_valid_lead(self):
        root = Path(tempfile.mkdtemp())
        first = self.run_new('idle', {'FLEET_JOBS_ROOT': str(root)})[1]
        out, second, log = self.run_new('idle', {'FLEET_JOBS_ROOT': str(root)})
        self.assertEqual(second.name, first.name + '-2')
        self.assertIn('agent start lead-fix-login-bug-2 ', log)
        self.assertEqual((second / 'lead').read_text(), 'lead-fix-login-bug-2\n')
        root, name = Path(tempfile.mkdtemp()), 'a' * 27       # lead-<27> is exactly 32
        self.run_new('idle', {'FLEET_JOBS_ROOT': str(root)}, name=name)
        self.run_new('idle', {'FLEET_JOBS_ROOT': str(root)}, name=name)
        leads = sorted((j / 'lead').read_text().strip() for j in (root / 'jobs').iterdir())
        self.assertEqual(leads, ['lead-' + 'a' * 25 + '-2', 'lead-' + name])
        self.assertTrue(all(fj.NAME.fullmatch(l) for l in leads))

    def test_claude_and_cursor_workers_may_write_the_job_folder(self):
        job = Path(tempfile.mkdtemp()) / 'job'
        for kind in ('claude', 'cursor'):
            args = fj.cli_args(job, 'build-x', kind, None, None, [])
            self.assertEqual(args[args.index('--add-dir') + 1], str(job.absolute()), kind)

    def test_new_starts_the_lead_on_the_table_model(self):
        _, _, log = self.run_new('idle')
        self.assertIn('--model claude-opus-5-5 --effort xhigh', log)
        _, _, log = self.run_new('idle', {'FLEET_LEAD_MODEL': 'claude-fable-5-1', 'FLEET_LEAD_EFFORT': 'max'})
        self.assertIn('--model claude-fable-5-1 --effort max', log)

    def test_new_forks_the_planning_chat_into_the_lead_but_not_into_the_reopen_record(self):
        sid = '0b5f1c2e-7d3a-4e8b-9c41-2a6f8e9d1b37'
        _, job, log = self.run_new('idle', fork=sid)
        self.assertIn(f'--kind claude --pane w9:p2 --timeout 90000 -- --resume {sid} --fork-session --permission-mode auto', log)
        self.assertIn('planning chat', (job / 'briefs/lead-fix-login-bug.md').read_text())
        self.assertNotIn(sid, (job / 'agents.tsv').read_text())
        _, job, log = self.run_new('idle')
        self.assertNotIn('--resume', log)
        self.assertNotIn('planning chat', (job / 'briefs/lead-fix-login-bug.md').read_text())

    def test_new_refuses_a_fork_that_is_not_a_session_id(self):
        with self.assertRaises(ValueError) as refused:
            self.run_new('idle', fork='--dangerously-skip-permissions')
        self.assertIn('--fork takes a Claude session id', str(refused.exception))

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
        brief = job / 'briefs' / (agent + '.md')
        if agent != fj.roster(job)[1]:
            brief = valid_brief(job, agent)
        error = None
        with mock.patch.dict(os.environ, {'HERDR': herdr}), contextlib.redirect_stdout(io.StringIO()):
            try:
                fj.start(job, agent, 'claude', 'w9:p3', str(brief), **kw)
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
        brief = valid_brief(job, agent)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'HERDR': herdr}), contextlib.redirect_stdout(out):
            fj.start(job, agent, 'claude', 'w9:p3', str(brief))
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


class Gates(unittest.TestCase):
    """Gate questions go back to whoever started the job; only the owner's recorded yes, at that commit, opens one."""
    SHA = 'a' * 40

    def setUp(self):
        from unittest import mock
        self.home = Path(tempfile.mkdtemp())
        routes = self.home / 'routes'
        routes.mkdir()
        (routes / 'alpha').write_text('URL=http://127.0.0.1:9/never\n')  # queued only: no flusher in this HOME
        env = {'HOME': str(self.home), 'HERDR_EVENTS_ROUTES_DIR': str(routes), 'HERDR_EVENTS_HOME': str(self.home / 'events'),
               'HERDR_EVENTS_OWNER': '', 'HERDR_WORKSPACE_ID': 'w9', 'HERDR_PANE_ID': 'w9:p1'}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        self.job = job_with([('lead-demo', 'claude')])

    def bot_job(self):
        (self.job / 'owner').write_text('alpha\n')
        return self.job

    def quiet(self, call, *args):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            call(*args)
        return out.getvalue()

    def gate_ids(self):
        return sorted(p.stem for p in (self.job / 'gates').glob('*.json'))

    def approve(self, ident, sha):
        from unittest import mock
        with mock.patch.object(fj, 'inside_herdr', return_value=False):
            return self.quiet(fj.approve_gate, self.job, ident, sha, 'owner in Grok Bot chat')

    def test_new_records_the_bot_that_started_the_job(self):
        tag = self.home / '.config/herdr-events/owners/w9'
        tag.parent.mkdir(parents=True)
        cases = [({'HERDR_EVENTS_OWNER': 'alpha'}, 'alpha'), ({}, ''), ({'TAG': 'owner=alpha\n'}, 'alpha')]
        for env, owner in cases:
            if 'TAG' in env:
                tag.write_text(env.pop('TAG'))
            _, job, _ = Fixes.run_new(self, 'idle', env)
            brief = (job / 'briefs/lead-fix-login-bug.md').read_text()
            self.assertEqual((job / 'owner').read_text().strip() if (job / 'owner').exists() else '', owner)
            self.assertIn('gate-ok', brief)
            self.assertIn('goes back to alpha' if owner else 'your own question card', brief)

    def test_new_marks_the_workspace_and_tells_the_lead_to_finish(self):
        home = Path(tempfile.mkdtemp())
        _, job, _ = Fixes.run_new(self, 'idle', {'HOME': str(home)})
        marker = home / '.config/herdr-events/jobs/w9'
        self.assertEqual(marker.read_text().strip(), str(job.absolute()))
        self.assertEqual((job / 'workspace').read_text().strip(), 'w9')
        self.assertIn('fleet-job finish ' + str(job) + ' "<one line on where it ended>" once',
                      (job / 'briefs/lead-fix-login-bug.md').read_text())

    def test_finish_posts_one_done_and_clears_the_marker(self):
        self.bot_job()
        (self.job / 'workspace').write_text('w9\n')
        marker = self.home / '.config/herdr-events/jobs/w9'
        marker.parent.mkdir(parents=True)
        marker.write_text(str(self.job.absolute()) + '\n')
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'finish', str(self.job), 'shipped the fix'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FINISHED ' + str(self.job.absolute()), result.stdout)
        queued = [json.loads(p.read_text()) for p in (self.home / 'events/queue').glob('*.json')]
        self.assertEqual(len(queued), 1)
        event = queued[0]['payload']
        self.assertEqual(queued[0]['route'], 'alpha')
        self.assertEqual((event['source'], event['state'], event['summary'], event['owner']),
                         ('stampede', 'done', 'shipped the fix', 'alpha'))
        self.assertNotIn('pane', event)
        self.assertFalse(marker.exists())
        self.assertEqual((self.job / 'finished').read_text().strip(), 'shipped the fix')
        again = subprocess.run([str(SCRIPTS / 'fleet-job'), 'finish', str(self.job), 'again'],
                               capture_output=True, text=True)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(list((self.home / 'events/queue').glob('*.json'))), 1)

    def test_finish_on_a_local_job_clears_the_marker(self):
        (self.job / 'workspace').write_text('w9\n')
        marker = self.home / '.config/herdr-events/jobs/w9'
        marker.parent.mkdir(parents=True)
        marker.write_text(str(self.job.absolute()) + '\n')
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'finish', str(self.job), 'stopped for good'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        queue = self.home / 'events/queue'
        queued = list(queue.glob('*.json')) if queue.is_dir() else []
        self.assertEqual(queued, [])  # no route of its own: the ordinary relay logs it

    def test_a_bot_started_gate_posts_a_gate_event(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(fj.ask_gate, self.job, 'Push the docs branch', self.SHA)  # a second gate at once is its own event
        queued = [json.loads(p.read_text()) for p in sorted((self.home / 'events/queue').glob('*.json'))]
        self.assertEqual(len(queued), 2)
        event = next(q['payload'] for q in queued if q['payload']['pr'] == 12)
        self.assertEqual(queued[0]['route'], 'alpha')
        self.assertEqual((event['source'], event['state'], event['owner']), ('stampede', 'gate', 'alpha'))
        self.assertEqual((event['action'], event['sha'], event['options']), ('Merge PR #12 into main', self.SHA, ['yes', 'no']))
        self.assertIn(event['gate'], self.gate_ids())
        self.assertIn('approve-gate ' + str(self.job.absolute()) + ' ' + event['gate'] + ' --sha ' + self.SHA, event['approve'])
        self.assertFalse((self.job / 'asks').exists(), 'a bot-started gate never puts a card on the phone')
        self.assertNotIn('pane', event)  # the flusher keeps only a pane's newest event; a gate must never be dropped
        self.assertEqual(event['lead_pane'], 'w9:p1')

    def test_a_queued_gate_survives_a_later_turn_end_from_the_lead_pane(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(fj.ask_gate, self.job, 'Push the docs branch', self.SHA)
        tag = self.home / '.config/herdr-events/owners/w9'  # the bot tagged the workspace, so the lead's turn ends go to it too
        tag.parent.mkdir(parents=True)
        tag.write_text('owner=alpha\n')
        post = ROOT / 'skills/grokbot-herdr/scripts/herdr-event-post'
        subprocess.run([str(post), 'source=claude', 'state=Stop', 'pane=w9:p1'], check=True)
        queue = self.home / 'events/queue'
        self.assertEqual(len(list(queue.glob('*.json'))), 3)
        subprocess.run([str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], check=True, timeout=30)  # the route is down
        states = sorted(json.loads(p.read_text())['payload']['state'] for p in queue.glob('*.json'))
        self.assertEqual(states, ['Stop', 'gate', 'gate'])

    def test_a_question_in_a_bot_started_job_goes_to_the_bot(self):
        self.bot_job()
        self.quiet(fj.ask, self.job, 'Keep the file in the repo root?', ['Yes', 'No'])
        self.quiet(fj.ask, self.job, 'And the second one?', [])  # a second question at once is its own event
        events = [json.loads(p.read_text())['payload'] for p in sorted((self.home / 'events/queue').glob('*.json'))]
        self.assertEqual([e['state'] for e in events], ['question', 'question'])
        first = next(e for e in events if e['options'])
        self.assertEqual((first['owner'], first['question'], first['options']), ('alpha', 'Keep the file in the repo root?', ['Yes', 'No']))
        self.assertIn('tell ' + str(self.job.absolute()) + ' lead', first['answer'])
        self.assertFalse((self.job / 'asks').exists(), 'no phone card in a bot-started job')
        with self.assertRaises(ValueError):
            fj.cancel(self.job, first['ask'])  # nothing to cancel on the phone: one plain refusal

    def test_the_owners_yes_is_recorded_and_matched_to_the_commit(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job, ident, self.SHA)  # nothing recorded yet
        self.approve(ident, self.SHA)
        self.assertIn('APPROVED ' + ident + ' by owner in Grok Bot chat', self.quiet(fj.gate_ok, self.job, ident, self.SHA))
        self.assertIn('GATE ' + ident + ' APPROVED by owner in Grok Bot chat', (self.job / 'inbox/lead-demo.md').read_text())

    def test_a_stale_commit_is_refused(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):
            self.approve(ident, 'b' * 40)  # the bot's yes was for another commit
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        self.approve(ident, self.SHA)
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job, ident, 'c' * 40)  # a push after the yes withdraws it
        with self.assertRaises(ValueError):
            fj.ask_gate(self.job, 'Merge', 'abc123')  # a short sha could match more than one commit

    def test_an_agents_own_yes_is_refused(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):  # HERDR_PANE_ID is set: a command from a Herdr pane
            fj.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat')
        env = {k: v for k, v in os.environ.items() if not k.startswith('HERDR_')}
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'approve-gate', str(self.job), ident, '--sha', self.SHA, '--by', 'me'],
                                env={**env, 'HERDR_ENV': '1'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("an agent's own say-so never counts", result.stderr)
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        fake = Path(tempfile.mkdtemp()) / 'herdr'  # a process named herdr and its child: a pane's tree, HERDR_* stripped
        fake.symlink_to('/bin/bash')
        server = subprocess.Popen([str(fake), '-c', 'sleep 30; true'], stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.kill)
        deadline = time.time() + 10
        while not subprocess.run(['pgrep', '-P', str(server.pid)], capture_output=True, text=True).stdout.strip():
            self.assertLess(time.time(), deadline, 'the fake server never started its child')
            time.sleep(0.05)
        child = int(subprocess.run(['pgrep', '-P', str(server.pid)], capture_output=True, text=True).stdout.split()[0])
        self.addCleanup(lambda: subprocess.run(['kill', str(child)], capture_output=True))
        self.assertTrue(fj.inside_herdr({}, child))
        self.assertFalse(fj.inside_herdr({}, 1))

    def test_a_local_gate_refuses_approve_gate_and_ignores_a_swapped_command(self):
        from unittest import mock
        with mock.patch.object(fj, 'ask_background'):
            self.quiet(fj.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        with mock.patch.object(fj, 'inside_herdr', return_value=False), self.assertRaises(PermissionError):
            fj.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat')
        no = Asks.fake_ask(self, 'exit 1')
        yes = Asks.fake_ask(self, 'echo yes')
        with mock.patch.object(fj, 'ASK_CMD', no):
            fj.ask_now(self.job, 'Gate?', [], yes, ident)  # a hidden _ask with its own --command never opens a gate
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())

    def test_a_local_job_asks_fleet_ask_cmd(self):
        args = Path(tempfile.mkdtemp()) / 'args'
        fake = Asks.fake_ask(self, 'printf "%s\\n" "$@" > ' + str(args) + '; echo yes')
        env = {k: v for k, v in os.environ.items() if not k.startswith('HERDR_')}
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'ask', str(self.job), '--gate', '--sha', self.SHA, '--pr', '3',
                                 'Merge PR #3 into main'], env={**env, 'FLEET_ASK_CMD': fake}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        ident = self.gate_ids()[0]
        deadline = time.time() + 10
        while not (self.job / 'gates' / (ident + '.approved')).exists():
            self.assertLess(time.time(), deadline, 'the local gate never recorded the yes')
            time.sleep(0.05)
        self.assertIn('Gate ' + ident + ': Merge PR #3 into main (PR #3) at ' + self.SHA[:12] + '?', args.read_text())
        self.assertIn('by owner, through fake-ask', self.quiet(fj.gate_ok, self.job, ident, self.SHA))
        refused = subprocess.run([str(SCRIPTS / 'fleet-job'), 'ask', str(self.job), '--gate', '--sha', self.SHA, '--option', 'a',
                                  '--option', 'b', 'Merge'], env=env, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2)

    # review-codex, round 1

    def test_p1_a_hidden_ask_asks_the_gates_own_question_and_never_a_bot_gate(self):
        from unittest import mock
        with mock.patch.object(fj, 'ask_background'):
            self.quiet(fj.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        args = Path(tempfile.mkdtemp()) / 'args'
        fake = Asks.fake_ask(self, 'printf "%s\\n" "$@" > ' + str(args) + '; echo yes')
        with mock.patch.object(fj, 'ASK_CMD', fake):
            fj.ask_now(self.job, 'Continue the read-only review?', ['Sure'], None, ident)
        self.assertIn('Gate ' + ident + ': Merge PR #3 into main (PR #3) at', args.read_text())
        self.assertNotIn('read-only review', args.read_text())
        self.assertNotIn('Sure', args.read_text())
        (self.job / 'gates' / (ident + '.json')).write_text(json.dumps({**fj.load_gate(self.job, ident), 'route': 'alpha'}))
        args.unlink()
        with mock.patch.object(fj, 'ASK_CMD', fake), self.assertRaises(PermissionError):
            fj.ask_now(self.job, 'Merge?', [], None, ident)  # a bot's gate never goes to the phone
        self.assertFalse(args.exists())

    def test_p1_a_gate_changed_while_asked_is_not_recorded(self):
        from unittest import mock
        with mock.patch.object(fj, 'ask_background'):
            self.quiet(fj.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        record = self.job / 'gates' / (ident + '.json')
        swap = json.dumps({**fj.load_gate(self.job, ident), 'action': 'Deploy to production'})
        fake = Asks.fake_ask(self, "printf '%s' " + shlex.quote(swap) + ' > ' + str(record) + '; echo yes')
        with mock.patch.object(fj, 'ASK_CMD', fake):
            fj.ask_now(self.job, '', [], None, ident)
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        self.assertIn('GATE NOT RECORDED', (self.job / 'inbox/lead-demo.md').read_text())

    def test_p1_no_route_for_the_bot_is_a_refusal_not_a_lost_gate(self):
        self.bot_job()
        (self.home / 'routes/alpha').unlink()
        (self.home / 'routes/default').write_text('URL=http://127.0.0.1:9/another-bot\n')  # never a fallback
        with self.assertRaises(ValueError):
            fj.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        with self.assertRaises(ValueError):
            fj.ask(self.job, 'Keep it?', [])
        self.assertFalse((self.job / 'gates').exists() and any((self.job / 'gates').iterdir()))
        self.assertFalse((self.home / 'events/queue').exists() and any((self.home / 'events/queue').iterdir()))

    def test_p2_gate_ok_needs_the_record_of_that_very_gate(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(fj.ask_gate, self.job, 'Send a draft to the owner', self.SHA)
        first, second = self.gate_ids()
        self.approve(first, self.SHA)
        (self.job / 'gates' / (second + '.approved')).write_text((self.job / 'gates' / (first + '.approved')).read_text())
        with self.assertRaises(PermissionError):
            fj.gate_ok(self.job, second, self.SHA)

    def test_p2_a_malformed_starter_is_refused_before_any_job_exists(self):
        tag = self.home / '.config/herdr-events/owners/w9'
        tag.parent.mkdir(parents=True)
        tag.write_text('owner=alpha\n')
        for env, bad_tag in (({'HERDR_EVENTS_OWNER': 'Alpha'}, None), ({}, 'owner=../escape\n')):
            if bad_tag:
                tag.write_text(bad_tag)
            with self.assertRaises(ValueError):
                Fixes.run_new(self, 'idle', env)

    # review-codex, round 2
    def test_r2_a_queued_gate_waits_out_a_route_that_loses_its_url(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        (self.home / 'routes/alpha').unlink()  # the owner rotates the route while the gate waits
        subprocess.run([str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], check=True, timeout=30)
        self.assertEqual([json.loads(p.read_text())['payload']['state'] for p in (self.home / 'events/queue').glob('*.json')], ['gate'])

    # review-codex, round 3
    def test_r3_a_held_or_expired_question_or_gate_tells_its_lead_once(self):
        self.bot_job()
        self.quiet(fj.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(fj.ask, self.job, 'Keep it?', [])
        (self.home / 'routes/alpha').unlink()
        flush, queue = [str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], self.home / 'events/queue'
        for _ in range(2):  # every flush holds them; the lead hears it once
            subprocess.run(flush, check=True, timeout=30)
        told = (self.job / 'inbox.log').read_text().splitlines()
        self.assertEqual(sorted(line.split()[1] for line in told), ['gate', 'question'])
        self.assertTrue(all(line.startswith('UNDELIVERED ') and 'held' in line and 'for alpha' in line for line in told))
        curl = self.home / '.local/bin/curl'  # the route comes back: both go out, the lead hears nothing more
        curl.parent.mkdir(parents=True)
        curl.write_text('#!/bin/sh\ncat >/dev/null; printf 200\n')
        curl.chmod(0o755)
        (self.home / 'routes/alpha').write_text('URL=http://127.0.0.1:9/never\n')
        subprocess.run(flush, check=True, timeout=30)
        self.assertEqual((list(queue.glob('*.json')), list((self.home / 'events/held').iterdir())), ([], []))
        self.quiet(fj.ask_gate, self.job, 'Push the docs branch', self.SHA)
        (self.home / 'routes/alpha').unlink()
        subprocess.run(flush, check=True, timeout=30)
        for path in queue.glob('*.json'):
            os.utime(path, (time.time() - 86460,) * 2)
        subprocess.run(flush, check=True, timeout=30)
        last = (self.job / 'inbox.log').read_text().splitlines()[-1]
        self.assertTrue(last.startswith('UNDELIVERED gate ') and 'after 24 h' in last, last)
        self.assertEqual(len(list((self.home / 'events/dead').glob('*.json'))), 1)

    def test_r2_a_route_with_no_effective_url_or_no_queue_is_a_refusal(self):
        self.bot_job()
        (self.home / 'routes/alpha').write_text('URL="" # disabled during route rotation\n')
        with self.assertRaises(ValueError):
            fj.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        (self.home / 'routes/alpha').write_text('URL=http://127.0.0.1:9/never\n')
        blocked = self.home / 'not-a-folder'
        blocked.write_text('a file where the queue should be')
        from unittest import mock
        with mock.patch.dict(os.environ, {'HERDR_EVENTS_HOME': str(blocked)}), self.assertRaises(ValueError):
            fj.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        with mock.patch.dict(os.environ, {'HERDR_EVENTS_HOME': str(blocked)}), self.assertRaises(ValueError):
            fj.ask(self.job, 'Keep it?', [])
        self.assertEqual(self.gate_ids(), [], 'a gate its bot never hears is taken back')

    def test_r2_each_answer_names_its_question(self):
        self.bot_job()
        self.quiet(fj.ask, self.job, 'Keep the first file?', ['Yes', 'No'])
        self.quiet(fj.ask, self.job, 'Keep the second file?', ['Yes', 'No'])
        events = [json.loads(p.read_text())['payload'] for p in (self.home / 'events/queue').glob('*.json')]
        for event in events:
            self.assertIn('ANSWER ' + event['ask'] + ' ' + event['question'] + ': ', event['answer'])
        self.assertEqual(len({event['answer'] for event in events}), 2)


def screen_herdr(screen):
    """A fake herdr whose `agent read` shows this screen; every other call answers an empty result."""
    folder = Path(tempfile.mkdtemp())
    (folder / 'screen.txt').write_text(screen)
    script = folder / 'herdr'
    script.write_text('#!/bin/bash\ncase "$1 $2" in\n  "agent read") cat ' + str(folder / 'screen.txt') + ';;\n'
                      '  *) echo \'{"result":{}}\';;\nesac\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


CARD = 'Which nudge copy?\n❯ 1. Option A\n  2. Option B\n  4. Type something.\nEnter to select · ↑/↓ to navigate · Esc to cancel\n'


class FrontDoor(unittest.TestCase):
    """A chat outside Herdr stays the owner's only contact: the lead posts to <job>/outbox and the front door relays it."""
    def setUp(self):
        from unittest import mock
        self.job = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        (self.job / 'front-door').write_text('relay\n')
        patch = mock.patch.dict(os.environ, {'HERDR': screen_herdr('❯ \n')})
        patch.start()
        self.addCleanup(patch.stop)

    def quiet(self, fn, *args):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = fn(*args)
        return result, out.getvalue()

    def test_post_numbers_items_copies_files_and_logs_one_line(self):
        shot = Path(tempfile.mkdtemp()) / 'after.png'
        shot.write_bytes(b'png')
        _, out = self.quiet(fj.post, self.job, 'Screens for the nudge', [str(shot)])
        self.assertIn('POSTED 001', out)
        self.assertEqual((self.job / 'outbox/001/after.png').read_bytes(), b'png')
        self.assertIn(str(self.job.absolute() / 'outbox/001/after.png'), (self.job / 'outbox/001.md').read_text())
        self.quiet(fj.post, self.job, 'Report ready', [])
        self.assertEqual((self.job / 'outbox.log').read_text().splitlines(),
                         ['001 post Screens for the nudge', '002 post Report ready'])
        with self.assertRaises(ValueError):
            fj.post(self.job, 'missing', ['/nonexistent/file.png'])

    def test_wait_prints_unseen_items_once_then_times_out(self):
        self.quiet(fj.post, self.job, 'PLAN READY: two lanes', [])
        code, out = self.quiet(fj.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        self.assertIn('# 001 post', out)
        self.assertIn('PLAN READY: two lanes', out)
        code, out = self.quiet(fj.wait, self.job, 0, 0)
        self.assertEqual(code, 3)
        self.assertIn('TIMEOUT', out)

    def test_wait_and_tell_see_a_lead_held_at_a_card(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'HERDR': screen_herdr(CARD)}):
            code, out = self.quiet(fj.wait, self.job, 5, 0)
            self.assertEqual(code, 0)
            self.assertIn('BLOCKED_ON_CARD lead-demo', out)
            self.assertIn('Which nudge copy?', out)
            code, out = self.quiet(fj.tell, self.job, 'lead', 'ANSWER: option B')
        self.assertEqual(code, 3)
        self.assertIn('BLOCKED_ON_CARD lead-demo', out)
        self.assertNotIn('DELIVERED', out)
        self.assertIn('ANSWER: option B', (self.job / 'inbox/lead-demo.md').read_text())  # still queued for after the card
        code, out = self.quiet(fj.tell, self.job, 'lead', 'next')
        self.assertIsNone(code)
        self.assertIn('DELIVERED lead-demo', out)

    def test_a_question_goes_to_the_outbox_not_the_phone(self):
        ident, out = self.quiet(fj.ask, self.job, 'Customer.io copy too?', ['yes', 'no'])
        self.assertIn('posted to the front door as outbox 001', out)
        item = (self.job / 'outbox/001.md').read_text()
        self.assertIn('Customer.io copy too?\n- yes\n- no', item)
        self.assertIn(f'ANSWER {ident}', item)
        self.assertFalse((self.job / 'asks').exists())  # no phone card was started

    def test_a_gate_goes_to_the_outbox_and_the_front_door_records_the_quoted_yes(self):
        from unittest import mock
        sha = 'a' * 40
        _, out = self.quiet(fj.ask_gate, self.job, 'mark PR #444 ready for review', sha, 444)
        ident = next((self.job / 'gates').glob('*.json')).stem
        item = (self.job / 'outbox/001.md').read_text()
        self.assertIn(f'# 001 gate', item)
        self.assertIn(f'approve-gate {self.job.absolute()} {ident} --sha {sha}', item)
        self.assertEqual(fj.load_gate(self.job, ident)['route'], 'front-door')
        with mock.patch.object(fj, 'inside_herdr', return_value=False):
            self.quiet(fj.approve_gate, self.job, ident, sha, "owner in desktop chat: 'push the PR'")
        _, out = self.quiet(fj.gate_ok, self.job, ident, sha)
        self.assertIn("APPROVED " + ident + " by owner in desktop chat: 'push the PR'", out)
        with mock.patch.object(fj, 'inside_herdr', return_value=True), self.assertRaises(PermissionError):
            fj.approve_gate(self.job, ident, sha, 'the lead itself')

    def test_the_leads_own_card_and_files_become_posts(self):
        card = {'tool_input': {'questions': [{'question': 'Ready + DM?', 'options': [{'label': 'Yes', 'description': 'both'}]}]}}
        decision = json.loads(fj.ask_lead(self.job, 'lead-demo', card))['hookSpecificOutput']
        self.assertEqual(decision['permissionDecision'], 'deny')
        self.assertIn('outbox 001', decision['permissionDecisionReason'])
        self.assertIn('Ready + DM?\n- Yes: both', (self.job / 'outbox/001.md').read_text())
        shot = Path(tempfile.mkdtemp()) / 'plan.md'
        shot.write_text('the plan')
        decision = json.loads(fj.send_file(self.job, 'lead-demo', {'tool_input': {'files': [str(shot)], 'caption': 'The plan'}}))
        self.assertEqual(decision['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual((self.job / 'outbox/002/plan.md').read_text(), 'the plan')
        self.assertEqual(fj.send_file(self.job, 'build-x', {'tool_input': {'files': [str(shot)]}}), '{}')  # only the lead's
        (self.job / 'front-door').unlink()
        self.assertEqual(fj.ask_lead(self.job, 'lead-demo', card), '{}')   # a job without a front door: the card goes ahead
        self.assertEqual(fj.send_file(self.job, 'lead-demo', {'tool_input': {'files': [str(shot)]}}), '{}')

    def test_a_plan_is_approved_only_once_it_was_posted_as_it_stands(self):
        from unittest import mock
        patch = mock.patch.object(fj, 'inside_herdr', return_value=False)
        patch.start()
        self.addCleanup(patch.stop)
        plan = self.job / 'plan.md'
        plan.write_text('Size: big\n# Plan v1\n')
        with self.assertRaises(PermissionError) as refused:
            fj.approve(self.job, "owner in desktop chat: 'ok - lets go'")
        self.assertIn('has not been shown this plan', str(refused.exception))
        self.quiet(fj.post, self.job, 'PLAN READY', [str(plan)])
        self.quiet(fj.approve, self.job, "owner in desktop chat: 'approve as written'")
        self.assertIn('approve as written', (self.job / 'approved').read_text())
        plan.write_text('Size: big\n# Plan v2\n')   # changed after the owner saw it
        with self.assertRaises(PermissionError):
            fj.approve(self.job, 'owner')
        plan.write_text('Size: big\n# Plan v1\n')
        (self.job / 'fleet-plan.md').write_text('layout, never posted')   # the detailed plan counts too
        with self.assertRaises(PermissionError) as refused:
            fj.approve(self.job, 'owner')
        self.assertIn('fleet-plan.md', str(refused.exception))

    def test_the_lead_cannot_approve_its_own_plan_in_a_front_door_job(self):
        from unittest import mock
        (self.job / 'plan.md').write_text('Size: big\n')
        self.quiet(fj.post, self.job, 'PLAN READY', [str(self.job / 'plan.md')])
        with mock.patch.object(fj, 'inside_herdr', return_value=True), self.assertRaises(PermissionError) as refused:
            fj.approve(self.job, 'the lead itself')
        self.assertIn('outside Herdr', str(refused.exception))
        self.assertFalse((self.job / 'approved').exists())

    def test_finish_posts_to_the_outbox_and_wait_notices_a_lead_that_is_gone(self):
        from unittest import mock
        code, out = self.quiet(fj.wait, self.job, 5, 0)   # nothing posted, lead alive: times out
        self.assertEqual(code, 3)
        self.quiet(fj.finish, self.job, 'all merged')
        self.assertIn('# 001 done', (self.job / 'outbox/001.md').read_text())
        code, out = self.quiet(fj.wait, self.job, 5, 0)
        self.assertEqual((code, '# 001 done' in out), (0, True))
        gone = Path(tempfile.mkdtemp()) / 'herdr'
        gone.write_text('#!/bin/sh\necho \'{"error":{"code":"agent_not_found"}}\'; exit 1\n')
        gone.chmod(0o755)
        with mock.patch.dict(os.environ, {'HERDR': str(gone)}):
            code, out = self.quiet(fj.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        self.assertIn('LEAD_GONE lead-demo', out)

    def test_new_with_a_front_door_writes_the_relay_brief(self):
        out, job, log = Fixes.run_new(self, 'idle', front=True, review=True)
        self.assertTrue((job / 'front-door').is_file())
        brief = (job / 'briefs/lead-fix-login-bug.md').read_text()
        self.assertIn('post it with fleet-job post', brief)
        self.assertIn('never to your pane', brief)
        self.assertIn('it goes to the front door', brief)
        self.assertIn('SendUserFile', (job / 'hooks/lead-fix-login-bug-claude.json').read_text())
        with self.assertRaises(ValueError) as refused:   # a bot-owned workspace is not a front door
            Fixes.run_new(self, 'idle', env={'HERDR_EVENTS_OWNER': 'alpha'}, front=True)
        self.assertIn('owned by the bot alpha', str(refused.exception))
        out, job, _ = Fixes.run_new(self, 'idle')
        self.assertFalse((job / 'front-door').exists())
        self.assertNotIn('never to your pane', (job / 'briefs/lead-fix-login-bug.md').read_text())
