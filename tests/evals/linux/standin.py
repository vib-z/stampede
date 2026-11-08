#!/usr/bin/env python3
"""standin.py: a stand-in agent CLI for the live evals, installed as `claude` and `codex` in a scratch ~/.local/bin.

It is what Herdr and stampede see of an agent, and nothing more: a process named like the agent, the agent's own
prompt screen (Herdr's detection manifests read it: Claude's prompt box and `? for shortcuts`, Codex's `›` prompt
with its placeholder), a working line and a spinner in the terminal title while it acts, the OSC 7501 status Herdr
Core reads, and the agent's hook contract. A Claude stand-in runs the hooks of its --settings file as Claude does:
SessionStart at start (its watchPaths answer is what it then watches), FileChanged on a watched file with exit 2
taken as a wake, Stop after each turn and SessionEnd at exit, each with Claude's JSON on stdin. A Codex stand-in runs
the notify command from -c notify=[...] after each turn with Codex's JSON as the last argument, and writes the
rollout file Codex would. Every stand-in reads the brief its first prompt names and does what that brief's
`stand-in:` lines say (tell <agent> <text>, report <path> [text], write <path> <text>, sleep <s>, log <text>); a
worker echoes every later prompt to the lead with `stampede tell`. No model, no sign-in, nothing spent.

Environment: STANDIN_SKIN overrides the skin taken from argv[0]; STANDIN_WORK_SECONDS (default 2) is how long a turn
takes; STANDIN_LOG_DIR is where a stand-in with no job logs (default ~/.local/state/standin)."""
import json, os, re, select, shlex, signal, subprocess, sys, termios, threading, time, tty, uuid
from datetime import datetime
from pathlib import Path

VERSIONS = {'claude': '2.1.300 (Claude Code)', 'codex': 'codex-cli 0.100.0'}
TITLES = {'claude': ('✳ claude', '⠋ claude'), 'codex': ('codex', '⠋ codex')}  # (idle, working) terminal titles
SPINNERS = {'claude': '⠻⠹⠸⠼⠴⠦⠧⠇⠏⠋', 'codex': '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'}
WORK = float(os.environ.get('STANDIN_WORK_SECONDS', '2'))
POLL = 0.4
POINTER = re.compile(r'Read (\S+\.md)')


class Agent:
    def __init__(self, skin, argv):
        self.skin, self.argv = skin, argv
        self.name, self.job, self.settings, self.model, self.effort = '', None, {}, '', ''
        self.session, self.first_prompt, self.notify, self.resumed = uuid.uuid4().hex, None, None, False
        self.transcript, self.draft, self.working, self.turns, self.watched, self.done_briefs = [], '', '', 0, {}, set()
        self.parse()
        self.cwd = os.getcwd()
        self.log_path = (self.job / 'standin' / (self.name + '.log')) if self.job and self.name else \
            Path(os.environ.get('STANDIN_LOG_DIR') or Path.home() / '.local/state/standin') / f'{skin}-{os.getpid()}.log'
        self.tty = os.isatty(0)
        self.saved = termios.tcgetattr(0) if self.tty else None

    def parse(self):
        a, i, add_dirs = self.argv, 0, []
        while i < len(a):
            x, nxt = a[i], a[i + 1] if i + 1 < len(a) else ''
            if x == '--add-dir':
                add_dirs.append(nxt); i += 2
            elif x == '-n' and self.skin == 'claude':
                self.name = nxt; i += 2
            elif x == '--settings':
                self.settings = json.loads(Path(nxt).read_text()); i += 2
            elif x in ('--model', '-m'):
                self.model = nxt; i += 2
            elif x == '--effort':
                self.effort = nxt; i += 2
            elif x in ('--session-id', '--resume'):
                self.session, self.resumed = nxt, x == '--resume'; i += 2
            elif x == 'resume' and self.skin == 'codex':
                self.session, self.resumed = nxt, True; i += 2
            elif x == '-c':
                key, _, value = nxt.partition('=')
                if key == 'notify':
                    self.notify = json.loads(value)
                    if '--agent' in self.notify:  # stampede's notify hook names the agent: fleet-job hook --agent <name> codex-notify <job>
                        self.name = self.notify[self.notify.index('--agent') + 1]
                elif key == 'model_reasoning_effort':
                    self.effort = value.strip('"')
                i += 2
            elif x in ('--permission-mode',):
                i += 2
            elif x.startswith('-'):
                i += 1
            else:
                self.first_prompt = x; i += 1
        for folder in add_dirs:  # fleet-job passes the job folder first; it is the one holding the lead's name
            if (Path(folder) / 'lead').is_file():
                self.job = Path(folder).resolve()
                break
        if self.job and not self.name and self.first_prompt:
            found = re.match(r'You are (\S+)', self.first_prompt)
            self.name = found.group(1).rstrip('.,') if found else ''

    # the job
    @property
    def lead(self):
        return bool(self.job) and (self.job / 'lead').read_text().strip() == self.name

    def log(self, text):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a') as out:
            out.write(f'{datetime.now():%H:%M:%S} {text}\n')

    # the screen
    def say(self, text):
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', str(text))[:200]
        self.transcript = (self.transcript + [text])[-12:]

    def out(self, text):
        os.write(1, text.encode())

    def draw(self):
        cols, rows = (os.get_terminal_size(1) if self.tty else (80, 24))
        idle_title, busy_title = TITLES[self.skin]
        title = busy_title if self.working else idle_title
        if self.working:
            glyph = SPINNERS[self.skin][int(time.monotonic() * 8) % 10]
            title = glyph + ' ' + (self.working if self.skin == 'codex' else 'claude')
        lines = list(self.transcript) + ['']
        seconds = int(time.monotonic() - self.started) if self.working else 0
        if self.skin == 'claude':
            if self.working:
                lines += [f'✻ {self.working}… ({seconds}s · esc to interrupt)', '']
            rule = '─' * max(10, cols - 2)
            lines += [rule, '❯ ' + self.draft, rule, '  ? for shortcuts']
        else:
            if self.working:
                lines += [f'• {self.working} ({seconds}s • esc to interrupt)', '']
            lines += ['› ' + (self.draft or 'Ask Codex to do anything'), '  ? for shortcuts']
        lines = lines[-(rows - 1):] if rows > 2 else lines
        state = 'working' if self.working else 'idle'
        self.out('\x1b]0;' + title + '\x07' + f'\x1b]7501;state={state}:app={self.skin}\x1b\\' + '\x1b[2J\x1b[H'
                 + '\r\n'.join(line[:cols] for line in lines))

    # hooks
    def hooks(self, event):
        out = []
        for row in self.settings.get('hooks', {}).get(event, []):
            out += [h['command'] for h in row.get('hooks', []) if h.get('type') == 'command']
        return out

    def hook(self, event, extra=None, command=None):
        """Run one event's hook commands (or one command) as Claude does: bash -c <command>, the event's JSON on stdin.
        Returns [(command, exit code, stdout, stderr)]."""
        payload = {'session_id': self.session, 'transcript_path': str(Path.home() / '.claude/projects/standin' / (self.session + '.jsonl')),
                   'cwd': self.cwd, 'hook_event_name': event, **(extra or {})}
        results = []
        for cmd in ([command] if command else self.hooks(event)):
            try:
                done = subprocess.run(['bash', '-c', cmd], input=json.dumps(payload), capture_output=True, text=True, timeout=120)
                results.append((cmd, done.returncode, done.stdout, done.stderr))
            except (OSError, subprocess.SubprocessError) as error:
                results.append((cmd, -1, '', str(error)))
            self.log(f'hook {event} -> exit {results[-1][1]} {results[-1][2].strip()[:200]} {results[-1][3].strip()[:2000]}')
        return results

    def session_start(self):
        for _, code, stdout, _ in self.hook('SessionStart', {'source': 'resume' if self.resumed else 'startup'}):
            try:
                paths = json.loads(stdout).get('hookSpecificOutput', {}).get('watchPaths', [])
            except ValueError:
                paths = []
            for path in paths:
                self.watched[path] = self.stamp(path)

    @staticmethod
    def stamp(path):
        try:
            st = os.stat(path)
            return st.st_size, st.st_mtime_ns
        except OSError:
            return None

    def changed_files(self):
        for path, old in list(self.watched.items()):
            now = self.stamp(path)
            if now != old:
                self.watched[path] = now
                yield path

    # a turn
    def turn(self, text, source):
        self.turns += 1
        self.log(f'prompt ({source}): {text[:4000]}')
        self.say('> ' + text)
        self.working, self.started = ('Working' if self.skin == 'codex' else 'Thinking'), time.monotonic()
        self.draw()
        did = self.act(text, source)
        while time.monotonic() - self.started < WORK:
            time.sleep(0.5)
            self.draw()
        self.working = ''
        if self.skin == 'claude':
            blocked = [r for r in self.hook('Stop', {'stop_hook_active': False, 'last_assistant_message': did})
                       if '"block"' in r[2]]
            if blocked:
                self.say('⏺ stop hook: ' + re.sub(r'\s+', ' ', blocked[0][2])[:160])
                self.hook('Stop', {'stop_hook_active': True, 'last_assistant_message': did})
        elif self.notify:
            payload = {'type': 'agent-turn-complete', 'thread-id': self.session, 'turn-id': f'turn-{self.turns}', 'cwd': self.cwd,
                       'input-messages': [text], 'last-assistant-message': did}
            try:
                done = subprocess.run([*self.notify, json.dumps(payload)], capture_output=True, text=True, timeout=120)
                self.log(f'notify -> exit {done.returncode} {done.stderr.strip()[:200]}')
            except (OSError, subprocess.SubprocessError) as error:
                self.log(f'notify failed: {error}')
        self.draw()

    def act(self, text, source):
        """Do what the prompt asks: read a brief it names and follow its stand-in lines; echo anything else to the lead."""
        done = []
        brief = POINTER.search(text)
        if brief and Path(brief.group(1)).is_file():
            path = Path(brief.group(1))
            if not self.name:
                self.name = re.sub(r'\.md$', '', path.name)
            self.say(f'⏺ Read {path}')
            if str(path) not in self.done_briefs:
                self.done_briefs.add(str(path))
                for line in path.read_text().splitlines():
                    if line.strip().startswith('stand-in:'):
                        done.append(self.directive(line.split(':', 1)[1].strip()))
        elif self.job and not self.lead and self.name and source != 'argv':
            self.run(['stampede', 'tell', str(self.job), 'lead', f'ECHO {self.name}: {text[:300]}'])
            done.append('echoed to the lead')
        else:
            done.append('noted')
        summary = '; '.join(done) or 'noted'
        self.log('did: ' + summary)
        return summary

    def directive(self, line):
        verb, _, rest = line.partition(' ')
        if verb == 'tell':
            agent, _, text = rest.partition(' ')
            self.run(['stampede', 'tell', str(self.job), agent, text])
            return f'told {agent}'
        if verb in ('report', 'write'):
            path, _, text = rest.partition(' ')
            path = Path(path) if path.startswith('/') else ((self.job or Path.cwd()) if verb == 'report' else Path.cwd()) / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(('Status: DONE\n\n' if verb == 'report' else '') + (text or f'{self.name} did its lane.') + '\n')
            return f'wrote {path}'
        if verb == 'sleep':
            time.sleep(float(rest or 1))
            return f'slept {rest}'
        if verb == 'log':
            self.say('⏺ ' + rest)
            return 'logged'
        return f'unknown directive {verb}'

    def run(self, argv):
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            self.log(f'ran {shlex.join(argv)[:200]} -> exit {done.returncode} {(done.stdout + done.stderr).strip()[:200]}')
            self.say('⏺ ' + shlex.join(argv[:3]) + f' (exit {done.returncode})')
        except (OSError, subprocess.SubprocessError) as error:
            self.log(f'ran {shlex.join(argv)[:200]} -> {error}')

    # input
    def reader(self, lines):
        buf = b''
        while True:
            try:
                chunk = os.read(0, 4096)
            except OSError:
                chunk = b''
            if not chunk:
                lines.append(None)
                return
            buf += chunk
            while True:
                text = buf.decode('utf-8', 'replace')
                text = re.sub(r'\x1b\[20[01]~', '', text)  # bracketed paste marks
                if '\x03' in text:  # ctrl+c clears a draft, as Claude does
                    text = text.split('\x03')[-1]
                    self.draft = ''
                if '\x04' in text and not text.strip('\x04'):
                    lines.append(None)
                    return
                cut = re.search(r'[\r\n]', text)
                if not cut:
                    self.draft = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|[\x00-\x1f\x7f]', '', text)
                    buf = text.encode()
                    break
                line, rest = text[:cut.start()], text[cut.end():]
                line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|[\x00-\x1f\x7f]', '', line).strip()
                self.draft, buf = '', rest.encode()
                if line:
                    lines.append(line)

    def main(self):
        if self.tty:
            tty.setraw(0)
        try:
            self.log(f'start skin={self.skin} name={self.name} job={self.job} session={self.session} pane={os.environ.get("HERDR_PANE_ID")} argv={shlex.join(self.argv)}')
            if self.skin == 'codex':
                self.rollout()
            if self.skin == 'claude':
                self.session_start()
            self.draw()
            lines = []
            threading.Thread(target=self.reader, args=(lines,), daemon=True).start()
            if self.first_prompt:
                self.turn(self.first_prompt, 'argv')
            last_draw = time.monotonic()
            while True:
                if lines:
                    line = lines.pop(0)
                    if line is None or line in ('/exit', '/quit'):
                        self.log('exit on ' + ('EOF' if line is None else line))
                        return 0
                    self.turn(line, 'typed')
                    continue
                for path in self.changed_files():
                    woke = [r for r in self.hook('FileChanged', {'file_path': path}) if r[1] == 2 and r[3].strip()]
                    for _, _, _, stderr in woke:
                        self.turn(stderr.strip(), 'wake ' + Path(path).name)
                if time.monotonic() - last_draw > 0.3:
                    self.draw()
                    last_draw = time.monotonic()
                time.sleep(POLL)
        finally:
            if self.skin == 'claude':
                self.hook('SessionEnd', {'reason': 'exit'})
            if self.tty:
                termios.tcsetattr(0, termios.TCSADRAIN, self.saved)
            self.out('\x1b]0;\x07\x1b]7501;state=done:app=' + self.skin + '\x1b\\\r\n')

    def rollout(self):
        """The session file Codex writes, which stampede's notify hook reads to tell the agent's own turns apart."""
        now = datetime.now()
        folder = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'sessions' / f'{now:%Y}' / f'{now:%m}' / f'{now:%d}'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'rollout-{now:%Y-%m-%dT%H-%M-%S}-{self.session}.jsonl'
        if not path.exists():
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': self.session, 'source': 'cli'}}) + '\n')


def main(argv):
    skin = os.environ.get('STANDIN_SKIN') or Path(sys.argv[0]).name
    if skin not in VERSIONS:
        skin = 'claude'
    if argv[:1] in (['--version'], ['-V']):
        return print(VERSIONS[skin])
    if argv[:1] in (['--help'], ['-h']):
        print(f'{skin} stand-in for the stampede evals (tests/evals/linux/standin.py)\n\nOptions:\n  --version\n'
              + ('  --no-daemon    run without the app server\n' if skin == 'codex' else '  --permission-mode <mode>\n'))
        return 0
    agent = Agent(skin, argv)
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    return agent.main()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)
