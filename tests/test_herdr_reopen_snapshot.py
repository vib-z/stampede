"""grokbot-herdr's herdr-reopen-snapshot against fixture JSON: REOPEN.md and reopen.sh, then reopen.sh against a fake herdr (stdlib)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/grokbot-herdr/scripts/herdr-reopen-snapshot'

# Logs every call. Reads come from state.json; creates hand out new ids numbered by the call count.
FAKE_HERDR = r'''#!/usr/bin/env python3
import json, os, sys
d, a = os.environ['FAKE_DIR'], sys.argv[1:]
with open(f'{d}/calls', 'a') as f:
    f.write(' '.join(a) + '\n')
n = len(open(f'{d}/calls').read().splitlines())
s = json.load(open(f'{d}/state.json'))
key = ' '.join(a[:2])
if key == 'pane layout':
    r = {'layout': {'panes': s['layout'][a[a.index('--pane') + 1]]}}
elif key == 'tab list':
    r = {'tabs': s['tabs'].get(a[a.index('--workspace') + 1], [])}
elif key == 'workspace create':
    r = {'workspace': {'workspace_id': 'w9'}, 'tab': {'tab_id': 'w9:t1'}, 'root_pane': {'pane_id': f'w9:p{n}'}}
elif key == 'tab create':
    r = {'tab': {'tab_id': f'w9:t{n}'}, 'root_pane': {'pane_id': f'w9:p{n}'}}
elif key == 'pane split':
    r = {'pane': {'pane_id': f'w9:p{n}'}}
else:
    r = s.get(key, {})
print(json.dumps({'result': r}))
'''
LOGGER = '#!/bin/bash\necho "$(basename "$0") $*" >> "$FAKE_DIR/calls"\n'


def pane(pid, tab, label, cwd, agent=None, session=None):
    p = {'pane_id': pid, 'tab_id': tab, 'workspace_id': 'wJ', 'label': label, 'cwd': cwd, 'agent': agent}
    if session:
        p['agent_session'] = {'agent': agent, 'kind': 'id', 'value': session}
    return p


def rect(pid, x, y, w, h):
    return {'pane_id': pid, 'rect': {'x': x, 'y': y, 'width': w, 'height': h}}


class ReopenSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.dir, self.job, home = t, t / 'job', t / 'home'
        (home / '.local/bin').mkdir(parents=True)
        for name, body in (('herdr', FAKE_HERDR), ('herdr-events-owner', LOGGER), ('herdr-send', LOGGER)):
            f = home / '.local/bin' / name
            f.write_text(body)
            f.chmod(0o755)
        self.env = dict(os.environ, HOME=str(home), FAKE_DIR=str(t), HERDR=str(home / '.local/bin/herdr'))
        self.repo, self.wt = t / 'repo', t / 'repo/wt api'
        self.wt.mkdir(parents=True)
        self.panes = [pane('wJ:p1', 'wJ:t1', 'lead-demo', str(self.repo), 'claude', 's-lead'),
                      pane('wJ:p2', 'wJ:t1', 'build-api', str(self.wt), 'codex', 's-api'),
                      pane('wJ:p3', 'wJ:t1', 'notes', str(self.repo)),
                      pane('wJ:p4', 'wJ:t2', 'review-api', str(self.repo), 'claude', 's-rev')]
        self.state(workspaces=[{'workspace_id': 'wJ', 'label': 'demo-job', 'tokens': {'owner': 'bot-alpha'}}])

    def tearDown(self):
        self.tmp.cleanup()

    def state(self, workspaces):
        named = [p for p in self.panes if p['agent']]
        (self.dir / 'state.json').write_text(json.dumps({
            'workspace list': {'workspaces': workspaces},
            'tabs': {'wJ': [{'tab_id': 'wJ:t1', 'label': 'build'}, {'tab_id': 'wJ:t2', 'label': 'review'}, {'tab_id': 'wJ:t3', 'label': 'mine'}],
                     'wP': [{'tab_id': 'wP:t1', 'label': 'build'}]},
            'pane list': {'panes': self.panes},
            'agent list': {'agents': [{'pane_id': p['pane_id'], 'name': p.get('label')} for p in named]},
            'layout': {'wJ:p1': [rect('wJ:p1', 0, 0, 100, 20), rect('wJ:p2', 101, 0, 99, 40), rect('wJ:p3', 0, 21, 100, 19)],
                       'wJ:p4': [rect('wJ:p4', 0, 0, 200, 40)], 'wJ:p9': [rect('wJ:p9', 0, 0, 200, 40)]}}))

    def run_cmd(self, *args):
        r = subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def reopen(self, *args):
        (self.dir / 'calls').unlink(missing_ok=True)
        r = subprocess.run([str(self.job / 'reopen.sh'), *args], env=self.env, capture_output=True, text=True, timeout=30)
        calls = (self.dir / 'calls').read_text() if (self.dir / 'calls').exists() else ''
        return r, calls

    def snapshot_all(self):
        self.run_cmd('record', str(self.job), 'lead-demo', 'claude', str(self.job / 'lead.md'), '--',
                     '--model', 'claude-opus-5-5', '--effort', 'xhigh', '--permission-mode', 'auto', '-n', 'lead-demo')
        self.run_cmd('record', str(self.job), 'build-api', 'codex', str(self.job / 'build-api.md'), '--',
                     '-m', 'gpt-6-astra', '-c', 'model_reasoning_effort="ultra"', '--approve-for-me')
        self.run_cmd('record', str(self.job), 'review-api', 'claude', '-', '--', '--model', 'claude-fable-5-1', '--effort', 'max')
        self.run_cmd('wJ', str(self.job))
        self.panes[3].update(agent=None)       # review-api exits before the refresh that precedes a close
        self.panes[3].pop('agent_session')
        self.state(workspaces=[{'workspace_id': 'wJ', 'label': 'demo-job', 'tokens': {'owner': 'bot-alpha'}}])
        self.run_cmd('wJ', str(self.job))
        self.state(workspaces=[])              # then the owner said yes and the workspace was closed

    def test_only_the_jobs_own_agents_are_kept(self):
        self.panes = self.panes[:2] + [pane('wJ:p9', 'wJ:t3', 'owner-other', str(self.repo), 'claude', 'owner-session'),
                                       pane('wJ:p3', 'wJ:t1', 'owner-here', str(self.repo), 'claude', 'here-session')]
        self.state(workspaces=[{'workspace_id': 'wJ', 'label': 'demo-job'}])
        self.run_cmd('record', str(self.job), 'lead-demo', 'claude', '-', '--', '--permission-mode', 'auto')
        self.run_cmd('record', str(self.job), 'build-api', 'codex', '-', '--', '--approve-for-me')
        self.run_cmd('wJ', str(self.job))
        names = [l.split('\t')[0] for l in (self.job / 'agents.tsv').read_text().splitlines() if not l.startswith('#')]
        self.assertEqual(names, ['lead-demo', 'build-api'])
        for f in ('REOPEN.md', 'reopen.sh'):
            text = (self.job / f).read_text()
            self.assertIn('build-api', text)
            for s in ('owner-other', 'owner-session', 'wJ:t3', "'mine'", 'here-session'):
                self.assertNotIn(s, text, f)
        self.assertIn(f'| build | wJ:p3 | owner-here | `{self.repo}` | shell |', (self.job / 'REOPEN.md').read_text())
        self.assertNotIn('start owner-here', (self.job / 'reopen.sh').read_text())   # kept as a plain shell pane

    def test_unlabelled_pane(self):
        self.panes.append({'pane_id': 'wJ:p5', 'tab_id': 'wJ:t1', 'workspace_id': 'wJ', 'cwd': str(self.repo), 'agent': 'claude',
                           'agent_session': {'agent': 'claude', 'kind': 'id', 'value': 's-x'}})   # herdr omits label on an unrenamed pane
        self.state(workspaces=[{'workspace_id': 'wJ', 'label': 'demo-job', 'tokens': {'owner': 'bot-alpha'}}])
        self.run_cmd('record', str(self.job), 'lead-demo', 'claude', '-', '--')   # t1 holds one of the job's agents
        self.run_cmd('wJ', str(self.job))
        self.assertIn('| build | wJ:p5 | - |', (self.job / 'REOPEN.md').read_text())   # listed, no crash

    def test_record_md_and_script(self):
        self.snapshot_all()
        md = (self.job / 'REOPEN.md').read_text()
        for s in ('`demo-job`', 'owner tag `bot-alpha`', f'| build | wJ:p2 | build-api | `{self.wt}` | codex | gpt-6-astra | ultra | s-api |',
                  f'| review | wJ:p4 | review-api | `{self.repo}` | claude | claude-fable-5-1 | max | s-rev | - |', f'| build | wJ:p3 | notes | `{self.repo}` | shell |',
                  "herdr agent start build-api --kind codex --pane <build-api> --timeout 90000 -- resume s-api -m gpt-6-astra -c 'model_reasoning_effort=\"ultra\"' --approve-for-me"):
            self.assertIn(s, md)
        self.assertNotRegex(md + (self.job / 'reopen.sh').read_text(), '[\u2013\u2014]')
        self.assertTrue(os.access(self.job / 'reopen.sh', os.X_OK))
        self.assertEqual(subprocess.run(['bash', '-n', str(self.job / 'reopen.sh')]).returncode, 0)

    def test_reopen_recreates_layout_and_resumes(self):
        self.snapshot_all()
        r, calls = self.reopen()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('REOPENED demo-job in w9', r.stdout)
        c = calls.splitlines()
        self.assertIn(f'workspace create --cwd {self.repo} --label demo-job --no-focus', c)
        self.assertIn('herdr-events-owner w9 bot-alpha', c)
        self.assertIn('tab rename w9:t1 build', c)
        root = next(l.split()[2] for l in c if l.startswith('pane rename') and l.endswith(' lead-demo'))
        self.assertIn(f'pane split --pane {root} --direction right --cwd {self.wt} --no-focus', c)
        self.assertIn(f'pane split --pane {root} --direction down --cwd {self.repo} --no-focus', c)
        self.assertIn(f'tab create --workspace w9 --cwd {self.repo} --label review --no-focus', c)
        starts = [l for l in c if l.startswith('agent start')]
        self.assertEqual(len(starts), 3)          # the shell pane gets no agent
        self.assertTrue(any(l.endswith('-- resume s-api -m gpt-6-astra -c model_reasoning_effort="ultra" --approve-for-me') for l in starts), starts)
        self.assertTrue(any(l.endswith('-- --resume s-rev --model claude-fable-5-1 --effort max') for l in starts), starts)
        self.assertFalse(any(l.startswith('herdr-send') for l in c))

    def test_fresh_and_prompt(self):
        self.snapshot_all()
        r, calls = self.reopen('--fresh', '--prompt')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('resume', calls)
        self.assertIn(f'herdr-send lead-demo You are lead-demo in a herdr fleet. Read {self.job}/lead.md and do everything it says.', calls)
        self.assertEqual(calls.count('herdr-send'), 2)    # review-api has no brief recorded

    def test_refuses_when_label_is_open(self):
        self.snapshot_all()
        self.state(workspaces=[{'workspace_id': 'wK', 'label': 'demo-job'}])
        r, calls = self.reopen()
        self.assertEqual(r.returncode, 2)
        self.assertIn('refused', r.stderr)
        self.assertNotIn('workspace create', calls)

    def test_into_adds_only_missing_tabs(self):
        self.snapshot_all()
        self.state(workspaces=[{'workspace_id': 'wP', 'label': 'project'}])
        r, calls = self.reopen('--into', 'wP')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('kept tab build: already open in wP', r.stdout)
        self.assertNotIn('workspace create', calls)
        self.assertNotIn('herdr-events-owner', calls)
        self.assertIn(f'tab create --workspace wP --cwd {self.repo} --label review --no-focus', calls)
        self.assertEqual([l.split()[2] for l in calls.splitlines() if l.startswith('agent start')], ['review-api'])

    def test_refuses_when_a_cwd_is_gone(self):
        self.snapshot_all()
        self.wt.rmdir()                        # the worktree was removed after the close
        r, calls = self.reopen()
        self.assertEqual(r.returncode, 3)
        self.assertIn(f'cwd {self.wt} is gone', r.stderr)
        self.assertNotIn('workspace create', calls)


if __name__ == '__main__':
    unittest.main()
