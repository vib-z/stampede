"""fleet-job: a Herdr job's messages, background owner questions, plan approval and per-CLI hooks.
Ported from stampede (scripts/stampede_hooks.py at 0871ae3) and cut down."""
import fcntl, glob, hashlib, json, os, re, shlex, signal, subprocess, sys, uuid
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')
ASK_CMD = os.environ.get('FLEET_ASK_CMD', 'moshi-hook ask --require-remote --source herdr-fleet --timeout 24h')


def line(value):
    return ' '.join(str(value).split())


def append(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(text.rstrip('\n') + '\n')


def roster(job):
    """name -> kind from agents.tsv, and the lead's name from the `lead` file."""
    job = Path(job)
    people = {}
    tsv = job / 'agents.tsv'
    if tsv.is_file():
        for row in tsv.read_text().splitlines():
            if row and not row.startswith('#'):
                name, kind = row.split('\t')[:2]
                people[name] = kind
    lead = (job / 'lead').read_text().strip() if (job / 'lead').is_file() else ''
    return people, lead


def tell(job, name, text):
    people, lead = roster(job)
    name = lead if name == 'lead' else name
    if not NAME.fullmatch(name or '') or name not in people:
        raise ValueError('agent is not in this job: ' + str(name))
    if people[name] == 'claude':
        append(Path(job) / 'inbox' / (name + '.md'), line(text))
        return print('DELIVERED ' + name + ' (inbox file)')
    if subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-send'), name, text],
                      env={**os.environ, 'FLEET_JOB_DIR': str(Path(job).absolute())}).returncode:
        raise SystemExit(2)  # herdr-send printed its one FAILED line (focused, blocked or gone); never a traceback


def ask_now(job, question, options, command=None):
    """Ask the owner and wait; the answer, or why it failed, goes to the lead's inbox."""
    argv = shlex.split(command or ASK_CMD)
    for option in options:
        argv += ['--option', option]
    try:
        result = subprocess.run([*argv, '--', question], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            status, answer = 'ANSWER', line(result.stdout)
        elif result.returncode == 1:
            status, answer = 'ANSWER', 'no (denied or cancelled)'
        else:
            status, answer = 'ASK FAILED', 'exit ' + str(result.returncode) + ': ' + line(result.stderr or result.stdout)
    except OSError as error:
        status, answer = 'ASK FAILED', 'exit 127: ' + line(error)
    tell(job, 'lead', status + ' ' + line(question) + ': ' + answer)
    return 0 if status == 'ANSWER' else 1


def ask_background(job, question, options, command=None):
    """Detach the question in its own process group, so cancel stops it and its child card together."""
    job = Path(job).absolute()
    folder = job / 'asks'
    folder.mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex[:12]
    argv = [sys.executable, '-I', str(SCRIPTS / 'fleet_job.py'), '_ask', str(job), '--command', command or ASK_CMD,
            *['--option=' + option for option in options], '--', question]
    with (folder / (ident + '.log')).open('a') as output:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    (folder / (ident + '.pid')).write_text(str(process.pid) + '\n')
    (folder / (ident + '.txt')).write_text(line(question) + '\n')
    print('ASKED ' + ident + ' (the answer goes to the lead inbox; cancel with: fleet-job cancel ' + str(job) + ' ' + ident + ')')
    return ident


def cancel(job, ident):
    """Stop an answered or unwanted question: its waiter and its card, as one process group."""
    pid = int((Path(job) / 'asks' / (ident + '.pid')).read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    (Path(job) / 'asks' / (ident + '.pid')).unlink()
    print('CANCELLED ' + ident)


def plan_digest(job):
    """One fingerprint over the plan the owner saw: plan.md, or fleet-plan.md for a detailed plan, or both."""
    digest = hashlib.sha256()
    found = False
    for name in ('plan.md', 'fleet-plan.md'):
        path = Path(job) / name
        if path.is_file():
            digest.update(name.encode() + b'\0' + path.read_bytes())
            found = True
    return digest.hexdigest() if found else ''


def approve(job, by):
    """Record the owner's yes for this exact plan, then wake the lead."""
    digest = plan_digest(job)
    if not digest:
        raise ValueError('no plan.md or fleet-plan.md to approve')
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    (Path(job) / 'approved').write_text(f'Approved: {when} by {line(by)}, plan {digest}\n')
    tell(job, 'lead', f'Approved by {line(by)} at {when}. Start the panes the plan names.')


def require_approval(job):
    """A review job may open panes only once the owner approved the plan as it stands."""
    job = Path(job)
    if not (job / 'review').is_file():
        return
    record = (job / 'approved').read_text() if (job / 'approved').is_file() else ''
    if not record.rstrip().endswith('plan ' + plan_digest(job)):
        raise PermissionError('the owner asked to see this plan: run fleet-job approve after their yes, '
                              'and again after any change to the plan')


def report_done(path):
    path = Path(path)
    if not path.is_file():
        return False
    head = path.read_text(errors='replace').splitlines()[:10]
    return any(re.match(r'Status:\s*(DONE|PASS|FINDINGS)\b', row.strip()) for row in head)


def watched(job, agent, lead):
    job = Path(job).absolute()
    return [job / 'inbox' / (agent + '.md')] + ([job / 'inbox.log'] if lead else [])


def watch_paths(job, agent, lead):
    """The files Claude watches; creates only absent ones, since touching a watched file fires its hook again."""
    paths = watched(job, agent, lead)
    for path in paths:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    return [str(path) for path in paths]


def wake(job, agent, payload):
    """Return the complete new lines of a watched file since the last wake (exit 2 in the hook wakes Claude)."""
    job = Path(job).absolute()
    (job / 'hooks').mkdir(exist_ok=True)
    changed = Path(payload.get('file_path') or '').resolve()
    if str(changed) not in {str(p.resolve()) for p in watched(job, agent, agent == roster(job)[1])}:
        return []
    with (job / 'hooks/.wake.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = job / 'hooks' / ('wake-' + agent + '.json')
        state = json.loads(state_path.read_text()) if state_path.is_file() else {}
        content = changed.read_bytes()
        offset = state.get(str(changed), 0)
        offset = 0 if offset > len(content) else offset
        addition = content[offset:]
        complete = addition.rfind(b'\n') + 1
        state[str(changed)] = offset + complete
        state_path.write_text(json.dumps(state) + '\n')
    return [line(row.decode('utf-8', 'replace')) for row in addition[:complete].split(b'\n')[:-1] if row.strip()]


def claude_stop(job, agent, payload):
    """Announce each report whose content changed; send a worker with no done report back once."""
    job = Path(job)
    record = job / 'hooks' / (agent + '.json')
    reports = json.loads(record.read_text()).get('reports', []) if record.is_file() else []
    if not reports:
        append(job / 'inbox.log', 'TURN ' + agent)
        return ''
    state_path = job / 'hooks' / ('reported-' + agent + '.json')
    seen = json.loads(state_path.read_text()) if state_path.is_file() else {}
    done = [report for report in reports if report_done(job / report)]
    for report in done:
        digest = hashlib.sha256((job / report).read_bytes()).hexdigest()
        if seen.get(report) != digest:
            seen[report] = digest
            append(job / 'inbox.log', 'REPORT ' + report)
    state_path.write_text(json.dumps(seen) + '\n')
    if done:
        return ''
    if payload.get('hook_event_name') == 'Stop' and not payload.get('stop_hook_active'):
        return json.dumps({'decision': 'block', 'reason': 'Finish your lane and write ' + ' or '.join(reports)
                           + ' with Status: DONE (a review: PASS or FINDINGS) in its first 10 lines. If you need an answer, write it to '
                           + str(job / 'questions' / (agent + '.md')) + ' and end your turn.'})
    append(job / 'inbox.log', 'TURN ' + agent + ' ended without a report')
    return ''


def ask_lead(job, agent, payload):
    """A worker's question card becomes a file for the lead; the lead's own card (a merge, a gate) goes ahead."""
    if agent == roster(job)[1]:
        return '{}'
    questions = payload.get('tool_input', {}).get('questions', [])
    text = ['# Questions from ' + agent]
    for question in questions:
        text += ['', str(question.get('question', 'Owner input needed'))]
        text += ['- ' + str(o.get('label', '')) + ': ' + str(o.get('description', '')) for o in question.get('options', [])]
    append(Path(job) / 'questions' / (agent + '.md'), '\n'.join(text))
    first = line(questions[0].get('question', '')) if questions else 'needs input'
    append(Path(job) / 'inbox.log', 'QUESTION ' + agent + ': ' + first)
    return json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                       'permissionDecisionReason': 'Question saved for the lead. End your turn; the answer arrives in your inbox.'}})


def codex_notify(job, agent, payload):
    """Only the agent's own turns reach the lead: a thread whose session file is missing, or starts with a parent
    or a sub-agent source, is Codex's background work (as stampede's codex_notify at 0871ae3)."""
    if payload.get('type') != 'agent-turn-complete':
        return
    thread = payload.get('thread-id')
    if not thread or payload.get('parent_thread_id') or isinstance(payload.get('source'), dict) and payload['source'].get('subagent'):
        return
    home = os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex')
    files = glob.glob(os.path.join(home, 'sessions', '*', '*', '*', 'rollout-*' + thread + '.jsonl'))
    if not files:
        return
    with open(files[0]) as source:
        first = json.loads(source.readline()).get('payload', {})
    if first.get('parent_thread_id') or isinstance(first.get('source'), dict) and first['source'].get('subagent'):
        return
    append(Path(job) / 'inbox.log', line('TURN ' + agent + ' ' + payload.get('last-assistant-message', '')))


def session_end(job, agent, payload):
    """A worker's session ended (exit, crash, closed pane): tell the lead. Never for the lead itself."""
    if agent != roster(job)[1]:
        append(Path(job) / 'inbox.log', line('GONE ' + agent + ' ' + payload.get('reason', '')))
    return ''


def cursor_stop(job, agent, payload):
    """Every stop reaches the lead with its status: completed, error or aborted."""
    append(Path(job) / 'inbox.log', line('TURN ' + agent + ' ' + str(payload.get('status', ''))))
    return '{}'


def hook_command(job, agent, action):
    return shlex.join([str(SCRIPTS / 'fleet-job'), 'hook', '--agent', agent, action, str(Path(job).absolute())])


def linked_worktree(folder):
    """True when folder is a git worktree added with `git worktree add`, not a main checkout."""
    def git(*a):
        return subprocess.run(['git', '-C', str(folder), 'rev-parse', '--path-format=absolute', *a],
                              capture_output=True, text=True).stdout.strip()
    common, own = git('--git-common-dir'), git('--git-dir')
    return bool(common) and common != own


YOLO = {'claude': ['--dangerously-skip-permissions'], 'codex': ['--yolo'], 'cursor': ['--yolo']}
AUTO = {'claude': ['--permission-mode', 'auto'], 'codex': ['--approve-for-me'], 'cursor': ['--auto-review']}


def cli_args(job, agent, kind, model, effort, reports, lead=False, yolo_in=None):
    """Flags, model, effort and per-CLI hooks for one agent of this job.
    Auto mode by default; yolo only for a worker whose folder is its own linked worktree (the owner's call, case by case)."""
    if yolo_in is not None and (lead or not linked_worktree(yolo_in)):
        raise PermissionError('yolo is only for a worker in its own git worktree, never the lead')
    mode = YOLO[kind] if yolo_in is not None and kind in YOLO else AUTO.get(kind, [])
    job = Path(job).absolute()
    (job / 'hooks').mkdir(parents=True, exist_ok=True)
    (job / 'hooks' / (agent + '.json')).write_text(json.dumps({'kind': kind, 'reports': reports}) + '\n')
    if kind == 'claude':
        settings = job / 'hooks' / (agent + '-claude.json')
        hooks = {'SessionStart': [{'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'watch-paths')}]}],
                 'CwdChanged': [{'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'watch-paths')}]}],
                 'FileChanged': [{'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'wake'), 'asyncRewake': True}]}],
                 'PreToolUse': [{'matcher': 'AskUserQuestion', 'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'ask-lead')}]}]}
        if not lead:  # the lead watches inbox.log, so its own turn ends must not write there
            for event in ('Stop', 'StopFailure'):
                hooks[event] = [{'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'claude-stop')}]}]
            hooks['SessionEnd'] = [{'hooks': [{'type': 'command', 'command': hook_command(job, agent, 'session-end')}]}]
        settings.write_text(json.dumps({'hooks': hooks}, indent=2) + '\n')
        args = mode + ['-n', agent, '--settings', str(settings)]
        args += ['--model', model] if model else []
        return args + (['--effort', effort] if effort else [])
    if kind == 'codex':
        args = mode + ['--add-dir', str(job), '-c', 'notify=' + json.dumps(shlex.split(hook_command(job, agent, 'codex-notify')))]
        args += ['-m', model] if model else []
        return args + (['-c', f'model_reasoning_effort="{effort}"'] if effort else [])
    if kind == 'cursor':
        plugin = job / 'hooks' / (agent + '-cursor')
        (plugin / '.cursor-plugin').mkdir(parents=True, exist_ok=True)
        (plugin / 'hooks').mkdir(exist_ok=True)
        (plugin / '.cursor-plugin/plugin.json').write_text(json.dumps({'name': agent + '-hooks'}) + '\n')
        (plugin / 'hooks/hooks.json').write_text(json.dumps({'version': 1, 'hooks': {'stop': [{'command': hook_command(job, agent, 'cursor-stop')}]}}) + '\n')
        return mode + ['--trust', '--plugin-dir', str(plugin)] + (['--model', model] if model else [])
    raise ValueError('fleet-job starts claude, codex or cursor; start ' + kind + ' by hand and record it with herdr-reopen-snapshot')


class HerdrError(RuntimeError):
    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


def herdr(*args):
    result = subprocess.run([os.environ.get('HERDR', 'herdr'), *args], capture_output=True, text=True)
    data = json.loads(result.stdout or result.stderr or '{}')
    if result.returncode or data.get('error'):
        error = data.get('error')
        raise HerdrError('herdr ' + ' '.join(args[:2]) + ': ' + line(error or result.stderr),
                         error.get('code', '') if isinstance(error, dict) else '')
    return data.get('result', {})


def launch(agent, kind, pane, args):
    """Start an agent in its pane; True when it is held at a startup dialog. Herdr answers agent_not_ready
    when a dialog is up during start (the name stays usable), or reports blocked once it is up."""
    try:
        herdr('agent', 'start', agent, '--kind', kind, '--pane', pane, '--timeout', '90000', '--', *args)
    except HerdrError as error:
        if error.code != 'agent_not_ready':
            raise
        return True
    ready = herdr('agent', 'wait', agent, '--until', 'idle', '--until', 'done', '--until', 'blocked', '--timeout', '30000')
    return ready.get('agent', {}).get('agent_status') == 'blocked'


def start(job, agent, kind, pane, brief, model=None, effort=None, reports=(), yolo_in=None):
    """Start one agent in an existing pane at its shell prompt, record it, and send its brief pointer."""
    require_approval(job)
    if not NAME.fullmatch(agent):
        raise ValueError('agent names are <role>-<scope>, lowercase')
    lead = agent == roster(job)[1]  # a restarted lead keeps the lead's hooks
    if yolo_in is not None:
        if lead:
            raise PermissionError('yolo is never for the lead')
        live = herdr('pane', 'get', pane)['pane'].get('foreground_cwd')  # the shell's live folder; the stored cwd never qualifies
        if not live or Path(live).resolve() != Path(yolo_in).expanduser().resolve():
            raise PermissionError(f'pane {pane}\'s shell is in {live or "an unknown folder"}, not {yolo_in}: '
                                  'yolo only runs in a pane whose shell sits in the worker\'s own worktree')
        yolo_in = Path(live).resolve()
    args = cli_args(job, agent, kind, model, effort, list(reports), lead=lead, yolo_in=yolo_in)
    herdr('pane', 'rename', pane, agent)
    blocked = launch(agent, kind, pane, args)
    snapshot = str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot')
    subprocess.run([snapshot, 'record', str(job), agent, kind, str(brief), '--', *args], check=True)
    if blocked:
        print(f'BLOCKED {agent}: clear the startup dialog, then fleet-job tell {job} {agent} "Read {brief}"')
        return
    tell(job, agent, f'You are {agent} in a herdr fleet. Read {brief} and do everything it says.')


FILLER = {'a', 'an', 'the', 'on', 'in', 'of', 'to', 'for', 'and', 'please', 'can', 'you', 'we', 'i', 'my', 'our', 'it', 'this', 'that'}


def slug(ask):
    words = [w for w in re.findall(r'[a-z0-9]+', ask.lower().split('\n')[0]) if w not in FILLER]
    out = ''
    for word in words:
        if len(out) + bool(out) + len(word) > 24:
            break
        out += '-' * bool(out) + word
    return out or 'job'


def new(ask_file, workspace, name=None, review=False, pane=None):
    """Front door: make the job, start its lead on Claude with hooks, print the lead's name.
    pane: an existing empty pane for the lead (a fresh workspace's root pane), whose tab becomes `lead`; else a new tab."""
    if not (workspace or pane):
        raise ValueError('new needs --workspace or --pane, or run it inside Herdr')
    ask = Path(ask_file).expanduser().read_text()
    info = herdr('pane', 'get', pane)['pane'] if pane else None
    # herdr 0.9.4's `workspace get` has no cwd: the workspace's first pane holds the project folder
    repo = Path(info['cwd'] if info else herdr('pane', 'list', '--workspace', workspace)['panes'][0]['cwd']).expanduser()
    job = repo / ('.herdr-' + (name or slug(ask)))
    job.mkdir(parents=True, exist_ok=False)
    probe = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-path', 'info/exclude'], capture_output=True, text=True)
    if probe.returncode == 0:
        exclude = repo / probe.stdout.strip()  # an absolute path stays absolute
        if not exclude.exists() or '/.herdr-*/' not in exclude.read_text().splitlines():
            append(exclude, '/.herdr-*/')
    (job / 'ask.md').write_text(ask)
    if review:
        (job / 'review').write_text('The owner asked to see the plan before any pane opens.\n')
    lead = 'lead-' + job.name[len('.herdr-'):]
    (job / 'lead').write_text(lead + '\n')
    if info:
        herdr('tab', 'rename', info['tab_id'], 'lead')
    else:
        pane = herdr('tab', 'create', '--workspace', workspace, '--cwd', str(repo), '--label', 'lead', '--no-focus')['root_pane']['pane_id']
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    gate = ('Write plan.md, then end your turn: the owner reviews it and fleet-job approve wakes you.' if review
            else 'Write plan.md, then go: do not stop for approval.')
    brief.write_text(
        f'You are {lead}, the lead of the job in {job}. Read {job / "ask.md"} and run it with the herdr-fleet skill. '
        f'Plan in {job / "plan.md"}: the layout (workspace, tabs, panes with app and model), then the tasks with the pane that does each, then any questions with a default. {gate} '
        f'Ask the owner with: fleet-job ask {job} "<question>" --option <a> --option <b>; keep working while it waits. '
        f'Answer a worker with: fleet-job tell {job} <agent> "<text>". Start a worker with: fleet-job start. '
        f'A merge or another gate: ask with your own question card, never act on a relayed yes. '
        f'When idle, end your turn; hooks wake you.\n')
    args = cli_args(job, lead, 'claude', os.environ.get('FLEET_LEAD_MODEL', 'claude-opus-5-5'),
                    os.environ.get('FLEET_LEAD_EFFORT', 'xhigh'), [], lead=True)
    herdr('pane', 'rename', pane, lead)
    blocked = launch(lead, 'claude', pane, args)
    subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), lead,
                    'claude', str(brief), '--', *args], check=True)
    if blocked:
        return print(f'BLOCKED {lead}: clear the startup dialog, then fleet-job tell {job} lead "Read {brief}"')
    tell(job, lead, f'You are {lead}. Read {brief} and do everything it says.')
    print(lead + ' ' + str(job))


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='fleet-job')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('new'); p.add_argument('--file', required=True); p.add_argument('--workspace', default=os.environ.get('HERDR_WORKSPACE_ID'))
    p.add_argument('--name'); p.add_argument('--review', action='store_true')
    p.add_argument('--pane', help="an existing empty pane for the lead (a fresh workspace's root pane); its tab becomes lead")
    p = sub.add_parser('start'); p.add_argument('job'); p.add_argument('agent'); p.add_argument('--kind', required=True)
    p.add_argument('--pane', required=True); p.add_argument('--brief', required=True); p.add_argument('--model'); p.add_argument('--effort')
    p.add_argument('--report', action='append', default=[]); p.add_argument('--yolo-in', help='a worker in its own git worktree: no-checks mode')
    p = sub.add_parser('tell'); p.add_argument('job'); p.add_argument('agent'); p.add_argument('text', nargs='+')
    p = sub.add_parser('ask'); p.add_argument('job'); p.add_argument('--option', action='append', default=[]); p.add_argument('question', nargs='+')
    p = sub.add_parser('cancel'); p.add_argument('job'); p.add_argument('ident')
    p = sub.add_parser('approve'); p.add_argument('job'); p.add_argument('--by', required=True)
    p = sub.add_parser('hook'); p.add_argument('action'); p.add_argument('job'); p.add_argument('--agent', required=True)
    p.add_argument('payload', nargs='?', help="Codex's notify JSON, passed as the last argument; other hooks read stdin")
    p = sub.add_parser('_ask'); p.add_argument('job'); p.add_argument('--command'); p.add_argument('--option', action='append', default=[])
    p.add_argument('question', nargs='+')
    a = parser.parse_args(argv)
    try:
        return run(a)
    except (ValueError, PermissionError) as error:
        if a.cmd == 'hook':  # a hook's exit 2 blocks or wakes Claude; keep a hook's error a plain failure
            raise
        print('fleet-job ' + a.cmd + ': ' + line(error), file=sys.stderr)
        return 2


def run(a):
    if a.cmd == 'new':
        return new(a.file, a.workspace, a.name, a.review, a.pane)
    if a.cmd == 'start':
        return start(a.job, a.agent, a.kind, a.pane, a.brief, a.model, a.effort, a.report, a.yolo_in)
    if a.cmd == 'tell':
        return tell(a.job, a.agent, ' '.join(a.text))
    if a.cmd == 'ask':
        return ask_background(a.job, ' '.join(a.question), a.option) and 0
    if a.cmd == 'cancel':
        return cancel(a.job, a.ident)
    if a.cmd == 'approve':
        return approve(a.job, a.by)
    if a.cmd == '_ask':
        return ask_now(a.job, ' '.join(a.question), a.option, a.command)
    raw = a.payload if a.payload is not None else sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    lead = a.agent == roster(a.job)[1]
    if a.action == 'watch-paths':
        event = 'CwdChanged' if payload.get('hook_event_name') == 'CwdChanged' else 'SessionStart'
        print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'watchPaths': watch_paths(a.job, a.agent, lead)}}))
        return 0
    if a.action == 'wake':
        lines = wake(a.job, a.agent, payload)
        if lines:
            print('\n'.join(lines), file=sys.stderr)
            return 2
        return 0
    out = {'ask-lead': lambda: ask_lead(a.job, a.agent, payload), 'claude-stop': lambda: claude_stop(a.job, a.agent, payload),
           'codex-notify': lambda: codex_notify(a.job, a.agent, payload) or '', 'cursor-stop': lambda: cursor_stop(a.job, a.agent, payload),
           'session-end': lambda: session_end(a.job, a.agent, payload)}[a.action]()
    if out:
        print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]) or 0)
