"""One stampede job per client and backend, against the repo's fakes, for tests/test_clients.py.

A Job is one client driving one job on the Herdr TUI or on Herdr Core in a scratch folder of its own. play() runs the
steps behind the outcomes O2 to O9 once, in order, through the real `stampede` command, and keeps what each command
did in `steps`; test_clients.py asserts them. The client's commands run with its environment and process tree: inside
Herdr (the pane's ids), outside it (an app's command: no Herdr ids, no Herdr process above it), or over ssh (the same,
under a process named sshd). The lead's commands run with the lead's own environment. Nothing touches a real Herdr,
Herdr Core or agent CLI: the fake Herdr of test_herdr_reopen_snapshot through HERDR and PATH, tests/fake_hc.py through HC.
"""
import json, re, shlex, subprocess, sys, tempfile, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_core import CoreCase, FAKE_HC, SHA
from test_fleet_job import valid_brief
from test_herdr_reopen_snapshot import FAKE_HERDR, pane, rect

STAMPEDE = ROOT / 'scripts/stampede'
BOT_SCRIPTS = ROOT / 'skills/grokbot-herdr/scripts'
OTHER_SHA = 'b' * 40
QUESTION, ANSWER, GATE, SUMMARY = 'Keep hello in the repo root?', 'yes, the root', 'Merge PR #3 into main', 'hello written'
# a recorder in place of Moshi (FLEET_ASK_CMD): logs each card; answers a question with its first option, and a gate
# (no options) with yes only once the test makes the file `yes` beside it, the owner's tap; no yes in 60 s is a no
ASK = '#!/bin/bash\nprintf "%s\\n" "$*" >> "$(dirname "$0")/asked"\nwhile [ $# -gt 0 ]; do\n' \
      '  [ "$1" = --option ] && { echo "$2"; exit 0; }; shift\ndone\n' \
      'for _ in $(seq 600); do [ -e "$(dirname "$0")/yes" ] && { echo yes; exit 0; }; sleep 0.1; done\nexit 1\n'


def detached(argv, env, host):
    """Run argv under a process named host whose parent is pid 1, as a command from an app or an ssh session runs:
    no Herdr pane or Herdr Core process above it, wherever the suite itself runs. Returns (code, stdout, stderr)."""
    box = Path(tempfile.mkdtemp(prefix='xc-'))
    (box / host).symlink_to('/bin/bash')
    script = ('for _ in $(seq 250); do [ "$(ps -o ppid= -p $$ | tr -d " ")" = 1 ] && break; sleep 0.02; done; '
              '"$@" >"$0.out" 2>"$0.err" </dev/null; echo $? >"$0.tmp"; mv "$0.tmp" "$0.code"')
    subprocess.run(['/bin/bash', '-c', '"$0" -c "$1" "${@:2}" >/dev/null 2>&1 &', str(box / host), script, str(box / 'run'),
                    *argv], env=env, check=True)
    deadline = time.time() + 60
    while not (box / 'run.code').exists():
        if time.time() > deadline:
            return 124, '', f'{host}: {argv} did not end in 60 s'
        time.sleep(0.02)
    result = int((box / 'run.code').read_text()), (box / 'run.out').read_text(), (box / 'run.err').read_text()
    subprocess.run(['rm', '-rf', str(box)])
    return result


class Job:
    """One client driving one job on one backend. CoreCase's fake-core helpers read self.core, so they work here too."""
    WS, NAME, LEAD = 'w9', 'xc', 'lead-xc'  # the fake Herdr's workspace; new --name xc makes .herdr-xc and its lead

    state, terminal, calls, labels, program = CoreCase.state, CoreCase.terminal, CoreCase.calls, CoreCase.labels, CoreCase.program

    def __init__(self, client, row, backend, root, workers):
        """row: the client's CLIENTS row; workers: WORKERS, the kinds each backend takes. The lead starts every kind of
        every backend, so a kind this backend does not take is refused; it tells the first kind here that is not Claude."""
        self.client, self.row, self.backend, self.bot = client, row, backend, row.get('bot')
        self.kinds, self.takes = tuple(dict.fromkeys(k for kinds in workers.values() for k in kinds)), workers[backend]
        self.worker = 'build-' + next(k for k in self.takes if k != 'claude')  # prompted, where a Claude agent reads its inbox
        self.root = root / f'{client}-{backend}'
        self.repo, self.core, self.herdr = self.root / 'code/repo', self.root / 'core', self.root / 'herdr'
        self.home, self.events, self.queue = self.root / 'home', self.root / 'events', self.root / 'queue'
        self.bin = self.home / '.local/bin'
        self.job = self.repo / ('.herdr-' + self.NAME)
        self.steps, self.error = {}, ''
        for folder in (self.repo, self.core, self.herdr, self.bin, self.events, self.root / 'routes'):
            folder.mkdir(parents=True)
        for name, body in [('herdr', FAKE_HERDR), ('ask', ASK)] + [(k, '#!/bin/sh\nexit 0\n') for k in {'claude', *self.kinds}]:
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        if self.bot:
            (self.root / 'routes' / self.bot).write_text('URL=http://127.0.0.1:9/never\n')  # queued only: no flusher here
        self.base = {'HOME': str(self.home), 'PATH': f'{self.bin}:{Path(sys.executable).parent}:/usr/bin:/bin',
                     'TMPDIR': tempfile.gettempdir(), 'HERDR': str(self.bin / 'herdr'), 'FAKE_DIR': str(self.herdr),
                     'HC': str(FAKE_HC), 'FAKE_HC': str(self.core), 'HERDR_EVENTS_DIR': str(self.events),
                     'HERDR_EVENTS_HOME': str(self.queue), 'HERDR_EVENTS_ROUTES_DIR': str(self.root / 'routes'),
                     'FLEET_TRUST_ROOT': str(self.root / 'code'), 'FLEET_ASK_CMD': str(self.bin / 'ask'),
                     'HERDR_EVENTS_MACHINE': 'test', 'STAMPEDE_NO_UPDATE_CHECK': '1'}
        self.fake_herdr()

    def fake_herdr(self):
        """The fake Herdr's answers: one workspace w9 whose panes hold the lead and the workers, idle at an empty prompt."""
        repo, ws = str(self.repo), self.WS
        panes = [{**pane(f'{ws}:p{n}', f'{ws}:t{1 + (n > 1)}', name, repo, kind, 's-' + name), 'workspace_id': ws}
                 for n, (name, kind) in enumerate([(self.LEAD, 'claude')] + [('build-' + k, k) for k in self.kinds], 1)]
        (self.herdr / 'state.json').write_text(json.dumps({
            'pane get': {'pane': {**panes[0], 'foreground_cwd': repo}}, 'pane list': {'panes': panes},
            'agent wait': {'agent': {'agent_status': 'idle'}}, 'agent get': {'agent': {'agent_status': 'idle'}},
            'agent read': '› Ask Codex to do anything', 'agent prompt': {'type': 'agent_prompted'},
            'agent list': {'agents': [{'pane_id': p['pane_id'], 'name': p['label']} for p in panes]},
            'workspace list': {'workspaces': [{'workspace_id': ws, 'label': self.NAME}]},
            'tabs': {ws: [{'tab_id': f'{ws}:t1', 'label': 'lead'}, {'tab_id': f'{ws}:t2', 'label': 'build'}]},
            'layout': {f'{ws}:p1': [rect(f'{ws}:p1', 0, 0, 200, 40)],
                       f'{ws}:p2': [rect(f'{ws}:p{n}', 0, 13 * (n - 2), 200, 12) for n in range(2, 2 + len(self.kinds))]}}))

    # environments
    def client_env(self, where=None):
        """The client's environment: where it runs (default: its own), and the bot that owns its jobs."""
        env = dict(self.base)
        where = where or self.row['where']
        if where == 'inside':
            env.update(HERDR_ENV='1', HERDR_PANE_ID=f'{self.WS}:p9', HERDR_TAB_ID=f'{self.WS}:t9', HERDR_WORKSPACE_ID=self.WS)
        elif where == 'core':  # a program in a Herdr Core terminal, hc exec included
            env.update(HC_TERMINAL_ID='t9', HC_TERMINAL_SOCKET=str(self.root / 't9.sock'), HC_SCOPE='t9')
        if self.bot and (self.backend == 'core' or self.row['owner_from'] == 'env'):
            env['HERDR_EVENTS_OWNER'] = self.bot  # on Core there is no workspace to tag
        return env

    def lead_env(self):
        """The lead's environment: its Herdr pane on the TUI; on Core what launch_env gives its terminal."""
        if self.backend == 'tui':
            return {**self.base, 'HERDR_ENV': '1', 'HERDR_PANE_ID': f'{self.WS}:p1', 'HERDR_TAB_ID': f'{self.WS}:t1',
                    'HERDR_WORKSPACE_ID': self.WS}
        owner = (self.job / 'owner').read_text().strip() if (self.job / 'owner').is_file() else ''
        return {**self.base, 'STAMPEDE_JOB_KEY': self.key, 'HC_TERMINAL_ID': self.address(self.LEAD),
                **({'HERDR_EVENTS_OWNER': owner} if owner else {})}

    # running commands
    def run(self, step, argv, env, host=None):
        if host:
            result = detached([str(a) for a in argv], env, host)
        else:
            done = subprocess.run([str(a) for a in argv], env=env, capture_output=True, text=True, timeout=60)
            result = done.returncode, done.stdout, done.stderr
        self.steps[step] = result
        return result

    def front(self, step, *argv, where=None):
        """A command the client runs: stampede's, unless argv names another program."""
        where = where or self.row['where']
        argv = argv if str(argv[0]).startswith('/') or argv[0] in ('bash', 'herdr') else (STAMPEDE, *argv)
        return self.run(step, argv, self.client_env(where), {'outside': 'client', 'ssh': 'sshd'}.get(where))

    def lead(self, step, *argv):
        return self.run(step, (STAMPEDE, *argv), self.lead_env())

    # what the job left
    @property
    def key(self):
        return (self.job / 'workspace').read_text().strip()

    def address(self, agent):
        return json.loads((self.job / 'core.json').read_text())[agent]['address']

    def inbox(self, agent=None):
        path = self.job / 'inbox' / ((agent or self.LEAD) + '.md')
        return path.read_text() if path.is_file() else ''

    def queued(self):
        """Every event queued for a bot: {route, payload}, oldest first."""
        return [json.loads(p.read_text()) for p in sorted((self.queue / 'queue').glob('*.json'))] if (self.queue / 'queue').is_dir() else []

    def relay_log(self):
        path = self.home / 'Library/Logs/herdr-events.log'
        return path.read_text() if path.is_file() else ''

    def herdr_calls(self):
        path = self.herdr / 'calls'
        return path.read_text().splitlines() if path.is_file() else []

    def asked(self):
        path = self.bin / 'asked'
        return path.read_text() if path.is_file() else ''

    def until(self, check, seconds=20):
        deadline = time.time() + seconds
        while not check() and time.time() < deadline:
            time.sleep(0.05)
        return check()

    # the job, step by step
    def play(self):
        try:
            for step in (self.start, self.workers, self.question, self.gate, self.tell, self.reopen, self.no_poll, self.finish):
                step()
        except Exception:
            self.error = traceback.format_exc()
        return self

    def start(self):
        """O2: the front door writes the ask and runs stampede new as its guide says."""
        ask = self.root / 'ask.md'
        ask.write_text(f'Write hello-{self.client}-{self.backend}.txt with one worker.\n')
        if self.backend == 'core':
            self.front('new', 'new', '--core', '--file', ask, '--cwd', self.repo, '--name', self.NAME)
            return
        if self.row['where'] == 'inside':  # a chat in a Herdr pane: the lead gets a lead tab in this workspace
            self.front('new', 'new', '--file', ask, '--name', self.NAME)
            return
        code, out, _ = self.front('workspace', 'herdr', 'workspace', 'create', '--cwd', self.repo, '--label', self.NAME, '--no-focus')
        root_pane = json.loads(out)['result']['root_pane']['pane_id'] if code == 0 else '-'
        if self.bot and self.row['owner_from'] == 'tag':  # grokbot-herdr Step 3: tag the workspace before agents start
            self.front('tag', BOT_SCRIPTS / 'herdr-events-owner', self.WS, self.bot)
        self.front('new', 'new', '--file', ask, '--pane', root_pane, '--name', self.NAME)

    def workers(self):
        """O3: the lead starts one worker of every kind, each in its pane on the TUI; a kind this backend does not take is
        refused."""
        for n, kind in enumerate(self.kinds, 2):
            brief = valid_brief(self.job, 'build-' + kind)
            where = ('--pane', f'{self.WS}:p{n}') if self.backend == 'tui' else ()
            self.lead('start ' + kind, 'start', self.job, 'build-' + kind, '--kind', kind, '--brief', brief, *where)

    def question(self):
        """O4: the lead asks; the client's channel gets it; the client's answer reaches the lead."""
        self.lead('ask', 'ask', self.job, QUESTION, '--option', ANSWER, '--option', 'no')
        if self.bot:
            event = next(q['payload'] for q in self.queued() if q['payload'].get('state') == 'question')
            answer = shlex.split(event['answer'])  # fleet-job tell <job> lead "ANSWER <id> <question>: <the owner's words>"
            self.front('answer', STAMPEDE, *answer[1:-1], answer[-1].replace("<the owner's words>", ANSWER))
        else:
            self.until(lambda: ANSWER in self.inbox())

    def gate(self):
        """O5: the lead asks a gate. Before the owner's yes, and after each approve-gate that must be refused, gate-ok
        refuses and no yes is recorded (`closed`); then the real yes, the bot's approve-gate over ssh or the tap on the
        phone card, opens it for that commit only."""
        out = self.lead('gate', 'ask', self.job, '--gate', '--sha', SHA, '--pr', '3', GATE)[1]
        self.ident = ident = (re.findall(r'^GATE ([0-9a-f]{12}) ', out, re.M) or ['000000000000'])[0]
        approve = ('approve-gate', self.job, ident, '--by', f'owner in {self.bot or "local"} chat', '--sha')
        record = self.job / 'gates' / (ident + '.approved')
        self.closed = {}  # what ran -> (gate-ok's exit code right after it, whether a yes was recorded)

        def closed(after):
            self.closed[after] = self.lead('gate-ok after ' + after, 'gate-ok', self.job, ident, '--sha', SHA)[0], record.exists()
        closed('the ask')
        refused = [('approve other commit', OTHER_SHA, None), ('approve inside Herdr', SHA, 'inside'),
                   ('approve in a Core terminal', SHA, 'core')] + ([] if self.bot else [('approve', SHA, None)])
        for name, sha, where in refused:  # a local job's own approve-gate is refused too: its yes is the phone's
            self.front(name, *approve, sha, where=where)
            closed(name)
        if self.bot:
            self.front('approve', *approve, SHA)
        else:
            (self.bin / 'yes').touch()
            self.until(record.is_file)
        self.lead('gate-ok other commit', 'gate-ok', self.job, ident, '--sha', OTHER_SHA)
        self.lead('gate-ok', 'gate-ok', self.job, ident, '--sha', SHA)

    def tell(self):
        """O6: the client tells the lead and a worker that is not Claude; on Core again while that worker is working."""
        self.front('tell lead', 'tell', self.job, 'lead', 'Use the repo root')
        self.front('tell worker', 'tell', self.job, self.worker, 'Check the path')
        if self.backend == 'core':
            self.terminal(self.address(self.worker), status={'state': 'working'})
            self.front('tell working worker', 'tell', self.job, self.worker, 'And the error path')
            self.terminal(self.address(self.worker), status={'state': 'idle'})

    def reopen(self):
        """O8: reopen.sh on the live job; on the TUI the lead first writes the reopen record."""
        if self.backend == 'tui':
            self.run('snapshot', (BOT_SCRIPTS / 'herdr-reopen-snapshot', self.WS, self.job), self.lead_env())
        self.before_reopen = len(self.calls('run')), len(self.herdr_calls())
        self.front('reopen', 'bash', self.job / 'reopen.sh')

    def no_poll(self):
        """O9: while the job is open, the lead's plain turn end stays on the machine and its block reaches the job's bot,
        as the Herdr plugin (TUI) or the job's follower (Core) posts them."""
        where = f'hc:{self.key}/{self.address(self.LEAD)}' if self.backend == 'core' else f'{self.WS}:p1'
        source, post = 'hc' if self.backend == 'core' else 'herdr', BOT_SCRIPTS / 'herdr-event-post'
        self.queue_before = len(self.queued())
        self.run('turn end', (post, f'source={source}', 'state=done', f'pane={where}'), self.base)
        self.queue_after_turn_end = len(self.queued())
        self.run('blocked', (post, f'source={source}', 'state=blocked', f'pane={where}'), self.base)

    def finish(self):
        """O7: the lead finishes the job twice; one done event, and the marker is gone."""
        self.marker = self.events / 'jobs' / self.key
        self.marked = self.marker.read_text().strip() if self.marker.is_file() else None  # the job path, while open
        self.lead('finish', 'finish', self.job, SUMMARY)
        self.lead('finish again', 'finish', self.job, SUMMARY)
