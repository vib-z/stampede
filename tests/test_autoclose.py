"""finish.auto_close: a finished job's own Herdr TUI workspace closes by itself only when nothing is left to lose or answer."""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/herdr-fleet/scripts'))
from stampede import autoclose as autoclose_, herdrapi as herdrapi_, owner as owner_, settings as settings_  # noqa: E402


class AutoClose(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        patch = mock.patch.dict(os.environ, {'HOME': str(self.home), 'HERDR_EVENTS_DIR': str(self.home / 'events')})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop('XDG_CONFIG_HOME', None)
        self.config(auto_close='true', close_after='0')
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        for args in (['init', '-q'], ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'one']):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True)
        self.job = self.home / 'jobs/2026-11-24-alpha-demo'
        self.job.mkdir(parents=True)
        (self.job / 'agents.tsv').write_text('lead-demo\tclaude\t-\t-\t-\nbuild-x\tclaude\t-\t-\t-\n')
        (self.job / 'lead').write_text('lead-demo\n')
        (self.job / 'workspace').write_text('w9\n')
        (self.job / 'workdir').write_text(str(self.repo) + '\n')
        (self.job / 'finished').write_text('shipped\n')
        (self.home / 'events/owners').mkdir(parents=True)
        (self.home / 'events/owners/w9').write_text('owner=alpha\n')
        self.panes = [('w9:p1', 'lead-demo', 'idle'), ('w9:p2', 'build-x', 'done')]
        self.calls = []
        mock.patch.object(herdrapi_, 'herdr', self.herdr).start()
        mock.patch.object(autoclose_, 'QUIET_EVERY', 0).start()
        self.scripts = self.home / 'scripts'
        self.scripts.mkdir()
        for name, body in (('herdr-reopen-snapshot', f'touch "$2/reopen.sh"; echo "$*" >> {self.home}/snap'),
                           ('herdr-events-owner', f'echo "$*" >> {self.home}/owner; [ "$2" = --clear ] && rm -f {self.home}/events/owners/$1; true'),
                           ('herdr-event-post', f'printf "%s\\n" "$1" >> {self.home}/posted')):
            (self.scripts / name).write_text('#!/bin/bash\n' + body + '\n')
            (self.scripts / name).chmod(0o755)
        mock.patch.object(autoclose_, 'SCRIPTS', self.scripts).start()
        self.addCleanup(mock.patch.stopall)

    def config(self, **values):
        path = self.home / '.config/stampede/config.toml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[finish]\n' + ''.join(f'{k} = {v}\n' for k, v in values.items()))

    def herdr(self, *args, timeout=None):
        self.calls.append(args)
        if args[:2] == ('agent', 'list'):
            return {'agents': [{'pane_id': p, 'name': n, 'workspace_id': 'w9', 'agent_status': s} for p, n, s in self.panes]}
        if args[:2] == ('pane', 'list'):
            return {'panes': [{'pane_id': p, 'agent_status': s, 'cwd': str(self.repo)} for p, _, s in self.panes]}
        if args[:2] == ('workspace', 'close'):
            return {}
        raise AssertionError(args)

    def run_closer(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = autoclose_.run(self.job)
        return code, out.getvalue()

    def events(self):
        path = self.home / 'posted'
        return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []

    def test_a_clean_finished_job_closes_its_own_workspace(self):
        code, out = self.run_closer()
        self.assertEqual(code, 0, out)
        self.assertIn(('workspace', 'close', 'w9'), self.calls)
        self.assertEqual((self.home / 'owner').read_text(), 'w9 --clear\n')
        self.assertEqual((self.home / 'snap').read_text(), f'w9 {self.job}\n')
        event = self.events()[0]
        self.assertEqual((event['source'], event['state'], event['workspace'], event['owner']), ('stampede', 'closed', 'w9', 'alpha'))
        self.assertIn(str(self.job / 'reopen.sh'), event['summary'])
        self.assertIn('CLOSED w9', out)

    def kept(self, reason):
        code, out = self.run_closer()
        self.assertEqual(code, 1, out)
        self.assertNotIn(('workspace', 'close', 'w9'), self.calls)
        self.assertFalse((self.home / 'owner').exists(), 'the owner tag stays')
        self.assertTrue((self.home / 'events/owners/w9').exists())
        event = self.events()[-1]
        self.assertEqual((event['state'], event['owner']), ('kept', 'alpha'))
        self.assertIn(reason, event['summary'])

    def test_uncommitted_changes_keep_it(self):
        (self.repo / 'notes.txt').write_text('draft\n')
        self.kept(f'{self.repo.resolve()} has uncommitted changes')

    def test_a_gate_waiting_on_the_owner_keeps_it(self):
        (self.job / 'gates').mkdir()
        (self.job / 'gates/0123456789ab.json').write_text('{}\n')
        self.kept('gate 0123456789ab waits on the owner')
        (self.job / 'gates/0123456789ab.approved').write_text('{}\n')
        self.calls.clear()
        self.assertEqual(self.run_closer()[0], 0)

    def test_a_pane_that_is_not_the_job_s_keeps_it(self):
        self.panes.append(('w9:p3', '', 'idle'))   # the owner's own shell: a project workspace
        self.kept('pane w9:p3 is not one of this job\'s agents')

    def test_another_open_job_keeps_it(self):
        (self.home / 'events/jobs').mkdir()
        (self.home / 'events/jobs/w9').write_text('/elsewhere/job\n')
        self.kept('another job is open in it (/elsewhere/job)')

    def test_an_agent_still_working_keeps_it(self):
        self.panes[1] = ('w9:p2', 'build-x', 'working')
        with mock.patch.object(autoclose_, 'QUIET_FOR', 0):
            self.kept('build-x still working after 0 minutes')

    def test_an_unfinished_job_keeps_it(self):
        (self.job / 'finished').unlink()
        self.kept('the job has not finished')

    def test_a_failed_reopen_record_keeps_it(self):
        (self.scripts / 'herdr-reopen-snapshot').write_text('#!/bin/bash\necho "no herdr" >&2; exit 1\n')
        self.kept('the reopen record was not written (no herdr)')

    def test_a_failed_close_puts_the_owner_tag_back(self):
        def refuse(*args, timeout=None):
            if args[:2] == ('workspace', 'close'):
                raise herdrapi_.HerdrError('herdr workspace close: no', 'refused')
            return self.herdr(*args)
        herdrapi_.herdr = refuse
        code, out = self.run_closer()
        self.assertEqual(code, 1, out)
        self.assertEqual((self.home / 'owner').read_text(), 'w9 --clear\nw9 alpha\n')
        self.assertEqual(self.events()[-1]['state'], 'kept')

    def test_the_setting_is_off_by_default_and_the_user_s_own(self):
        self.assertEqual(autoclose_.enabled(self.job), 'w9')
        (self.home / '.config/stampede/config.toml').unlink()
        self.assertEqual(autoclose_.enabled(self.job), '')
        self.assertIs(settings_.DEFAULTS['finish.auto_close'], False)
        (self.repo / '.stampede.toml').write_text('[finish]\nauto_close = true\n')
        loaded = settings_.load(repo=self.repo, env=os.environ)
        self.assertIs(loaded.get('finish.auto_close'), False)
        self.assertTrue(any('finish.auto_close is taken only from your own' in p for p in loaded.problems))
        self.config(auto_close='true')
        (self.job / 'backend').write_text('native\n')   # only a Herdr TUI workspace
        self.assertEqual(autoclose_.enabled(self.job), '')

    def test_finish_starts_one_closer_only_when_the_setting_is_on(self):
        (self.job / 'finished').unlink()
        with mock.patch.object(autoclose_, 'start') as started, mock.patch.object(owner_, 'post_local') as posted, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            owner_.finish(self.job, 'shipped')
            owner_.finish(self.job, 'again')
        started.assert_called_once_with(self.job)
        self.assertEqual(posted.call_args.args[1]['auto_close'], 'pending')
        self.assertIn(f'AUTO-CLOSE w9: closes once every agent is idle', out.getvalue())
        self.config(auto_close='false')
        (self.job / 'finished').unlink()
        with mock.patch.object(autoclose_, 'start') as started, mock.patch.object(owner_, 'post_local') as posted, \
                contextlib.redirect_stdout(io.StringIO()):
            owner_.finish(self.job, 'shipped')
        started.assert_not_called()
        self.assertNotIn('auto_close', posted.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
