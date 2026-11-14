"""fleet-job: messages, background questions, approval and hooks, all with fakes."""
import fcntl, json, os, shlex, stat, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/herdr-fleet/scripts'
sys.path.insert(0, str(SCRIPTS))
from stampede import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, agents as agents_, owner as owner_, hooks as hooks_, tui as tui_, relay as relay_, cli as cli_, settings as settings_
sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet import setUpModule, tearDownModule  # noqa: E402,F401: commands run in-process print status lines


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
                              for name in settings_.DEFAULTS['brief.sections'] if name not in omit))
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
        owner_.tell(job, 'build-api', 'first\nsecond')
        self.assertEqual((job / 'inbox/build-api.md').read_text(), 'first second\n')

    def test_tell_lead_resolves_the_lead(self):
        job = job_with([('lead-demo', 'claude')])
        owner_.tell(job, 'lead', 'hello')
        self.assertEqual((job / 'inbox/lead-demo.md').read_text(), 'hello\n')

    def test_tell_refuses_an_agent_outside_the_job(self):
        job = job_with([('lead-demo', 'claude')])
        with self.assertRaises(ValueError):
            owner_.tell(job, 'stranger', 'hi')


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
        self.assertEqual(owner_.ask_now(job, 'Go?', ['Yes', 'No'], command), 0)
        self.assertIn('ANSWER Go?: Yes', (job / 'inbox/lead-demo.md').read_text())

    def test_exit_3_is_reported_as_failed_with_its_code(self):
        job = job_with([('lead-demo', 'claude')])
        command = self.fake_ask('exit 3')
        owner_.ask_now(job, 'Go?', ['Yes', 'No'], command)
        self.assertIn('ASK FAILED Go?: exit 3', (job / 'inbox/lead-demo.md').read_text())

    def test_cancel_stops_the_whole_ask_and_its_child(self):
        job = job_with([('lead-demo', 'claude')])
        marker = Path(tempfile.mkdtemp()) / 'sleep.pid'
        command = self.fake_ask('sleep 300 & echo $! > ' + str(marker) + '; wait')
        ident = owner_.ask_background(job, 'Go?', ['Yes', 'No'], command)
        deadline = time.time() + 10
        while not (marker.is_file() and marker.read_text().strip()):
            self.assertLess(time.time(), deadline, 'the fake ask never started its child')
            time.sleep(0.05)
        child = int(marker.read_text())
        os.kill(child, 0)  # alive before the cancel
        owner_.cancel(job, ident)
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
        owner_.require_approval(job)  # no review file: no error

    def test_a_review_job_refuses_until_approved(self):
        job = job_with([('lead-demo', 'claude')])
        (job / 'review').write_text('owner asked to see the plan\n')
        (job / 'plan.md').write_text('# Plan: demo\n')
        with self.assertRaises(PermissionError):
            owner_.require_approval(job)
        owner_.approve(job, 'grokbot')
        owner_.require_approval(job)
        self.assertIn('Approved by grokbot', (job / 'inbox/lead-demo.md').read_text())

    def test_a_changed_plan_needs_a_new_approval(self):
        job = job_with([('lead-demo', 'claude')])
        (job / 'review').write_text('x\n')
        (job / 'plan.md').write_text('v1\n')
        owner_.approve(job, 'owner')
        (job / 'plan.md').write_text('v2\n')
        with self.assertRaises(PermissionError):
            owner_.require_approval(job)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.job = job_with([('lead-demo', 'claude'), ('build-api', 'claude')])
        (self.job / 'hooks').mkdir()
        (self.job / 'hooks/build-api.json').write_text(json.dumps({'reports': ['reports/api.md']}))

    def stop(self, active=False):
        return hooks_.claude_stop(self.job, 'build-api', {'hook_event_name': 'Stop', 'stop_hook_active': active})

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
        owner_.tell(self.job, 'lead', 'one')
        path = str(self.job / 'inbox/lead-demo.md')
        self.assertEqual(hooks_.wake(self.job, 'lead-demo', {'file_path': path}), ['one'])
        self.assertEqual(hooks_.wake(self.job, 'lead-demo', {'file_path': path}), [])

    def test_a_worker_question_becomes_a_file_and_a_line(self):
        out = hooks_.ask_lead(self.job, 'build-api', {'tool_input': {'questions': [{'question': 'Which DB?'}]}})
        self.assertEqual(json.loads(out)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('Which DB?', (self.job / 'questions/build-api.md').read_text())
        self.assertIn('QUESTION build-api: Which DB?', (self.job / 'inbox.log').read_text())

    def test_the_lead_may_ask_its_own_card(self):
        self.assertEqual(hooks_.ask_lead(self.job, 'lead-demo', {'tool_input': {'questions': []}}), '{}')

    def test_codex_and_cursor_turns_reach_the_lead(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'CODEX_HOME': codex_home(('t-main', {}))}):
            hooks_.codex_notify(self.job, 'build-api', {'type': 'agent-turn-complete', 'thread-id': 't-main', 'last-assistant-message': 'done'})
        hooks_.cursor_stop(self.job, 'build-api', {'status': 'completed'})
        log = (self.job / 'inbox.log').read_text()
        self.assertIn('TURN build-api done', log)
        self.assertEqual(log.count('TURN build-api'), 2)


class Start(unittest.TestCase):
    def test_claude_gets_auto_mode_and_its_hook_settings(self):
        job = job_with([('lead-demo', 'claude')])
        args = agents_.cli_args(job, 'build-api', 'claude', 'claude-opus-5-5', 'xhigh', ['reports/api.md'])
        self.assertEqual(args[:2], ['--permission-mode', 'auto'])
        settings = json.loads(Path(args[args.index('--settings') + 1]).read_text())
        self.assertIn('Stop', settings['hooks'])
        self.assertIn('FileChanged', settings['hooks'])
        self.assertEqual(json.loads((job / 'hooks/build-api.json').read_text())['reports'], ['reports/api.md'])

    def test_the_lead_has_no_stop_hook(self):
        job = job_with([('lead-demo', 'claude')])
        args = agents_.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True)
        settings = json.loads(Path(args[args.index('--settings') + 1]).read_text())
        self.assertNotIn('Stop', settings['hooks'])

    def test_codex_gets_approve_for_me_notify_and_the_job_dir(self):
        job = job_with([('lead-demo', 'claude')])
        args = agents_.cli_args(job, 'build-ui', 'codex', 'gpt-6.1-sol', 'xhigh', [])
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
            agents_.cli_args(job, 'build-api', 'codex', None, None, [], yolo_in=repo)
        tree = repo.parent / (repo.name + '-wt')
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', str(tree)], check=True)
        self.assertIn('--yolo', agents_.cli_args(job, 'build-api', 'codex', None, None, [], yolo_in=tree))
        self.assertIn('--dangerously-skip-permissions', agents_.cli_args(job, 'build-ui', 'claude', None, None, [], yolo_in=tree))
        with self.assertRaises(PermissionError):
            agents_.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True, yolo_in=tree)

    def test_cursor_gets_auto_review_and_a_stop_plugin(self):
        job = job_with([('lead-demo', 'claude')])
        args = agents_.cli_args(job, 'qa-ui', 'cursor', 'auto', None, [])
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
                        cli_.start(job, 'build-x', kind, 'w9:p3', brief, yolo_in=job.parent)
                    self.assertEqual(str(refused.exception), message)
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(cli_.main(argv), 2)
                self.assertEqual(stderr.getvalue(), 'stampede start: ' + message + '\n')
                self.assertFalse(log.exists(), 'not even a Herdr read should run')
                self.assertFalse((job / 'hooks').exists())
                self.assertEqual((job / 'agents.tsv').read_bytes(), before)
                self.assertNotIn('build-x', job_.roster(job)[0])

    def test_stampede_start_missing_done_when_exits_2_and_starts_nothing(self):
        job = job_with([('lead-demo', 'claude')])
        brief = valid_brief(job, omit=('Done when',))
        herdr, log = fake_herdr(job.parent)
        result = subprocess.run([str(ROOT / 'scripts/stampede'), 'start', str(job), 'build-x', '--kind', 'claude',
                                 '--pane', 'w9:p3', '--brief', str(brief)], capture_output=True, text=True,
                                env={**os.environ, 'HERDR': herdr})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, f'stampede start: brief {brief} is missing: Done when; '
                         'fill them in on skills/herdr-fleet/references/brief.md and start again\n')
        self.assertFalse(log.exists())
        self.assertFalse((job / 'hooks/build-x.json').exists())
        self.assertNotIn('build-x', job_.roster(job)[0])

    def test_an_empty_section_is_missing_before_any_level_heading(self):
        job = job_with([('lead-demo', 'claude')])
        text = valid_brief(job).read_text()
        for next_heading in ('# Notes', '###### Notes'):
            with self.subTest(next_heading=next_heading):
                empty = text.replace('## Goal\nDo the assigned work.\n', '## Goal\n \t\n' + next_heading + '\nOther context.\n')
                self.assertEqual(agents_.missing_sections(empty), ['Goal'])
        self.assertEqual(agents_.missing_sections(text.replace('## If blocked\nDo the assigned work.\n', '## If blocked\n \t\n')),
                         ['If blocked'])

    def test_heading_levels_case_and_title_suffixes_are_accepted(self):
        job = job_with([('lead-demo', 'claude')])
        text = valid_brief(job).read_text().replace('## Constraints', '## Constraints and anti-goals')
        for level in range(1, 7):
            with self.subTest(level=level):
                self.assertEqual(agents_.missing_sections(text.replace('## ', '#' * level + ' ').upper()), [])
        self.assertEqual(agents_.missing_sections(text.replace('## Goal', '####### Goal')), ['Goal'])
        self.assertEqual(agents_.missing_sections(text.replace('## Goal', 'Goal:')), ['Goal'])

    def test_a_missing_brief_file_is_refused_without_side_effects(self):
        from unittest import mock
        job = job_with([('lead-demo', 'claude')])
        brief = job / 'briefs/missing.md'
        before = (job / 'agents.tsv').read_bytes()
        herdr, log = fake_herdr(job.parent)
        with mock.patch.dict(os.environ, {'HERDR': herdr}), self.assertRaises(ValueError) as refused:
            cli_.start(job, 'build-x', 'claude', 'w9:p3', brief)
        self.assertEqual(str(refused.exception), f'brief {brief} does not exist')
        self.assertFalse(log.exists())
        self.assertFalse((job / 'hooks').exists())
        self.assertEqual((job / 'agents.tsv').read_bytes(), before)

    def test_a_restarted_lead_accepts_its_generated_one_paragraph_brief(self):
        out, job, _ = Fixes.run_new(self, 'idle')
        lead = job_.roster(job)[1]
        brief = job / 'briefs' / (lead + '.md')
        self.assertEqual(agents_.missing_sections(brief.read_text()), list(settings_.DEFAULTS['brief.sections']))
        error, log = ReviewRound1.start(self, job, lead, job.parent)
        self.assertIsNone(error)
        self.assertIn('agent start ' + lead, log)
        self.assertIn('Read ' + str(brief), (job / 'inbox' / (lead + '.md')).read_text())

    def test_the_template_matches_the_required_sections_and_is_complete(self):
        import re
        template = (SCRIPTS.parent / 'references/brief.md').read_text()
        self.assertEqual(tuple(re.findall(r'^## (.+)$', template, re.M)), tuple(settings_.DEFAULTS['brief.sections']))
        self.assertEqual(agents_.missing_sections(template), [])


class Command(unittest.TestCase):
    def test_hook_wake_exits_2_with_the_new_lines(self):
        job = job_with([('lead-demo', 'claude')])
        owner_.tell(job, 'lead', 'REPORT reports/api.md')
        payload = json.dumps({'file_path': str(job / 'inbox/lead-demo.md')})
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'hook', 'wake', str(job), '--agent', 'lead-demo'],
                                input=payload, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('REPORT reports/api.md', result.stderr)

    def test_new_job_folder_name(self):
        self.assertEqual(job_.slug('Fix the login bug on the billing page, please'), 'fix-login-bug-billing')


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
            self.code = cli_.new(ask, 'w9', **kw)
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
            self.assertEqual(job_.jobs_root(), Path.home() / 'code/herdr-jobs')
        with mock.patch.dict(os.environ, {'FLEET_JOBS_ROOT': '~/elsewhere'}):
            self.assertEqual(job_.jobs_root(), Path.home() / 'elsewhere')

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
        self.assertTrue(all(base_.NAME.fullmatch(l) for l in leads))

    def test_claude_and_cursor_workers_may_write_the_job_folder(self):
        job = Path(tempfile.mkdtemp()) / 'job'
        for kind in ('claude', 'cursor'):
            args = agents_.cli_args(job, 'build-x', kind, None, None, [])
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
        self.assertIn('BLOCKED lead-fix-login-bug: clear the startup dialog, then stampede tell ' + str(job) + ' lead "Read '
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
        worker = settings(agents_.cli_args(job, 'build-api', 'claude', None, None, []))
        lead = settings(agents_.cli_args(job, 'lead-demo', 'claude', None, None, [], lead=True))
        self.assertIn('SessionEnd', worker['hooks'])
        self.assertNotIn('SessionEnd', lead['hooks'])
        hooks_.session_end(job, 'build-api', {'reason': 'other'})
        hooks_.session_end(job, 'lead-demo', {'reason': 'other'})
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
        if agent != job_.roster(job)[1]:
            brief = valid_brief(job, agent)
        error = None
        with mock.patch.dict(os.environ, {'HERDR': herdr}), contextlib.redirect_stdout(io.StringIO()):
            try:
                cli_.start(job, agent, 'claude', 'w9:p3', str(brief), **kw)
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
        args = agents_.cli_args(job, 'build-ui', 'codex', None, None, [])
        notify = json.loads(next(a for a in args if a.startswith('notify='))[len('notify='):])
        payload = json.dumps({'type': 'agent-turn-complete', 'thread-id': 't-main', 'last-assistant-message': 'shipped'})
        result = subprocess.run(notify + [payload], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                env={**os.environ, 'CODEX_HOME': codex_home(('t-main', {}))})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('TURN build-ui shipped', (job / 'inbox.log').read_text())

    def test_r3_consuming_the_inbox_never_touches_it(self):
        job = job_with([('lead-demo', 'claude')])
        paths = hooks_.watch_paths(job, 'lead-demo', True)
        owner_.tell(job, 'lead', 'one')
        before = [os.stat(path).st_mtime_ns for path in paths]
        time.sleep(0.05)
        self.assertEqual(hooks_.wake(job, 'lead-demo', {'file_path': paths[0]}), ['one'])
        self.assertEqual(hooks_.wake(job, 'lead-demo', {'file_path': paths[0]}), [])
        self.assertEqual(hooks_.watch_paths(job, 'lead-demo', True), paths)
        self.assertEqual([os.stat(path).st_mtime_ns for path in paths], before)

    def test_r6_every_cursor_stop_reaches_the_lead_with_its_status(self):
        job = job_with([('lead-demo', 'claude'), ('qa-ui', 'cursor')])
        args = agents_.cli_args(job, 'qa-ui', 'cursor', None, None, [])
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
            self.assertEqual(hooks_.claude_stop(job, 'review-api', {'hook_event_name': 'Stop'}), '')
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
            cli_.start(job, agent, 'claude', 'w9:p3', str(brief))
        return out.getvalue()

    def test_a_startup_dialog_at_start_is_blocked_not_a_crash(self):
        job = job_with([('lead-demo', 'claude')])
        out = self.run_start(job, 'build-x', 'agent_not_ready')
        self.assertIn('BLOCKED build-x: clear the startup dialog, then stampede tell ' + str(job) + ' build-x "Read '
                      + str(job / 'briefs/build-x.md') + '"', out)
        self.assertIn('build-x', job_.roster(job)[0])  # the reopen record was written
        self.assertFalse((job / 'inbox/build-x.md').exists())

    def test_a_startup_dialog_at_new_is_blocked_not_a_crash(self):
        out, job, log = Fixes.run_new(self, 'idle', start_error='agent_not_ready')
        self.assertIn('BLOCKED lead-fix-login-bug: clear the startup dialog, then stampede tell ' + str(job) + ' lead "Read '
                      + str(job / 'briefs/lead-fix-login-bug.md') + '"', out)
        self.assertIn('lead-fix-login-bug', job_.roster(job)[0])
        self.assertFalse((job / 'inbox/lead-fix-login-bug.md').exists())

    def test_any_other_herdr_error_still_fails(self):
        job = job_with([('lead-demo', 'claude')])
        with self.assertRaises(RuntimeError):
            self.run_start(job, 'build-x', 'agent_pane_not_found')
        self.assertNotIn('build-x', job_.roster(job)[0])

    def test_codex_background_turns_never_wake_the_lead(self):
        from unittest import mock
        job = job_with([('lead-demo', 'claude'), ('review-hello', 'codex')])
        home = codex_home(('t-main', {}), ('t-sub', {'source': {'subagent': 'thread_spawn'}}),
                          ('t-child', {'parent_thread_id': 't-main'}))
        turn = lambda thread, text, **extra: hooks_.codex_notify(job, 'review-hello', {
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
    def cli(self, *args, path_herdr=None, drop=(), **more):
        env = {**{k: v for k, v in os.environ.items() if k not in drop}, **more}
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
        no_core = str(ask.parent / 'no-core.sock')   # this machine's own Herdr Core is not asked
        result = self.cli('new', '--file', str(ask), '--set', 'backend=tui', drop=('HERDR_WORKSPACE_ID',), path_herdr=herdr, HC_SOCKET=no_core)
        self.assertEqual((result.returncode, result.stderr.strip()),
                         (2, 'stampede new: new needs --workspace or --pane, or run it inside Herdr (the setting backend is tui); to run it here on Herdr Core, '
                             f'run the next line\nstampede new --core --file {ask} --cwd {ROOT}'))
        self.assertFalse(log.exists())

    def test_new_names_core_when_herdr_cannot_take_the_job_and_a_core_answers(self):
        """D2: the Herdr TUI stays the default backend. When it is not there (no target outside Herdr, a server that is
        not running, no herdr at all) and a Herdr Core answers on its socket, the error names new --core; with no core,
        or a Herdr that answers, nothing changes. Nothing is made either way."""
        import socket, threading
        folder = Path(tempfile.mkdtemp(dir='/tmp'))   # a Unix socket path is short
        ask = folder / 'ask.md'
        ask.write_text('Fix the login bug\n')
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(folder / 'core.sock'))
        server.listen(8)

        def answer():   # a core that answers hello, as herdr-event-core --alive asks
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                with conn:
                    conn.recv(4096)
                    conn.sendall(b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
        threading.Thread(target=answer, daemon=True).start()
        self.addCleanup(server.close)
        down = folder / 'herdr'
        down.write_text('#!/bin/bash\necho \'{"error":{"code":"server_not_running","message":"no herdr server is running"}}\'\nexit 1\n')
        down.chmod(0o755)
        hint = 'Herdr Core answers here, so this job can run on it: new --core --file <ask.md> [--cwd <repo>]'
        env = {'FLEET_JOBS_ROOT': str(folder / 'jobs-root'), 'HC_SOCKET': str(folder / 'core.sock')}
        cases = ((('new', '--file', str(ask), '--set', 'backend=tui'), {'drop': ('HERDR_WORKSPACE_ID',)}, 2,
                  'new needs --workspace or --pane, or run it inside Herdr (the setting backend is tui); '),
                 (('new', '--file', str(ask), '--workspace', 'w9'), {'path_herdr': down}, 1, 'no herdr server is running'),
                 (('new', '--file', str(ask), '--workspace', 'w9'), {'HERDR': str(folder / 'no-herdr')}, 2, 'did not answer'))
        for argv, kw, code, said in cases:
            with self.subTest(argv=argv[2:], kw=sorted(kw)):
                result = self.cli(*argv, **kw, **env)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn(said, result.stderr)
                self.assertIn(hint, result.stderr)
                lines = result.stderr.strip().splitlines()   # one line, and a refusal's own command to run on the next
                self.assertEqual(len(lines), 2 if lines[-1].startswith('stampede new --core ') else 1, lines)
                quiet = self.cli(*argv, **kw, **{**env, 'HC_SOCKET': str(folder / 'none.sock')})
                self.assertEqual(quiet.returncode, code)
                self.assertNotIn('Herdr Core answers', quiet.stderr)
        self.assertFalse((folder / 'jobs-root').exists())

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
        xdg = os.environ.pop('XDG_STATE_HOME', None)
        self.addCleanup(lambda: os.environ.__setitem__('XDG_STATE_HOME', xdg) if xdg is not None else None)
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
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            return self.quiet(owner_.approve_gate, self.job, ident, sha, 'owner in Grok Bot chat',
                              owner_.gate_digest(owner_.load_gate(self.job, ident)))

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
            self.assertEqual('fleet-job post ' + str(job) in brief and 'it goes to alpha' in brief, bool(owner))

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
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(owner_.ask_gate, self.job, 'Push the docs branch', self.SHA)  # a second gate at once is its own event
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
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(owner_.ask_gate, self.job, 'Push the docs branch', self.SHA)
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
        self.quiet(owner_.ask, self.job, 'Keep the file in the repo root?', ['Yes', 'No'])
        self.quiet(owner_.ask, self.job, 'And the second one?', [])  # a second question at once is its own event
        events = [json.loads(p.read_text())['payload'] for p in sorted((self.home / 'events/queue').glob('*.json'))]
        self.assertEqual([e['state'] for e in events], ['question', 'question'])
        first = next(e for e in events if e['options'])
        self.assertEqual((first['owner'], first['question'], first['options']), ('alpha', 'Keep the file in the repo root?', ['Yes', 'No']))
        self.assertIn('tell ' + str(self.job.absolute()) + ' lead', first['answer'])
        self.assertFalse((self.job / 'asks').exists(), 'no phone card in a bot-started job')
        with self.assertRaises(ValueError):
            owner_.cancel(self.job, first['ask'])  # nothing to cancel on the phone: one plain refusal

    def test_a_post_in_a_bot_started_job_goes_to_the_bot(self):
        self.bot_job()
        shot = Path(tempfile.mkdtemp()) / 'after.png'
        shot.write_bytes(b'png')
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'post', str(self.job), 'PLAN READY: two lanes', '--file', str(shot)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        item = self.job.absolute() / 'outbox/001.md'
        self.assertEqual(result.stdout.strip(), f'POSTED 001 to alpha (and {item})')
        self.assertEqual((self.job / 'outbox/001/after.png').read_bytes(), b'png')  # the outbox stays the record
        self.assertEqual((self.job / 'outbox.log').read_text().splitlines(), ['001 post PLAN READY: two lanes'])
        queued = [json.loads(p.read_text()) for p in (self.home / 'events/queue').glob('*.json')]
        self.assertEqual(len(queued), 1)
        event = queued[0]['payload']
        self.assertEqual(queued[0]['route'], 'alpha')
        self.assertEqual((event['source'], event['state'], event['owner'], event['text'], event['outbox'], event['item']),
                         ('stampede', 'post', 'alpha', 'PLAN READY: two lanes', '001', str(item)))
        self.assertEqual(event['files'], [str(self.job.absolute() / 'outbox/001/after.png')])
        self.assertNotIn('pane', event)  # the flusher keeps only a pane's newest event; a post must never be dropped
        self.quiet(owner_.post, self.job, 'Report ready', [])  # a second post is its own event, never de-duped
        self.assertEqual(len(list((self.home / 'events/queue').glob('*.json'))), 2)

    def test_a_post_the_relay_refuses_fails_loudly(self):
        (self.job / 'owner').write_text('beta\n')  # no route of its own: the strict relay refuses, never the default route
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'post', str(self.job), 'Report ready'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('POSTED', result.stdout)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        for part in ('outbox 001', 'beta never heard it', 'herdr-doctor --relay', 'post again'):
            self.assertIn(part, result.stderr)
        self.assertTrue((self.job / 'outbox/001.md').is_file())  # the item stays
        queue = self.home / 'events/queue'
        self.assertEqual(list(queue.glob('*.json')) if queue.is_dir() else [], [])

    def test_a_post_in_a_local_or_front_door_job_sends_no_event(self):
        said = self.quiet(owner_.post, self.job, 'local', [])
        self.assertIn('POSTED 001 to the outbox only', said)   # no one is told, and the line says so, with how to change it
        for part in ('no bot or front door hears it', 'HERDR_EVENTS_OWNER=<bot>', '--front-door'):
            self.assertIn(part, said)
        self.bot_job()
        (self.job / 'front-door').write_text('relay\n')  # a front door relays the outbox itself
        self.assertIn('POSTED 002 for the front door to relay', self.quiet(owner_.post, self.job, 'front', []))
        queue = self.home / 'events/queue'
        self.assertEqual(list(queue.glob('*.json')) if queue.is_dir() else [], [])

    def test_the_owners_yes_is_recorded_and_matched_to_the_commit(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):
            owner_.gate_ok(self.job, ident, self.SHA)  # nothing recorded yet
        self.approve(ident, self.SHA)
        self.assertIn('APPROVED ' + ident + ' by owner in Grok Bot chat', self.quiet(owner_.gate_ok, self.job, ident, self.SHA))
        self.assertIn('GATE ' + ident + ' APPROVED by owner in Grok Bot chat', (self.job / 'inbox/lead-demo.md').read_text())

    def test_a_stale_commit_is_refused(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):
            self.approve(ident, 'b' * 40)  # the bot's yes was for another commit
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        self.approve(ident, self.SHA)
        with self.assertRaises(PermissionError):
            owner_.gate_ok(self.job, ident, 'c' * 40)  # a push after the yes withdraws it
        with self.assertRaises(ValueError):
            owner_.ask_gate(self.job, 'Merge', 'abc123')  # a short sha could match more than one commit

    def test_an_agents_own_yes_is_refused(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        ident = self.gate_ids()[0]
        with self.assertRaises(PermissionError):  # HERDR_PANE_ID is set: a command from a Herdr pane
            owner_.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat')
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
        self.assertTrue(herdrapi_.inside_herdr({}, child))
        self.assertFalse(herdrapi_.inside_herdr({}, 1))

    def test_a_local_gate_refuses_approve_gate_and_ignores_a_swapped_command(self):
        from unittest import mock
        with mock.patch.object(owner_, 'ask_background'):
            self.quiet(owner_.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False), self.assertRaises(PermissionError):
            owner_.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat')
        no = Asks.fake_ask(self, 'exit 1')
        yes = Asks.fake_ask(self, 'echo yes')
        with mock.patch.object(owner_, 'ASK_CMD', no):
            owner_.ask_now(self.job, 'Gate?', [], yes, ident)  # a hidden _ask with its own --command never opens a gate
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
        self.assertIn('by owner, through fake-ask', self.quiet(owner_.gate_ok, self.job, ident, self.SHA))
        refused = subprocess.run([str(SCRIPTS / 'fleet-job'), 'ask', str(self.job), '--gate', '--sha', self.SHA, '--option', 'a',
                                  '--option', 'b', 'Merge'], env=env, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2)

    # review-codex, round 1

    def test_p1_a_hidden_ask_asks_the_gates_own_question_and_never_a_bot_gate(self):
        from unittest import mock
        with mock.patch.object(owner_, 'ask_background'):
            self.quiet(owner_.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        args = Path(tempfile.mkdtemp()) / 'args'
        fake = Asks.fake_ask(self, 'printf "%s\\n" "$@" > ' + str(args) + '; echo yes')
        with mock.patch.object(owner_, 'ASK_CMD', fake):
            owner_.ask_now(self.job, 'Continue the read-only review?', ['Sure'], None, ident)
        self.assertIn('Gate ' + ident + ': Merge PR #3 into main (PR #3) at', args.read_text())
        self.assertNotIn('read-only review', args.read_text())
        self.assertNotIn('Sure', args.read_text())
        (self.job / 'gates' / (ident + '.json')).write_text(json.dumps({**owner_.load_gate(self.job, ident), 'route': 'alpha'}))
        args.unlink()
        with mock.patch.object(owner_, 'ASK_CMD', fake), self.assertRaises(PermissionError):
            owner_.ask_now(self.job, 'Merge?', [], None, ident)  # a bot's gate never goes to the phone
        self.assertFalse(args.exists())

    def test_p1_a_gate_changed_while_asked_is_not_recorded(self):
        from unittest import mock
        with mock.patch.object(owner_, 'ask_background'):
            self.quiet(owner_.ask_gate, self.job, 'Merge PR #3 into main', self.SHA, 3)
        ident = self.gate_ids()[0]
        record = self.job / 'gates' / (ident + '.json')
        swap = json.dumps({**owner_.load_gate(self.job, ident), 'action': 'Deploy to production'})
        fake = Asks.fake_ask(self, "printf '%s' " + shlex.quote(swap) + ' > ' + str(record) + '; echo yes')
        with mock.patch.object(owner_, 'ASK_CMD', fake):
            owner_.ask_now(self.job, '', [], None, ident)
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        self.assertIn('GATE NOT RECORDED', (self.job / 'inbox/lead-demo.md').read_text())

    def test_p1_no_route_for_the_bot_is_a_refusal_not_a_lost_gate(self):
        self.bot_job()
        (self.home / 'routes/alpha').unlink()
        (self.home / 'routes/default').write_text('URL=http://127.0.0.1:9/another-bot\n')  # never a fallback
        with self.assertRaises(ValueError):
            owner_.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        with self.assertRaises(ValueError):
            owner_.ask(self.job, 'Keep it?', [])
        self.assertFalse((self.job / 'gates').exists() and any((self.job / 'gates').iterdir()))
        self.assertFalse((self.home / 'events/queue').exists() and any((self.home / 'events/queue').iterdir()))

    def test_p2_gate_ok_needs_the_record_of_that_very_gate(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(owner_.ask_gate, self.job, 'Send a draft to the owner', self.SHA)
        first, second = self.gate_ids()
        self.approve(first, self.SHA)
        (self.job / 'gates' / (second + '.approved')).write_text((self.job / 'gates' / (first + '.approved')).read_text())
        with self.assertRaises(PermissionError):
            owner_.gate_ok(self.job, second, self.SHA)

    def test_e17_a_yes_covers_only_the_gate_as_asked(self):
        """eval G17, G18: the yes is bound to the gate's action, PR, commit and route, not only its id and commit."""
        import shlex
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        (ident,) = self.gate_ids()
        command = shlex.split(json.loads(next((self.home / 'events/queue').glob('*.json')).read_text())['payload']['approve'])
        digest = command[command.index('--digest') + 1]
        self.assertEqual(digest, owner_.gate_digest(owner_.load_gate(self.job, ident)))  # the bot is handed the gate as asked
        path = self.job / 'gates' / (ident + '.json')
        asked = path.read_text()
        path.write_text(asked.replace('Merge PR #12 into main', 'Delete the production database'))
        from unittest import mock
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False), self.assertRaises(PermissionError):
            owner_.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat', digest)
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())
        path.write_text(asked)
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            self.quiet(owner_.approve_gate, self.job, ident, self.SHA, 'owner in Grok Bot chat', digest)
        self.quiet(owner_.gate_ok, self.job, ident, self.SHA)
        path.write_text(asked.replace('"pr": 12', '"pr": 13'))
        with self.assertRaises(PermissionError) as refused:
            owner_.gate_ok(self.job, ident, self.SHA)
        self.assertIn('changed after the yes', str(refused.exception))

    def test_e17b_approve_gate_without_the_digest_is_refused(self):
        """review round 2, R1: leaving --digest out is no way around the check."""
        from unittest import mock
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        (ident,) = self.gate_ids()
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False), self.assertRaises(PermissionError) as refused:
            owner_.approve_gate(self.job, ident, self.SHA, 'owner in Grok Bot chat')
        self.assertIn('--digest', str(refused.exception))
        self.assertFalse((self.job / 'gates' / (ident + '.approved')).exists())

    def test_e18_cancel_signals_only_this_questions_own_waiter(self):
        """review round 2 recheck, R4: another job whose path starts with this one's, another question, a reused pid."""
        from unittest import mock
        job = str(Path(self.job).absolute())
        cases = {f'python3 fleet_job.py _ask {job} --ident abcdefabcdef --command c -- q': True,
                 f'python3 fleet_job.py _ask {job}-other --ident abcdefabcdef --command c -- q': False,
                 f'python3 fleet_job.py _ask {job} --ident 000000000000 --command c -- q': False,
                 'sleep 60': False}
        for args, mine in cases.items():
            with mock.patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, args + '\n', '')):
                self.assertEqual(owner_.own_waiter(self.job, 4242, 'abcdefabcdef'), mine, args)

    def test_e20_a_yes_recorded_before_the_digest_or_cut_short_is_refused(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        (ident,) = self.gate_ids()
        record = self.job / 'gates' / (ident + '.approved')
        for old in ({'gate': ident, 'sha': self.SHA, 'by': 'owner', 'at': 'then'}, {'gate': ident, 'sha': self.SHA}):
            record.write_text(json.dumps(old) + '\n')
            with self.assertRaises(PermissionError):
                owner_.gate_ok(self.job, ident, self.SHA)

    def test_e21_a_process_table_that_does_not_show_this_command_cannot_approve(self):
        from unittest import mock
        for answer in (subprocess.CompletedProcess([], 0, '', ''), subprocess.CompletedProcess([], 0, '  1     0 launchd\n', '')):
            with mock.patch.object(subprocess, 'run', return_value=answer):
                self.assertTrue(herdrapi_.inside_herdr({}, 4242))
        with mock.patch.object(subprocess, 'run', side_effect=FileNotFoundError('ps')):
            self.assertTrue(herdrapi_.inside_herdr({}))
        for rows in ('4242  4141 python3\n', '  1     0 launchd\n 4242  4141 python3\n 4141  4242 bash\n'):
            with mock.patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, rows, '')):
                self.assertTrue(herdrapi_.inside_herdr({}, 4242))  # an ancestor not shown, or a loop (review round 2, R7)
        rows = '  1     0 launchd\n 4242     1 bash\n'
        with mock.patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, rows, '')):
            self.assertFalse(herdrapi_.inside_herdr({}, 4242))  # shown, with no Herdr above it: outside

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
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        (self.home / 'routes/alpha').unlink()  # the owner rotates the route while the gate waits
        subprocess.run([str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], check=True, timeout=30)
        self.assertEqual([json.loads(p.read_text())['payload']['state'] for p in (self.home / 'events/queue').glob('*.json')], ['gate'])

    # review-codex, round 3
    def test_r3_a_held_or_expired_question_or_gate_tells_its_lead_once(self):
        self.bot_job()
        self.quiet(owner_.ask_gate, self.job, 'Merge PR #12 into main', self.SHA, 12)
        self.quiet(owner_.ask, self.job, 'Keep it?', [])
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
        self.quiet(owner_.ask_gate, self.job, 'Push the docs branch', self.SHA)
        (self.home / 'routes/alpha').unlink()
        subprocess.run(flush, check=True, timeout=30)
        for path in queue.glob('*.json'):
            os.utime(path, (time.time() - 86460,) * 2)
        subprocess.run(flush, check=True, timeout=30)
        last = (self.job / 'inbox.log').read_text().splitlines()[-1]
        self.assertTrue(last.startswith('UNDELIVERED gate ') and 'after 24 h' in last, last)
        self.assertEqual(len(list((self.home / 'events/dead').glob('*.json'))), 1)

    def test_a_held_post_tells_its_lead_once_and_goes_out_when_the_route_comes_back(self):
        self.bot_job()
        post = [str(SCRIPTS / 'fleet-job'), 'post', str(self.job)]
        self.assertEqual(subprocess.run(post + ['PLAN READY: two lanes'], capture_output=True, text=True).returncode, 0)
        (self.home / 'routes/alpha').unlink()  # the owner rotates the route after the post was queued
        flush, queue = [str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], self.home / 'events/queue'
        for _ in range(2):  # every flush holds it; the lead hears it once
            subprocess.run(flush, check=True, timeout=30)
        self.assertEqual([json.loads(p.read_text())['payload']['state'] for p in queue.glob('*.json')], ['post'])
        self.assertIn('held (route alpha has no URL)', (self.home / 'events/flush.log').read_text())
        told = (self.job / 'inbox.log').read_text().splitlines()
        self.assertEqual(len(told), 1, told)
        self.assertTrue(told[0].startswith('UNDELIVERED post outbox 001 for alpha held: '), told[0])
        self.assertIn('do not post it again', told[0])  # it goes out by itself: a second post would be heard twice
        curl = self.home / '.local/bin/curl'
        curl.parent.mkdir(parents=True)
        curl.write_text('#!/bin/sh\ncat >/dev/null; printf 200\n')
        curl.chmod(0o755)
        (self.home / 'routes/alpha').write_text('URL=http://127.0.0.1:9/never\n')
        subprocess.run(flush, check=True, timeout=30)
        self.assertEqual((list(queue.glob('*.json')), list((self.home / 'events/held').iterdir())), ([], []))
        self.assertEqual(len((self.job / 'inbox.log').read_text().splitlines()), 1, 'sent: the lead hears nothing more')

    def test_a_post_dead_after_24_h_tells_its_lead_to_post_again(self):
        self.bot_job()
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'post', str(self.job), 'Report ready'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.home / 'routes/alpha').unlink()
        flush, queue = [str(ROOT / 'skills/grokbot-herdr/scripts/herdr-event-flush')], self.home / 'events/queue'
        subprocess.run(flush, check=True, timeout=30)
        for path in queue.glob('*.json'):
            os.utime(path, (time.time() - 86460,) * 2)
        subprocess.run(flush, check=True, timeout=30)
        told = (self.job / 'inbox.log').read_text().splitlines()
        self.assertEqual(len(told), 2, told)  # held once, then dead once
        self.assertTrue(told[-1].startswith('UNDELIVERED post outbox 001 for alpha after 24 h'), told[-1])
        self.assertIn('the bot never heard it', told[-1])
        self.assertIn('post again', told[-1])
        self.assertEqual((list(queue.glob('*.json')), len(list((self.home / 'events/dead').glob('*.json')))), ([], 1))

    def test_r2_a_route_with_no_effective_url_or_no_queue_is_a_refusal(self):
        self.bot_job()
        (self.home / 'routes/alpha').write_text('URL="" # disabled during route rotation\n')
        with self.assertRaises(ValueError):
            owner_.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        (self.home / 'routes/alpha').write_text('URL=http://127.0.0.1:9/never\n')
        blocked = self.home / 'not-a-folder'
        blocked.write_text('a file where the queue should be')
        from unittest import mock
        with mock.patch.dict(os.environ, {'HERDR_EVENTS_HOME': str(blocked)}), self.assertRaises(ValueError):
            owner_.ask_gate(self.job, 'Merge PR #12 into main', self.SHA, 12)
        with mock.patch.dict(os.environ, {'HERDR_EVENTS_HOME': str(blocked)}), self.assertRaises(ValueError):
            owner_.ask(self.job, 'Keep it?', [])
        self.assertEqual(self.gate_ids(), [], 'a gate its bot never hears is taken back')

    def test_r2_each_answer_names_its_question(self):
        self.bot_job()
        self.quiet(owner_.ask, self.job, 'Keep the first file?', ['Yes', 'No'])
        self.quiet(owner_.ask, self.job, 'Keep the second file?', ['Yes', 'No'])
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
        scratch = Path(tempfile.mkdtemp())  # finish takes the handed-mark lock: never the user's own events folder
        patch = mock.patch.dict(os.environ, {'HERDR': screen_herdr('❯ \n'), 'HERDR_EVENTS_DIR': str(scratch / 'events'),
                                             'HERDR_EVENTS_HOME': str(scratch / 'queue')})
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
        _, out = self.quiet(owner_.post, self.job, 'Screens for the nudge', [str(shot)])
        self.assertIn('POSTED 001', out)
        self.assertEqual((self.job / 'outbox/001/after.png').read_bytes(), b'png')
        self.assertIn(str(self.job.absolute() / 'outbox/001/after.png'), (self.job / 'outbox/001.md').read_text())
        self.quiet(owner_.post, self.job, 'Report ready', [])
        self.assertEqual((self.job / 'outbox.log').read_text().splitlines(),
                         ['001 post Screens for the nudge', '002 post Report ready'])
        with self.assertRaises(ValueError):
            owner_.post(self.job, 'missing', ['/nonexistent/file.png'])

    def test_wait_prints_unseen_items_once_then_times_out(self):
        self.quiet(owner_.post, self.job, 'PLAN READY: two lanes', [])
        code, out = self.quiet(owner_.wait, self.job, 5, 0)
        self.assertEqual(code, 0)
        self.assertIn('# 001 post', out)
        self.assertIn('PLAN READY: two lanes', out)
        code, out = self.quiet(owner_.wait, self.job, 0, 0)
        self.assertEqual(code, 3)
        self.assertIn('TIMEOUT', out)

    def test_wait_and_tell_see_a_lead_held_at_a_card(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'HERDR': screen_herdr(CARD)}):
            code, out = self.quiet(owner_.wait, self.job, 5, 0)
            self.assertEqual(code, 0)
            self.assertIn('BLOCKED_ON_CARD lead-demo', out)
            self.assertIn('Which nudge copy?', out)
            code, out = self.quiet(owner_.tell, self.job, 'lead', 'ANSWER: option B')
        self.assertEqual(code, 3)
        self.assertIn('BLOCKED_ON_CARD lead-demo', out)
        self.assertNotIn('DELIVERED', out)
        self.assertIn('ANSWER: option B', (self.job / 'inbox/lead-demo.md').read_text())  # still queued for after the card
        code, out = self.quiet(owner_.tell, self.job, 'lead', 'next')
        self.assertIsNone(code)
        self.assertIn('DELIVERED lead-demo', out)

    def test_a_question_goes_to_the_outbox_not_the_phone(self):
        ident, out = self.quiet(owner_.ask, self.job, 'Customer.io copy too?', ['yes', 'no'])
        self.assertIn('posted to the front door as outbox 001', out)
        item = (self.job / 'outbox/001.md').read_text()
        self.assertIn('Customer.io copy too?\n- yes\n- no', item)
        self.assertIn(f'ANSWER {ident}', item)
        self.assertFalse((self.job / 'asks').exists())  # no phone card was started

    def test_a_gate_goes_to_the_outbox_and_the_front_door_records_the_quoted_yes(self):
        from unittest import mock
        sha = 'a' * 40
        _, out = self.quiet(owner_.ask_gate, self.job, 'mark PR #444 ready for review', sha, 444)
        ident = next((self.job / 'gates').glob('*.json')).stem
        item = (self.job / 'outbox/001.md').read_text()
        self.assertIn(f'# 001 gate', item)
        self.assertIn(f'approve-gate {self.job.absolute()} {ident} --sha {sha}', item)
        self.assertEqual(owner_.load_gate(self.job, ident)['route'], 'front-door')
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=False):
            self.quiet(owner_.approve_gate, self.job, ident, sha, "owner in desktop chat: 'push the PR'", owner_.gate_digest(owner_.load_gate(self.job, ident)))
        _, out = self.quiet(owner_.gate_ok, self.job, ident, sha)
        self.assertIn("APPROVED " + ident + " by owner in desktop chat: 'push the PR'", out)
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=True), self.assertRaises(PermissionError):
            owner_.approve_gate(self.job, ident, sha, 'the lead itself')

    def test_the_leads_own_card_and_files_become_posts(self):
        card = {'tool_input': {'questions': [{'question': 'Ready + DM?', 'options': [{'label': 'Yes', 'description': 'both'}]}]}}
        decision = json.loads(hooks_.ask_lead(self.job, 'lead-demo', card))['hookSpecificOutput']
        self.assertEqual(decision['permissionDecision'], 'deny')
        self.assertIn('outbox 001', decision['permissionDecisionReason'])
        self.assertIn('Ready + DM?\n- Yes: both', (self.job / 'outbox/001.md').read_text())
        shot = Path(tempfile.mkdtemp()) / 'plan.md'
        shot.write_text('the plan')
        decision = json.loads(hooks_.send_file(self.job, 'lead-demo', {'tool_input': {'files': [str(shot)], 'caption': 'The plan'}}))
        self.assertEqual(decision['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual((self.job / 'outbox/002/plan.md').read_text(), 'the plan')
        self.assertEqual(hooks_.send_file(self.job, 'build-x', {'tool_input': {'files': [str(shot)]}}), '{}')  # only the lead's
        (self.job / 'front-door').unlink()
        self.assertEqual(hooks_.ask_lead(self.job, 'lead-demo', card), '{}')   # a job without a front door: the card goes ahead
        self.assertEqual(hooks_.send_file(self.job, 'lead-demo', {'tool_input': {'files': [str(shot)]}}), '{}')

    def test_a_plan_is_approved_only_once_it_was_posted_as_it_stands(self):
        from unittest import mock
        patch = mock.patch.object(herdrapi_, 'inside_herdr', return_value=False)
        patch.start()
        self.addCleanup(patch.stop)
        plan = self.job / 'plan.md'
        plan.write_text('Size: big\n# Plan v1\n')
        with self.assertRaises(PermissionError) as refused:
            owner_.approve(self.job, "owner in desktop chat: 'ok - lets go'")
        self.assertIn('has not been shown this plan', str(refused.exception))
        self.quiet(owner_.post, self.job, 'PLAN READY', [str(plan)])
        with self.assertRaises(PermissionError) as refused:   # posted, but the front door has not received it yet
            owner_.approve(self.job, "owner in desktop chat: 'ok - lets go'")
        self.assertIn('has not received this plan.md yet', str(refused.exception))
        self.quiet(owner_.wait, self.job, 5, 0)
        self.quiet(owner_.approve, self.job, "owner in desktop chat: 'approve as written'")
        self.assertIn('approve as written', (self.job / 'approved').read_text())
        plan.write_text('Size: big\n# Plan v2\n')   # changed after the owner saw it
        with self.assertRaises(PermissionError):
            owner_.approve(self.job, 'owner')
        plan.write_text('Size: big\n# Plan v1\n')
        (self.job / 'fleet-plan.md').write_text('layout, never posted')   # the detailed plan counts too
        with self.assertRaises(PermissionError) as refused:
            owner_.approve(self.job, 'owner')
        self.assertIn('fleet-plan.md', str(refused.exception))

    def test_the_lead_cannot_approve_its_own_plan_in_a_front_door_job(self):
        from unittest import mock
        (self.job / 'plan.md').write_text('Size: big\n')
        self.quiet(owner_.post, self.job, 'PLAN READY', [str(self.job / 'plan.md')])
        with mock.patch.object(herdrapi_, 'inside_herdr', return_value=True), self.assertRaises(PermissionError) as refused:
            owner_.approve(self.job, 'the lead itself')
        self.assertIn('outside Herdr', str(refused.exception))
        self.assertFalse((self.job / 'approved').exists())

    def test_finish_posts_to_the_outbox_and_wait_notices_a_lead_that_is_gone(self):
        from unittest import mock
        code, out = self.quiet(owner_.wait, self.job, 5, 0)   # nothing posted, lead alive: times out
        self.assertEqual(code, 3)
        self.quiet(owner_.finish, self.job, 'all merged')
        self.assertIn('# 001 done', (self.job / 'outbox/001.md').read_text())
        code, out = self.quiet(owner_.wait, self.job, 5, 0)
        self.assertEqual((code, '# 001 done' in out), (0, True))
        gone = Path(tempfile.mkdtemp()) / 'herdr'
        gone.write_text('#!/bin/sh\necho \'{"error":{"code":"agent_not_found"}}\'; exit 1\n')
        gone.chmod(0o755)
        with mock.patch.dict(os.environ, {'HERDR': str(gone)}):
            code, out = self.quiet(owner_.wait, self.job, 5, 0)
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


class LeadChoice(unittest.TestCase):
    """stampede new --lead claude|codex: Claude by default and unchanged; Codex hooked, woken by typed inbox lines, its
    own turns to the relay, its gates by gate-ok only. No test types into a real pane: herdr-send is a fake."""

    def setUp(self):
        from unittest import mock
        folder = Path(tempfile.mkdtemp())
        self.sent = folder / 'sent'
        send = folder / 'herdr-send'
        send.write_text('#!/bin/bash\nprintf "%s %s\\n" "$1" "$2" >> "$(dirname "$0")/sent"\necho "SUBMITTED $1"\n')
        send.chmod(0o755)
        mock.patch.object(tui_, 'HERDR_SEND', send).start()
        mock.patch.dict(os.environ, {'HERDR_EVENTS_DIR': str(folder / 'events'), 'HERDR_EVENTS_HOME': str(folder / 'queue')}).start()
        self.kick = mock.patch.object(tui_, 'deliver_soon').start()
        self.addCleanup(mock.patch.stopall)
        self.job = job_with([('lead-demo', 'codex'), ('build-x', 'claude')])

    def new(self, env=(), **kw):
        clean = {'FLEET_LEAD_KIND': '', 'FLEET_LEAD_MODEL': '', 'FLEET_LEAD_EFFORT': ''}  # whatever the machine sets
        return Fixes.run_new(self, 'idle', {**clean, **dict(env)}, **kw)

    def test_without_the_flag_the_lead_is_claude_as_before_and_lead_claude_is_the_same(self):
        runs = [self.new(), self.new(kind='claude')]
        for out, job, log in runs:
            brief = job / 'briefs/lead-fix-login-bug.md'
            self.assertIn(f'agent start lead-fix-login-bug --kind claude --pane w9:p2 --timeout 90000 -- --permission-mode auto '
                          f'--add-dir {job} -n lead-fix-login-bug --settings {job}/hooks/lead-fix-login-bug-claude.json '
                          '--model claude-opus-5-5 --effort xhigh', log)
            self.assertEqual((job / 'inbox/lead-fix-login-bug.md').read_text(),
                             f'You are lead-fix-login-bug. Read {brief} and do everything it says.\n')
            self.assertIn('hooks wake you', brief.read_text())
            self.assertIn("yes typed in your pane or card", brief.read_text())
            self.assertFalse(self.sent.exists())
            self.assertEqual(job_.lead_kind(job), 'claude')
        same = [log.replace(str(job.parents[2]), 'TMP') for _, job, log in runs]
        self.assertEqual(same[0], same[1])
        texts = [(job / 'briefs/lead-fix-login-bug.md').read_text().replace(str(job.parents[2]), 'TMP') for _, job, _ in runs]
        self.assertEqual(texts[0], texts[1])

    def test_the_standing_choice_and_the_flag_over_it(self):
        for env, kw, cli in (({'FLEET_LEAD_KIND': 'codex'}, {}, 'codex'), ({'FLEET_LEAD_KIND': 'codex'}, {'kind': 'claude'}, 'claude'),
                             ({'FLEET_LEAD_KIND': 'claude'}, {'kind': 'codex'}, 'codex')):
            with self.subTest(env=env, kw=kw):
                _, job, log = self.new(env, **kw)
                self.assertIn('agent start lead-fix-login-bug --kind ' + cli + ' ', log)
                self.assertEqual(job_.lead_kind(job), cli)

    def test_lead_codex_starts_hooked_on_astra_and_its_pointer_is_typed_now(self):
        out, job, log = self.new(kind='codex')
        brief = job / 'briefs/lead-fix-login-bug.md'
        self.assertIn(f'agent start lead-fix-login-bug --kind codex --pane w9:p2 --timeout 90000 -- --approve-for-me --add-dir {job} '
                      '-c notify=', log)
        self.assertIn('"hook", "--agent", "lead-fix-login-bug", "codex-notify"', log)
        self.assertIn('-c sandbox_workspace_write.network_access=true', log)
        self.assertIn('-m gpt-6-astra -c model_reasoning_effort="ultra"', log)
        self.assertEqual(job_.roster(job), ({'lead-fix-login-bug': 'codex'}, 'lead-fix-login-bug'))
        self.assertEqual(self.sent.read_text(), f'lead-fix-login-bug You are lead-fix-login-bug. Read {brief} and do everything it says.\n')
        self.assertFalse((job / 'inbox/lead-fix-login-bug.md').exists())   # typed now, never left for a deliverer
        self.assertTrue(out.endswith('SUBMITTED lead-fix-login-bug\nlead-fix-login-bug ' + str(job) + '\n'))
        self.assertIsNone(self.code)
        text = brief.read_text()
        self.assertNotIn('typed in your pane', text)
        self.assertNotIn('question card', text)
        self.assertIn(f'fleet-job types each new line of {job / "inbox.log"}', text)
        self.assertIn('so a yes typed here, an agent\'s word or a relayed yes never counts', text)

    def test_lead_codex_takes_a_given_pane_the_front_door_and_review(self):
        out, job, log = self.new(kind='codex', pane='w9:p1', front=True, review=True)
        self.assertIn('tab rename w9:t1 lead', log)
        self.assertIn('agent start lead-fix-login-bug --kind codex --pane w9:p1 ', log)
        self.assertNotIn('tab create', log)
        self.assertTrue((job / 'front-door').is_file() and (job / 'review').is_file())
        text = (job / 'briefs/lead-fix-login-bug.md').read_text()
        self.assertIn('post it with fleet-job post', text)                         # the plan goes to the front door first
        self.assertIn('it goes to the front door, which asks the owner', text)
        self.assertIn('Act only after fleet-job gate-ok', text)
        self.assertNotIn('typed in your pane', text)

    def test_a_codex_lead_whose_pointer_does_not_go_in_is_blocked_with_the_tell_to_resend(self):
        from unittest import mock
        with mock.patch.object(tui_, 'herdr_send', return_value=(False, 'FAILED lead-fix-login-bug focused: the owner is in that pane')):
            out, job, _ = self.new(kind='codex')
        self.assertEqual(self.code, 1)
        self.assertEqual(out, 'BLOCKED lead-fix-login-bug: its brief pointer did not go in (FAILED lead-fix-login-bug focused: the owner '
                              f'is in that pane); fix that, then stampede tell {job} lead "Read {job / "briefs/lead-fix-login-bug.md"}"\n')

    def test_an_invalid_lead_is_refused_before_anything_is_made(self):
        for env, kw in (({}, {'kind': 'cursor'}), ({'FLEET_LEAD_KIND': 'fable'}, {})):
            root = Path(tempfile.mkdtemp())
            with self.subTest(env=env, kw=kw), self.assertRaises(ValueError) as refused:
                self.new({'FLEET_JOBS_ROOT': str(root), **env}, **kw)
            self.assertIn('the lead runs on claude or codex, not', str(refused.exception))
            self.assertFalse((root / 'jobs').exists())
        ask = Path(tempfile.mkdtemp()) / 'ask.md'
        ask.write_text('Fix the login bug\n')
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), 'new', '--file', str(ask), '--workspace', 'w9', '--lead', 'cursor'],
                                capture_output=True, text=True, env={**os.environ, 'HERDR': '/nonexistent/herdr', 'FLEET_JOBS_ROOT': str(ask.parent)})
        self.assertEqual(result.returncode, 2)
        self.assertIn("argument --lead: invalid choice: 'cursor'", result.stderr)   # the choices' quoting differs by Python version
        self.assertIn('claude', result.stderr.splitlines()[-1])
        self.assertFalse((ask.parent / 'jobs').exists())

    def test_a_fork_takes_a_claude_lead_only(self):
        from unittest import mock
        sid = '0b5f1c2e-7d3a-4e8b-9c41-2a6f8e9d1b37'
        for env, kw, said in (({}, {'kind': 'codex', 'fork': sid}, '--fork forks a Claude chat, so it takes a Claude lead'),
                              ({'FLEET_LEAD_KIND': 'codex'}, {'fork': sid}, '--fork forks a Claude chat'),
                              ({}, {'kind': 'codex', 'fork': sid, 'core': True}, '--fork forks a Claude chat')):
            root = Path(tempfile.mkdtemp())
            with self.subTest(kw=kw), self.assertRaises(ValueError) as refused:
                self.new({'FLEET_JOBS_ROOT': str(root), **env}, **kw)
            self.assertIn(said, str(refused.exception))
            self.assertFalse((root / 'jobs').exists())
        _, job, log = self.new({'FLEET_LEAD_KIND': 'codex'}, kind='claude', fork=sid)   # --lead claude forks as before
        self.assertIn(f'--kind claude --pane w9:p2 --timeout 90000 -- --resume {sid} --fork-session', log)
        # typing_unsafe asks the machine's own Herdr Core for its version and hold: not this test's subject, and no test's to ask
        with mock.patch.dict(os.environ, {'FLEET_LEAD_KIND': 'codex'}), mock.patch.object(relay_, 'new_core', return_value=0) as core, \
                mock.patch.object(hcapi_, 'typing_unsafe', return_value=''):
            self.assertEqual(cli_.new('ask.md', None, core=True, relay=True), 0)
        self.assertEqual(core.call_args.args[5], 'codex')   # the standing choice is the lead of a Core job too

    def test_its_sandbox_reaches_the_network_git_and_the_worktrees_and_a_workers_does_not(self):
        from unittest import mock
        repo = Path(tempfile.mkdtemp()).resolve() / 'repo'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (self.job / 'workdir').write_text(str(repo) + '\n')
        root = Path(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {'FLEET_JOBS_ROOT': str(root)}):
            lead = agents_.cli_args(self.job, 'lead-demo', 'codex', 'gpt-6-astra', 'ultra', [], lead=True)
            worker = agents_.cli_args(self.job, 'build-ui', 'codex', 'gpt-6-astra', 'ultra', [])
        dirs = [lead[i + 1] for i, a in enumerate(lead) if a == '--add-dir']
        self.assertEqual(dirs, [str(self.job.absolute()), str(root.absolute() / 'worktrees'), str(repo / '.git')])
        self.assertIn('sandbox_workspace_write.network_access=true', lead)
        self.assertTrue((root / 'worktrees').is_dir())
        self.assertEqual([worker[i + 1] for i, a in enumerate(worker) if a == '--add-dir'], [str(self.job.absolute())])
        self.assertNotIn('sandbox_workspace_write.network_access=true', worker)

    def test_the_lead_model_and_effort_reach_only_the_cli_their_model_names(self):
        from unittest import mock
        for env, codex, claude in (
                ({}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'xhigh')),
                ({'FLEET_LEAD_MODEL': 'claude-opus-5-5', 'FLEET_LEAD_EFFORT': 'xhigh'}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'xhigh')),
                ({'FLEET_LEAD_MODEL': 'opus', 'FLEET_LEAD_EFFORT': 'max'}, ('gpt-6-astra', 'ultra'), ('opus', 'max')),
                ({'FLEET_LEAD_EFFORT': 'high'}, ('gpt-6-astra', 'ultra'), ('claude-opus-5-5', 'high')),
                ({'FLEET_LEAD_MODEL': 'gpt-6.1-sol', 'FLEET_LEAD_EFFORT': 'xhigh'}, ('gpt-6.1-sol', 'xhigh'), ('claude-opus-5-5', 'xhigh'))):
            with self.subTest(env=env), mock.patch.dict(os.environ, {'FLEET_LEAD_MODEL': '', 'FLEET_LEAD_EFFORT': '', **env}):
                self.assertEqual(agents_.lead_model('codex'), codex)
                self.assertEqual(agents_.lead_model('claude'), claude)
                self.assertEqual(agents_.lead_model('codex', 'gpt-6-luna', 'low'), ('gpt-6-luna', 'low'))

    def test_a_restarted_lead_keeps_the_lead_model_of_its_cli_and_gets_a_brief_for_it(self):
        import contextlib, io
        from unittest import mock
        job = job_with([('lead-demo', 'claude')])
        brief = job / 'briefs/lead-demo.md'
        brief.parent.mkdir()
        brief.write_text(agents_.lead_brief(job.absolute(), 'lead-demo', '', False, None))
        for kind, want in (('codex', '-m gpt-6-astra -c model_reasoning_effort="ultra"'), ('claude', '--model claude-opus-5-5 --effort xhigh')):
            herdr, log = fake_herdr(job.parent)
            with self.subTest(kind=kind), mock.patch.dict(os.environ, {'HERDR': herdr, 'FLEET_JOBS_ROOT': tempfile.mkdtemp(),
                                                                       'FLEET_LEAD_MODEL': '', 'FLEET_LEAD_EFFORT': ''}), \
                    contextlib.redirect_stdout(io.StringIO()):
                cli_.start(job, 'lead-demo', kind, 'w9:p1', str(brief))
            self.assertIn(want, log.read_text())
            self.assertEqual('typed in your pane' in brief.read_text(), kind == 'claude')   # rewritten for each CLI it moved to
        self.assertIn('lead-demo You are lead-demo in a herdr fleet', self.sent.read_text())   # the Codex restart's pointer, typed
        core = job_with([('lead-demo', 'claude')])
        (core / 'backend').write_text('core\n')
        for folder in (job, core):  # no backend runs a lead on another CLI
            with self.subTest(job=folder.name), self.assertRaises(ValueError) as refused:
                cli_.start(folder, 'lead-demo', 'cursor', None, '-')
            self.assertIn('the lead runs on claude or codex', str(refused.exception))

    def test_a_refused_or_failed_switch_never_leaves_a_lead_the_other_clis_brief(self):
        import contextlib, io
        from unittest import mock
        job = job_with([('lead-demo', 'codex')])
        brief = job / 'briefs/lead-demo.md'
        brief.parent.mkdir()
        brief.write_text(agents_.lead_brief(job.absolute(), 'lead-demo', '', False, None, kind='codex'))
        codex_text = brief.read_text()
        with self.assertRaises(ValueError):   # refused after the kind checks: --cwd is for a Core job
            cli_.start(job, 'lead-demo', 'claude', 'w9:p1', str(brief), cwd='/tmp')
        self.assertEqual(brief.read_text(), codex_text)
        herdr, _ = fake_herdr(job.parent, start_error='agent_start_failed')
        with mock.patch.dict(os.environ, {'HERDR': herdr, 'FLEET_JOBS_ROOT': tempfile.mkdtemp()}), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(herdrapi_.HerdrError):
            cli_.start(job, 'lead-demo', 'claude', 'w9:p1', str(brief))   # the switch to Claude fails at launch
        self.assertEqual(job_.lead_kind(job), 'codex')                    # the roster, and so reopen.sh, still say Codex
        self.assertEqual(brief.read_text(), codex_text)                 # and so does the brief again
        brief.write_text(agents_.lead_brief(job.absolute(), 'lead-demo', '', False, None))   # a Claude brief left by an older copy
        herdr, _ = fake_herdr(job.parent)
        with mock.patch.dict(os.environ, {'HERDR': herdr, 'FLEET_JOBS_ROOT': tempfile.mkdtemp()}), \
                contextlib.redirect_stdout(io.StringIO()):
            cli_.start(job, 'lead-demo', 'codex', 'w9:p1', str(brief))   # the retry on Codex puts it right
        self.assertNotIn('typed in your pane', brief.read_text())
        self.assertIn('Act only after fleet-job gate-ok', brief.read_text())

    def test_tell_writes_its_inbox_file_and_wakes_the_deliverer(self):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            owner_.tell(self.job, 'lead', 'ANSWER yes')
        self.assertEqual(out.getvalue(), 'DELIVERED lead-demo (inbox file; typed into its pane once it is idle)\n')
        self.assertEqual((self.job / 'inbox/lead-demo.md').read_text(), 'ANSWER yes\n')
        self.kick.assert_called_once_with(self.job)

    def test_worker_lines_wake_a_codex_lead_and_not_a_claude_one(self):
        import contextlib, io
        hooks_.cursor_stop(self.job, 'build-x', {'status': 'completed'})
        hooks_.session_end(self.job, 'build-x', {'reason': 'exit'})
        self.assertEqual((self.job / 'inbox.log').read_text(), 'TURN build-x completed\nGONE build-x exit\n')
        self.assertEqual(self.kick.call_count, 2)
        claude = job_with([('lead-demo', 'claude'), ('build-x', 'claude')])
        hooks_.cursor_stop(claude, 'build-x', {'status': 'completed'})
        with contextlib.redirect_stdout(io.StringIO()):
            owner_.tell(claude, 'lead', 'hi')
        self.assertEqual(self.kick.call_count, 2)

    def test_its_own_turn_goes_to_the_relay_and_never_to_inbox_log(self):
        from unittest import mock
        folder = Path(tempfile.mkdtemp())
        relay = folder / 'relay'
        relay.write_text('#!/bin/bash\nprintf "%s" "$1" > ' + str(folder / 'got') + '\n')
        relay.chmod(0o755)
        payload = {'type': 'agent-turn-complete', 'thread-id': 't-main', 'last-assistant-message': 'planned'}
        with mock.patch.object(hooks_, 'RELAY_CODEX', relay):
            hooks_.codex_notify(self.job, 'lead-demo', payload)
        self.assertEqual(json.loads((folder / 'got').read_text()), payload)
        self.assertFalse((self.job / 'inbox.log').exists())
        self.kick.assert_called_once_with(self.job)

    def test_gates_count_only_the_recorded_yes(self):
        from unittest import mock
        claude = job_with([('lead-demo', 'claude')])
        self.assertFalse(owner_.pane_yes(self.job))
        self.assertTrue(owner_.pane_yes(claude))
        (claude / 'backend').write_text('core\n')
        self.assertFalse(owner_.pane_yes(claude))
        (self.job / 'gates').mkdir()
        (self.job / 'gates/0123456789ab.json').write_text(json.dumps({'gate': '0123456789ab', 'sha': 'a' * 40, 'route': 'stompy'}))
        with self.assertRaises(PermissionError) as refused:
            owner_.gate_ok(self.job, '0123456789ab', 'a' * 40)
        self.assertEqual(str(refused.exception), 'gate 0123456789ab has no recorded yes: wait for it')
        with mock.patch.dict(os.environ, {'HERDR_ENV': '1'}), self.assertRaises(PermissionError) as refused:
            owner_.approve_gate(self.job, '0123456789ab', 'a' * 40, 'owner')
        self.assertNotIn('pane', str(refused.exception))
        local = agents_.lead_brief(self.job, 'lead-demo', '', False, None, kind='codex')
        self.assertIn(f'ask it with fleet-job ask {self.job} --gate', local)
        self.assertNotIn('card', local.split('(a phone card)')[0])


class Deliver(unittest.TestCase):
    """The deliverer types a Codex lead's unread inbox lines into its pane, once each, only while it is idle and unfocused."""

    def setUp(self):
        from unittest import mock
        self.job = job_with([('lead-demo', 'codex'), ('build-x', 'claude')])
        (self.job / 'hooks').mkdir()
        base_.append(self.job / 'inbox.log', 'REPORT reports/build-x.md')
        base_.append(self.job / 'inbox/lead-demo.md', 'GATE 0123456789ab APPROVED by owner')
        mock.patch.object(tui_, 'DELIVER_EVERY', 0).start()
        self.ready = mock.patch.object(tui_, 'ready', return_value=True).start()
        self.send = mock.patch.object(tui_, 'herdr_send', return_value=(True, 'SUBMITTED lead-demo')).start()
        self.addCleanup(mock.patch.stopall)

    def deliver(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            return tui_.deliver(self.job)

    def test_both_files_in_one_marked_prompt_and_never_twice(self):
        self.assertEqual(self.deliver(), 0)
        text = self.send.call_args.args[2]
        self.assertTrue(text.startswith('[fleet-job inbox for lead-demo, not typed by the owner] '))
        self.assertIn('inbox.log: REPORT reports/build-x.md', text)
        self.assertIn('lead-demo.md: GATE 0123456789ab APPROVED by owner', text)
        self.assertEqual(self.deliver(), 0)
        self.assertEqual(self.send.call_count, 1)
        base_.append(self.job / 'inbox.log', 'TURN build-x done')
        self.deliver()
        self.assertEqual(self.send.call_args.args[2], '[fleet-job inbox for lead-demo, not typed by the owner] inbox.log: TURN build-x done')

    def test_a_failed_send_moves_no_offset_and_is_retried(self):
        self.send.side_effect = [(False, 'FAILED lead-demo focused'), (True, 'SUBMITTED lead-demo')]
        self.assertEqual(self.deliver(), 0)
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.send.call_args_list[0], self.send.call_args_list[1])
        self.assertEqual(tui_.unread(self.job, 'lead-demo'), [])

    def test_a_busy_lead_keeps_its_lines_until_the_deadline(self):
        from unittest import mock
        self.ready.return_value = False
        with mock.patch.object(tui_, 'DELIVER_FOR', 0.05):
            self.assertEqual(self.deliver(), 3)
        self.send.assert_not_called()
        self.assertEqual(len(tui_.unread(self.job, 'lead-demo')), 2)

    def test_a_second_deliverer_leaves_it_to_the_first(self):
        with (self.job / 'hooks/.deliver.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.deliver(), 0)
        self.send.assert_not_called()

    def test_a_claude_lead_has_no_deliverer(self):
        (self.job / 'agents.tsv').write_text('lead-demo\tclaude\t-\t-\t-\n')
        self.assertEqual(self.deliver(), 0)
        self.send.assert_not_called()
        result = subprocess.run([str(SCRIPTS / 'fleet-job'), '_wake', str(self.job)], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertFalse((self.job / 'hooks/deliver.log').exists())

    def test_a_long_inbox_is_cut_with_where_to_read_the_rest(self):
        base_.append(self.job / 'inbox.log', 'TURN build-x ' + 'x' * 3000)
        self.deliver()
        text = self.send.call_args.args[2]
        self.assertLessEqual(len(text), tui_.DELIVER_MAX + 200)
        self.assertIn('(cut: read the rest at the end of ' + str(self.job / 'inbox' / 'lead-demo.md'), text)

    def test_ready_means_idle_or_done_unfocused_and_no_draft(self):
        from unittest import mock
        footer = '\n  GPT-6-Astra ultra · ~/repo · Main [default]\n  ? for shortcuts            ⚠ 2 warnings · f2 to view\n'
        empty = '» Ask Codex to do anything\n' + footer     # as Codex showed it live, 3 Nov 2026
        draft = '» Explain how to get started\n\n  GPT-6-Astra ultra · ~/repo · Main [default]\n          ⚠ 2 warnings · f2 to view\n'
        for shown, screen, want in (({'agent_status': 'idle'}, empty, True), ({'agent_status': 'done'}, empty, True),
                                    ({'agent_status': 'done'}, '› \n' + footer, True),
                                    ({'agent_status': 'idle', 'focused': True}, empty, False),
                                    ({'agent_status': 'working'}, empty, False),
                                    ({'agent_status': 'idle'}, draft, False),                    # a placeholder phrase in a draft
                                    ({'agent_status': 'idle'}, '  Worked for 7s\n› half a reply from the owner\n  GPT-6-Astra ultra\n', False),
                                    ({'agent_status': 'idle'}, '• To get started, ? for shortcuts\n' + draft, False),  # in earlier output
                                    ({'agent_status': 'idle'}, '? for shortcuts\n' + draft, False),    # a footer above the prompt
                                    ({'agent_status': 'idle'}, CODEX_167_EMPTY, True),              # Codex 0.167.1, live 11 Nov 2026
                                    ({'agent_status': 'done'}, CODEX_167_EMPTY, True),
                                    ({'agent_status': 'idle'}, CODEX_167_DRAFT, False),             # its draft hides the whole row
                                    ({'agent_status': 'idle'}, CODEX_167_FOOTER + '\n' + CODEX_167_DRAFT, False),  # above the prompt
                                    ({'agent_status': 'idle', 'focused': True}, CODEX_167_EMPTY, False),
                                    ({'agent_status': 'working'}, CODEX_167_EMPTY, False),
                                    ({'agent_status': 'idle'}, CODEX_167_QUOTED, False),            # a draft that quotes the footer
                                    ({'agent_status': 'idle'}, CODEX_167_EMPTY + '  something below the footer\n', False),
                                    ({'agent_status': 'idle'}, '› \n' + CODEX_167_FOOTER.strip() + '\n› \n', False),  # last row a prompt
                                    ({'agent_status': 'idle'}, '', False)):                         # nothing readable
            with self.subTest(shown=shown, screen=screen), mock.patch.object(herdrapi_, 'herdr', return_value={'agent': shown}), \
                    mock.patch.object(tui_, 'screen_of', return_value=screen):
                self.assertEqual(REAL_READY('lead-demo'), want)
        with mock.patch.object(herdrapi_, 'herdr', side_effect=herdrapi_.HerdrError('gone', 'agent_not_found')):
            self.assertFalse(REAL_READY('lead-demo'))

    def test_a_stalled_herdr_or_herdr_send_never_holds_the_lock(self):
        from unittest import mock
        folder = Path(tempfile.mkdtemp())
        stall = folder / 'stall'
        stall.write_text('#!/bin/bash\necho $$ >> "$(dirname "$0")/pids"\nsleep 30\n')
        stall.chmod(0o755)
        with mock.patch.object(tui_, 'ready', REAL_READY), mock.patch.object(tui_, 'DELIVER_CALL', 0.3), \
                mock.patch.dict(os.environ, {'HERDR': str(stall)}):
            started = time.monotonic()
            self.assertEqual(self.deliver(), 4)          # agent get hangs: the deliverer lets go at once
            self.assertLess(time.monotonic() - started, 5)
        self.send.assert_not_called()
        self.assertEqual(len(tui_.unread(self.job, 'lead-demo')), 2)   # nothing marked read
        with mock.patch.object(tui_, 'HERDR_SEND', stall), mock.patch.object(tui_, 'DELIVER_SEND', 0.3):
            started = time.monotonic()
            self.assertEqual(REAL_SEND(self.job, 'lead-demo', 'hi'), (False, 'FAILED lead-demo: herdr-send did not finish in 0.3 s'))
            self.assertLess(time.monotonic() - started, 5)
        for pid in (folder / 'pids').read_text().split():   # every stalled child was stopped
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid), 0)
        self.assertEqual(self.deliver(), 0)               # and the next deliverer is not shut out
        self.send.assert_called_once()

    def test_herdr_out_of_reach_lets_go_of_the_lock_at_once(self):
        self.ready.side_effect = ValueError('herdr agent get did not answer (Operation not permitted)')
        self.assertEqual(self.deliver(), 4)
        self.send.assert_not_called()
        self.ready.side_effect, self.ready.return_value = None, True
        self.assertEqual(self.deliver(), 0)   # the next deliverer is not shut out
        self.send.assert_called_once()

    def test_control_characters_never_become_keys(self):
        base_.append(self.job / 'inbox.log', 'TURN build-x done\x1b[2J\x07')
        self.deliver()
        self.assertNotRegex(self.send.call_args.args[2], r'[\x00-\x1f\x7f-\x9f]')


REAL_READY, REAL_SEND = tui_.ready, tui_.herdr_send  # Deliver's setUp mocks both

# Codex 0.167.1's screen as Herdr read it live on 11 Nov 2026 (path shortened): its footer row starts with an arrow,
# and a draft hides that whole row.
CODEX_167_FOOTER = '  ← for agents · ? for shortcuts                                       ⚠ 2 warnings · f2 to view'
CODEX_167_TOP = ('     ~/repo\n\n⚠ Heads up, you have less than 25% of your weekly limit left. Run /status for a breakdown.\n'
                 + '\n' * 30 + '                                                  ⚠ weekly limit: 19% left · /status\n\n')
CODEX_167_EMPTY = CODEX_167_TOP + '› Ask Codex to do anything\n\n  GPT-6.1-Sol default · ~/repo\n' + CODEX_167_FOOTER + '\n'
CODEX_167_DRAFT = (CODEX_167_TOP + '› Explain how to get started\n\n  GPT-6.1-Sol default · ~/repo\n'
                   '                                                         ⚠ 2 warnings · f2 to view\n')
CODEX_167_QUOTED = (CODEX_167_TOP + '› Explain this footer:\n  Here is what I see: ← for agents · ? for shortcuts\n\n'
                    '  GPT-6.1-Sol default · ~/repo\n                                     ⚠ 2 warnings · f2 to view\n')  # review R1
