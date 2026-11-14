"""Gates held by code (stampede/gates.py): the [gates] keys and the job's owner-side record, logged opt-outs, stampede merge
with a fake gh on PATH, and the pre-push hook in a real scratch repo with a scratch bare remote."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core import ROOT, SCRIPTS, LEAD, git  # noqa: E402
from test_native import NativeCase, FLEET  # noqa: E402
from stampede import gates as gates_, job as job_, owner as owner_, settings as settings_, agents as agents_  # noqa: E402

SHA, OTHER = 'a' * 40, 'b' * 40
FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
state = json.load(open(os.environ['GH_STATE']))
with open(os.environ['GH_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
verb = ' '.join(sys.argv[1:3])
if verb == 'pr merge' and state.get('fail'):
    sys.stderr.write('GraphQL: Head branch was modified\\n'); sys.exit(1)
if verb == 'pr view' and 'mergeCommit' in sys.argv:
    print(state.get('merge_commit', ''))
elif verb == 'pr view':
    print(json.dumps({'headRefOid': state['head'], 'isDraft': state.get('draft', False), 'state': state.get('state', 'OPEN')}))
'''


class Scratch(unittest.TestCase):
    """A scratch events folder, HOME and job folder (whose workdir is a scratch repo folder), outside any Herdr pane."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.events, self.home, self.repo, self.bin = (self.root / n for n in ('events', 'home', 'repo', 'bin'))
        for folder in (self.events, self.home, self.repo, self.bin):
            folder.mkdir()
        env = {'HERDR_EVENTS_DIR': str(self.events), 'HOME': str(self.home), 'GIT_CONFIG_NOSYSTEM': '1',
               'PATH': f'{self.bin}:{ROOT / "scripts"}:' + os.environ.get('PATH', '/usr/bin:/bin')}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        for name in ('XDG_CONFIG_HOME', 'STAMPEDE_JOB_KEY', 'HERDR_WORKSPACE_ID', 'HERDR_ENV', 'HERDR_PANE_ID'):
            os.environ.pop(name, None)
        self.job = self.root / 'jobs' / 'demo'
        self.job.mkdir(parents=True)
        (self.job / 'lead').write_text('lead-demo\n')
        (self.job / 'workdir').write_text(str(self.repo) + '\n')

    def begin(self, **flags):
        settings = settings_.load(env={}, home=self.home, flags={'gates.' + k: v for k, v in flags.items()})
        gates_.begin(self.job, settings, self.repo)

    def gate(self, ident='0123456789ab', sha=SHA, pr=12, approve=True, kind='merge'):
        gate = {'gate': ident, 'action': f'merge PR {pr} at {sha}', 'pr': pr, 'sha': sha, 'route': 'local', 'asked': 'now',
                **({'kind': kind} if kind else {})}
        (self.job / 'gates').mkdir(exist_ok=True)
        (self.job / 'gates' / (ident + '.json')).write_text(json.dumps(gate) + '\n')
        if approve:
            (self.job / 'gates' / (ident + '.approved')).write_text(json.dumps(
                {'gate': ident, 'sha': sha, 'by': 'owner', 'at': 'now', 'digest': owner_.gate_digest(gate)}) + '\n')
        return ident


class Keys(Scratch):
    def test_every_gate_is_on_by_default_and_without_a_record(self):
        self.assertEqual(gates_.names(), ['merge', 'push_default_branch', 'deploy', 'publish', 'send', 'spend', 'close'])
        self.assertTrue(all(settings_.DEFAULTS['gates.' + n] for n in gates_.names()))
        self.assertEqual(gates_.off(self.job), [])
        self.begin()
        self.assertEqual(gates_.off(self.job), [])
        self.assertFalse((self.job / 'gates.log').exists())
        self.assertNotIn('switched these gates off', agents_.lead_brief(self.job, 'lead-demo', '', False, None))

    def test_a_repo_file_cannot_switch_a_gate_off(self):
        (self.repo / '.stampede.toml').write_text('[gates]\nmerge = false\n')
        found = settings_.load(repo=self.repo, env={}, home=self.home)
        self.assertTrue(found.get('gates.merge'))
        self.assertIn('gates.merge is taken only from your own', ' '.join(found.problems))
        with self.assertRaises(ValueError), mock.patch('sys.stderr'):
            settings_.for_new(self.repo, {})

    def test_the_record_lives_outside_the_job_and_a_forged_one_for_another_folder_counts_for_nothing(self):
        self.begin(merge=False)
        self.assertTrue(gates_.record_path(self.job).is_relative_to(self.events) if hasattr(Path, 'is_relative_to')
                        else str(gates_.record_path(self.job)).startswith(str(self.events)))
        self.assertEqual(gates_.off(self.job), ['merge'])
        record = json.loads(gates_.record_path(self.job).read_text())
        record['job'] = '/elsewhere'
        gates_.record_path(self.job).write_text(json.dumps(record))
        self.assertEqual(gates_.off(self.job), [])
        (self.job / 'settings.json').write_text(json.dumps({'values': {'gates.merge': False}, 'sources': {'gates.merge': 'user'}}))
        self.assertTrue(settings_.current(self.job).get('gates.merge'), 'the job folder never decides a gate')


class OptOuts(NativeCase):
    def test_no_gate_is_logged_in_the_brief_in_config_show_and_at_finish(self):
        job = self.started(no_gate=['merge', 'spend'])
        log = (job / 'gates.log').read_text().splitlines()
        self.assertEqual([row.split(' ', 1)[1] for row in log], ['OFF merge (flag)', 'OFF spend (flag)'])
        self.assertRegex(log[0], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ OFF')
        brief = (job / 'briefs' / (LEAD + '.md')).read_text()
        self.assertIn('The owner switched these gates off for this job: merge, spend; those need no yes. Every other gate still '
                      'needs the owner\'s recorded yes.', brief)
        self.assertIn(f'Merge only with stampede merge {job} <pr>', brief)
        shown = self.cli('config', 'show', '--job', job)
        self.assertIn('gates.merge = false  (flag, at new)', shown.stdout)
        self.assertIn('gates.close = true  (default, at new)', shown.stdout)
        code, out = self.quiet(owner_.finish, job, 'done')
        self.assertIn('gates off: merge, spend\nFINISHED', out)

    def test_a_user_file_opt_out_holds_for_the_job_made_then(self):
        user = self.root / 'home/.config/stampede/config.toml'
        user.parent.mkdir(parents=True)
        user.write_text('[gates]\npush_default_branch = false\n')
        job = self.started()
        self.assertEqual((job / 'gates.log').read_text().split(' ', 1)[1], 'OFF push_default_branch (user)\n')
        self.assertIn('gates off for this job: push_default_branch;', (job / 'briefs' / (LEAD + '.md')).read_text())
        user.unlink()
        self.assertEqual(gates_.off(job), ['push_default_branch'], 'the record, not the live file, decides')

    def test_with_no_gate_off_finish_prints_as_before(self):
        job = self.started()
        self.assertFalse((job / 'gates.log').exists())
        _, out = self.quiet(owner_.finish, job, 'done')
        self.assertNotIn('gates off', out)

    def test_an_unknown_no_gate_is_refused_with_the_list(self):
        ask = self.root / 'ask.md'
        ask.write_text('Fix the login bug\n')
        result = self.cli('new', '--core', '--file', ask, '--cwd', self.repo, '--no-gate', 'mege')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--no-gate mege is no gate: it takes merge, push_default_branch, deploy', result.stderr)


class Merge(Scratch):
    def setUp(self):
        super().setUp()
        (self.bin / 'gh').write_text(FAKE_GH)
        (self.bin / 'gh').chmod(0o755)
        self.state, self.log = self.root / 'gh.json', self.root / 'gh.log'
        os.environ.update({'GH_STATE': str(self.state), 'GH_LOG': str(self.log)})
        self.pr(head=SHA)
        self.report = self.job / 'reports' / 'review.md'
        self.report.parent.mkdir()
        self.review(f'# review\n\nStatus: PASS\nReviewed: {SHA}\n')

    def pr(self, **fields):
        self.state.write_text(json.dumps({'merge_commit': 'c' * 40, **fields}))

    def review(self, text):
        self.report.write_text(text)

    def calls(self):
        return [json.loads(row) for row in self.log.read_text().splitlines()] if self.log.is_file() else []

    def merge(self, *extra):
        return subprocess.run([str(FLEET), 'merge', str(self.job), '12', '--sha', SHA, '--review', str(self.report), *extra],
                              capture_output=True, text=True)

    def refused(self, *extra):
        result = self.merge(*extra)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse([c for c in self.calls() if c[:2] == ['pr', 'merge']], 'nothing merged')
        return result.stderr

    def test_the_review_report_must_pass_that_very_commit(self):
        self.report.unlink()
        self.assertIn('no review report', self.refused('--gate', self.gate()))
        self.review('Status: FINDINGS\nReviewed: ' + SHA + '\n')
        self.assertIn('says Status: FINDINGS, not PASS', self.refused('--gate', self.gate()))
        self.review('\n' * 10 + 'Status: PASS\nReviewed: ' + SHA + '\n')
        self.assertIn('Status: (none), not PASS', self.refused('--gate', self.gate()), 'only the first 10 lines count')
        self.review('Status: PASS\n')
        self.assertIn('names no Reviewed:', self.refused('--gate', self.gate()))
        self.review(f'Status: PASS\nReviewed: {OTHER}\n')
        self.assertIn(f'the review report passes {OTHER}, not {SHA}', self.refused('--gate', self.gate()))

    def test_a_moved_head_or_a_closed_pr_is_refused(self):
        self.pr(head=OTHER)
        self.assertIn(f'the review report passes {SHA} but the PR head is {OTHER}: review the new commit',
                      self.refused('--gate', self.gate()))
        self.pr(head=SHA, state='MERGED')
        self.assertIn('PR 12 is merged, not open', self.refused('--gate', self.gate()))

    def test_the_merge_gate_needs_an_approved_gate_for_this_pr_at_this_commit(self):
        err = self.refused()
        self.assertEqual(err, 'stampede merge: the merge gate is on: ask the owner with the next line, then run this again with '
                              f"--gate <id>\nstampede ask {self.job} --gate --kind merge --sha {SHA} --pr 12 'merge PR 12 at {SHA}'\n")
        self.assertIn('has no recorded yes', self.refused('--gate', self.gate(approve=False)))
        self.assertIn('is not a merge gate for PR 12 (it is merge, PR 13)', self.refused('--gate', self.gate('1123456789ab', pr=13)))
        self.assertIn('is not a merge gate for PR 12 (it is of no kind', self.refused('--gate', self.gate('2123456789ab', kind=None)))
        self.assertIn('(it is send, PR 12)', self.refused('--gate', self.gate('3123456789ab', kind='send')))
        self.assertIn('no gate', self.refused('--gate', 'ffffffffffff'))

    def test_an_approved_gate_merges_the_reviewed_commit(self):
        self.pr(head=SHA, draft=True)
        result = self.merge('--gate', self.gate())
        self.assertEqual((result.returncode, result.stdout), (0, f'MERGED 12 {"c" * 40}\n'), result.stderr)
        self.assertEqual(self.calls(), [['pr', 'view', '12', '--json', 'headRefOid,isDraft,state'], ['pr', 'ready', '12'],
                                        ['pr', 'merge', '12', '--squash', '--match-head-commit', SHA],
                                        ['pr', 'view', '12', '--json', 'mergeCommit', '-q', '.mergeCommit.oid']])
        row = (self.job / 'merges.log').read_text().splitlines(True)[-1].split(' ', 1)[1]
        self.assertEqual(row, f'MERGED 12 {SHA} {"c" * 40} squash review {self.report} gate 0123456789ab\n')
        self.assertFalse((self.job / 'gates.log').exists())

    def test_with_the_gate_off_it_merges_without_one_and_logs_it_and_the_method_is_a_setting(self):
        self.begin(merge=False)
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'cfg')}):
            (self.root / 'cfg/stampede').mkdir(parents=True)
            (self.root / 'cfg/stampede/config.toml').write_text('[merge]\nmethod = "rebase"\n')
            result = self.merge()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['pr', 'merge', '12', '--rebase', '--match-head-commit', SHA], self.calls())
        self.assertNotIn(['pr', 'ready', '12'], self.calls())
        self.assertEqual([r.split(' ', 1)[1] for r in (self.job / 'gates.log').read_text().splitlines()],
                         ['OFF merge (flag)', f'MERGE 12 {SHA} without the merge gate (off: flag)'])
        self.assertIn('gate off', (self.job / 'merges.log').read_text())

    def test_a_gh_failure_is_exit_1_with_its_line(self):
        self.pr(head=SHA, fail=True)
        result = self.merge('--gate', self.gate())
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, 'stampede merge: gh pr merge failed: GraphQL: Head branch was modified\n')
        rows = [r.split(' ', 1)[1] for r in (self.job / 'merges.log').read_text().splitlines()]
        self.assertEqual(rows, [f'MERGING 12 {SHA} squash review {self.report} gate 0123456789ab',
                                f'FAILED 12 {SHA} squash review {self.report} gate 0123456789ab: gh pr merge failed: GraphQL: Head '
                                'branch was modified'])


class Hook(Scratch):
    def setUp(self):
        super().setUp()
        self.bare = self.root / 'remote.git'
        git('init', '--bare', '-q', '-b', 'main', str(self.bare), cwd=self.root)
        git('init', '-q', '-b', 'main', cwd=self.repo)
        git('remote', 'add', 'origin', str(self.bare), cwd=self.repo)
        git('commit', '-q', '--allow-empty', '-m', 'one', cwd=self.repo)
        self.hook = self.repo / '.git/hooks/pre-push'

    def test_new_installs_it_once_and_leaves_an_existing_hook_or_hooks_path_alone(self):
        self.begin()
        self.assertIn(gates_.HOOK_MARK, self.hook.read_text())
        self.assertTrue(os.access(self.hook, os.X_OK))
        with mock.patch('sys.stderr') as err:
            self.begin()  # a second job in the same repo
        self.assertEqual((self.hook.read_text(), err.write.called), (gates_.HOOK, False))
        self.hook.write_text('#!/bin/sh\nexit 0\n')
        with mock.patch('sys.stderr') as err:
            self.begin()
        self.assertEqual(self.hook.read_text(), '#!/bin/sh\nexit 0\n')
        self.assertIn('already exists); to hold the push gate, add this line', ''.join(c.args[0] for c in err.write.call_args_list))
        self.hook.unlink()
        git('config', 'core.hooksPath', '.githooks', cwd=self.repo)
        with mock.patch('sys.stderr') as err:
            self.begin()
        self.assertFalse(self.hook.exists())
        self.assertIn('core.hooksPath is set (.githooks)', ''.join(c.args[0] for c in err.write.call_args_list))
        git('config', '--unset', 'core.hooksPath', cwd=self.repo)
        self.begin(push_default_branch=False)
        self.assertFalse(self.hook.exists(), 'with the gate off nothing is installed')

    def push(self, ref, job=True):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
        if job:
            env['STAMPEDE_JOB_KEY'] = 'hc-0123456789ab'
        return subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:' + ref], cwd=self.repo, capture_output=True, text=True, env=env)

    def head(self):
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True).stdout.strip()

    def marked(self, **flags):
        self.begin(**flags)
        (self.events / 'jobs').mkdir(exist_ok=True)
        (self.events / 'jobs' / 'hc-0123456789ab').write_text(str(self.job) + '\n')

    def test_a_job_s_push_to_main_needs_the_gate_and_every_other_push_passes(self):
        self.marked()
        self.assertEqual(self.push('feature').returncode, 0)
        refused = self.push('main')
        self.assertNotEqual(refused.returncode, 0)
        sha = self.head()
        self.assertIn(f'stampede prepush: a push of {sha} to main needs the owner\'s yes. Ask it with the next line, then push '
                      f"again once stampede gate-ok prints APPROVED:\nstampede ask {self.job} --gate --kind push_default_branch "
                      f"--sha {sha} 'push {sha} to main'\n", refused.stderr)
        self.assertNotIn(sha, subprocess.run(['git', 'branch', '--list', 'main', '-v'], cwd=self.bare, capture_output=True,
                                             text=True).stdout)
        self.assertEqual(self.push('main', job=False).returncode, 0, 'the owner\'s own shell is never touched')
        git('commit', '-q', '--allow-empty', '-m', 'two', cwd=self.repo)
        self.assertNotEqual(self.push('main').returncode, 0)
        self.gate(sha=self.head(), pr=None)  # a merge gate at that sha opens no push
        self.assertNotEqual(self.push('main').returncode, 0)
        self.gate('1123456789ab', sha=self.head(), pr=None, kind='push_default_branch')
        result = self.push('main')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_with_the_push_gate_off_a_push_to_main_passes_and_is_logged(self):
        self.marked(push_default_branch=False)
        gates_.install_hook(self.repo)  # a hook from another job of this repo
        self.assertEqual(self.push('main').returncode, 0)
        rows = (self.job / 'gates.log').read_text().splitlines()
        self.assertEqual(rows[-1].split(' ', 1)[1], f'PUSH {self.head()} to main without the push gate (off: flag)')

    def test_the_remote_s_head_names_the_default_branch(self):
        self.marked()
        git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/trunk', cwd=self.repo)
        self.assertEqual(self.push('main').returncode, 0)
        self.assertNotEqual(self.push('trunk').returncode, 0)



class Round1Merge(Merge):
    """The review's findings on merge: R1 (the report's own header only), R4 (the log first), R8, R9, decision 1."""

    def test_r1_only_the_report_s_own_header_counts(self):
        cases = {
            'duplicate status': (f'Status: PASS\nReviewed: {SHA}\nStatus: FINDINGS\n', 'has 2 Status: lines in its first 10 lines (PASS, FINDINGS)'),
            'duplicate reviewed': (f'Status: PASS\nReviewed: {SHA}\nReviewed: {OTHER}\n', 'has 2 Reviewed: lines'),
            'fenced pass example': (f'```\nStatus: PASS\nReviewed: {SHA}\n```\nStatus: FINDINGS\nReviewed: {SHA}\n',
                                    'says Status: FINDINGS, not PASS'),
            'indented pass example': (f'    Status: PASS\n    Reviewed: {SHA}\nStatus: FINDINGS\nReviewed: {SHA}\n',
                                      'says Status: FINDINGS, not PASS'),
            'pass only in a fence': (f'~~~\nStatus: PASS\nReviewed: {SHA}\n~~~\n', 'says Status: (none), not PASS'),
            'pass only quoted': (f'> Status: PASS\n> Reviewed: {SHA}\n', 'says Status: (none), not PASS'),
            'pass with words after it': (f'Status: PASS with notes\nReviewed: {SHA}\n', 'says Status: PASS with notes, not PASS'),
            'a lowercase status': (f'status: PASS\nReviewed: {SHA}\n', 'says Status: (none)'),
            'a fence left open hides the rest': (f'```\nStatus: PASS\nReviewed: {SHA}\n', 'says Status: (none)'),
        }
        for name, (text, said) in cases.items():
            with self.subTest(name):
                self.review(text)
                self.assertIn(said, self.refused('--gate', self.gate()))
        self.review(f'# review\n\n```\nStatus: FINDINGS\n```\nStatus: PASS\nReviewed: {SHA}  \n')
        self.assertEqual(self.merge('--gate', self.gate()).returncode, 0, 'a fenced example does not count against it either')

    def test_r4_the_log_is_written_before_anything_merges(self):
        (self.job / 'merges.log').mkdir()
        err = self.refused('--gate', self.gate())
        self.assertIn('merges.log cannot be written', err)
        self.assertIn('nothing was merged', err)
        (self.job / 'merges.log').rmdir()
        self.pr(head=SHA, merge_commit='')  # gh merged, but the merge commit cannot be read back
        result = self.merge('--gate', self.gate())
        self.assertEqual((result.returncode, result.stdout), (0, 'MERGED 12\n'), result.stderr)
        self.assertIn('MERGED 12 ' + SHA + ' (merge commit not read)', (self.job / 'merges.log').read_text())

    def test_r9_the_ask_line_runs_as_printed_with_spaces_in_the_job_path(self):
        spaced = self.root / 'my jobs' / 'demo job'
        spaced.parent.mkdir()
        self.job.rename(spaced)
        self.job, self.report = spaced, spaced / 'reports' / 'review.md'
        line = self.refused().splitlines()[1]
        self.assertEqual(__import__('shlex').split(line), ['stampede', 'ask', str(spaced), '--gate', '--kind', 'merge', '--sha',
                                                           SHA, '--pr', '12', f'merge PR 12 at {SHA}'])

    def test_d1_a_merge_gate_asked_with_kind_merge_opens_merge(self):
        (self.job / 'ask.md').write_text('x\n')
        with mock.patch.object(owner_, 'ask_background'), mock.patch('sys.stdout'):
            owner_.ask_gate(self.job, f'merge PR 12 at {SHA}', SHA, 12, 'merge')
        (ident,) = [g.stem for g in (self.job / 'gates').glob('*.json')]
        gate = owner_.load_gate(self.job, ident)
        self.assertEqual(gate['kind'], 'merge')
        self.assertEqual(owner_.gate_question(gate), f'Gate {ident} (merge): merge PR 12 at {SHA} (PR #12) at {SHA[:12]}?')
        before = owner_.gate_digest(gate)
        self.assertNotEqual(before, owner_.gate_digest({**gate, 'kind': 'send'}), 'the digest covers the kind')
        record = {'gate': ident, 'sha': SHA, 'by': 'owner', 'at': 'now', 'digest': before}
        (self.job / 'gates' / (ident + '.approved')).write_text(json.dumps(record))
        self.assertEqual(self.merge('--gate', ident).returncode, 0)

    def test_d1_ask_kind_takes_only_a_gate_name(self):
        (self.job / 'ask.md').write_text('x\n')
        result = subprocess.run([str(FLEET), 'ask', str(self.job), '--gate', '--kind', 'mergee', '--sha', SHA, 'x'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice: 'mergee'", result.stderr)
        result = subprocess.run([str(FLEET), 'ask', str(self.job), '--kind', 'merge', 'which?'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stderr.strip()), (2, 'stampede ask: --kind is for a gate: ask --gate --kind <name>'))


class Round1Keys(Scratch):
    def test_r8_a_job_with_no_record_shows_every_gate_on_whatever_the_user_says(self):
        (self.job / 'ask.md').write_text('x\n')
        user = self.home / '.config/stampede/config.toml'
        user.parent.mkdir(parents=True)
        user.write_text('[gates]\nmerge = false\n')
        shown = subprocess.run([str(FLEET), 'config', 'show', '--job', str(self.job)], capture_output=True, text=True).stdout
        self.assertIn('gates.merge = true  (no record: all on)', shown)
        self.assertEqual(gates_.off(self.job), [])


class Round1Hook(Hook):
    """R2, R3, R5, R6 and decision 2, in a real scratch repo with a scratch bare remote."""

    def stand_in(self, body):
        (self.bin / 'stampede').write_text('#!/bin/sh\n' + body)
        (self.bin / 'stampede').chmod(0o755)

    def without_stampede(self):
        git_bin = os.path.dirname(subprocess.run(['sh', '-c', 'command -v git'], capture_output=True, text=True).stdout.strip())
        return {'PATH': f'{git_bin}:/usr/bin:/bin'}

    def push_env(self, ref, job=True, **env):
        with mock.patch.dict(os.environ, env):
            return self.push(ref, job)

    def test_r2_a_default_branch_with_a_slash_is_whole(self):
        self.marked()
        git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/release/stable', cwd=self.repo)
        self.assertNotEqual(self.push('release/stable').returncode, 0)
        self.assertEqual(self.push('stable').returncode, 0)
        self.assertEqual(self.push('main').returncode, 0)

    def test_r3_outside_a_job_the_hook_never_calls_stampede(self):
        self.marked()
        self.stand_in('echo called >> "$0.log"; exit 2\n')  # an old stampede without prepush
        for ref in ('feature', 'main'):
            self.assertEqual(self.push(ref, job=False).returncode, 0, ref)
        self.assertFalse((self.bin / 'stampede.log').exists())
        with mock.patch.dict(os.environ, {'STAMPEDE_JOB_KEY': 'hc-ffffffffffff'}):  # a key with no marker
            self.assertEqual(self.push('main', job=False).returncode, 0)

    def test_r3_inside_a_job_a_missing_old_or_crashing_stampede_warns_and_lets_the_push_through(self):
        self.marked()
        result = self.push_env('main', **self.without_stampede())
        self.assertEqual(result.returncode, 0)
        self.assertIn('stampede-hook: stampede is not on PATH, so this job\'s push gate was not checked', result.stderr)
        for body, code in (('exit 2\n', 2), ('echo Traceback >&2; exit 1\n', 1)):
            self.stand_in(body)
            result = self.push('main')
            self.assertEqual(result.returncode, 0, body)
            self.assertIn(f'stampede prepush failed (exit {code}), so this job\'s push gate was not checked', result.stderr)
        git('commit', '-q', '--allow-empty', '-m', 'two', cwd=self.repo)
        self.stand_in(f'exit {gates_.REFUSED}\n')
        self.assertNotEqual(self.push('main').returncode, 0, 'only the refusal stops it')

    def test_r3_the_suggested_line_in_an_existing_hook_behaves_the_same(self):
        self.marked()
        self.hook.write_text('#!/bin/sh\n' + gates_.HOOK_LINE + '\n')  # the last line: its status is the hook's
        self.hook.chmod(0o755)
        self.assertEqual(self.push('feature').returncode, 0)
        self.assertNotEqual(self.push('main').returncode, 0, 'a job\'s push to main is refused')
        self.assertEqual(self.push_env('main', **self.without_stampede()).returncode, 0, 'stampede absent')
        git('commit', '-q', '--allow-empty', '-m', 'two', cwd=self.repo)
        self.stand_in('exit 2\n')
        self.assertEqual(self.push('main').returncode, 0, 'an old stampede')

    def test_r5_a_symlink_or_an_empty_hooks_path_counts_as_there(self):
        target = self.root / 'nowhere' / 'hook'
        self.hook.parent.mkdir(exist_ok=True)
        self.hook.symlink_to(target)
        with mock.patch('sys.stderr') as err:
            self.begin()
        self.assertFalse(target.exists() or target.parent.exists(), 'a dangling symlink is never followed')
        self.assertIn('already exists', ''.join(c.args[0] for c in err.write.call_args_list))
        self.hook.unlink()
        mine = self.root / 'mine'
        mine.write_text(gates_.HOOK)
        self.hook.symlink_to(mine)
        with mock.patch('sys.stderr') as err:
            self.begin()
        self.assertIn('already exists', ''.join(c.args[0] for c in err.write.call_args_list), 'a symlink is not ours, even to ours')
        self.hook.unlink()
        git('config', 'core.hooksPath', '', cwd=self.repo)
        with mock.patch('sys.stderr') as err:
            self.begin()
        self.assertFalse(self.hook.exists())
        self.assertIn('core.hooksPath is set (empty)', ''.join(c.args[0] for c in err.write.call_args_list))

    def test_r6_a_stale_core_key_falls_through_to_the_workspace_marker(self):
        self.begin()
        (self.events / 'jobs').mkdir(exist_ok=True)
        (self.events / 'jobs' / 'w9').write_text(str(self.job) + '\n')
        (self.events / 'jobs' / 'hc-0123456789ab').write_text('/gone/job\n')  # stale: its folder is gone
        env = {**os.environ, 'HERDR_WORKSPACE_ID': 'w9', 'STAMPEDE_JOB_KEY': 'hc-0123456789ab'}
        lines = [f'refs/heads/main {self.head()} refs/heads/main {"0" * 40}']
        with mock.patch('sys.stderr'), mock.patch.dict(os.environ, {'GIT_DIR': str(self.repo / '.git')}):
            self.assertEqual(gates_.prepush('origin', lines, env), gates_.REFUSED)
            env['STAMPEDE_JOB_KEY'] = 'hc-ffffffffffff'  # no marker at all
            self.assertEqual(gates_.prepush('origin', lines, env), gates_.REFUSED)
            self.assertEqual(gates_.prepush('origin', lines, {'STAMPEDE_JOB_KEY': 'hc-0123456789ab'}), 0)

    def test_d2_new_records_the_remote_s_default_branch(self):
        git('push', '-q', 'origin', 'HEAD:trunk', cwd=self.repo)
        git('symbolic-ref', 'HEAD', 'refs/heads/trunk', cwd=self.bare)  # the remote's HEAD; no origin/HEAD here
        self.marked()
        self.assertEqual(gates_.recorded(self.job)['default_branch'], {'origin': 'trunk', str(self.bare): 'trunk'})
        self.assertEqual(self.push('main').returncode, 0)
        git('commit', '-q', '--allow-empty', '-m', 'two', cwd=self.repo)
        self.assertNotEqual(self.push('trunk').returncode, 0)
        result = subprocess.run(['git', 'push', '-q', str(self.bare), 'HEAD:trunk'], cwd=self.repo, capture_output=True,
                                text=True, env={**os.environ, 'STAMPEDE_JOB_KEY': 'hc-0123456789ab'})
        self.assertNotEqual(result.returncode, 0, 'a push by URL finds the branch by the URL')


if __name__ == '__main__':
    unittest.main()
