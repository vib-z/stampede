#!/usr/bin/env python3
"""The sandbox fleet test of a Core-native job (stampede new --core): ten named checks on a real Herdr Core in a scratch
session of its own, never the machine's own core, through this checkout's scripts/stampede.

    python3 tests/evals/live/native_fleet.py [--only tree,fanout] [--keep]

What is real: hc and its core, the stampede command, the job folder, Core's tree, notes and waits. What stands in: the
agents (core_agent.py as `claude`: OSC 7501 status, no model) and the helpers' work (sleep, a blocked status, a result
file sent with hc send). The bot's route is a URL on 127.0.0.1 that is never flushed, so nothing leaves the machine.
It prints a table of checks and seconds and exits 0 only when every check passed. The scratch folder under /tmp is
removed unless --keep. The machine's own core is only listed, before and after, once its socket answers."""
import argparse, json, os, platform, re, shlex, shutil, subprocess, sys, tempfile, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STAMPEDE = ROOT / 'scripts/stampede'
FLEET_JOB = ROOT / 'skills/herdr-fleet/scripts/fleet-job'
EVENT_CORE = ROOT / 'skills/grokbot-herdr/scripts/herdr-event-core'
AGENT = HERE / 'core_agent.py'
DARWIN = platform.system() == 'Darwin'
BOT = 'evalbot'
BRIEF = '# {name}\n\n## Goal\nStand in.\n\n## Why\nThe sandbox fleet test.\n\n## Inputs\nNone.\n\n## Constraints\nNone.\n\n' \
        '## Done when\nThe runner says so.\n\n## Report back\nNothing.\n\n## If blocked\nEnd your turn.\n'
BLOCKER = '#!/bin/sh\n# a stand-in child that reports blocked and stays so\nprintf \'\\033]7501;state=blocked:app=stand-in\\033\\\\\'\nexec sleep 600\n'
RESULT = '#!/bin/sh\n# a stand-in helper: writes its result file, sends its parent the path: result <name> <file> <parent address>\n' \
         '# it reports status as an agent does: hc 0.1.21 tags a send <hc from=...> only from a terminal that reports one\n' \
         'printf \'\\033]7501;state=working:app=stand-in\\033\\\\\'\nexec result-plain "$@"\n'
PLAIN = '#!/bin/sh\n# a plain program helper: the same, with no status, so its line arrives as bare text\nmkdir -p "$(dirname "$2")" && echo "Status: DONE" > "$2"\nhc send "$3" "$1: done $2"\nsleep 1\n'


class Fail(Exception):
    pass


class Fleet:
    def __init__(self, keep):
        self.keep, self.t = keep, Path(tempfile.mkdtemp(prefix='nf.', dir='/tmp'))  # a socket path holds at most 103 bytes
        self.session, self.log = 'nf' + uuid.uuid4().hex[:6], []
        base = {k: v for k, v in os.environ.items() if not k.startswith(('HC_', 'HERDR_', 'STAMPEDE_', 'FLEET_', 'CLAUDE', 'CODEX'))}
        t = self.t
        self.env = {**base, 'HOME': str(t / 'h'), 'HC_SESSION': self.session, 'XDG_STATE_HOME': str(t / 'state'),
                    'XDG_RUNTIME_DIR': str(t / 'run'), 'XDG_CONFIG_HOME': str(t / 'config'),
                    'PATH': f'{t / "bin"}:{base.get("PATH", "/usr/bin:/bin")}', 'FLEET_TRUST_ROOT': str(t / 'code'),
                    'FLEET_JOBS_ROOT': str(t / 'jobs'), 'HERDR_EVENTS_DIR': str(t / 'events'), 'HERDR_EVENTS_HOME': str(t / 'queue'),
                    'HERDR_EVENTS_ROUTES_DIR': str(t / 'routes'), 'HERDR_EVENTS_MACHINE': 'evalhost', 'FLEET_ASK_CMD': 'false',
                    'FLEET_WATCH_NOTIFY': '0', 'STAMPEDE_NO_UPDATE_CHECK': '1'}
        self.repo, self.jobs = None, {}

    # --- commands --------------------------------------------------------------------------------------------------
    def sh(self, argv, env=None, timeout=120):
        argv = [str(a) for a in argv]
        try:
            done = subprocess.run(argv, env=env or self.env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            done = subprocess.CompletedProcess(argv, 124, '', f'timed out after {timeout} s')
        self.log.append(f'$ {shlex.join(argv)[:240]} -> {done.returncode} {(done.stdout + done.stderr).strip()[-400:]}')
        return done

    def hc(self, *args, timeout=90):
        done = self.sh(['hc', args[0], '--json', *args[1:]], timeout=timeout)
        if done.returncode:
            raise Fail(f'hc {" ".join(args)}: exit {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}')
        return json.loads(done.stdout or '{}')

    def stampede(self, *args, env=None, timeout=180):
        return self.sh([STAMPEDE, *args], env=env, timeout=timeout)

    def terminals(self):
        """Every terminal of the scratch core with its labels: one terminal.list through hc connect."""
        request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'terminal.list', 'params': {'all': True}})
        done = subprocess.run(['hc', 'connect'], input=request + '\n', capture_output=True, text=True, env=self.env, timeout=30)
        return json.loads(done.stdout.splitlines()[0])['result']['terminals']

    def of(self, key, live=True):
        return [t for t in self.terminals() if (t.get('labels') or {}).get('stampede.job') == key and (not live or t['state'] == 'live')]

    def by_name(self, key):
        return {t['labels']['stampede.agent']: t for t in self.of(key)}

    def until(self, what, check, seconds=30):
        deadline = time.time() + seconds
        while time.time() < deadline:
            found = check()
            if found:
                return found
            time.sleep(0.3)
        raise Fail(f'{what} (not within {seconds} s)')

    def standin(self, job, name):
        path = job / 'standin' / (name + '.log')
        return [json.loads(r) for r in path.read_text().splitlines() if r.strip()] if path.is_file() else []

    # --- the scratch world -----------------------------------------------------------------------------------------
    def prepare(self):
        t = self.t
        for folder in ('state', 'run', 'config', 'bin', 'code/repo', 'jobs', 'events', 'queue', 'routes', 'h/.local/bin'):
            (t / folder).mkdir(parents=True, exist_ok=True)
        write = lambda path, text: (path.write_text(text), path.chmod(0o755))
        for kind in ('claude', 'codex'):
            write(t / 'bin' / kind, f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -I {shlex.quote(str(AGENT))} --kind {kind} "$@"\n')
        (t / 'bin/fleet-job').symlink_to(FLEET_JOB)  # what a stand-in agent runs to start its own children
        write(t / 'bin/blocker', BLOCKER)
        write(t / 'bin/result', RESULT)
        write(t / 'bin/result-plain', PLAIN)
        write(t / 'h/.local/bin/herdr-event-flush', '#!/bin/sh\n# no flusher: events stay in the scratch queue\nexit 0\n')
        (t / 'routes' / BOT).write_text('URL=http://127.0.0.1:9/never\nKEY=none\n')
        (t / 'routes' / BOT).chmod(0o600)
        self.repo = (t / 'code/repo').resolve()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        env = {**self.env, **({'SSH_CONNECTION': '127.0.0.1 1 127.0.0.1 22'} if DARWIN else {})}  # an ssh start: no launchd job
        started = self.sh(['hc', 'server', 'start', '--json'], env=env)
        if started.returncode:
            raise SystemExit(f'BLOCKED: hc server start for the scratch session failed: {started.stderr.strip()[-300:]}')

    def cleanup(self):
        try:
            for terminal in self.terminals():
                if terminal['state'] == 'live':
                    self.sh(['hc', 'kill', '--json', terminal['address']])
            self.sh(['hc', 'server', 'stop', '--json'], timeout=60)
        finally:
            if not self.keep:
                shutil.rmtree(self.t, ignore_errors=True)

    def new(self, name, *flags, owner=None):
        ask = self.t / f'ask-{name}.md'
        ask.write_text(f'Sandbox fleet test: {name}.\n')
        env = {**self.env, **({'HERDR_EVENTS_OWNER': owner} if owner else {})}
        made = self.stampede('new', '--core', '--file', ask, '--cwd', self.repo, '--name', name, *flags, env=env)
        if made.returncode:
            raise Fail(f'stampede new --core --name {name}: exit {made.returncode}: {(made.stdout + made.stderr).strip()[-300:]}')
        lead, job = made.stdout.strip().splitlines()[-1].split(' ', 1)
        job = Path(job)
        self.jobs[name] = (lead, job, (job / 'workspace').read_text().strip())
        return self.jobs[name]

    def start(self, job, name, *args, env=None, want='STARTED'):
        done = self.stampede('start', job, name, *args, env=env)
        if done.returncode or not done.stdout.strip().splitlines()[-1].startswith(f'{want} {name}'):
            raise Fail(f'stampede start {name}: exit {done.returncode}: {(done.stdout + done.stderr).strip()[-300:]}')
        return done.stdout

    def helper(self, job, name, *args):
        brief = self.t / f'brief-{name}.md'
        brief.write_text(BRIEF.format(name=name))
        return self.start(job, name, '--kind', 'claude', '--brief', brief, *args)

    def done_turn(self, key, name):
        return self.until(f'{name} ended its first turn', lambda: (self.by_name(key).get(name) or {}).get('turn', 0) >= 1, 30)

    def running(self, key):
        return sum(1 for t in self.of(key) if t['labels'].get('stampede.role') == 'helper' and
                   ((t.get('status') or {}).get('state') not in ('idle', 'done') or t['labels'].get('stampede.kind') == 'program'))


def own_core():
    """The machine's own core: (alive, [address name state]) by its socket first, never an hc call that could start it."""
    env = {k: v for k, v in os.environ.items() if k not in ('HC_SESSION', 'HC_SOCKET')}
    alive = subprocess.run([sys.executable, '-I', str(EVENT_CORE), '--alive'], env=env, capture_output=True).returncode == 0
    if not alive:
        return False, []
    listed = json.loads(subprocess.run(['hc', 'ls', '--json'], env=env, capture_output=True, text=True, timeout=30).stdout or '{}')
    return True, sorted(f'{t["address"]} {t.get("state")}' for t in listed.get('terminals', []))


# --- the checks ----------------------------------------------------------------------------------------------------
def tree(f, s):
    lead, job, key = f.new('tree')
    for name in ('help-a', 'help-b'):
        f.helper(job, name)
        f.done_turn(key, name)
    for parent, subs in (('help-a', ('sub-a1', 'sub-a2')), ('help-b', ('sub-b1', 'sub-b2'))):
        for sub in subs:  # the helper itself starts its children, from inside its own terminal
            told = f.stampede('tell', job, parent, f'fleet-job start {job} {sub} -- sleep 900')
            if told.returncode:
                raise Fail(f'tell {parent}: {told.stdout} {told.stderr}')
            f.until(f'{parent} started {sub}', lambda: sub in f.by_name(key), 30)
    named = f.by_name(key)
    want = {'help-a': lead, 'help-b': lead, 'sub-a1': 'help-a', 'sub-a2': 'help-a', 'sub-b1': 'help-b', 'sub-b2': 'help-b'}
    address = {n: t['address'] for n, t in named.items()}
    wrong = {n: named[n].get('parent') for n, p in want.items() if named.get(n, {}).get('parent') != address.get(p)}
    if wrong or named[lead].get('parent') is not None:
        raise Fail(f'Core parents differ from the starters: {wrong}, lead parent {named[lead].get("parent")}')
    shown = json.loads(f.stampede('tree', job, '--json').stdout)
    if sorted(n['name'] for n in shown['nodes']) != sorted([lead, *want]) or len(shown['nodes']) != 7:
        raise Fail(f'stampede tree --json shows {[n["name"] for n in shown["nodes"]]}')
    if named[lead]['labels'].get('stampede.space') != 'tree':
        raise Fail(f'the lead carries {named[lead]["labels"]}')
    return f'7 nodes, each Core parent its starter (subs started from inside help-a and help-b); tree --json agrees'


def fanout(f, s):
    lead, job, key = f.new('fan')
    names = [f'fan-{i:02}' for i in range(1, 21)]
    began, starts, first12 = time.time(), [], None
    for i, name in enumerate(names):
        out = f.start(job, name, '--', 'sleep', str(8 + i % 4), want='STARTED' if i < 12 else 'QUEUED')
        if i == 11:
            first12 = time.time() - began
    s['layout'] = {n: t['labels'] for n, t in f.by_name(key).items()}
    queue = sorted((job / 'queue').glob('*.json'))
    if len(queue) != 8:
        raise Fail(f'{len(queue)} queued, not 8')
    # as a lead does: wait for Core's news of a child, then stampede next. Two ends can come as one piece of news, or one
    # next can fill the place a later end freed, so a next may rightly start nothing; it must never leave a place free
    # while something waits: WAITING says <n> running, cap <c>, and n is c.
    address, peak, ended, order, nexts, deadline = f.by_name(key)[lead]['address'], 0, set(), [], 0, time.time() + 120
    helpers = lambda: [t for t in f.of(key, live=False) if t['labels'].get('stampede.role') == 'helper']
    while len(ended) < 20 and time.time() < deadline:
        f.hc('wait', '--children', 'any', address, '--timeout', '30', timeout=40)
        rows = helpers()
        peak = max(peak, sum(t['state'] == 'live' for t in rows))
        ended = {t['labels']['stampede.agent'] for t in rows if t['state'] == 'finished'}
        out, nexts = f.stampede('next', job).stdout, nexts + 1
        order += re.findall(r'^STARTED (\S+)', out, re.M)
        waiting = re.search(r'^WAITING \d+ queued \((\d+) running, cap (\d+)\)', out, re.M)
        if waiting and waiting.group(1) != waiting.group(2):
            raise Fail(f'next left a place free while a start waited: {out.strip()}; Core then: '
                       f'{sorted((t["labels"]["stampede.agent"], t["state"]) for t in rows)}')
        peak = max(peak, sum(t['state'] == 'live' for t in helpers()))
    total = time.time() - began
    if peak > 12 or len(ended) != 20 or order != names[12:]:
        raise Fail(f'peak {peak} running, {len(ended)} of 20 ran, next started {order}')
    s['fanout'] = (first12, total)
    return (f'peak {peak} running, 8 queued; {nexts} next calls, one per piece of Core news, started fan-13..fan-20 oldest first '
            f'and never left a place free; first 12 in {first12:.1f} s, all 20 done in {total:.1f} s')


def cap(f, s):
    lead, job, key = f.new('cap', '--max-helpers', '3')
    for i in range(1, 6):
        f.start(job, f'cap-{i}', '--', 'sleep', '900', want='STARTED' if i <= 3 else 'QUEUED')
    counts = [f.running(key) for _ in range(5) if not time.sleep(0.4)]
    if set(counts) != {3}:
        raise Fail(f'running sampled {counts}, not 3')
    return f'3 STARTED, 2 QUEUED (3 running, cap 3); sampled {counts}'


def grid(tab, names):
    """The owner's order for the names of one tab, in start order: 1 the first; 2 splits 1 right; 3 splits 2 down; 4
    splits 1 down. {name: (tab, pane, split, beside)}."""
    splits = {2: ('right', 0), 3: ('down', 1), 4: ('down', 0)}
    return {n: (tab, i + 1, *((splits[i + 1][0], names[splits[i + 1][1]]) if i else (None, None))) for i, n in enumerate(names)}


def placed(labels):
    return (labels.get('herdr.tab'), int(labels.get('stampede.pane') or 0), labels.get('stampede.split'), labels.get('stampede.beside'))


def layout(f, s):
    if 'layout' not in s:
        raise Fail('needs fanout')
    lead, job, key = f.jobs['fan']
    fan = [f'fan-{i:02}' for i in range(1, 13)]
    want = {**grid('main', [lead, *fan[:3]]), **grid('main-2', fan[3:7]), **grid('main-3', fan[7:11]), **grid('main-4', fan[11:])}
    got = {n: placed(l) for n, l in s['layout'].items()}
    problems = [f'fan: {n} at {got.get(n)}, not {w}' for n, w in want.items() if got.get(n) != w]
    problems += [f'spaces {spaces}'] if (spaces := {l.get('herdr.space') for l in s['layout'].values()}) != {'fan'} else []
    lead, job, key = f.jobs['tree']  # its subs were started by help-a and help-b: a nested level takes its place by the same rule
    want = {**grid('main', [lead, 'help-a', 'help-b', 'sub-a1']), **grid('main-2', ['sub-a2', 'sub-b1', 'sub-b2'])}
    for i in range(1, 6):
        f.start(job, f'ci-{i}', '--tab', 'ci', '--', 'sleep', '900')
    want.update({**grid('ci', [f'ci-{i}' for i in range(1, 5)]), **grid('ci-2', ['ci-5'])})
    got = {n: placed(t['labels']) for n, t in f.by_name(key).items()}
    problems += [f'tree: {n} at {got.get(n)}, not {w}' for n, w in want.items() if got.get(n) != w]
    shown = {n['name']: (n.get('tab'), n.get('pane'), n.get('split'), n.get('beside')) for n in json.loads(f.stampede('tree', job, '--json').stdout)['nodes']}
    problems += [f'tree --json: {n} at {shown.get(n)}, Core labels {g}' for n, g in got.items() if shown.get(n) != g]
    close = lambda name: (lambda done: None if not done.returncode and done.stdout.startswith(f'CLOSED {name}') else problems.append(
        f'stampede close {name}: exit {done.returncode}: {(done.stdout + done.stderr).strip()[-300:]}'))(f.stampede('close', job, name))
    close('ci-2')  # the product's way out, so the record says closed and no reopen starts them again
    f.start(job, 'ci-6', '--tab', 'ci', '--', 'sleep', '900')
    freed = placed(f.by_name(key)['ci-6']['labels'])
    problems += [f'ci-6 took {freed}, not the freed ci pane 2'] if freed != ('ci', 2, 'right', 'ci-1') else []
    for name in ('ci-1', 'ci-3', 'ci-4', 'ci-5', 'ci-6'):
        close(name)
    s['closed'] = [f'ci-{i}' for i in range(1, 7)]
    if problems:
        raise Fail('; '.join(problems))
    return ('fan: lead, fan-01..03 as panes 1 to 4 of main (none; right of lead; down of fan-01; down of lead), the same 2x2 on '
            'main-2 and main-3, fan-12 pane 1 of main-4; tree: the subs of help-a and help-b by the same rule; --tab ci: 4 as '
            'panes 1 to 4, the 5th pane 1 of ci-2; ci-6 took the freed pane 2; tree --json shows pane, split, beside')


def blocked(f, s):
    lead, job, key = f.new('wait')
    f.helper(job, 'parent-p')
    f.done_turn(key, 'parent-p')
    p = f.by_name(key)['parent-p']['address']
    s['p'] = p
    f.start(job, 'stuck', '--parent', 'parent-p', '--', 'blocker')
    waited = f.hc('wait', '--children', 'any', p, '--timeout', '20', timeout=30)
    child = (waited.get('children') or [{}])[0]
    if child.get('status') != 'blocked' or child.get('terminal') != f.by_name(key)['stuck']['address']:
        raise Fail(f'hc wait --children any {p} gave {waited}')
    stuck = f.by_name(key)['stuck']['address']
    screen = f.until('the note on the parent\'s screen', lambda: re.search(rf'<hc>{stuck} \S+ is blocked', f.sh(['hc', 'read', p, '--lines', '40']).stdout), 15)
    f.hc('kill', stuck)
    return f'hc wait --children any {p} returned {stuck} blocked; the parent\'s screen shows "{screen.group(0)}"'


def waiting(f, s):
    lead, job, key = f.jobs.get('wait') or (None, None, None)
    if not job:
        raise Fail('needs blocked')
    f.helper(job, 'parent-w')
    f.done_turn(key, 'parent-w')
    w = f.by_name(key)['parent-w']['address']
    f.start(job, 'quick', '--parent', 'parent-w', '--', 'sleep', '2')
    f.start(job, 'slow', '--parent', 'parent-w', '--', 'sleep', '7')
    began = time.time()
    first = f.hc('wait', '--children', 'any', w, '--timeout', '30', timeout=40)
    any_s = time.time() - began
    rest = f.hc('wait', '--children', 'all', w, '--timeout', '30', timeout=40)
    all_s = time.time() - began
    live = [n for n in ('quick', 'slow') if n in f.by_name(key)]
    if not 1 <= any_s < 5 or not 6 <= all_s < 12 or live or not all(c.get('ended') for c in rest.get('children', [])):
        raise Fail(f'any after {any_s:.1f} s ({first}), all after {all_s:.1f} s ({rest}), still live {live}')
    return f'any returned on the first child ({any_s:.1f} s), all once none worked ({all_s:.1f} s)'


def results(f, s):
    lead, job, key = f.jobs.get('wait') or (None, None, None)
    if not job:
        raise Fail('needs blocked')
    p, path, bare = s['p'], job / 'reports/res-1.md', job / 'reports/res-2.md'
    screen = lambda: f.sh(['hc', 'read', p, '--lines', '80']).stdout.replace('\n', '')
    f.start(job, 'res-1', '--parent', 'parent-p', '--', 'result', 'res-1', path, p)
    shown = f.until('the tagged message on the parent\'s screen',
                    lambda: re.search(rf'<hc from="\S+ res-1[^"]*">res-1: done {re.escape(str(path))}</hc>', screen()), 20)
    f.start(job, 'res-2', '--parent', 'parent-p', '--', 'result-plain', 'res-2', bare, p)  # reports no status
    f.until('the plain program\'s line on the parent\'s screen', lambda: f'res-2: done {bare}' in screen(), 20)
    if re.search(r'<hc from="\S+ res-2', screen()):
        raise Fail('a plain program\'s send arrived tagged, which the contract says it does not')
    for each in (path, bare):
        if not each.read_text().startswith('Status: DONE'):
            raise Fail(f'{each} holds {each.read_text()!r}')
    return f'an agent\'s line arrived tagged ({shown.group(0)!r}), a plain program\'s as bare text; both files are there'


def rebuild(f, s):
    lead, job, key = f.jobs.get('tree') or (None, None, None)
    if not job:
        raise Fail('needs tree')
    f.start(job, 'keeper', '--outlive-parent', '--', 'sleep', '900')
    snap = f.stampede('snapshot', job)
    if snap.returncode or not Path(snap.stdout.strip().splitlines()[-1]).is_file():
        raise Fail(f'stampede snapshot: exit {snap.returncode}: {(snap.stdout + snap.stderr).strip()[-300:]}')
    named = f.by_name(key)
    before = {n: t['address'] for n, t in named.items()}
    places = {n: placed(t['labels']) for n, t in named.items()}
    f.hc('kill', before[lead])
    f.until('the branch ended with the lead', lambda: (lambda n: n if set(n) == {'keeper'} else None)(f.by_name(key)), 20)
    helpers, subs = ['help-a', 'help-b'], ['sub-a1', 'sub-a2', 'sub-b1', 'sub-b2']
    began = time.time()
    first = f.stampede('reopen', job, timeout=300)  # no flag: the lead, and the never-ran Claude helpers through the queue
    seconds = time.time() - began
    lines = first.stdout.strip().splitlines()
    walk = [i for i, line in enumerate(lines) if re.match(r'(SKIPPED|DONE|LIVE) ', line)]
    problems = [f'reopen exit {first.returncode}: {first.stderr.strip()[-200:]}'] if first.returncode else []
    problems += [f'the first reopen started {started}, not the lead then {helpers} under it'] \
        if (started := re.findall(r'^STARTED (\S+)', first.stdout, re.M)) != [lead, *helpers] else []
    problems += ['the helpers\' STARTED lines come before the walk ended, not from the drain after it'] \
        if walk and min(i for i, line in enumerate(lines) if line.startswith('STARTED help-')) < max(walk) else []
    problems += [f'no SKIPPED (a program) for {n}'] if (n := [p for p in subs if f'SKIPPED {p} (a program: --rerun-programs' not in first.stdout]) else []
    problems += [f'{n} came back resumed'] if (n := [h for h in helpers if f.by_name(key).get(h, {}).get('labels', {}).get('stampede.resumed')]) else []
    problems += [f'no DONE line for {n} closed by name'] if (n := [c for c in s.get('closed', []) if f'DONE {c} (closed)' not in first.stdout]) else []
    problems += ['no LIVE line for keeper'] if not re.search(r'^LIVE keeper ', first.stdout, re.M) else []
    problems += [f'{n} left in the queue'] if (n := len(list((job / 'queue').glob('*.json')))) else []
    second = f.stampede('reopen', job, '--rerun-programs', timeout=300)
    problems += [f'reopen --rerun-programs (exit {second.returncode}) started {started}, not {subs}'] \
        if second.returncode or sorted(started := re.findall(r'^STARTED (\S+)', second.stdout, re.M)) != subs else []
    third = f.stampede('reopen', job, '--rerun-programs', timeout=300)
    problems += [f'a third reopen (exit {third.returncode}) started {re.findall(r"^STARTED (\S+)", third.stdout, re.M)}'] \
        if third.returncode or re.search(r'^STARTED', third.stdout, re.M) else []
    named = f.by_name(key)
    address = {n: t['address'] for n, t in named.items()}
    want = {'help-a': lead, 'help-b': lead, 'sub-a1': 'help-a', 'sub-a2': 'help-a', 'sub-b1': 'help-b', 'sub-b2': 'help-b'}
    wrong = {n: named.get(n, {}).get('parent') for n, p in want.items() if named.get(n, {}).get('parent') != address.get(p)}
    same = [n for n in [lead, *want] if address.get(n) == before.get(n)]
    moved = {n: (places[n], placed(named[n]['labels'])) for n in [lead, *want] if n in named and placed(named[n]['labels']) != places[n]}
    count = {n: sum(1 for t in f.of(key) if t['labels'].get('stampede.agent') == n) for n in [lead, *want]}
    problems += [f'Core parents {wrong}'] if wrong else []
    problems += [f'the same address as before for {same}'] if same else []
    problems += [f'places changed (before, after): {moved}'] if moved else []
    problems += [f'live terminals per name {count}'] if set(count.values()) != {1} else []
    keeper = next((n for n in json.loads(f.stampede('tree', job, '--json').stdout)['nodes'] if n['name'] == 'keeper'), {})
    problems += [f'stampede tree --json shows keeper as {keeper}, not outlived'] if not keeper.get('outlived') else []
    problems += queued_reopen(f, s)
    if problems:
        raise Fail('; '.join(problems) + f'. First reopen: {" | ".join(lines)}')
    s['rebuild'] = seconds
    return (f'lead killed: its branch ended, keeper (--outlive-parent) lived on; a plain reopen in {seconds:.1f} s started the lead, '
            f'then help-a and help-b (never ran) from the queue, SKIPPED the 4 programs, DONE (closed) for the '
            f'{len(s.get("closed", []))} closed by name, keeper LIVE and outlived {keeper["outlived"]}; --rerun-programs then started '
            f'the 4 under their parents; same places, new addresses; a third reopen started nothing; {s["queued"]}')


def queued_reopen(f, s):
    """The cap job (cap 3, 3 running and 2 queued): its lead killed, a reopen --rerun-programs starts the lead and what
    the cap allows, QUEUED for the rest; each place freed (a helper killed) lets one stampede next start one more."""
    lead, job, key = f.jobs.get('cap') or (None, None, None)
    if not job:
        return ['needs cap']
    f.hc('kill', f.by_name(key)[lead]['address'])
    f.until('the cap job\'s branch ended', lambda: not f.of(key), 20)
    back = f.stampede('reopen', job, '--rerun-programs', timeout=300)
    queued = re.findall(r'^QUEUED (\S+) \((\d+) running, cap (\d+)\)', back.stdout, re.M)
    started = re.findall(r'^STARTED (cap-\d)', back.stdout, re.M)
    problems = [] if not back.returncode and len(started) == 3 and len(queued) == 2 and {q[1:] for q in queued} == {('3', '3')} \
        else [f'cap reopen: exit {back.returncode}, STARTED {started}, QUEUED {queued}: {" | ".join(back.stdout.strip().splitlines())}']
    peak, later = f.running(key), []
    for _ in range(2):
        f.hc('kill', next(t['address'] for t in f.of(key) if t['labels'].get('stampede.role') == 'helper'))
        out = f.stampede('next', job).stdout
        later += re.findall(r'^STARTED (\S+)', out, re.M)
        peak = max(peak, f.running(key))
    if later != [q[0] for q in queued] or peak > 3 or list((job / 'queue').glob('*.json')):
        problems.append(f'cap: next started {later} after two places freed, not {[q[0] for q in queued]}; peak {peak} running')
    s['queued'] = f'cap 3: reopen STARTED {len(started)}, QUEUED {" ".join(q[0] for q in queued)} (3 running, cap 3); next started each as a place freed, peak {peak}'
    return problems


def teardown(f, s):
    lead, job, key = f.jobs.get('tree') or (None, None, None)
    if not job:
        raise Fail('needs tree')
    shown = {n['name']: n for n in json.loads(f.stampede('tree', job, '--json').stdout)['nodes']}
    began = time.time()
    closed = f.stampede('close', job, timeout=300)
    seconds = time.time() - began
    order = re.findall(r'^CLOSED (\S+)', closed.stdout, re.M)
    parent = {n['address']: n['name'] for n in shown.values()}
    early = [n for n in order if n in shown and shown[n]['parent'] in parent and order.index(parent[shown[n]['parent']]) < order.index(n)]
    alive = [t['labels'].get('stampede.agent') for t in f.of(key)]
    if closed.returncode or sorted(order) != sorted(shown) or order[-1:] != [lead] or early or alive or not (job / 'closed').is_file() \
            or ('keeper' in shown) != ('keeper' in order[:-1]):
        raise Fail(f'close exit {closed.returncode}, order {order}, a parent before its child {early}, still live {alive}: '
                   f'{(closed.stdout + closed.stderr).strip()[-300:]}')
    back = f.stampede('reopen', job, '--rerun-programs', timeout=300)  # a whole-job close marks no node: reopen brings it back
    again = set(re.findall(r'^STARTED (\S+)', back.stdout, re.M))
    kept = [c for c in s.get('closed', []) if f'DONE {c} (closed)' not in back.stdout]
    if back.returncode or again != set(shown) or kept:
        raise Fail(f'reopen after the close: exit {back.returncode}, started {sorted(again)}, not {sorted(shown)}; '
                   f'no DONE (closed) for {kept}: {" | ".join(back.stdout.strip().splitlines())}')
    end = f.stampede('close', job, timeout=300)
    if end.returncode or [t for t in f.of(key)]:
        raise Fail(f'the last close: exit {end.returncode}, still live {[t["labels"].get("stampede.agent") for t in f.of(key)]}')
    lead, job, key = f.jobs.get('cap') or (None, None, None)  # a finished job: stampede finish, then the lead killed
    if not job:
        raise Fail('needs cap')
    done = f.stampede('finish', job, 'the fleet test is done with it')
    f.hc('kill', f.by_name(key)[lead]['address'])
    refused = f.stampede('reopen', job, '--rerun-programs', timeout=300)
    said = (refused.stdout + refused.stderr).strip().splitlines()
    plain = f.stampede('reopen', job, timeout=300)
    if done.returncode or refused.returncode != 2 or len(said) != 1 or 'the job is finished' not in said[0] \
            or re.search(r'^(STARTED|QUEUED) ', plain.stdout, re.M) or list((job / 'queue').glob('*.json')):
        raise Fail(f'finish exit {done.returncode}; reopen --rerun-programs of a finished job: exit {refused.returncode}, said {said}; '
                   f'a plain reopen: {" | ".join(plain.stdout.strip().splitlines())}')
    return (f'CLOSED {" ".join(order)} (leaves first, keeper the outlived child before the lead, the lead last) in {seconds:.1f} s; '
            f'nothing of the job was live; reopen then brought back the same {len(again)}, closed-by-name helpers stayed DONE (closed); '
            f'a finished job: reopen --rerun-programs refused in one line, exit 2; a plain reopen started and queued nothing')


def watchdog(f, s):
    lead, job, key = f.new('watch', owner=BOT)
    sweep = lambda: f.sh([sys.executable, '-I', EVENT_CORE, '--sweep'], timeout=120)
    events = lambda: [json.loads(p.read_text()).get('payload') or {} for p in sorted((f.t / 'queue/queue').glob('*.json'))]
    mine = lambda: [e.get('state') for e in events() if e.get('workspace') == key and e.get('source') == 'hc']
    told = f.stampede('tell', job, 'lead', 'block')
    if told.returncode:
        raise Fail(f'tell lead block: {told.stdout} {told.stderr}')
    f.until('the lead reports blocked', lambda: (f.by_name(key)[lead].get('status') or {}).get('state') == 'blocked', 20)
    sweep()
    sweep()
    after_block = mine()
    f.hc('kill', f.by_name(key)[lead]['address'])
    sweep()
    sweep()
    got = mine()
    if after_block != ['blocked'] or sorted(got) != ['blocked', 'dead']:
        raise Fail(f'events after the block {after_block}, after the kill {got}')
    lead, job, key = f.new('lost', owner=BOT)  # a lead killed and removed before any sweep saw it: Core has no row at all
    address = f.by_name(key)[lead]['address']
    f.hc('kill', address)
    f.hc('rm', address)
    sweep()
    first = mine()
    sweep()
    sweep()
    if first != ['dead'] or mine() != ['dead']:
        raise Fail(f'a lead removed before any sweep: events after one sweep {first}, after three {mine()}')
    return ('two sweeps of a blocked lead queued one blocked event; two sweeps after its kill one dead event; a lead killed and '
            'removed before any sweep: one dead event, then none in two more sweeps')


CHECKS = [('tree', tree), ('fanout', fanout), ('cap', cap), ('layout', layout), ('blocked', blocked), ('waiting', waiting),
          ('results', results), ('rebuild', rebuild), ('teardown', teardown), ('watchdog', watchdog)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--only', help='a comma-separated list of checks: ' + ','.join(n for n, _ in CHECKS))
    parser.add_argument('--keep', action='store_true', help='leave the scratch folder (not the core) for a look')
    args = parser.parse_args()
    if not shutil.which('hc'):
        raise SystemExit('BLOCKED: hc is not on PATH')
    picked = args.only.split(',') if args.only else [n for n, _ in CHECKS]
    before = own_core()
    f, rows, state = Fleet(args.keep), [], {}
    version = subprocess.run(['hc', '--version'], capture_output=True, text=True).stdout.strip()
    print(f'{version}, scratch HC_SESSION={f.session} under {f.t}', flush=True)
    try:
        f.prepare()
        for number, (name, check) in enumerate(CHECKS, 1):
            if name not in picked:
                continue
            began, f.log = time.time(), []
            try:
                word, text = 'PASS', check(f, state)
            except Fail as error:
                word, text = 'FAIL', str(error)
            except Exception as error:  # noqa: BLE001: any break of a check is its FAIL, and the run goes on
                word, text = 'FAIL', f'{type(error).__name__}: {error}'
            if word == 'FAIL' and os.environ.get('NATIVE_FLEET_DEBUG'):
                print('\n'.join(f.log[-15:]), file=sys.stderr)
            rows.append((number, name, word, time.time() - began, text))
            print(f'{word} {number:>2} {name:<9} {rows[-1][3]:6.1f} s  {text}', flush=True)
    finally:
        f.cleanup()
    after = own_core()
    print('\n| # | check | result | seconds |\n|---|---|---|---|')
    for n, name, word, seconds, _ in rows:
        print(f'| {n} | {name} | {word} | {seconds:.1f} |')
    print(f'\nthe machine\'s own core: before {"up" if before[0] else "down"}, {len(before[1])} terminals; after '
          f'{"up" if after[0] else "down"}, {len(after[1])} terminals; ' + ('the same' if before == after else
          f'gone {sorted(set(before[1]) - set(after[1]))}, new {sorted(set(after[1]) - set(before[1]))}'))
    print(f'  before: {", ".join(before[1])}\n  after:  {", ".join(after[1])}')
    return 0 if rows and all(r[2] == 'PASS' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
