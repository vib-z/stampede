#!/usr/bin/env python3
"""core_agent.py: a stand-in for Claude Code or Codex in a Herdr Core terminal, for the core-live evals (core_e2e.py).

It is what Herdr Core and stampede see of an agent, and nothing more: it reports OSC 7501 status (idle at start, then
working and done for every prompt), takes its first prompt from argv as the CLIs do, reads later prompts from its
terminal (hc send), runs the hooks stampede gave it the way the CLI would (Claude: SessionStart, then FileChanged on
the files that hook names, Stop after every turn; Codex: notify after every turn, with a rollout file for its thread),
and draws an empty-prompt line so hc read shows a prompt with nothing typed. No model runs and nothing is spent.

    claude  -> core_agent.py --kind claude <claude args...> [first prompt]
    codex   -> core_agent.py --kind codex  <codex args...>  [first prompt]

A prompt is chat unless one of its lines is an instruction for the stand-in:
    sleep <seconds>        stay working that long (a tell meanwhile is refused as working)
    report <path>          write a report with Status: DONE at <path> (relative to the job folder)
    detach <pid file>      start a deliberately detached child (its own session) and write its pid there
    fleet-job <args...>    run fleet-job with these arguments (a reply, a question, a gate, finish)
    block                  report blocked and stay so (a dialog no one answers), as a stuck agent does
Everything it does is appended to <job>/standin/<agent>.log, one JSON object per line, for the runner to check."""
import json, os, queue, re, shlex, subprocess, sys, threading, time, uuid
from datetime import datetime
from pathlib import Path

VALUED = {'--add-dir', '-n', '--settings', '--model', '--effort', '--session-id', '--resume', '-c', '-m', '--permission-mode', '--name'}
MARKER = '\r\n› \r\n'  # an empty Codex-like prompt line: tell_core refuses a screen that shows text typed and no marker


def status(word):
    os.write(1, ('\x1b]7501;state=' + word + ':app=core-agent\x1b\\').encode())


class Agent:
    def __init__(self, argv):
        self.kind = 'claude'
        if argv[:2] and argv[0] == '--kind':
            self.kind, argv = argv[1], argv[2:]
        self.argv, flags, positional = argv, {}, []
        i = 0
        while i < len(argv):
            if argv[i] in VALUED and i + 1 < len(argv):
                flags.setdefault(argv[i], []).append(argv[i + 1])
                i += 2
            elif argv[i].startswith('-'):
                i += 1
            else:
                positional.append(argv[i])
                i += 1
        self.job = Path(flags['--add-dir'][0]) if flags.get('--add-dir') else None
        self.settings = json.loads(Path(flags['--settings'][0]).read_text()) if flags.get('--settings') else {}
        self.notify = next((json.loads(v[len('notify='):]) for v in flags.get('-c', []) if v.startswith('notify=')), None)
        self.session = (flags.get('--session-id') or flags.get('--resume') or [''])[0]
        if self.kind == 'codex' and positional[:1] == ['resume']:
            self.session, positional = positional[1], positional[2:]
        self.prompt = ' '.join(positional)
        self.name = (flags.get('-n') or flags.get('--name') or [None])[0]
        if not self.name and self.notify and '--agent' in self.notify:
            self.name = self.notify[self.notify.index('--agent') + 1]
        self.name = self.name or 'agent'
        self.thread = self.session or uuid.uuid4().hex
        self.events, self.blocked = queue.Queue(), False
        folder = self.job / 'standin' if self.job else Path('/tmp')
        folder.mkdir(parents=True, exist_ok=True)
        self.log_path = folder / (self.name + '.log')

    def log(self, **fields):
        row = {'at': datetime.now().strftime('%H:%M:%S.%f')[:-3], 'pid': os.getpid(), **fields}
        with self.log_path.open('a') as out:
            out.write(json.dumps(row) + '\n')

    def run_hooks(self, event, payload):
        """Every hook of one event in the Claude settings, as Claude runs them: the payload on stdin; (exit, stdout, stderr)."""
        results = []
        for group in self.settings.get('hooks', {}).get(event, []):
            for hook in group.get('hooks', []):
                try:
                    done = subprocess.run(shlex.split(hook['command']), input=json.dumps(payload), capture_output=True, text=True, timeout=120)
                    result = (done.returncode, done.stdout, done.stderr)
                except (OSError, subprocess.TimeoutExpired) as error:
                    result = (127, '', str(error))
                self.log(event='hook', hook=event, exit=result[0], stdout=result[1][-2000:], stderr=result[2][-2000:])
                results.append(result)
        return results

    def watch(self, paths):
        """Poll the files the SessionStart hook named; a change is a FileChanged event, as Claude Code's file watch."""
        def stat(path):
            try:
                st = os.stat(path)
                return st.st_size, st.st_mtime_ns
            except OSError:
                return None
        seen = {p: stat(p) for p in paths}
        while True:
            time.sleep(0.25)
            for path in paths:
                now = stat(path)
                if now != seen[path]:
                    seen[path] = now
                    self.events.put(('changed', path))

    def read_stdin(self):
        """Lines typed or pasted into the terminal (hc send) are prompts; EOF ends the agent."""
        buffer = b''
        while True:
            try:
                chunk = os.read(0, 4096)
            except OSError:
                chunk = b''
            if not chunk:
                self.events.put(('eof', None))
                return
            buffer += chunk
            while b'\n' in buffer or b'\r' in buffer:
                cut = min(i for i in (buffer.find(b'\n'), buffer.find(b'\r')) if i >= 0)
                line, buffer = buffer[:cut], buffer[cut + 1:]
                if line.strip():
                    self.events.put(('prompt', line.decode('utf-8', 'replace')))

    def act(self, text):
        """The stand-in's instructions in a prompt, each logged with what came of it."""
        for row in text.splitlines():
            row = row.strip()
            found = re.fullmatch(r'sleep (\d+)', row)
            if found:
                self.log(event='action', action='sleep', seconds=int(found.group(1)))
                time.sleep(int(found.group(1)))
                continue
            found = re.fullmatch(r'report (\S+)', row)
            if found:
                path = Path(found.group(1))
                path = path if path.is_absolute() else (self.job or Path.cwd()) / path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'Status: DONE\n\n{self.name} wrote this report at {datetime.now():%H:%M:%S}.\n')
                self.log(event='action', action='report', path=str(path))
                continue
            found = re.fullmatch(r'detach (\S+)', row)
            if found:
                child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'], start_new_session=True,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                Path(found.group(1)).write_text(str(child.pid) + '\n')
                self.log(event='action', action='detach', child=child.pid, pid_file=found.group(1))
                continue
            if row == 'block':
                self.blocked = True
                self.log(event='action', action='block')
                continue
            found = re.fullmatch(r'fleet-job (.+)', row)
            if found:
                argv = ['fleet-job', *shlex.split(found.group(1))]
                try:
                    done = subprocess.run(argv, capture_output=True, text=True, timeout=300)
                    result = {'exit': done.returncode, 'stdout': done.stdout[-2000:], 'stderr': done.stderr[-2000:]}
                except (OSError, subprocess.TimeoutExpired) as error:
                    result = {'exit': 127, 'stdout': '', 'stderr': str(error)}
                self.log(event='action', action='fleet-job', argv=argv, **result)

    def turn(self, text, source):
        self.log(event='prompt', source=source, text=text[:2000])
        status('working')
        self.act(text)
        time.sleep(0.3)
        if self.blocked:
            status('blocked')
            return
        status('done')
        os.write(1, MARKER.encode())
        if self.kind == 'codex' and self.notify:
            payload = {'type': 'agent-turn-complete', 'thread-id': self.thread, 'turn-id': uuid.uuid4().hex,
                       'last-assistant-message': f'{self.name} finished a turn'}
            try:
                done = subprocess.run([*self.notify, json.dumps(payload)], capture_output=True, text=True, timeout=120)
                self.log(event='notify', exit=done.returncode, stdout=done.stdout[-2000:], stderr=done.stderr[-2000:])
            except (OSError, subprocess.TimeoutExpired) as error:
                self.log(event='notify', exit=127, stderr=str(error))
            return
        payload = {'hook_event_name': 'Stop', 'session_id': self.session, 'stop_hook_active': False}
        for code, out, _ in self.run_hooks('Stop', payload):
            try:
                blocked = code == 0 and json.loads(out or '{}').get('decision') == 'block'
            except ValueError:
                blocked = False
            if blocked:  # Claude goes on once, then stops again with stop_hook_active set
                self.run_hooks('Stop', {**payload, 'stop_hook_active': True})

    def rollout(self):
        """Codex keeps a rollout file per thread; stampede's notify hook reads its first line to tell a thread from a sub-agent."""
        home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
        day = datetime.now()
        folder = home / 'sessions' / f'{day:%Y}' / f'{day:%m}' / f'{day:%d}'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'rollout-{day:%Y-%m-%dT%H-%M-%S}-{self.thread}.jsonl'
        if not path.exists():
            path.write_text(json.dumps({'timestamp': day.isoformat(), 'type': 'session_meta', 'payload': {'id': self.thread, 'cwd': os.getcwd()}}) + '\n')

    def main(self):
        self.log(event='start', kind=self.kind, name=self.name, session=self.session, prompt=self.prompt, argv=self.argv, cwd=os.getcwd(),
                 env={k: v for k, v in os.environ.items() if k.startswith(('HC_', 'STAMPEDE_', 'HERDR_', 'FLEET_'))}, ppid=os.getppid())
        if self.kind == 'codex':
            self.rollout()
        status('idle')
        os.write(1, MARKER.encode())
        paths = []
        for code, out, _ in self.run_hooks('SessionStart', {'hook_event_name': 'SessionStart', 'session_id': self.session, 'cwd': os.getcwd()}):
            try:
                paths += json.loads(out or '{}').get('hookSpecificOutput', {}).get('watchPaths', []) if code == 0 else []
            except ValueError:
                pass
        if paths:
            threading.Thread(target=self.watch, args=(paths,), daemon=True).start()
        threading.Thread(target=self.read_stdin, daemon=True).start()
        if self.prompt:
            self.turn(self.prompt, 'argv')
        while True:
            try:
                kind, value = self.events.get(timeout=1)
            except queue.Empty:
                continue
            if kind == 'eof':
                self.log(event='exit', reason='stdin closed')
                return 0
            if kind == 'prompt' and value.strip() in ('/exit', '/quit'):  # the CLIs' own way out
                self.log(event='exit', reason=value.strip())
                return 0
            if kind == 'prompt':
                self.turn(value, 'terminal')
            elif kind == 'changed':
                lines = []
                for code, _, err in self.run_hooks('FileChanged', {'hook_event_name': 'FileChanged', 'session_id': self.session, 'file_path': value}):
                    if code == 2:  # the wake hook: its stderr is what Claude reads next
                        lines += [row for row in err.splitlines() if row.strip()]
                if lines:
                    self.turn('\n'.join(lines), 'wake')


if __name__ == '__main__':
    raise SystemExit(Agent(sys.argv[1:]).main())
