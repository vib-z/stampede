#!/usr/bin/env python3
"""tui_e2e.py: the tui-live cases T01 to T10, one stampede job driven through the real `stampede` command against a
real Herdr TUI server in a scratch home, with stand-in agents. Records through record.py.

What must be there first (tests/evals/linux/inside.sh makes it in the Linux container; a scratch HOME on a Mac works the
same way): a running herdr server for this HOME; the checkout under test installed with install.sh, so `stampede`,
`herdr-send` and the relay scripts in ~/.local/bin are its own; the stand-ins on PATH as `claude` and `codex`
(tests/evals/linux/standin.py); a route file for --bot whose URL is a local stand-in route recording what it receives
(--route-log, tests/evals/linux/route_server.py); a scratch git repo under FLEET_TRUST_ROOT; the plugin linked (I05).

    python3 tests/evals/live/tui_e2e.py --label baseline-linux-tui --bot evalbot --route-log ~/route-received.jsonl --repo ~/code/eval-repo

Real: Herdr, its server, panes, agent detection, prompts and plugin events; every stampede command; the relay scripts.
Stand-ins: the agents (no model, nothing spent) and the bot's webhook (127.0.0.1). The job is started as a bot would
start it, from outside Herdr (workspace create, owner tag, stampede new --pane); the lead's own commands run inside a
real pane of the job's workspace (an `ops` tab), so Herdr's ids and process tree are real on both sides.
Order: T01 T02 T03 T04 T10 T05 T06 T07 T08 T09. T09's first check is measured while the job is open, its second after finish;
it also fails when a plain turn end from a workspace reopen.sh made reached the bot while the job was open."""
import argparse, json, os, platform, re, shlex, subprocess, sys, tempfile, time, traceback, uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tests/evals'))
import record  # noqa: E402

STAMPEDE = ROOT / 'scripts/stampede'
SCRIPTS = ROOT / 'skills/grokbot-herdr/scripts'
HOME = Path.home()
EVENTS = Path(os.environ.get('HERDR_EVENTS_DIR') or HOME / '.config/herdr-events')
STATE = Path(os.environ.get('XDG_STATE_HOME') or HOME / '.local/state')
RELAY_LOG = HOME / 'Library/Logs/herdr-events.log' if platform.system() == 'Darwin' else STATE / 'herdr-events.log'
HERDR_VARS = ('HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_SOCKET_PATH', 'HERDR_BIN_PATH',
              'HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE')
OTHER = 'b' * 40
ORDER = ['T01', 'T02', 'T03', 'T04', 'T10', 'T05', 'T06', 'T07', 'T08', 'T09']
SECTIONS = ('Goal', 'Why', 'Inputs', 'Constraints', 'Done when', 'Report back', 'If blocked')
OUTSIDE = '''#!/bin/bash
# runs "$@" with its ancestry (pid ppid comm, up to pid 1) printed first on stderr, for the record
p=$$; chain=""
while [ "$p" -gt 0 ]; do
  row=$(ps -o pid=,ppid=,comm= -p "$p" 2>/dev/null) || break
  chain="$chain$(echo $row);"
  p=$(echo $row | awk '{print $2}')
done
echo "ANCESTRY: $chain" >&2
exec "$@"
'''


class Blocked(Exception):
    pass


class Ev:
    def __init__(self, ident):
        self.ident, self.cmds, self.log, self.started = ident, [], [], time.time()

    def note(self, text):
        self.log.append(text)


def brief(job, agent, goal, lines):
    """A worker brief on the hand-off template, every section filled, plus the stand-in's lines."""
    body = {'Goal': goal, 'Why': 'The Linux live eval checks dispatch, messages, wake-ups and gates on a real Herdr.',
            'Inputs': '- The repo this pane runs in, and this job folder.', 'Constraints': '- The stand-in lines below are the whole lane.',
            'Done when': f'- [ ] {agent} did what the stand-in lines say.', 'Report back': f'reports/{agent}.md with Status: DONE in its first 10 lines.',
            'If blocked': f'Write questions/{agent}.md and end your turn.'}
    text = f'# {agent}\n\n' + ''.join(f'## {s}\n{body[s]}\n\n' for s in SECTIONS) + ''.join('stand-in: ' + row + '\n' for row in lines)
    path = job / 'briefs' / f'{agent}.md'
    path.write_text(text)
    return path


class Live:
    def __init__(self, a):
        self.bot, self.route_log, self.repo, self.name = a.bot, Path(a.route_log), Path(a.repo).resolve(), a.name
        self.scratch = Path(tempfile.mkdtemp(prefix='tui-e2e.'))
        (self.scratch / 'outside.sh').write_text(OUTSIDE)
        self.ev = Ev('none')
        self.ws = self.first_ws = self.job = self.lead = self.ops = None
        self.reopened = []  # workspace ids reopen.sh made
        self.finished_at = None  # when the first finish ran (T08)
        self.sha = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        self.op = 0
        self.workers = {}  # name -> kind

    # running things
    def sh(self, argv, env=None, timeout=120, quiet=False, cwd=None):
        argv = [str(x) for x in argv]
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd, stdin=subprocess.DEVNULL)
            code, out, err = done.returncode, done.stdout, done.stderr
        except subprocess.TimeoutExpired:
            code, out, err = 124, '', f'timed out after {timeout} s'
        except OSError as error:
            code, out, err = 127, '', str(error)
        if not quiet:
            self.ev.cmds.append(shlex.join(argv) + f'  -> exit {code}')
            self.ev.log.append(f'$ {shlex.join(argv)}\n[{code}] {out.strip()[-1200:]}\n{err.strip()[-600:]}'.rstrip())
        return code, out, err

    def herdr(self, *args, quiet=False, timeout=120):
        code, out, err = self.sh(['herdr', *args], quiet=quiet, timeout=timeout)
        try:
            data = json.loads(out or err or '{}')
        except ValueError:
            raise ValueError(f'herdr {" ".join(map(str, args[:2]))} answered no JSON: {(out or err).strip()[:200]}')
        if code or data.get('error'):
            raise ValueError(f'herdr {" ".join(map(str, args[:2]))}: {json.dumps(data.get("error")) if data.get("error") else err.strip()[:200]}')
        return data.get('result', {})

    def text(self, *args):
        return self.sh(['herdr', *args], quiet=True)[1]

    def outside(self, argv, timeout=120):
        """A command from outside Herdr, as the bot's own computer runs it: no Herdr or Core variables; its ancestry is logged."""
        env = {k: v for k, v in os.environ.items() if k not in HERDR_VARS}
        return self.sh(['bash', self.scratch / 'outside.sh', *argv], env=env, timeout=timeout)

    def ops_pane(self):
        """A shell pane of the job's workspace for the lead's commands, in a tab named ops (made once per workspace)."""
        if self.ops:
            try:
                self.herdr('pane', 'get', self.ops, quiet=True)
                return self.ops
            except ValueError:
                self.ops = None
        tab = self.herdr('tab', 'create', '--workspace', self.ws, '--cwd', str(self.repo), '--label', 'ops', '--no-focus')
        self.ops = tab['root_pane']['pane_id']
        time.sleep(1.5)
        return self.ops

    def in_pane(self, cmd, timeout=150):
        """Run one shell command in the ops pane, as the lead would in its own pane: (exit code, its output)."""
        pane = self.ops_pane()
        self.op += 1
        out, token = self.scratch / f'op{self.op}.out', f'OPDONE{self.op}'
        shell = f'( {cmd} ) >{shlex.quote(str(out))} 2>&1; echo "EXIT=$? OP""DONE{self.op}"'
        self.herdr('pane', 'run', pane, shell, quiet=True)
        try:
            self.herdr('pane', 'wait-output', pane, '--match', token, '--timeout', str(timeout * 1000), quiet=True, timeout=timeout + 10)
        except ValueError as error:
            self.ev.log.append(f'[pane {pane}] wait-output: {error}')
        screen = self.text('pane', 'read', pane, '--source', 'recent-unwrapped', '--lines', '60')
        found = re.search(rf'EXIT=(\d+) {token}', screen)
        code = int(found.group(1)) if found else -1
        text = out.read_text() if out.exists() else ''
        self.ev.cmds.append(f'[pane {pane}] {cmd}  -> exit {code}')
        self.ev.log.append(f'[pane {pane}] $ {cmd}\n[{code}] {text.strip()[-1200:]}')
        return code, text

    @staticmethod
    def wait(check, seconds, every=0.5):
        deadline = time.time() + seconds
        while time.time() < deadline:
            found = check()
            if found:
                return found
            time.sleep(every)
        return check()

    # the job's state
    def agent(self, name):
        try:
            return self.herdr('agent', 'get', name, quiet=True).get('agent')
        except ValueError:
            return None

    def agents(self):
        try:
            return {a.get('name'): a for a in self.herdr('agent', 'list', quiet=True).get('agents', [])}
        except ValueError:
            return {}

    def inbox(self, agent=None):
        path = self.job / 'inbox' / f'{agent or self.lead}.md'
        return path.read_text() if path.is_file() else ''

    def inbox_log(self):
        path = self.job / 'inbox.log'
        return path.read_text() if path.is_file() else ''

    def standin_log(self, agent):
        path = self.job / 'standin' / f'{agent}.log'
        return path.read_text() if path.is_file() else ''

    def route_events(self):
        rows = self.route_log.read_text().splitlines() if self.route_log.is_file() else []
        return [json.loads(r).get('body') for r in rows if r.strip() and isinstance(json.loads(r).get('body'), dict)]

    def relay_log(self):
        return RELAY_LOG.read_text() if RELAY_LOG.is_file() else ''

    def settled(self, names):
        shown = self.agents()
        return all(shown.get(n, {}).get('agent_status') in ('idle', 'done') for n in names)

    def require(self, what):
        if what == 'job' and not self.job:
            raise Blocked('T01 did not start the job')
        if what == 'workers' and not self.workers:
            raise Blocked('T02 did not start the workers')

    def round_trip(self, worker, seconds=60):
        """tell the worker from the lead's pane; its echo must land in the lead's inbox and wake the lead."""
        token = uuid.uuid4().hex[:8]
        code, out = self.in_pane(f'stampede tell {shlex.quote(str(self.job))} {worker} {shlex.quote("please reply: " + token)}')
        echoed = self.wait(lambda: f'ECHO {worker}: please reply: {token}' in self.inbox(), seconds)
        woke = echoed and self.wait(lambda: token in self.standin_log(self.lead), 30)
        return code, out, bool(echoed), bool(woke), token

    def marker_note(self, old):
        """What happened to the job marker and <job>/workspace at a reopen from old to self.ws, as measured."""
        named = (self.job / 'workspace').read_text().strip() if (self.job / 'workspace').is_file() else ''
        new_marker, old_marker = (EVENTS / 'jobs' / self.ws).is_file(), (EVENTS / 'jobs' / old).is_file()
        if named == self.ws and new_marker and not old_marker:
            return f'the job marker moved to jobs/{self.ws} and <job>/workspace names {self.ws}'
        return f'the job marker did not follow: <job>/workspace names {named or "nothing"}, jobs/{self.ws} {"present" if new_marker else "absent"}, jobs/{old} {"kept" if old_marker else "gone"}'

    @staticmethod
    def relay_time(line):
        try:
            return datetime.strptime(line[:24], '%Y-%m-%dT%H:%M:%S%z').timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def verdict(checks, notes=''):
        text = '; '.join(f'{k} {"ok" if v else "NO"}' for k, v in checks.items())
        return ('pass' if all(checks.values()) else 'fail'), text, notes

    # the cases
    def t01(self):
        """A job starts on a real Herdr: the bot's front door from outside Herdr."""
        ws = self.herdr('workspace', 'create', '--cwd', str(self.repo), '--label', self.name, '--no-focus')
        self.ws = self.first_ws = ws['workspace']['workspace_id']
        root = ws['root_pane']['pane_id']
        time.sleep(1)
        tagged = self.sh([SCRIPTS / 'herdr-events-owner', self.ws, self.bot])
        ask = self.scratch / 'ask.md'
        ask.write_text('Run the Linux live eval job: one worker writes hello-linux.txt, another reports in.\n')
        code, out, err = self.outside([STAMPEDE, 'new', '--file', ask, '--pane', root, '--name', self.name], timeout=180)
        last = out.strip().splitlines()[-1] if out.strip() else ''
        if code or not re.fullmatch(r'lead-\S+ /\S+', last):  # BLOCKED <lead>: ... is exit 0 too, and no job to go on with
            return 'fail', f'stampede new exit {code}: {(out + err).strip()[-400:]}', ''
        self.lead, job = last.split(' ', 1)
        self.job = Path(job)
        pointer = f'Read {self.job}/briefs/{self.lead}.md'
        shown = self.wait(lambda: (self.agent(self.lead) or {}).get('agent_status') in ('idle', 'done') and self.agent(self.lead), 30)
        woke = self.wait(lambda: 'prompt (wake' in self.standin_log(self.lead) and pointer in self.standin_log(self.lead), 30)
        tabs = self.herdr('tab', 'list', '--workspace', self.ws).get('tabs', [])
        panes = self.herdr('pane', 'list', '--workspace', self.ws).get('panes', [])
        checks = {'exit 0 and lead printed': code == 0 and bool(self.lead), 'owner tag set': tagged[0] == 0,
                  'Herdr shows the lead as claude, idle': bool(shown) and shown.get('agent') == 'claude',
                  'hooks settings written': (self.job / 'hooks' / f'{self.lead}-claude.json').is_file(),
                  'brief pointer in the inbox': pointer in self.inbox(), 'the stand-in woke through its FileChanged hook': bool(woke),
                  'owner file names the bot': (self.job / 'owner').is_file() and (self.job / 'owner').read_text().strip() == self.bot,
                  'job marker written': (EVENTS / 'jobs' / self.ws).is_file(),
                  'tab renamed lead': any(t.get('label') == 'lead' for t in tabs),
                  'pane labelled with the lead': any(p.get('label') == self.lead for p in panes)}
        self.ev.note(f'herdr agent get {self.lead}: {json.dumps(shown)}\nstand-in log:\n{self.standin_log(self.lead)}')
        return self.verdict(checks, notes=f'job {self.job.name}, workspace {self.ws}, lead {self.lead}')

    def t02(self):
        """Dispatch two workers: a Claude stand-in (inbox pointer) and a Codex stand-in (pointer typed by herdr-send)."""
        self.require('job')
        tab = self.herdr('tab', 'create', '--workspace', self.ws, '--cwd', str(self.repo), '--label', 'build', '--no-focus')
        p1 = tab['root_pane']['pane_id']
        time.sleep(1)
        p2 = self.herdr('pane', 'split', '--pane', p1, '--direction', 'right', '--cwd', str(self.repo), '--no-focus')['pane']['pane_id']
        time.sleep(1.5)
        b1 = brief(self.job, 'build-claude', 'Write hello-linux.txt in the repo and report.',
                   ['write hello-linux.txt hello from build-claude on Linux', 'report reports/build-claude.md build-claude wrote hello-linux.txt'])
        b2 = brief(self.job, 'build-codex', 'Report in to the lead.', ['tell lead hello from build-codex'])
        r1 = self.in_pane(f'stampede start {self.job} build-claude --kind claude --pane {p1} --brief {b1} --report reports/build-claude.md')
        r2 = self.in_pane(f'stampede start {self.job} build-codex --kind codex --pane {p2} --brief {b2}')
        snap = self.in_pane(f'herdr-reopen-snapshot {self.ws} {self.job}')
        hello = self.wait(lambda: (self.repo / 'hello-linux.txt').is_file(), 30)
        said = self.wait(lambda: 'hello from build-codex' in self.inbox(), 45)
        shown = self.agents()
        rows = [r.split('\t')[:2] for r in (self.job / 'agents.tsv').read_text().splitlines() if r and not r.startswith('#')]
        reopen = (self.job / 'REOPEN.md').read_text() if (self.job / 'REOPEN.md').is_file() else ''
        checks = {'start build-claude exit 0, DELIVERED': r1[0] == 0 and 'DELIVERED build-claude' in r1[1],
                  'start build-codex exit 0, SUBMITTED': r2[0] == 0 and 'SUBMITTED build-codex' in r2[1],
                  'Herdr lists both, named, right kinds': shown.get('build-claude', {}).get('agent') == 'claude' and shown.get('build-codex', {}).get('agent') == 'codex',
                  'in their panes': shown.get('build-claude', {}).get('pane_id') == p1 and shown.get('build-codex', {}).get('pane_id') == p2,
                  'agents.tsv records all three': {r[0] for r in rows} == {self.lead, 'build-claude', 'build-codex'},
                  'REOPEN.md names both workers': 'build-claude' in reopen and 'build-codex' in reopen and (self.job / 'reopen.sh').is_file(),
                  'the Claude worker did its brief (hello-linux.txt)': bool(hello),
                  'the Codex worker did its brief (told the lead)': bool(said)}
        if r1[0] == 0 and r2[0] == 0:
            self.workers = {'build-claude': 'claude', 'build-codex': 'codex'}
        self.ev.note(f'snapshot: {snap[1].strip()[-300:]}\nagents: {json.dumps({k: {x: v.get(x) for x in ("agent", "agent_status", "pane_id")} for k, v in shown.items()})}')
        return self.verdict(checks)

    def t03(self):
        """tell reaches each worker; each reply (a tell to the lead) lands in the lead's inbox and wakes it."""
        self.require('workers')
        c1, o1, echo1, woke1, t1 = self.round_trip('build-codex')
        c2, o2, echo2, woke2, t2 = self.round_trip('build-claude')
        checks = {'tell build-codex SUBMITTED (herdr-send)': c1 == 0 and 'SUBMITTED' in o1, 'its echo in the lead inbox': echo1,
                  'tell build-claude DELIVERED (inbox file)': c2 == 0 and 'DELIVERED' in o2, 'its echo in the lead inbox': echo2,
                  'the lead woke on both echoes': woke1 and woke2}
        self.ev.note('lead inbox:\n' + self.inbox()[-1500:])
        return self.verdict(checks)

    def t04(self):
        """The Claude worker's report gave exactly one REPORT line, through its Stop hook; the Codex turn gave TURN lines."""
        self.require('workers')
        self.wait(lambda: 'REPORT reports/build-claude.md' in self.inbox_log(), 30)
        time.sleep(3)
        reports = [r for r in self.inbox_log().splitlines() if r.startswith('REPORT reports/build-claude.md')]
        turns = [r for r in self.inbox_log().splitlines() if r.startswith('TURN build-codex')]
        stop_runs = len(re.findall(r'hook Stop -> exit', self.standin_log('build-claude')))
        report = (self.job / 'reports/build-claude.md').read_text() if (self.job / 'reports/build-claude.md').is_file() else ''
        checks = {'exactly one REPORT line': len(reports) == 1, 'report says Status: DONE': report.startswith('Status: DONE'),
                  'the Stop hook ran at least twice (two turns), one line': stop_runs >= 2,
                  'the Codex notify gave a TURN line': len(turns) >= 1}
        self.ev.note('inbox.log:\n' + self.inbox_log()[-1500:] + '\nbuild-claude stand-in log:\n' + self.standin_log('build-claude')[-1200:])
        return self.verdict(checks, notes=f'{len(reports)} REPORT, {len(turns)} TURN build-codex, {stop_runs} Stop hook runs')

    def t10(self):
        """Herdr 0.9.5 reads the Codex stand-in's screen: codex, idle at its prompt, working while it prints; herdr-send reaches it."""
        self.require('workers')
        before = self.agent('build-codex') or {}
        explain = self.sh(['herdr', 'agent', 'explain', 'build-codex'])[1]
        token = uuid.uuid4().hex[:8]
        code, out = self.in_pane(f'stampede tell {shlex.quote(str(self.job))} build-codex {shlex.quote("please reply: " + token)}')
        seen, deadline = set(), time.time() + 8
        while time.time() < deadline:
            seen.add((self.agent('build-codex') or {}).get('agent_status'))
            time.sleep(0.2)
        after = self.wait(lambda: (self.agent('build-codex') or {}).get('agent_status') in ('idle', 'done') and self.agent('build-codex'), 20) or {}
        echoed = self.wait(lambda: token in self.inbox(), 30)
        checks = {'reported as codex': before.get('agent') == 'codex', 'idle or done at its prompt before': before.get('agent_status') in ('idle', 'done'),
                  'herdr-send SUBMITTED': code == 0 and 'SUBMITTED' in out, 'working observed during the turn': 'working' in seen,
                  'idle or done again after': after.get('agent_status') in ('idle', 'done'), 'the prompt reached it (echo)': bool(echoed)}
        self.ev.note(f'before: {json.dumps(before)}\nexplain:\n{explain.strip()[:800]}\nstatuses seen: {sorted(s for s in seen if s)}\nafter: {json.dumps(after)}')
        return self.verdict(checks, notes='Proves Herdr detects the stand-in screen as Codex and reads its state, not a real Codex.')

    def t05(self):
        """A gate: queued for the bot; approve-gate refused in a pane, accepted outside; gate-ok at the right and wrong commit."""
        self.require('job')
        gate = self.in_pane(f'stampede ask {shlex.quote(str(self.job))} --gate --sha {self.sha} --pr 3 "Merge PR #3 into main"')
        found = re.search(r'GATE ([0-9a-f]{12}) ', gate[1])
        if not found:
            return 'fail', f'ask --gate exit {gate[0]}: {gate[1].strip()[-300:]}', ''
        ident = found.group(1)
        event = self.wait(lambda: [e for e in self.route_events() if e.get('state') == 'gate' and e.get('gate') == ident], 20)
        before = self.in_pane(f'stampede gate-ok {shlex.quote(str(self.job))} {ident} --sha {self.sha}')
        inside = self.in_pane(f'stampede approve-gate {shlex.quote(str(self.job))} {ident} --sha {self.sha} --by "owner in {self.bot} chat"')
        recorded_inside = (self.job / 'gates' / f'{ident}.approved').is_file()
        line = event[0].get('approve', '') if event else ''
        approve = shlex.split(line) if line else [str(STAMPEDE), 'approve-gate', str(self.job), ident, '--sha', self.sha, '--by', f'owner in {self.bot} chat']
        outside = self.outside(approve)  # the bot's own computer runs the event's approve line as given; fleet-job is the installed link
        ok_right = self.in_pane(f'stampede gate-ok {shlex.quote(str(self.job))} {ident} --sha {self.sha}')
        ok_wrong = self.in_pane(f'stampede gate-ok {shlex.quote(str(self.job))} {ident} --sha {OTHER}')
        told = self.wait(lambda: f'GATE {ident} APPROVED' in self.inbox(), 10)
        checks = {'ask --gate printed GATE': gate[0] == 0, 'the bot route received the gate event': bool(event),
                  'gate-ok refused before any yes': before[0] != 0 and 'APPROVED' not in before[1],
                  'approve-gate inside a pane refused, nothing recorded': inside[0] != 0 and not recorded_inside and 'outside Herdr' in inside[1],
                  'approve-gate outside Herdr APPROVED': outside[0] == 0 and 'APPROVED' in outside[1],
                  'gate-ok at that commit APPROVED': ok_right[0] == 0 and 'APPROVED' in ok_right[1],
                  'gate-ok at another commit refused': ok_wrong[0] != 0 and 'APPROVED' not in ok_wrong[1],
                  'the lead was told of the yes': bool(told)}
        self.ev.note(f'gate event: {json.dumps(event[0]) if event else "none"}')
        return self.verdict(checks, notes=f'The outside yes ran the gate event\'s approve line as given ({"with" if "--digest" in line else "without"} --digest), '
                            'from this runner, whose ancestry (ANCESTRY line in the log) holds no herdr process.')

    def t06(self):
        """Close the workspace; reopen.sh refuses while open, then recreates it with every agent, and the job carries on."""
        self.require('workers')
        names = [self.lead, *self.workers]
        old = self.ws
        refused = self.outside(['bash', self.job / 'reopen.sh'])
        self.herdr('workspace', 'close', self.ws)
        self.ops = None
        gone = self.wait(lambda: not any(n in self.agents() for n in names), 30)
        reopened = self.outside(['bash', self.job / 'reopen.sh'], timeout=400)
        found = [w for w in self.herdr('workspace', 'list').get('workspaces', []) if w.get('label') == self.name]
        if found:
            self.ws = found[0]['workspace_id']
            self.reopened.append(self.ws)
        back = self.wait(lambda: all(n in self.agents() for n in names) and self.settled(names), 120)
        shown = self.agents()
        panes = {n: shown.get(n, {}).get('pane_id') for n in names}
        snap = self.in_pane(f'herdr-reopen-snapshot {self.ws} {self.job}') if found else (1, '')
        code, out, echoed, woke, _ = self.round_trip('build-codex') if found else (1, '', False, False, '')
        checks = {'refused while open (exit 2)': refused[0] == 2 and 'refused' in (refused[1] + refused[2]),
                  'agents gone after the close': bool(gone), 'reopen.sh exit 0, REOPENED': reopened[0] == 0 and 'REOPENED' in reopened[1],
                  'all three agents back, settled': bool(back), 'each in a pane of the new workspace': all(p and p.startswith(self.ws + ':') for p in panes.values()),
                  'the job carries on (tell, echo, lead woke)': code == 0 and echoed and woke}
        self.ev.note(f'panes after reopen: {json.dumps(panes)}; snapshot: {snap[1].strip()[-200:]}')
        return self.verdict(checks, notes=f'reopened as workspace {self.ws}; {self.marker_note(old)}')

    def t07(self):
        """herdr server stop and start again in this home; then the job's record and reopen.sh bring the job back."""
        self.require('workers')
        names = [self.lead, *self.workers]
        old = self.ws
        stopped = self.sh(['herdr', 'server', 'stop'])
        down = self.wait(lambda: 'status: running' not in self.sh(['herdr', 'status'], quiet=True)[1], 30)
        log = (HOME / 'herdr-server-restart.log').open('a')
        subprocess.Popen(['herdr', 'server'], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        up = self.wait(lambda: 'status: running' in self.sh(['herdr', 'status'], quiet=True)[1], 60)
        time.sleep(3)
        restored = self.herdr('workspace', 'list').get('workspaces', [])
        agents_after = self.agents()
        observed = f'{len(restored)} workspaces ({", ".join(w.get("label", "?") for w in restored)}), {len(agents_after)} agents ({", ".join(agents_after)})'
        for w in restored:
            if w.get('label') == self.name:
                self.herdr('workspace', 'close', w['workspace_id'])
        self.ops = None
        reopened = self.outside(['bash', self.job / 'reopen.sh'], timeout=400)
        found = [w for w in self.herdr('workspace', 'list').get('workspaces', []) if w.get('label') == self.name]
        if found:
            self.ws = found[0]['workspace_id']
            self.reopened.append(self.ws)
        back = self.wait(lambda: all(n in self.agents() for n in names) and self.settled(names), 120)
        if found:
            self.in_pane(f'herdr-reopen-snapshot {self.ws} {self.job}')
        code, out, echoed, woke, _ = self.round_trip('build-codex') if found else (1, '', False, False, '')
        checks = {'server stopped': stopped[0] == 0 and bool(down), 'server running again': bool(up),
                  'reopen.sh exit 0, REOPENED': reopened[0] == 0 and 'REOPENED' in reopened[1], 'all three agents back, settled': bool(back),
                  'the job carries on (tell, echo, lead woke)': code == 0 and echoed and woke}
        return self.verdict(checks, notes=f'after the restart Herdr showed {observed}; the restored shell workspace was closed before reopen.sh, '
                            f'as its refusal asks; {self.marker_note(old) if found else "no reopened workspace"}')

    def t08(self):
        """finish relays one done event to the bot's route; a second finish adds nothing; the marker is gone."""
        self.require('job')
        dones = lambda: [e for e in self.route_events() if e.get('source') == 'stampede' and e.get('state') == 'done' and e.get('job') == str(self.job)]
        before = len(dones())
        first = self.in_pane(f'stampede finish {shlex.quote(str(self.job))} "linux eval done"')
        self.finished_at = time.time()
        delivered = self.wait(lambda: len(dones()) == before + 1, 20)
        second = self.in_pane(f'stampede finish {shlex.quote(str(self.job))} "linux eval done"')
        time.sleep(5)
        after = len(dones())
        queue = list((Path(os.environ.get('HERDR_EVENTS_HOME') or HOME / '.herdr-events') / 'queue').glob('*.json'))
        checks = {'first finish FINISHED': first[0] == 0 and 'FINISHED' in first[1], 'one done event reached the route': bool(delivered),
                  'second finish FINISHED, no new event': second[0] == 0 and 'FINISHED' in second[1] and after == before + 1,
                  'queue empty (flushed)': not queue, 'marker gone': not (EVENTS / 'jobs' / self.first_ws).exists(),
                  'finished stamp written': (self.job / 'finished').is_file()}
        return self.verdict(checks, notes=f'{after - before} done event(s) at the route for this job')

    def t09(self):
        """Two checks: the plugin's post for a turn in the open job stayed home (job-skip), and after finish one turn gives one event."""
        self.require('workers')
        plugins = self.sh(['herdr', 'plugin', 'list'])[1]
        if 'stampede' not in plugins:
            raise Blocked('the stampede plugin is not linked in this Herdr (I05)')
        skips = [r for r in self.relay_log().splitlines() if 'job-skip' in r and f'workspace={self.first_ws}' in r and 'herdr pane=' in r]
        closed_at = self.finished_at or time.time()  # a turn end queued before finish was queued while the job was open
        leaked = [r for r in self.relay_log().splitlines() if 'queued' in r and 'herdr pane=' in r
                  and any(f'pane={w}:' in r for w in self.reopened) and self.relay_time(r) < closed_at]
        pane = (self.agent('build-claude') or {}).get('pane_id')
        if not pane:
            raise Blocked('no live build-claude pane')
        # the relay de-dupes one pane's state for 120 s: wait that out after this pane's last post, so the check is its own
        posted = [r for r in self.relay_log().splitlines() if f'pane={pane} ' in r and ('queued' in r or 'dedupe-skip' in r)]
        if posted:
            time.sleep(max(0, 125 - (time.time() - self.relay_time(posted[-1]))))
        mine = lambda: [e for e in self.route_events() if e.get('source') == 'herdr' and e.get('pane') == pane]
        before = len(mine())
        token = uuid.uuid4().hex[:8]
        self.in_pane(f'stampede tell {shlex.quote(str(self.job))} build-claude {shlex.quote("after finish: " + token)}')
        got = self.wait(lambda: len(mine()) > before, 45)
        time.sleep(8)
        new = mine()[before:]
        logs = [r for r in self.herdr('plugin', 'log', 'list', '--plugin', 'stampede').get('logs', []) if r.get('event') == 'pane.agent_status_changed']
        checks = {'turn ends in the open job were job-skipped by the relay': len(skips) >= 1,
                  'no plain turn end from a reopened workspace reached the bot while the job was open': not leaked,
                  'after finish, the plugin event reached the route': bool(got),
                  'exactly one event for that turn': len(new) == 1,
                  'it says working before, done or idle now': bool(new) and new[0].get('previous_state') == 'working' and new[0].get('state') in ('done', 'idle'),
                  'Herdr logged the hook runs as succeeded': bool(logs) and all(r.get('status') == 'succeeded' for r in logs)}
        self.ev.note(f'job-skip lines: {skips[-3:]}\nturn ends from reopened workspaces that reached the route while the job was open: {leaked[-4:]}\n'
                     f'new route events: {json.dumps(new)[:1200]}\nplugin log entries: {len(logs)}, last: {json.dumps(logs[-1:])[:400]}')
        return self.verdict(checks, notes=f'{len(skips)} job-skip lines for workspace {self.first_ws}; {len(new)} event(s) after finish; '
                            f'{len(leaked)} plain turn end(s) from the reopened workspaces {self.reopened} reached the bot while the job was open')


def preflight(a):
    """What every case needs; one reason, or ''."""
    status = subprocess.run(['herdr', 'status'], capture_output=True, text=True).stdout
    if 'status: running' not in status:
        return 'no running herdr server for this HOME (herdr status)'
    for tool in ('stampede', 'herdr-send', 'herdr-reopen-snapshot', 'claude', 'codex'):
        if not any((Path(p) / tool).exists() for p in os.environ.get('PATH', '').split(':')):
            return f'{tool} is not on PATH (install.sh, and the stand-ins as claude and codex)'
    routes = Path(os.environ.get('HERDR_EVENTS_ROUTES_DIR') or EVENTS / 'routes')
    if not (routes / a.bot).is_file():
        return f'no route file for the bot {a.bot} in {routes}'
    if not (Path(a.repo) / '.git').exists():
        return f'{a.repo} is not a git repo'
    return ''


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--label', required=True)
    p.add_argument('--bot', default='evalbot')
    p.add_argument('--route-log', required=True, help="the stand-in route's record of what it received (route_server.py --log)")
    p.add_argument('--repo', default=str(HOME / 'code/eval-repo'))
    p.add_argument('--name', default='evtui', help='the job name (stampede new --name); the lead is lead-<name>')
    p.add_argument('--cases', default='')
    p.add_argument('--out')
    p.add_argument('--extra', default='{}', help='JSON for env.json (the image digest and the host, from run.sh)')
    a = p.parse_args(argv)
    wanted = [c for c in ORDER if not a.cases or c in a.cases.split(',')]
    run = record.Run(a.label, backend='tui-live', cases=wanted, out_root=a.out, extra=json.loads(a.extra))
    reason = preflight(a)
    live = Live(a) if not reason else None
    for ident in wanted:
        ev = Ev(ident)
        notes = ''
        if reason:
            status, actual = 'blocked', reason
        else:
            live.ev = ev
            try:
                status, actual, notes = getattr(live, ident.lower())()
            except Blocked as why:
                status, actual = 'blocked', str(why)
            except Exception:
                status, actual = 'error', 'harness error: ' + traceback.format_exc().strip().splitlines()[-1]
                ev.note(traceback.format_exc())
        run.case(ident, status, None, actual, ev.cmds, '\n'.join(ev.log), time.time() - ev.started, notes)
    return run.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
