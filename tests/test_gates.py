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

    def gate(self, ident='0123456789ab', sha=SHA, pr=12, approve=True):
        gate = {'gate': ident, 'action': f'merge PR {pr} at {sha}', 'pr': pr, 'sha': sha, 'route': 'local', 'asked': 'now'}
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
        self.assertIn(f"the merge gate is on: ask the owner with stampede ask {self.job} --gate --sha {SHA} --pr 12 "
                      f"'merge PR 12 at {SHA}'", err)
        self.assertIn('has no recorded yes', self.refused('--gate', self.gate(approve=False)))
        self.assertIn('is not about PR 12', self.refused('--gate', self.gate('1123456789ab', pr=13)))
        self.assertIn('no gate', self.refused('--gate', 'ffffffffffff'))

    def test_an_approved_gate_merges_the_reviewed_commit(self):
        self.pr(head=SHA, draft=True)
        result = self.merge('--gate', self.gate())
        self.assertEqual((result.returncode, result.stdout), (0, f'MERGED 12 {"c" * 40}\n'), result.stderr)
        self.assertEqual(self.calls(), [['pr', 'view', '12', '--json', 'headRefOid,isDraft,state'], ['pr', 'ready', '12'],
                                        ['pr', 'merge', '12', '--squash', '--match-head-commit', SHA],
                                        ['pr', 'view', '12', '--json', 'mergeCommit', '-q', '.mergeCommit.oid']])
        row = (self.job / 'merges.log').read_text().split(' ', 1)[1]
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
        self.assertFalse((self.job / 'merges.log').exists())


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
        self.assertIn('core.hooksPath is .githooks', ''.join(c.args[0] for c in err.write.call_args_list))
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
        self.assertIn(f'stampede prepush: a push of {sha} to main needs the owner\'s yes. Ask with: stampede ask {self.job} '
                      f"--gate --sha {sha} 'push {sha} to main'", refused.stderr)
        self.assertNotIn(sha, subprocess.run(['git', 'branch', '--list', 'main', '-v'], cwd=self.bare, capture_output=True,
                                             text=True).stdout)
        self.assertEqual(self.push('main', job=False).returncode, 0, 'the owner\'s own shell is never touched')
        git('commit', '-q', '--allow-empty', '-m', 'two', cwd=self.repo)
        self.assertNotEqual(self.push('main').returncode, 0)
        self.gate(sha=self.head(), pr=None)
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


if __name__ == '__main__':
    unittest.main()
