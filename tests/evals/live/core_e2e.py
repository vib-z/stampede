#!/usr/bin/env python3
"""The core-live evals: the cases in cases.json with backend core-live (C01 to C16 and V03), run on a real Herdr Core (hc 0.1.13 or
later) in a scratch session of its own, never the machine's own core, through the real `stampede` command installed into
a scratch HOME by install.sh. Records through record.py; exits 0 when nothing failed or broke.

    python3 tests/evals/live/core_e2e.py --label baseline-core-macos [--cases C01,C02] [--out <dir>] [--keep]

What is real: hc and its core, the stampede command and its follower, the job record, the relay's queue. What stands
in: the agents (core_agent.py as `claude` and `codex`: OSC 7501 status, the CLIs' hooks, no model), the phone (a card
that never answers) and the bot's route (a URL on 127.0.0.1 that is never flushed). Nothing leaves the machine.

The scratch core: HC_SESSION, XDG_STATE_HOME, XDG_RUNTIME_DIR and XDG_CONFIG_HOME under a short folder in /tmp (a Unix
socket path holds at most 103 bytes), its HOME a scratch home, and every hc call of the run through a wrapper that logs
the session it named and refuses any other (C09). The machine's own core is only observed, by its socket, never with an
hc command. On macOS the core is started the way an ssh session starts it (a plain detached process); a start from a
desktop shell goes through a one-shot launchd job, which the run must not leave behind (the brief's rule: stop and
record if launchd gains anything). The owner's surrogate for approve-gate (C05) runs detached to pid 1 with every Herdr
and Core variable removed, as tests/clients_run.py's detached() runs a client outside Herdr, and its ancestry is logged; it runs
the gate event's own approve line as the bot was handed it (with --digest where the product adds one), never a line of its own.
"""
import argparse, json, os, platform, pty, re, select, shlex, shutil, signal, subprocess, sys, tempfile, time, traceback, uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
sys.path[:0] = [str(EVALS), str(EVALS.parent)]
import record  # noqa: E402
import hc_contract  # noqa: E402

ROOT = EVALS.parents[1]
FOLLOWER = ROOT / 'skills/grokbot-herdr/scripts/herdr-event-core'
AGENT = HERE / 'core_agent.py'
DARWIN = platform.system() == 'Darwin'
BOT = 'evalbot'
# the job's life, then jobs of their own (a Codex lead, the app's labels and a loss under keep), then the guards
ORDER = ['C01', 'C02', 'C03', 'C13', 'C04', 'C05', 'C10', 'C11', 'C06', 'C07', 'C08', 'C12', 'C14', 'C16', 'C15', 'V03', 'C09']
NEEDS = {'C02': 'C01', 'C03': 'C02', 'C13': 'C02', 'C04': 'C02', 'C05': 'C01', 'C10': 'C02', 'C11': 'C02', 'C06': 'C02', 'C07': 'C01',
         'C15': 'C16'}
HERDR_VARS = ('HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_SOCKET_PATH', 'HERDR_BIN_PATH')
BRIEF = """# {agent}: a stand-in worker of the core-live evals

## Goal
Do what the eval runner tells you through your terminal or your inbox.

## Why
The runner proves the job's lifecycle on a real Herdr Core; you are a stand-in agent, so no model runs.

## Inputs
Your inbox file and the prompts the runner sends.

## Constraints
Touch nothing outside the scratch folder.

## Done when
The runner has recorded its cases.

## Report back
{report}

## If blocked
Write to questions/{agent}.md and end your turn.
"""


class Fail(Exception):
    """The case ran and its expectation did not hold."""


class Blocked(Exception):
    """The case could not run here."""


class Skip(Exception):
    """The case does not apply here."""


DRAFT_WAIT = 30  # seconds the scratch core holds a send for a person's draft: stampede then stops a send after 20
RESTART_MARK = 'HC_EVAL_RESTART_MARK'  # set only in the shell that runs hc server restart (C10)


def restart_leak(start):
    """C10's oracle on a worker's start record (core_agent.py's start event): the reason it fails, or None. A record with
    no recorded environment mapping is a failure too, never read as an empty one."""
    env = start.get('env')
    if not isinstance(env, dict) or not env:
        return f'the start record holds no recorded environment, so nothing shows what the core passed the worker: {start}'
    if RESTART_MARK in env:
        return (f'a worker started after the restart got the restart shell\'s variable {RESTART_MARK}: the core took the new '
                f'environment, not the one it started with; the worker saw {env}')
    return None


def shell(path, text):
    Path(path).write_text(text)
    Path(path).chmod(0o755)


class Harness:
    def __init__(self, keep=False):
        self.keep, self.log, self.commands = keep, [], []
        self.pids, self.job, self.addr, self.state = [], None, {}, {}
        self.t = Path(tempfile.mkdtemp(prefix='sc.', dir='/tmp'))
        self.session = 'ev' + uuid.uuid4().hex[:6]
        self.real_hc = shutil.which('hc')
        self.real_home = Path(os.environ.get('HOME') or Path.home())
        self.home = self.t / 'h'  # short, and not /home/<user>, which the recorder scrubs
        base = {k: v for k, v in os.environ.items() if not k.startswith(('HC_', 'HERDR_', 'STAMPEDE_', 'FLEET_', 'CLAUDE', 'CODEX'))}
        self.env = {**base, 'HOME': str(self.home), 'HC_SESSION': self.session, 'XDG_STATE_HOME': str(self.t / 'state'),
                    'XDG_RUNTIME_DIR': str(self.t / 'run'), 'XDG_CONFIG_HOME': str(self.t / 'config'),
                    'PATH': f'{self.t / "bin"}:{self.home / ".local/bin"}:{base.get("PATH", "/usr/bin:/bin")}',
                    'FLEET_TRUST_ROOT': str(self.t / 'code'), 'FLEET_JOBS_ROOT': str(self.t / 'jobs'),
                    'HERDR_EVENTS_DIR': str(self.t / 'events'), 'HERDR_EVENTS_HOME': str(self.t / 'queue'),
                    'HERDR_EVENTS_ROUTES_DIR': str(self.t / 'routes'), 'HERDR_EVENTS_MACHINE': 'evalhost',
                    'FLEET_ASK_CMD': str(self.t / 'bin/phone'), 'FLEET_WATCH_NOTIFY': '0', 'STAMPEDE_NO_UPDATE_CHECK': '1'}
        self.outside_env = {k: v for k, v in self.env.items() if not k.startswith('HC_') and k not in HERDR_VARS}

    # --- the log of the case at hand -------------------------------------------------------------------------------
    def note(self, text):
        self.log.append(f'{datetime.now():%H:%M:%S} {text}')

    def take(self):
        """The case's log and commands, and a fresh start for the next."""
        log, commands, self.log, self.commands = '\n'.join(self.log), list(self.commands), [], []
        return log, commands

    def sh(self, argv, env=None, timeout=120, stdin=None, cwd=None, show=True):
        """One command, logged with its exit code and output tail; its CompletedProcess."""
        if show:
            self.commands.append(shlex.join([str(a) for a in argv]))
        try:
            done = subprocess.run([str(a) for a in argv], env=env or self.env, capture_output=True, text=True, timeout=timeout,
                                  input=stdin, cwd=cwd)
        except subprocess.TimeoutExpired:
            done = subprocess.CompletedProcess(argv, 124, '', f'timed out after {timeout} s')
        tail = (done.stdout.strip() + (' | ' + done.stderr.strip() if done.stderr.strip() else ''))[-600:]
        self.note(f'$ {shlex.join([str(a) for a in argv])[:300]} -> {done.returncode} {tail}')
        return done

    def hc(self, *args, env=None, timeout=90):
        """One hc command of the scratch session, through the logging wrapper: (exit code, JSON or {})."""
        done = self.sh(['hc', args[0], '--json', *args[1:]], env=env, timeout=timeout)
        try:
            return done.returncode, json.loads(done.stdout or done.stderr or '{}')
        except ValueError:
            return done.returncode or 1, {}

    def hc_ok(self, *args, **kw):
        code, data = self.hc(*args, **kw)
        if code:
            raise Fail(f'hc {" ".join(args)} failed ({code}): {data}')
        return data

    def stampede(self, *args, env=None, timeout=180):
        return self.sh(['stampede', *args], env=env, timeout=timeout)

    def until(self, what, check, seconds=30, every=0.3):
        """The value check() returns once it is truthy, within seconds; else Fail(what)."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            found = check()
            if found:
                return found
            time.sleep(every)
        raise Fail(f'{what} (not within {seconds} s)')

    # --- the job's files -------------------------------------------------------------------------------------------
    def read(self, name):
        path = self.job / name
        return path.read_text() if path.is_file() else ''

    def inbox_log(self):
        return [row for row in self.read('inbox.log').splitlines() if row.strip()]

    def core_json(self):
        return json.loads(self.read('core.json') or '{}')

    def standin(self, name, job=None):
        """What a stand-in agent logged (core_agent.py): one dict per line."""
        path = (job or self.job) / 'standin' / (name + '.log')
        return [json.loads(row) for row in path.read_text().splitlines() if row.strip()] if path.is_file() else []

    def relay_sent(self):
        state = self.read('relay-state.json')
        return set(json.loads(state).get('sent', [])) if state else set()

    def relay_log(self):
        path = self.home / 'Library/Logs/herdr-events.log' if DARWIN else self.t / 'state/herdr-events.log'
        return path.read_text().splitlines() if path.is_file() else []

    def queued(self):
        """The bot's queue: (file name, route, payload) of each event waiting."""
        out = []
        for path in sorted((self.t / 'queue/queue').glob('*.json')):
            data = json.loads(path.read_text())
            out.append((path.name, data.get('route'), data.get('payload') or {}))
        return out

    def job_terminals(self, key=None, all=False):
        return self.hc_ok('ls', *(['--all'] if all else []), '--label', 'stampede.job=' + (key or self.state['key'])).get('terminals', [])

    def live(self, key=None):
        return {t['name']: t['address'] for t in self.job_terminals(key) if t.get('state', 'live') == 'live'}

    def hc_calls(self):
        path = self.t / 'logs/hc-calls.log'
        return path.read_text().splitlines() if path.is_file() else []

    def alive_pid(self, pid):
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def default_core(self):
        """Whether the machine's own core answers on its socket: herdr-event-core --alive with this process's own
        environment, no HC_SESSION or HC_SOCKET; never an hc command, which could start a stopped core."""
        env = {k: v for k, v in os.environ.items() if k not in ('HC_SESSION', 'HC_SOCKET')}
        path = subprocess.run([sys.executable, '-I', str(FOLLOWER), '--socket'], env=env, capture_output=True, text=True).stdout.strip()
        alive = subprocess.run([sys.executable, '-I', str(FOLLOWER), '--alive'], env=env, capture_output=True, text=True).returncode == 0
        return {'socket': path, 'exists': Path(path).exists() if path else None, 'alive': alive}

    def launchd(self):
        """What launchd holds (macOS): LaunchAgents, and labels not Apple's own; {} elsewhere."""
        if not DARWIN:
            return {}
        agents = sorted(p.name for p in (self.real_home / 'Library/LaunchAgents').glob('*')) if (self.real_home / 'Library/LaunchAgents').is_dir() else []
        listed = subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout.splitlines()
        labels = sorted(row.split('\t')[-1] for row in listed[1:] if row.strip() and not row.split('\t')[-1].startswith('com.apple.'))
        return {'agents': agents, 'labels': labels}

    def real_state(self):
        """The machine's own Core state folder, by session name: the scratch session must never appear there."""
        folder = self.real_home / '.local/state/herdr-core'
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def outside(self, argv, host='bot-shell', timeout=90):
        """Run argv as the bot's own shell outside Herdr and Herdr Core runs it: a process whose parent is pid 1 (a double
        fork, as tests/clients_run.py detached() does), with every Herdr and Core variable removed, and its ancestry
        (pid, ppid, command up to pid 1) recorded. Returns (exit code, stdout, stderr, chain)."""
        box = Path(tempfile.mkdtemp(prefix='out-', dir=self.t))
        (box / host).symlink_to('/bin/bash')
        script = ('for _ in $(seq 250); do p=$(ps -o ppid= -p $$ 2>&1) || break; [ "${p// /}" = 1 ] && break; sleep 0.02; done; '
                  'if [ "${p// /}" != 1 ]; then : >"$0.out"; echo "not detached: the parent of $$ is not pid 1 (ps: ${p:-no answer})" >"$0.err"; '
                  'echo 125 >"$0.tmp"; mv "$0.tmp" "$0.code"; exit; fi; '
                  'c=$$; while [ "$c" -gt 1 ]; do ps -o pid=,ppid=,comm= -p "$c" >>"$0.chain"; c=$(ps -o ppid= -p "$c" | tr -d " "); [ -n "$c" ] || break; done; '
                  '"$@" >"$0.out" 2>"$0.err" </dev/null; echo $? >"$0.tmp"; mv "$0.tmp" "$0.code"')
        self.commands.append('(outside Herdr and Core, parent pid 1) ' + shlex.join([str(a) for a in argv]))
        subprocess.run(['/bin/bash', '-c', '"$0" -c "$1" "${@:2}" >/dev/null 2>&1 & echo $!', str(box / host), script, str(box / 'run'),
                        *[str(a) for a in argv]], env=self.outside_env, capture_output=True, text=True, check=True)
        deadline = time.time() + timeout
        while not (box / 'run.code').exists():
            if time.time() > deadline:
                raise Fail(f'the outside command did not end in {timeout} s')
            time.sleep(0.05)
        code, out, err = int((box / 'run.code').read_text()), (box / 'run.out').read_text(), (box / 'run.err').read_text()
        chain = (box / 'run.chain').read_text().strip() if (box / 'run.chain').is_file() else ''
        self.note(f'outside: exit {code}; chain (pid ppid comm, up to pid 1):\n{chain}\nout: {out.strip()[-300:]} err: {err.strip()[-300:]}')
        shutil.rmtree(box, ignore_errors=True)
        return code, out, err, chain

    # --- the scratch world -----------------------------------------------------------------------------------------
    def prepare(self):
        """The scratch folders, stand-ins, repo, scratch install and core; Blocked when the machine cannot run this."""
        missing = [tool for tool in ('hc', 'jq', 'git', 'python3', 'bash', 'ps') if not shutil.which(tool)]
        if missing:
            raise Blocked('not on PATH: ' + ', '.join(missing))
        t, home, bin_ = self.t, self.home, self.t / 'bin'
        for folder in ('state', 'run', 'config', 'bin', 'code', 'jobs', 'events', 'queue', 'routes', 'logs', 'h/.claude', 'h/.codex', 'h/.local/bin'):
            (t / folder).mkdir(parents=True, exist_ok=True)
        for kind in ('claude', 'codex'):  # the agent CLIs: the stand-in, with the CLI's own arguments
            shell(bin_ / kind, f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -I {shlex.quote(str(AGENT))} --kind {kind} "$@"\n')
        shell(bin_ / 'hc', '#!/bin/sh\n# every hc call of the run: logged with the session it names; another session is refused (C09)\n'
                           f'LOG={shlex.quote(str(t / "logs/hc-calls.log"))}\n'
                           f'if [ "${{HC_SESSION:-}}" != {shlex.quote(self.session)} ]; then echo "$(date +%T) REFUSED HC_SESSION=${{HC_SESSION:-unset}} $*" >>"$LOG"; '
                           'echo "hc wrapper: refused: HC_SESSION=${HC_SESSION:-unset} is not the scratch session" >&2; exit 97; fi\n'
                           'echo "$(date +%T) HC_SESSION=$HC_SESSION $*" >>"$LOG"\n'
                           f'exec {shlex.quote(self.real_hc)} "$@"\n')
        shell(bin_ / 'herdr', '#!/bin/sh\n# no Herdr TUI in this run: any call is an error, never the machine\'s own server\n'
                              'echo \'{"error":{"code":"no_herdr","message":"core-live evals run with no Herdr TUI"}}\'; exit 1\n')
        shell(bin_ / 'moshi-hook', '#!/bin/sh\n# no phone in this run\nprintf "%s\\n" "$*" >> "$(dirname "$0")/moshi.log"; exit 3\n')
        shell(bin_ / 'phone', '#!/bin/bash\n# FLEET_ASK_CMD: a card that never answers, so a background ask stays alive until something ends it\n'
                              'printf "%s\\n" "$*" >> "$(dirname "$0")/phone.log"\nsleep 3600\nexit 4\n')
        shell(home / '.local/bin/herdr-event-flush', '#!/bin/sh\n# no flusher: the bot\'s events stay in the queue and nothing leaves the machine\nexit 0\n')
        (t / 'config/herdr-core').mkdir(parents=True, exist_ok=True)  # the scratch core's own settings
        (t / 'config/herdr-core/config.toml').write_text(f'draft_wait = {DRAFT_WAIT}\n')  # a shorter hold than Core's 60 s, for C13
        (t / 'routes' / BOT).write_text('URL=http://127.0.0.1:9/never\nKEY=none\n')
        (t / 'routes' / BOT).chmod(0o600)
        repo = t / 'code/repo'
        repo.mkdir(parents=True)
        git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], env=self.env, capture_output=True, text=True, check=True).stdout.strip()
        git('init', '-q')
        git('config', 'user.email', 'evals@example.invalid')
        git('config', 'user.name', 'evals')
        (repo / 'README.md').write_text('# scratch\n')
        git('add', '.')
        git('commit', '-q', '-m', 'first')
        self.state['sha_a'] = git('rev-parse', 'HEAD')
        (repo / 'hello.txt').write_text('hello\n')
        git('add', '.')
        git('commit', '-q', '-m', 'second')
        self.state['sha_b'] = git('rev-parse', 'HEAD')
        self.repo = repo.resolve()  # as stampede records it (on macOS /tmp is a link to /private/tmp)
        installed = self.sh(['bash', str(ROOT / 'install.sh'), '--no-supervise'])
        if installed.returncode or not (home / '.local/bin/stampede').is_symlink():
            raise Blocked(f'install.sh --no-supervise into the scratch HOME failed ({installed.returncode}): {installed.stderr[-300:]}')
        self.state['before'] = {'default_core': self.default_core(), 'launchd': self.launchd(), 'real_state': self.real_state()}
        self.note(f'before: default core {self.state["before"]["default_core"]}; launchd labels {len(self.state["before"]["launchd"].get("labels", []))}')
        env = {**self.env, **({'SSH_CONNECTION': '127.0.0.1 1 127.0.0.1 22'} if DARWIN else {})}  # an ssh start: no launchd
        self.commands.append(('SSH_CONNECTION=... ' if DARWIN else '') + f'HC_SESSION={self.session} hc server start')
        started = self.sh(['hc', 'server', 'start', '--json'], env=env, show=False)
        if started.returncode:
            raise Blocked(f'hc server start failed for the scratch session ({started.returncode}): {(started.stderr or started.stdout)[-300:]}')
        self.state['core'] = json.loads(started.stdout or '{}')
        named = (self.state['core'].get('core') or {}).get('name')  # Core 0.1.20 names a core after the machine
        if named and named not in record.HOSTS:
            record.HOSTS.insert(0, named)  # so no run ever records it
        version = subprocess.run([self.real_hc, '--version'], capture_output=True, text=True).stdout.strip()
        self.state['hc_version'] = version
        after = self.launchd()
        gained = {k: sorted(set(after.get(k, [])) - set(self.state['before']['launchd'].get(k, []))) for k in after}
        if any(gained.values()):
            self.stop_core()
            raise Blocked(f'starting the scratch core registered with launchd: {gained}; the core was stopped and nothing ran')
        self.note(f'core started: {version}, pid {self.state["core"].get("pid")}, socket {self.t}/run/herdr-core/{self.session}.sock; launchd gained nothing')

    def stop_core(self):
        """End every terminal of the scratch session, then the core itself."""
        code, data = self.hc('ls', '--all')
        for terminal in data.get('terminals', []) if code == 0 else []:
            if terminal.get('state') == 'live':
                self.hc('kill', terminal['address'])
            self.hc('rm', terminal['address'])
        self.sh(['hc', 'server', 'stop', '--json'], timeout=60)

    def cleanup(self):
        self.stop_core()
        for pid in self.pids:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(int(pid), sig)
                except (ProcessLookupError, PermissionError):
                    try:
                        os.kill(int(pid), sig)
                    except (ProcessLookupError, PermissionError):
                        pass
        subprocess.run(['pkill', '-f', str(self.t)], capture_output=True)  # anything still naming the scratch folder is ours
        if not self.keep:
            shutil.rmtree(self.t, ignore_errors=True)

    # --- the cases -------------------------------------------------------------------------------------------------
    def new_job(self, name, owner, flags=()):
        ask = self.t / f'ask-{name}.md'
        ask.write_text(f'Eval job {name}: a stand-in lead and stand-in workers on Herdr Core.\n')
        env = {**self.env, **({'HERDR_EVENTS_OWNER': owner} if owner else {})}
        self.commands.append((f'HERDR_EVENTS_OWNER={owner} ' if owner else '') + shlex.join(['stampede', 'new', '--core', *flags, '--file', str(ask),
                                                                                             '--cwd', str(self.repo), '--name', name]))
        made = self.sh(['stampede', 'new', '--core', *flags, '--file', str(ask), '--cwd', str(self.repo), '--name', name], env=env, timeout=180, show=False)
        if made.returncode:
            raise Fail(f'stampede new --core exited {made.returncode}: {made.stdout.strip()[-300:]} {made.stderr.strip()[-300:]}')
        lead, job = made.stdout.strip().splitlines()[-1].split(' ', 1)
        return lead, Path(job)

    def worker_brief(self, agent, report=None):
        path = self.t / f'brief-{agent}.md'
        path.write_text(BRIEF.format(agent=agent, report=f'Write {report} with Status: DONE in its first 10 lines.' if report else 'Nothing: the runner reads your log.'))
        return path

    def start_worker(self, agent, kind, report=None, job=None):
        job = job or self.job
        args = ['start', str(job), agent, '--kind', kind, '--brief', str(self.worker_brief(agent, report))] + (['--report', report] if report else [])
        started = self.stampede(*args)
        found = re.search(r'STARTED ' + re.escape(agent) + r' \((\S+)\)', started.stdout)
        if started.returncode or not found:
            raise Fail(f'stampede start {agent} --kind {kind}: exit {started.returncode}: {started.stdout.strip()[-300:]} {started.stderr.strip()[-300:]}')
        return found.group(1)

    def c01(self):
        self.lead, self.job = self.new_job('ev1', BOT)
        key = self.read('workspace').strip()
        self.state['key'] = key
        if not re.fullmatch(r'hc-[0-9a-f]{12}', key):
            raise Fail(f'workspace holds no Core key: {key!r}')
        if self.read('backend').strip() != 'core':
            raise Fail('backend file is not core')
        endpoint = json.loads(self.read('endpoint') or '{}')
        if endpoint.get('session') != self.session:
            raise Fail(f'endpoint names {endpoint}, not the scratch session')
        if self.read('owner').strip() != BOT:
            raise Fail(f'owner is {self.read("owner").strip()!r}')
        entries = self.core_json()
        relay = 'relay-' + key[3:]
        for name, role in ((self.lead, 'lead'), (relay, 'relay')):
            entry = entries.get(name, {})
            if entry.get('state') != 'live' or entry.get('role') != role or not entry.get('address'):
                raise Fail(f'core.json entry for {name} is {entry}')
            self.addr[name] = entry['address']
        live = self.live(key)
        if set(live) != {self.lead, relay}:
            raise Fail(f'the job runs {sorted(live)}, not the lead and the follower')
        got = self.hc_ok('get', self.addr[self.lead])
        labels = got.get('labels') or {}
        want = {'stampede.job': key, 'stampede.agent': self.lead, 'stampede.role': 'lead'}
        if any(labels.get(k) != v for k, v in want.items()) or not labels.get('stampede.session'):
            raise Fail(f'the lead terminal carries labels {labels}')
        if got.get('parent') is not None:
            raise Fail(f'the lead terminal has a parent: {got.get("parent")}')
        brief = self.job / 'briefs' / (self.lead + '.md')
        pointer = f'You are {self.lead}. Read {brief} and do everything it says.'
        start = self.until('the lead stand-in logged its start', lambda: [r for r in self.standin(self.lead) if r.get('event') == 'start'], 20)[0]
        if start.get('prompt') != pointer:
            raise Fail(f'the lead\'s first prompt is {start.get("prompt")!r}, not the brief pointer')
        if start.get('session') != labels['stampede.session'] or '--session-id' not in start.get('argv', []):
            raise Fail(f'the lead did not start with --session-id {labels["stampede.session"]}: {start.get("argv")}')
        if 'HERDR_ENV' in start.get('env', {}) or 'HERDR_PANE_ID' in start.get('env', {}):
            raise Fail(f'the lead terminal got the caller\'s Herdr ids: {start.get("env")}')
        marker = self.t / 'events/jobs' / key
        if not marker.is_file() or marker.read_text().strip() != str(self.job):
            raise Fail(f'no job marker for {key}')
        if f'owner={BOT}' not in (self.t / 'events/owners' / key).read_text():
            raise Fail('the owner tag does not name the bot')
        if not (self.job / 'reopen.sh').is_file() or not (self.job / 'REOPEN.md').is_file():
            raise Fail('no reopen record written at new')
        status = (got.get('status') or {}).get('state')
        return (f'new --core made {self.job.name} (key {key}) on HC_SESSION={self.session}: record (backend, endpoint, owner, marker, tag), '
                f'follower {relay} at {self.addr[relay]} and lead at {self.addr[self.lead]} live with the job\'s labels and no parent; '
                f'the lead\'s first prompt is the brief pointer, status {status}')

    def c02(self):
        self.addr['worker-a'] = self.start_worker('worker-a', 'claude', report='reports/worker-a.md')
        self.addr['worker-b'] = self.start_worker('worker-b', 'codex')
        rows = {row.split('\t')[0]: row.split('\t') for row in self.read('agents.tsv').splitlines() if row and not row.startswith('#')}
        entries = self.core_json()
        said = []
        for name, kind in (('worker-a', 'claude'), ('worker-b', 'codex')):
            got = self.hc_ok('get', self.addr[name])
            labels = got.get('labels') or {}
            want = {'stampede.job': self.state['key'], 'stampede.agent': name, 'stampede.role': 'worker'}
            if any(labels.get(k) != v for k, v in want.items()) or (kind == 'claude') != bool(labels.get('stampede.session')):
                raise Fail(f'{name}\'s terminal carries labels {labels}')
            if got.get('state') != 'live' or got.get('parent') is not None:
                raise Fail(f'{name}\'s terminal: state {got.get("state")}, parent {got.get("parent")}')
            row = rows.get(name)
            if not row or row[1] != kind or (kind == 'claude' and row[2] != labels['stampede.session']) or not row[3].endswith(f'brief-{name}.md'):
                raise Fail(f'agents.tsv row for {name} is {row}')
            entry = entries.get(name, {})
            if entry.get('state') != 'live' or entry.get('address') != self.addr[name] or entry.get('role') != 'worker' or entry.get('cwd') != str(self.repo):
                raise Fail(f'core.json entry for {name} is {entry}')
            start = self.until(f'{name} logged its start', lambda: [r for r in self.standin(name) if r.get('event') == 'start'], 20)[0]
            brief = self.t / f'brief-{name}.md'
            if start.get('prompt') != f'You are {name} in a herdr fleet. Read {brief} and do everything it says.':
                raise Fail(f'{name}\'s first prompt is {start.get("prompt")!r}')
            if kind == 'codex' and '--no-daemon' not in start.get('argv', []):
                raise Fail(f'the Codex worker runs without --no-daemon: {start.get("argv")}')
            said.append(f'{name} ({kind}) at {self.addr[name]}')
        again = self.stampede('start', str(self.job), 'worker-a', '--kind', 'claude', '--brief', str(self.t / 'brief-worker-a.md'))
        if again.returncode != 2 or 'already running' not in again.stderr:
            raise Fail(f'a second start of worker-a was not refused: exit {again.returncode}: {again.stdout} {again.stderr}')
        return 'stampede start (no --core flag: the job\'s backend) put ' + ' and '.join(said) + \
               ' in Core terminals with the job\'s labels; agents.tsv and core.json record them; a second start of worker-a is refused (exit 2, already running)'

    def c03(self):
        worker, addr = 'worker-b', self.addr['worker-b']
        self.until('worker-b idle or done', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 20)
        word = self.hc_ok('get', addr)['status']['state']
        before = len(self.hc_calls())
        told = self.stampede('tell', str(self.job), worker, 'sleep 4')
        if told.returncode or f'SUBMITTED {worker}' not in told.stdout:
            raise Fail(f'tell while {word}: exit {told.returncode}: {told.stdout} {told.stderr}')
        sends = [row for row in self.hc_calls()[before:] if ' send ' in row]
        if len(sends) != 1 or (word == 'idle') != ('--if idle' in sends[0]):
            raise Fail(f'tell while {word} ran {sends}')
        self.until('worker-b working', lambda: self.hc('get', addr)[1].get('status', {}).get('state') == 'working', 10)
        refused = self.stampede('tell', str(self.job), worker, 'reply: too early')
        if refused.returncode != 2 or f'FAILED {worker} (working' not in refused.stdout:
            raise Fail(f'tell to a working worker was not refused: exit {refused.returncode}: {refused.stdout} {refused.stderr}')
        if any(r.get('event') == 'prompt' and 'too early' in r.get('text', '') for r in self.standin(worker)):
            raise Fail('the refused tell reached the worker')
        self.until('worker-b done', lambda: self.hc('get', addr)[1].get('status', {}).get('state') == 'done', 20)
        reply = f'hello lead, from {worker} at {datetime.now():%H:%M:%S}'
        told = self.stampede('tell', str(self.job), worker, f'fleet-job tell {self.job} lead {shlex.quote(reply)}')
        if told.returncode or f'SUBMITTED {worker}' not in told.stdout:
            raise Fail(f'tell while done: exit {told.returncode}: {told.stdout} {told.stderr}')
        self.until('the reply in the lead inbox', lambda: reply in self.read(f'inbox/{self.lead}.md'), 30)
        return (f'tell reached the idle Codex worker with hc send --if idle, was refused while it worked (FAILED, working, nothing typed), '
                f'went in once its turn was done, and the worker\'s reply (fleet-job tell lead) landed in inbox/{self.lead}.md')

    def c04(self):
        worker, addr = 'worker-a', self.addr['worker-a']
        reports = lambda: [row for row in self.inbox_log() if row.startswith('REPORT ')]
        if reports():
            raise Fail(f'a REPORT line before any report: {reports()}')
        told = self.stampede('tell', str(self.job), worker, 'report reports/worker-a.md')
        if told.returncode or 'DELIVERED worker-a' not in told.stdout:
            raise Fail(f'tell worker-a: exit {told.returncode}: {told.stdout} {told.stderr}')
        self.until('REPORT reports/worker-a.md in inbox.log', lambda: reports() == ['REPORT reports/worker-a.md'], 40)
        hooks = [r for r in self.standin(worker) if r.get('event') == 'hook' and r.get('hook') == 'Stop']
        wake = [r for r in self.standin(worker) if r.get('event') == 'prompt' and r.get('source') == 'wake']
        if not hooks or not wake:
            raise Fail(f'the stand-in ran no Stop hook or got no wake: {len(hooks)} Stop hooks, {len(wake)} wakes')
        n = len(self.standin(worker))
        told = self.stampede('tell', str(self.job), worker, 'a second turn with the report unchanged')
        self.until('a second Stop hook', lambda: len([r for r in self.standin(worker)[n:] if r.get('event') == 'hook' and r.get('hook') == 'Stop']) >= 1, 30)
        time.sleep(2)
        if reports() != ['REPORT reports/worker-a.md']:
            raise Fail(f'REPORT lines after the second turn: {reports()}')
        turns = self.hc_ok('get', addr).get('turn') or 0
        self.until('the follower posted every turn end', lambda: len([s for s in self.relay_sent() if s.startswith(addr + '|turn|')]) >= turns, 15)
        posted = sorted(int(s.rsplit('|', 1)[1]) for s in self.relay_sent() if s.startswith(addr + '|turn|'))
        if posted != list(range(1, turns + 1)):
            raise Fail(f'the follower posted turns {posted} for {turns} turn ends')
        logged = [row for row in self.relay_log() if f'pane=hc:{self.state["key"]}/{addr} ' in row and 'state=done' in row]
        if len(logged) != turns:
            raise Fail(f'the relay saw {len(logged)} turn ends of {worker} for {turns} turns: {logged[-3:]}')
        return (f'one REPORT line from the worker\'s Stop hook (run by the stand-in from its --settings, {len(hooks)} Stop runs), none added by a '
                f'second turn; the follower posted turns {posted} once each ({len(logged)} relay lines, kept home as job-skip)')

    def c05(self):
        job, sha, other = str(self.job), self.state['sha_b'], self.state['sha_a']
        lead_addr, before = self.addr[self.lead], len(self.standin(self.lead))
        self.hc_ok('send', lead_addr, f'fleet-job ask {job} --gate --sha {sha} "Commit hello.txt to the scratch repo"')
        asked = self.until('the lead asked the gate', lambda: [r for r in self.standin(self.lead)[before:] if r.get('event') == 'action' and '--gate' in r.get('argv', [])], 60)[0]
        found = re.search(r'GATE ([0-9a-f]{12}) queued for ' + BOT, asked.get('stdout', ''))
        if asked.get('exit') != 0 or not found:
            raise Fail(f'ask --gate from the lead: {asked}')
        gate = found.group(1)
        self.state['gate'] = gate
        if not (self.job / 'gates' / (gate + '.json')).is_file():
            raise Fail(f'no gate file for {gate}')
        queued = [q for q in self.queued() if q[2].get('state') == 'gate' and q[2].get('gate') == gate]
        if len(queued) != 1 or queued[0][1] != BOT:
            raise Fail(f'the gate event in the queue: {queued}')
        approved = self.job / 'gates' / (gate + '.approved')
        self.hc_ok('send', lead_addr, 'yes')
        self.until('the typed yes was taken as a prompt', lambda: any(r.get('event') == 'prompt' and r.get('text') == 'yes' for r in self.standin(self.lead)[before:]), 20)
        time.sleep(1)
        if approved.exists():
            raise Fail('a yes typed into the lead terminal made an approval record')
        check = self.stampede('gate-ok', job, gate, '--sha', sha)
        if check.returncode != 2 or 'APPROVED' in check.stdout or 'no recorded yes' not in check.stderr or 'typed' in check.stderr:
            raise Fail(f'gate-ok after the typed yes: exit {check.returncode}: {check.stdout} {check.stderr}')
        chain = 'c=$$; while [ "$c" -gt 1 ]; do ps -o pid=,ppid=,comm= -p "$c"; c=$(ps -o ppid= -p "$c" | tr -d " "); [ -n "$c" ] || break; done'
        under = self.sh(['hc', 'exec', '--', 'sh', '-c', f'echo "exec chain:"; {chain}; env | grep "^HC_" | sort; '
                         f'fleet-job approve-gate {shlex.quote(job)} {gate} --sha {sha} --by "owner, through hc exec"'], timeout=90)
        if under.returncode != 2 or 'runs only outside Herdr and Herdr Core' not in (under.stdout + under.stderr) or approved.exists():
            raise Fail(f'approve-gate under hc exec: exit {under.returncode}: {under.stdout[-300:]} {under.stderr[-300:]}')
        n = len(self.standin(self.lead))
        self.hc_ok('send', lead_addr, f'fleet-job approve-gate {job} {gate} --sha {sha} --by "typed in the lead terminal"')
        inside = self.until('the lead ran approve-gate in its terminal',
                            lambda: [r for r in self.standin(self.lead)[n:] if r.get('event') == 'action' and 'approve-gate' in ' '.join(r.get('argv', []))], 30)[0]
        if inside.get('exit') != 2 or 'runs only outside Herdr and Herdr Core' not in inside.get('stderr', '') or approved.exists():
            raise Fail(f'approve-gate inside the lead terminal: {inside}')
        approve = queued[0][2].get('approve') or ''  # the bot runs the gate event's own approve line, as given
        if not approve.startswith('fleet-job approve-gate '):
            raise Fail(f'the gate event carries no approve line: {approve!r}')
        code, out, err, chain_text = self.outside(shlex.split(approve))
        if code != 0 or f'APPROVED {gate} at {sha}' not in out or not approved.is_file():
            raise Fail(f'the gate event\'s approve line from outside: exit {code}: {out} {err}')
        if 'herdr' in chain_text.lower() or re.search(r'\bhc\b', chain_text):
            raise Fail(f'the outside approver had Herdr or Core above it: {chain_text}')
        self.until('GATE APPROVED in the lead inbox', lambda: f'GATE {gate} APPROVED by owner in {BOT} chat' in self.read(f'inbox/{self.lead}.md'), 20)
        check = self.stampede('gate-ok', job, gate, '--sha', sha)
        if check.returncode or f'APPROVED {gate}' not in check.stdout:
            raise Fail(f'gate-ok after the recorded yes: exit {check.returncode}: {check.stdout} {check.stderr}')
        stale = self.stampede('gate-ok', job, gate, '--sha', other)
        if stale.returncode != 2 or 'APPROVED' in stale.stdout or 'withdraws it' not in stale.stderr:
            raise Fail(f'gate-ok at another commit: exit {stale.returncode}: {stale.stdout} {stale.stderr}')
        return (f'gate {gate} queued for {BOT}; a typed yes recorded nothing (gate-ok: no recorded yes, no typed yes offered); approve-gate refused '
                f'under hc exec and inside the lead terminal (exit 2); from a shell outside both (parent pid 1, chain logged) APPROVED; gate-ok at '
                f'{sha[:12]} APPROVED, at {other[:12]} refused (withdrawn)')

    def c10(self):
        before = {name: self.hc_ok('get', addr) for name, addr in self.addr.items()}
        live_before = self.live()
        lines, sent, calls = list(self.inbox_log()), set(self.relay_sent()), len(self.hc_calls())
        env = {**self.env, RESTART_MARK: 'restarted'}  # a changed environment: 0.1.19 keeps the one the core started with
        self.commands.append(f'{RESTART_MARK}=restarted HC_SESSION={self.session} hc server restart')
        restarted = self.sh(['hc', 'server', 'restart', '--json'], env=env, timeout=90, show=False)
        if restarted.returncode:
            raise Fail(f'hc server restart: exit {restarted.returncode}: {restarted.stdout[-300:]} {restarted.stderr[-300:]}')
        self.until('the restarted core answers', lambda: self.hc('ls')[0] == 0, 30, 1)
        after = self.live()
        if after != live_before:
            raise Fail(f'the job\'s live terminals changed over the restart: {live_before} -> {after}')
        for name, got in before.items():
            now = self.hc_ok('get', self.addr[name])
            if now.get('state') != 'live' or now.get('pid') != got.get('pid'):
                raise Fail(f'{name}: state {now.get("state")}, pid {got.get("pid")} -> {now.get("pid")}')
        self.until('the follower reconnected (a new hc events stream)', lambda: any(' events ' in row for row in self.hc_calls()[calls:]), 60, 1)
        time.sleep(5)
        gone = [row for row in self.inbox_log() if row.startswith(('GONE', 'REPORT', 'LOST', 'ERROR', 'BLOCKED', 'RELAY DOWN'))]
        was = [row for row in lines if row.startswith(('GONE', 'REPORT', 'LOST', 'ERROR', 'BLOCKED', 'RELAY DOWN'))]
        if gone != was:
            raise Fail(f'the follower added lines over the restart: {gone} (was {was})')
        if not sent <= self.relay_sent():
            raise Fail('the follower lost its record of what it sent')
        self.addr['worker-d'] = self.start_worker('worker-d', 'claude')
        start = self.until('worker-d logged its start', lambda: [r for r in self.standin('worker-d') if r.get('event') == 'start'], 20)[0]
        self.note(f'worker-d, started after the restart, saw: {start.get("env")}')
        fault = restart_leak(start)
        if fault:
            raise Fail(fault)
        return (f'hc server restart kept the job\'s {len(before)} terminals (same addresses and pids); the follower reconnected and wrote no '
                f'duplicate line; a worker started after it did not get the restart shell\'s variable (its environment is in the log)')

    def c11(self):
        workers = {name: addr for name, addr in self.addr.items() if name.startswith('worker-')}
        pids = {name: self.hc_ok('get', addr).get('pid') for name, addr in workers.items()}
        count = len(self.job_terminals(all=True))
        self.hc_ok('kill', self.addr[self.lead])
        self.until('the lead terminal finished', lambda: self.hc('get', self.addr[self.lead])[1].get('state') == 'finished', 20)
        time.sleep(2)
        for name, addr in workers.items():
            now = self.hc_ok('get', addr)
            if now.get('state') != 'live' or now.get('pid') != pids[name]:
                raise Fail(f'{name} did not outlive the lead: state {now.get("state")}, pid {pids[name]} -> {now.get("pid")}')
        reopened = self.sh(['bash', str(self.job / 'reopen.sh')], timeout=200)
        started = re.findall(r'^(?:STARTED|RESTARTED) (\S+)', reopened.stdout, re.M)
        if reopened.returncode or started != [self.lead] or f'ACKNOWLEDGED {self.lead}' not in reopened.stdout:
            raise Fail(f'reopen.sh after the lead\'s kill: exit {reopened.returncode}, started {started}: {reopened.stdout[-400:]} {reopened.stderr[-200:]}')
        self.addr[self.lead] = self.core_json()[self.lead]['address']
        if len(self.job_terminals(all=True)) != count + 1:
            raise Fail('reopen started more than the lead')
        return (f'killing the lead left {", ".join(workers)} running (same pids); reopen.sh restarted the lead only ({self.addr[self.lead]}), '
                f'acknowledged through its wake hook, exit 0')

    def c06(self):
        count, gone = len(self.job_terminals(all=True)), len([row for row in self.inbox_log() if row.startswith('GONE worker-a')])
        sessions = {row.split('\t')[0]: row.split('\t')[2] for row in self.read('agents.tsv').splitlines() if row and not row.startswith('#')}
        self.hc_ok('kill', self.addr[self.lead])
        self.hc_ok('kill', self.addr['worker-a'])
        self.until('GONE worker-a from the follower', lambda: len([row for row in self.inbox_log() if row.startswith('GONE worker-a killed')]) > gone, 30)
        reopened = self.sh(['bash', str(self.job / 'reopen.sh')], timeout=200)
        started = sorted(re.findall(r'^(?:STARTED|RESTARTED) (\S+)', reopened.stdout, re.M))
        if reopened.returncode or started != sorted([self.lead, 'worker-a']) or f'ACKNOWLEDGED {self.lead}' not in reopened.stdout:
            raise Fail(f'reopen.sh: exit {reopened.returncode}, started {started}: {reopened.stdout[-400:]} {reopened.stderr[-200:]}')
        entries = self.core_json()
        for name in (self.lead, 'worker-a'):
            self.addr[name] = entries[name]['address']
            start = [r for r in self.standin(name) if r.get('event') == 'start'][-1]
            argv = start.get('argv', [])
            if '--resume' not in argv or argv[argv.index('--resume') + 1] != sessions[name]:
                raise Fail(f'{name} was not resumed with its session {sessions[name]}: {argv}')
        if len(self.job_terminals(all=True)) != count + 2 or set(self.live()) != {self.lead, 'worker-a', 'worker-b', 'worker-d', 'relay-' + self.state['key'][3:]}:
            raise Fail(f'after reopen: {sorted(self.live())}, {len(self.job_terminals(all=True))} terminals in all')
        again = self.sh(['bash', str(self.job / 'reopen.sh')], timeout=120)
        if again.returncode or f'LIVE {self.state["key"]}: no agent to restart' not in again.stdout or len(self.job_terminals(all=True)) != count + 2:
            raise Fail(f'a second reopen.sh: exit {again.returncode}: {again.stdout[-300:]} {again.stderr[-200:]}')
        return (f'the follower reported GONE worker-a killed; reopen.sh restarted exactly the lead and worker-a, each with --resume <its session>, '
                f'and left worker-b, worker-d and the follower alone; a second reopen.sh printed LIVE and started nothing')

    def c07(self):
        relay, job = 'relay-' + self.state['key'][3:], str(self.job)
        n = len(self.standin(self.lead))
        self.hc_ok('send', self.addr[self.lead], f'fleet-job finish {job} "ev1 done: every case ran"')
        done = self.until('the lead ran finish', lambda: [r for r in self.standin(self.lead)[n:] if r.get('event') == 'action' and 'finish' in r.get('argv', [])], 60)[0]
        if done.get('exit') != 0 or f'FINISHED {job}' not in done.get('stdout', ''):
            raise Fail(f'finish from the lead: {done}')
        events = [q for q in self.queued() if q[2].get('source') == 'stampede' and q[2].get('state') == 'done' and q[2].get('job') == job]
        if len(events) != 1 or events[0][1] != BOT:
            raise Fail(f'done events in the queue: {events}')
        self.until('the follower exited', lambda: self.hc('get', self.addr[relay])[1].get('state') == 'finished', 30)
        follower = self.hc_ok('get', self.addr[relay])
        if follower.get('exit_code') != 0:
            raise Fail(f'the follower ended with {follower.get("reason")} exit {follower.get("exit_code")}')
        if (self.t / 'events/jobs' / self.state['key']).exists():
            raise Fail('the job marker is still there after finish')
        def leftovers():
            rows = subprocess.run(['ps', '-axo', 'pid=,args='], capture_output=True, text=True).stdout.splitlines()
            return [row for row in rows if job in row and ('herdr-event-core' in row or 'fleet_job.py' in row)]
        self.until('no stampede process of the job', lambda: not leftovers(), 20) if leftovers() else None
        again = self.stampede('finish', job, 'ev1 done again')
        if again.returncode or 'FINISHED' not in again.stdout or len([q for q in self.queued() if q[2].get('state') == 'done']) != 1:
            raise Fail(f'a second finish: exit {again.returncode}: {again.stdout} {again.stderr}; queue {self.queued()}')
        return (f'finish from the lead queued one done event for {BOT}, the follower {relay} exited 0 by itself, the marker is gone, '
                f'no herdr-event-core or fleet_job.py process of the job is left (the stand-in agents keep running), and a second finish added nothing')

    # --- Herdr Core 0.1.20 and the Herdr app: the draft hold, a Codex lead, keep and the app's labels ---------------
    def core_version(self):
        found = re.search(r'(\d+)\.(\d+)\.(\d+)', self.state.get('hc_version', ''))
        return tuple(int(n) for n in found.groups()) if found else (0, 0, 0)

    def attach(self, address):
        """A person at a terminal: hc attach on a pty of its own. Returns (pid, fd); keys written to fd are a person's."""
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe('hc', ['hc', 'attach', address], self.env)
        self.pids.append(pid)
        self.commands.append(f'hc attach {address}   (on a pty: the person)')
        time.sleep(1.5)
        self.drain(fd)
        return pid, fd

    def drain(self, fd):
        while select.select([fd], [], [], 0.2)[0]:
            try:
                if not os.read(fd, 65536):
                    return
            except OSError:
                return

    def detach(self, pid, fd):
        for step in (lambda: os.write(fd, b'\x1c'), lambda: time.sleep(0.5), lambda: os.kill(pid, signal.SIGTERM), lambda: os.close(fd)):
            try:
                step()
            except OSError:
                pass

    def rows(self, job):
        return {row.split('\t')[0]: row.split('\t') for row in (job / 'agents.tsv').read_text().splitlines() if row and not row.startswith('#')}

    def prompts(self, name, job, since, holding):
        return [r for r in self.standin(name, job)[since:] if r.get('event') == 'prompt' and holding in r.get('text', '')]

    def end_job(self, job, key, summary):
        """finish a job of this run's own, then end what it still runs (stand-in agents outlive finish, as real ones do)."""
        done = self.stampede('finish', str(job), summary)
        if done.returncode or 'FINISHED' not in done.stdout:
            raise Fail(f'finish of {job.name}: exit {done.returncode}: {done.stdout[-200:]} {done.stderr[-200:]}')
        for terminal in self.job_terminals(key):
            self.hc('kill', terminal['address'])

    def c13(self):
        if self.core_version() < (0, 1, 20):
            raise Skip(f'{self.state["hc_version"]}: Herdr Core holds a send for a person\'s draft from 0.1.20 on')
        worker, addr, text = 'worker-b', self.addr['worker-b'], 'note after the draft'
        self.until('worker-b idle or done', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
        pid, fd = self.attach(addr)
        try:
            os.write(fd, b'half a thought')
            time.sleep(0.5)
            self.drain(fd)
            n, started = len(self.standin(worker)), time.time()
            self.commands.append(f'stampede tell {self.job} {worker} "{text}"   (while the person\'s draft "half a thought" sits unsent)')
            tell = subprocess.Popen(['stampede', 'tell', str(self.job), worker, text], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(5)
            held, early = tell.poll() is None, self.prompts(worker, self.job, n, '')
            os.write(fd, b'\x15')  # the person clears their line (ctrl+u)
            self.note(f'after 5 s: tell still waiting {held}; prompts the worker got meanwhile {len(early)}; the person then cleared the draft')
            try:
                out, err = tell.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                tell.kill()
                raise Fail('tell did not return within 120 s of the person clearing the draft')
            waited = time.time() - started
        finally:
            self.detach(pid, fd)
        self.note(f'tell: exit {tell.returncode} after {waited:.1f} s: {out.strip()} {err.strip()}')
        if not held or early:
            raise Fail(f'the tell did not wait for the person\'s draft: still running after 5 s {held}, prompts meanwhile {early}')
        if tell.returncode or f'SUBMITTED {worker} ({addr})' not in out:
            raise Fail(f'tell after the draft was cleared: exit {tell.returncode}: {out} {err}')
        got = self.until('the tell reached the worker', lambda: self.prompts(worker, self.job, n, text), 20)
        if [r['text'].strip() for r in self.prompts(worker, self.job, n, '')] != [text] or 'half a thought' in got[0]['text']:
            raise Fail(f'the worker got {[r["text"] for r in self.prompts(worker, self.job, n, "")]}, not the tell alone')
        # a draft the person leaves: Core would type the tell after it once its hold (DRAFT_WAIT) ran out
        self.until('worker-b done with that turn', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
        pid, fd = self.attach(addr)
        try:
            os.write(fd, b'left unsent')
            time.sleep(0.5)
            self.drain(fd)
            n, started = len(self.standin(worker)), time.time()
            left = self.stampede('tell', str(self.job), worker, 'a second note', timeout=DRAFT_WAIT + 60)
            took = time.time() - started
            time.sleep(max(0, DRAFT_WAIT + 5 - took))  # past the moment Core's hold ran out
            after_hold = self.prompts(worker, self.job, n, '')
            os.write(fd, b'\x15')  # the person clears the draft at last: nothing is waiting to go in
            time.sleep(5)
            after_clear = self.prompts(worker, self.job, n, '')
        finally:
            self.detach(pid, fd)
        if left.returncode != 2 or f'FAILED {worker} (hc send: no answer in {DRAFT_WAIT - 10} s' not in left.stdout:
            raise Fail(f'tell with a draft left alone: exit {left.returncode} after {took:.0f} s: {left.stdout} {left.stderr}')
        if after_hold or after_clear:
            raise Fail(f'something was typed after the draft: past the hold {after_hold}, after the person cleared it {after_clear}')
        return (f'with a person\'s unsent draft in the worker\'s terminal (typed through hc attach), stampede tell waited ({waited:.0f} s in all, '
                f'still waiting at 5 s, nothing typed meanwhile); once the person cleared the draft it printed SUBMITTED and the worker got '
                f'the tell alone, never the draft. With a draft left alone, the tell was stopped after {took:.0f} s (FAILED, read before any '
                f'resend), {DRAFT_WAIT - took:.0f} s before the core\'s {DRAFT_WAIT} s hold ran out, and nothing was typed then, when the hold ran '
                f'out, or after the person cleared the draft')

    def c14(self):
        lead, job = self.new_job('ev3', BOT, flags=('--lead', 'codex'))
        key = (job / 'workspace').read_text().strip()
        addr, relay = json.loads((job / 'core.json').read_text())[lead]['address'], 'relay-' + key[3:]
        try:
            start = self.until('the Codex lead logged its start', lambda: [r for r in self.standin(lead, job) if r.get('event') == 'start'], 30)[0]
            brief = job / 'briefs' / (lead + '.md')
            argv = start.get('argv', [])
            if start.get('kind') != 'codex' or '--no-daemon' not in argv or '--session-id' in argv or not any(a.startswith('notify=') for a in argv):
                raise Fail(f'the lead is not a Codex lead without its daemon and with its notify hook: {argv}')
            if start.get('prompt') != f'You are {lead}. Read {brief} and do everything it says.':
                raise Fail(f'the Codex lead\'s first prompt is {start.get("prompt")!r}, not the brief pointer')
            text = brief.read_text()
            if 'fleet-job types each new line of' not in text or 'into this terminal' not in text or 'prints APPROVED' not in text:
                raise Fail('the lead\'s brief is not a Codex lead\'s on Core')
            session = self.until('the lead\'s own session in agents.tsv, named by its first turn end', lambda: self.rows(job)[lead][2], 40)
            if self.rows(job)[lead][1] != 'codex' or not list((self.home / '.codex/sessions').glob(f'*/*/*/rollout-*{session}.jsonl')):
                raise Fail(f'agents.tsv row for the lead: {self.rows(job)[lead][:3]}')
            self.until('the lead done with its first turn', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
            n, calls = len(self.standin(lead, job)), len(self.hc_calls())
            told = self.stampede('tell', str(job), 'lead', 'ANSWER: keep hello in the root')
            if told.returncode or f'DELIVERED {lead} (inbox file; typed into its terminal once it is idle)' not in told.stdout:
                raise Fail(f'tell to the Codex lead: exit {told.returncode}: {told.stdout} {told.stderr}')
            typed = self.until('the answer typed into the lead\'s terminal', lambda: self.prompts(lead, job, n, 'ANSWER: keep hello in the root'), 90)[0]
            if not typed['text'].startswith(f'[fleet-job inbox for {lead}, not typed by the owner] '):
                raise Fail(f'the lead got {typed["text"]!r}, without the fleet-job marker')
            worker = self.start_worker('worker-x', 'claude', job=job)
            self.until('worker-x done with its brief', lambda: self.hc('get', worker)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
            self.hc_ok('kill', worker)
            self.until('the follower\'s GONE line typed into the lead\'s terminal', lambda: self.prompts(lead, job, n, 'inbox.log: GONE worker-x killed'), 90)
            time.sleep(8)  # a second delivery of either line would show by now
            twice = {line: len(self.prompts(lead, job, n, line)) for line in ('ANSWER: keep hello in the root', 'GONE worker-x killed')}
            if any(count != 1 for count in twice.values()):
                raise Fail(f'each line once, but the lead got {twice}')
            mine = [row for row in self.hc_calls()[calls:] if f' {addr} ' in row + ' ']
            if any(' keys ' in row for row in mine) or not any(' send ' in row for row in mine):
                raise Fail(f'the lead\'s terminal was written to by: {mine}')
            # the owner leaves text in the lead's prompt: the next line is not typed and the terminal is held; once the
            # owner sends their own text, the lead is pointed at the line, which itself is never typed
            self.until('the lead idle or done', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
            log, second = job / 'hooks/deliver.log', 'ANSWER: the second answer'
            pid, fd = self.attach(addr)
            try:
                os.write(fd, b'my own note')
                time.sleep(0.5)
                self.drain(fd)
                n = len(self.standin(lead, job))
                self.stampede('tell', str(job), 'lead', second)
                self.until('the deliverer holding the lead\'s terminal', lambda: f'HELD: a send to {lead}' in (log.read_text() if log.is_file() else ''),
                           DRAFT_WAIT + 40)
                meanwhile = self.prompts(lead, job, n, '')
                owed = json.loads((job / 'hooks/deliver-owed.json').read_text())
                held = [q[2] for q in self.queued() if q[2].get('kind') == 'held' and q[2].get('agent') == lead]
                os.write(fd, b'\r')  # the owner sends their own text: the lead takes a turn
                self.until('the owner\'s text as a prompt of its own', lambda: [r for r in self.prompts(lead, job, n, 'my own note')
                                                                               if r['text'].strip() == 'my own note'], 30)
                pointer = self.until('the pointer to the line', lambda: self.prompts(lead, job, n, 'may not have reached you'), 90)[0]
                time.sleep(6)  # a second pointer, or the line itself, would show by now
            finally:
                self.detach(pid, fd)
            if meanwhile or len(held) != 1 or owed != [[str(job / 'inbox' / (lead + '.md')), 2, 2]]:
                raise Fail(f'while the owner\'s text sat in the prompt: prompts typed {meanwhile}, owed {owed}, held events for the bot {held}')
            if self.prompts(lead, job, n, second) or len(self.prompts(lead, job, n, 'may not have reached you')) != 1 \
                    or f'lines 2 to 2 of {job / "inbox" / (lead + ".md")}' not in pointer['text']:
                raise Fail(f'after the owner sent their text the lead got {[r["text"] for r in self.prompts(lead, job, n, "")]}')
            if (job / 'hooks/deliver-held.json').exists() or (job / 'hooks/deliver-owed.json').exists():
                raise Fail('the hold or the owed lines are still recorded after the pointer went in')
        finally:
            if key:
                self.end_job(job, key, 'ev3 done')
        return (f'new --core --lead codex started {lead} at {addr} as Codex without its daemon, its brief pointer as its first prompt and its own '
                f'session in agents.tsv after its first turn; an answer for it and the follower\'s GONE worker-x line were each typed into its '
                f'terminal once by hc send, marked as from fleet-job, with no key pressed. With the owner\'s own text left in its prompt, the next '
                f'line was not typed: the send was stopped, the terminal held (one blocked event for the bot), and only after the owner sent their '
                f'text, a turn of its own, was the lead pointed once at the line to read; finish ended the job')

    def c16(self):
        lead, job = self.new_job('ev4', BOT, flags=('--app-space',))
        key = (job / 'workspace').read_text().strip()
        space, relay = 'stampede-' + key[3:], 'relay-' + key[3:]
        if (job / 'app-space').read_text().strip() != space:
            raise Fail(f'<job>/app-space holds {(job / "app-space").read_text()!r}')
        entries = json.loads((job / 'core.json').read_text())
        worker = self.start_worker('worker-k', 'codex', job=job)
        self.state['ev4'] = {'lead': lead, 'job': job, 'key': key, 'worker': worker}
        labels = {name: self.hc_ok('get', address).get('labels') or {} for name, address in
                  ((lead, entries[lead]['address']), ('worker-k', worker), (relay, entries[relay]['address']))}
        for name in (lead, 'worker-k'):
            if labels[name].get('herdr.space') != space or labels[name].get('herdr.tab') != name:
                raise Fail(f'{name} carries {labels[name]}, not herdr.space={space} and herdr.tab={name}')
        if any(k.startswith('herdr.') for k in labels[relay]):
            raise Fail(f'the follower carries the app\'s labels: {labels[relay]}')
        plain = 'not compared: no job without the flag ran in this run'
        if self.state.get('key'):
            others = [self.hc_ok('get', t['address']).get('labels') or {} for t in self.job_terminals(self.state['key'], all=True)]
            if any(k.startswith('herdr.') for found in others for k in found):
                raise Fail(f'a job started without --app-space carries the app\'s labels: {others}')
            plain = f'the {len(others)} terminals of the job started without the flag carry no herdr.* label'
        return (f'new --core --app-space labelled {lead} and worker-k herdr.space={space} and herdr.tab=<its name> on the real core, and the '
                f'follower not at all; {plain}')

    def c15(self):
        ev4 = self.state['ev4']
        job, key, addr, worker = ev4['job'], ev4['key'], ev4['worker'], 'worker-k'
        log = lambda: [row for row in (job / 'inbox.log').read_text().splitlines() if row.strip()] if (job / 'inbox.log').is_file() else []
        sent = lambda: set(json.loads((job / 'relay-state.json').read_text()).get('sent', [])) if (job / 'relay-state.json').is_file() else set()
        try:
            self.until('worker-k idle or done', lambda: self.hc('get', addr)[1].get('status', {}).get('state') in ('idle', 'done'), 30)
            told = self.stampede('tell', str(job), worker, 'sleep 40')
            if told.returncode:
                raise Fail(f'tell before the loss: {told.stdout} {told.stderr}')
            self.until('worker-k working', lambda: self.hc('get', addr)[1].get('status', {}).get('state') == 'working', 15)
            self.hc_ok('keep', addr)  # as the Herdr app does for a terminal it shows
            before, pid = sent(), self.hc_ok('get', addr).get('pid')
            self.commands.append(f'kill -9 {pid}   (the worker\'s own process: a loss, not an exit)')
            os.kill(int(pid), signal.SIGKILL)
            want = f'(a shell is in its place at {addr}: restart the agent with bash {job / "reopen.sh"})'
            self.until('the follower\'s GONE line naming the shell', lambda: [row for row in log() if row.startswith(f'GONE {worker} ') and want in row], 60)
            shell = self.until('a shell at the same address', lambda: (lambda t: t.get('state') == 'live' and t.get('pid') not in (None, pid)
                               and not any('STAMPEDE_JOB_KEY' in a for a in t.get('argv') or []) and t)(self.hc('get', addr)[1]), 40)
            time.sleep(5)  # anything the shell would wrongly cause shows by now
            gone = [row for row in log() if row.startswith(f'GONE {worker} ')]
            new = sorted(ident for ident in sent() - before if ident.startswith(addr + '|'))  # the lead's own turns are its own
            dead = [q[2] for q in self.queued() if q[2].get('pane') == f'hc:{key}/{addr}' and q[2].get('state') == 'dead']
            if len(gone) != 1 or new != sorted([f'{addr}|finished', f'{addr}|finished lead']) or len(dead) != 1 or dead[0].get('last_state') != 'working':
                raise Fail(f'GONE lines {gone}; what the follower told after the loss {new}; dead events {dead}')
            refused = self.stampede('tell', str(job), worker, 'are you there')
            if refused.returncode != 2 or f'its program was lost and Herdr Core put a shell in its place at {addr}' not in refused.stdout:
                raise Fail(f'tell to the shell: exit {refused.returncode}: {refused.stdout} {refused.stderr}')
            reopened = self.sh(['bash', str(job / 'reopen.sh')], timeout=200)
            started = re.findall(r'^(?:STARTED|RESTARTED) (\S+)', reopened.stdout, re.M)
            again = json.loads((job / 'core.json').read_text())[worker]['address']
            still = self.hc_ok('get', addr)
            if reopened.returncode or started != [worker] or again == addr or still.get('state') != 'live' or still.get('pid') != shell.get('pid'):
                raise Fail(f'reopen.sh: exit {reopened.returncode}, started {started}, worker-k now at {again}, the shell at {addr} is '
                           f'{still.get("state")}: {reopened.stdout[-300:]} {reopened.stderr[-200:]}')
            labels = self.hc_ok('get', again).get('labels') or {}
            if labels.get('herdr.tab') != worker or labels.get('stampede.agent') != worker:
                raise Fail(f'the restarted worker carries {labels}')
        finally:
            self.end_job(job, key, 'ev4 done')
        return (f'with keep on, kill -9 of worker-k\'s process made Core put a shell at {addr} (reason {dead[0].get("reason")}); the follower wrote one '
                f'GONE line naming the shell and one dead event for the bot (last state working), nothing as idle; tell refused the shell by name; '
                f'reopen.sh started worker-k again at {again} with the job\'s labels and left the shell alone')

    def v03(self):
        shown = self.sh(['hc', 'schema'], timeout=60)
        try:
            live = json.loads(shown.stdout)
        except ValueError:
            raise Fail(f'hc schema printed no JSON (exit {shown.returncode}): {shown.stderr[-200:]}')
        snapshot = hc_contract.snapshot()
        version = lambda schema: tuple(int(n) for n in schema['info']['version'].split('.')[:3])
        if version(live) < version(snapshot):
            raise Skip(f'hc {live["info"]["version"]} is older than the snapshot ({snapshot["info"]["version"]}): it may rightly lack what came since')
        here, kept = hc_contract.view(live), hc_contract.view(snapshot)
        if here != kept:
            differs = {k: (kept.get(k), here.get(k)) for k in sorted(set(here) | set(kept)) if here.get(k) != kept.get(k)}
            raise Fail(f'hc {live["info"]["version"]} differs from the snapshot in what stampede uses (snapshot, this machine): {differs}')
        return (f'hc schema {live["info"]["version"]} on this machine holds the {len(hc_contract.USES)} commands stampede uses (each method, '
                f'parameter, error kind and result field) and the {len(here["event types"])} event types, as the snapshot of '
                f'{snapshot["info"]["version"]} does')

    def c08(self):
        lead, job = self.new_job('ev2', None)
        key = (job / 'workspace').read_text().strip()
        if (job / 'owner').exists():
            raise Fail('the second job has an owner; it was meant to be local')
        entries = json.loads((job / 'core.json').read_text())
        self.addr['lead2'], self.addr['worker-c'] = entries[lead]['address'], self.start_worker('worker-c', 'claude', job=job)
        pid_file = job / 'standin' / 'detached.pid'
        told = self.stampede('tell', str(job), 'worker-c', f'detach {pid_file}')
        if told.returncode:
            raise Fail(f'tell worker-c: {told.stdout} {told.stderr}')
        child = int(self.until('the detached child\'s pid', lambda: pid_file.read_text().strip() if pid_file.is_file() else None, 30))
        self.pids.append(child)
        if not self.alive_pid(child):
            raise Fail(f'the detached child {child} is not alive before the kill')
        self.hc_ok('kill', self.addr['worker-c'])
        self.until('worker-c finished', lambda: self.hc('get', self.addr['worker-c'])[1].get('state') == 'finished', 20)
        time.sleep(3)
        child_alive = self.alive_pid(child)
        self.note(f'detached child {child} alive 3 s after hc kill of its terminal: {child_alive}')
        n = len(self.standin(lead, job))
        self.hc_ok('send', self.addr['lead2'], f'fleet-job ask {job} "Which colour?" --option red --option blue')
        asked = self.until('the lead asked', lambda: [r for r in self.standin(lead, job)[n:] if r.get('event') == 'action' and 'ask' in r.get('argv', [])], 60)[0]
        ident = re.search(r'ASKED ([0-9a-f]{12})', asked.get('stdout', ''))
        if asked.get('exit') != 0 or not ident:
            raise Fail(f'ask from the lead: {asked}')
        pid_path = job / 'asks' / (ident.group(1) + '.pid')
        ask_pid = int(pid_path.read_text().strip())
        self.pids.append(ask_pid)
        self.until('the phone card was asked', lambda: 'Which colour?' in ((self.t / 'bin/phone.log').read_text() if (self.t / 'bin/phone.log').is_file() else ''), 20)
        if not self.alive_pid(ask_pid):
            raise Fail(f'the background ask {ask_pid} is not alive while its card waits')
        n = len(self.standin(lead, job))
        self.hc_ok('send', self.addr['lead2'], f'fleet-job finish {job} "ev2 done"')
        self.until('the lead ran finish', lambda: (job / 'finished').is_file(), 60)
        time.sleep(2)
        ask_alive = self.alive_pid(ask_pid)
        self.hc_ok('kill', self.addr['lead2'])
        self.until('the lead terminal finished', lambda: self.hc('get', self.addr['lead2'])[1].get('state') == 'finished', 20)
        time.sleep(3)
        ask_after_lead = self.alive_pid(ask_pid)
        self.note(f'background ask {ask_pid}: alive after finish {ask_alive}, alive after the lead terminal\'s kill {ask_after_lead}')
        if not child_alive:
            raise Fail(f'the setsid child of the killed worker terminal died on {self.state["hc_version"]} (0.1.19 keeps detached programs)')
        if ask_alive:
            raise Fail(f'finish left the background ask alive (pid {ask_pid}, its card still waiting); after the lead terminal\'s kill it was '
                       f'{"still alive" if ask_after_lead else "gone"}: on 0.1.19 a detached helper outlives its terminal, so finish must end it')
        return f'the setsid child of the killed worker outlived its terminal; finish ended the background ask (pid {ask_pid})'

    def c12(self):
        if DARWIN:
            raise Skip('macOS: the 25 s polkit wait was a Linux terminal start (Core 0.1.17); nothing to measure here')
        polkit = {'pkexec': shutil.which('pkexec'), 'polkit_dir': Path('/usr/lib/polkit-1').exists() or Path('/usr/libexec/polkit-1').exists()}
        self.note(f'polkit: {polkit}')
        t0 = time.time()
        run = self.hc_ok('run', '--bg', '--no-parent', '--no-notify', '--name', 'probe-start', '--cwd', str(self.t), '--', str(self.t / 'bin/claude'))
        first = self.until('a first status', lambda: (self.hc('get', run['address'])[1].get('status') or {}).get('state'), 30, 0.1)
        took = time.time() - t0
        self.hc('kill', run['address'])
        self.hc('rm', run['address'])
        if took > 5:
            raise Fail(f'the first status ({first}) came after {took:.1f} s')
        return f'a Core terminal reported its first status ({first}) {took:.1f} s after hc run; polkit present: {bool(polkit["pkexec"] or polkit["polkit_dir"])}'

    def c09(self):
        socket_path = self.t / 'run/herdr-core' / (self.session + '.sock')
        config_ok = socket_path.exists() and (self.t / 'state/herdr-core' / self.session).is_dir()
        self.note(f'scratch socket {socket_path} exists: {socket_path.exists()}; scratch state dir exists: {(self.t / "state/herdr-core" / self.session).is_dir()}')
        self.stop_core()
        time.sleep(1)
        calls = self.hc_calls()
        refused = [row for row in calls if ' REFUSED ' in row]
        other = [row for row in calls if f'HC_SESSION={self.session} ' not in row and ' REFUSED ' not in row]
        after = {'default_core': self.default_core(), 'launchd': self.launchd(), 'real_state': self.real_state()}
        before = self.state['before']
        self.note(f'after: default core {after["default_core"]}; before: {before["default_core"]}')
        problems = []
        if not calls:
            problems.append('no hc call was logged')
        if refused or other:
            problems.append(f'{len(refused)} hc calls named another session: {(refused + other)[:3]}')
        if not config_ok:
            problems.append('the scratch socket or state folder was not under the scratch folder')
        if self.session in after['real_state'] or after['real_state'] != before['real_state']:
            problems.append(f'the machine\'s own Core state changed: {before["real_state"]} -> {after["real_state"]}')
        if after['launchd'] != before['launchd']:
            problems.append(f'launchd changed: {before["launchd"]} -> {after["launchd"]}')
        if before['default_core']['alive'] is None or not before['default_core']['socket']:
            raise Blocked('the default core cannot be observed by its socket here')
        if after['default_core']['alive'] != before['default_core']['alive'] or after['default_core']['exists'] != before['default_core']['exists']:
            problems.append(f'the default core changed: {before["default_core"]} -> {after["default_core"]}')
        if problems:
            raise Fail('; '.join(problems))
        return (f'{len(calls)} hc calls, every one with HC_SESSION={self.session}; config, state and socket under the scratch folder; the default '
                f'core only observed by its socket (alive before {before["default_core"]["alive"]}, after {after["default_core"]["alive"]}), '
                f'never an hc command; launchd and the machine\'s own Core state unchanged')


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--label', required=True)
    p.add_argument('--cases', default='', help='comma-separated ids; default: every core-live case')
    p.add_argument('--out', help='where the run folder goes (default tests/evals/runs)')
    p.add_argument('--keep', action='store_true', help='keep the scratch folder for a look')
    a = p.parse_args(argv)
    dataset = record.cases()
    owned = [i for i in ORDER if i in dataset and dataset[i]['backend'] == 'core-live']
    wanted = [c for c in a.cases.split(',') if c] or owned
    unknown = [c for c in wanted if c not in owned]
    if unknown:
        p.error('no core-live case ' + ', '.join(unknown))
    wanted = [i for i in ORDER if i in wanted]
    h = Harness(keep=a.keep)
    run = record.Run(a.label, backend='core-live', cases=wanted, out_root=a.out,
                     extra={'hc_session': h.session, 'scratch': str(h.t), 'stand_ins': 'claude and codex: tests/evals/live/core_agent.py; '
                            'phone (FLEET_ASK_CMD): a card that never answers; bot route: 127.0.0.1, never flushed',
                            'core_start': 'ssh-style (SSH_CONNECTION set), a plain detached process' if DARWIN else 'hc server start'})
    blocked, outcome = None, {}
    try:
        try:
            h.prepare()
        except Blocked as why:
            blocked = str(why)
        except Exception:
            blocked = 'the harness broke while preparing: ' + traceback.format_exc()[-1500:]
        setup_log, setup_commands = h.take()
        for ident in wanted:
            started = time.time()
            if blocked:
                run.case(ident, 'blocked', None, actual=blocked[:500], commands=setup_commands, log=setup_log)
                continue
            need = NEEDS.get(ident)
            if need and outcome.get(need) != 'pass':
                status, actual = 'blocked', f'needs {need} to pass in the same run (it was {outcome.get(need, "not run")})'
            else:
                try:
                    status, actual = 'pass', getattr(h, ident.lower())()
                except Fail as why:
                    status, actual = 'fail', str(why)
                except Blocked as why:
                    status, actual = 'blocked', str(why)
                except Skip as why:
                    status, actual = 'skip', str(why)
                except Exception:
                    status, actual = 'error', 'harness error: ' + traceback.format_exc()[-1200:]
                    h.note(traceback.format_exc())
            outcome[ident] = status
            log, commands = h.take()
            run.case(ident, status, None, actual=actual, commands=commands, log=(setup_log + '\n' if ident == wanted[0] else '') + log,
                     seconds=time.time() - started)
    finally:
        try:
            h.cleanup()
        except Exception:
            print('cleanup: ' + traceback.format_exc()[-500:], file=sys.stderr)
    return run.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
