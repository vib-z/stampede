"""fleet-job: a Herdr job's messages, background owner questions, plan approval and per-CLI hooks.
Ported from stampede (scripts/stampede_hooks.py at 0871ae3) and cut down."""
import fcntl, glob, hashlib, json, os, re, shlex, signal, subprocess, sys, uuid
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')
OWNER = re.compile(r'[a-z0-9][a-z0-9_-]{0,40}')  # a bot slug, as herdr-events-owner takes it
SHA = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?')
GATE = re.compile(r'[0-9a-f]{12}')
ASK_CMD = os.environ.get('FLEET_ASK_CMD', 'moshi-hook ask --require-remote --source herdr-fleet --timeout 24h')
BRIEF_SECTIONS = ('Goal', 'Why', 'Inputs', 'Constraints', 'Done when', 'Report back', 'If blocked')


def missing_sections(text):
    """Required brief headings whose section has no non-blank line, or is absent."""
    parts = re.split(r'(?m)^ {0,3}#{1,6}[ \t]+([^\n]*)\n?', text)
    filled = [parts[i].strip().lower() for i in range(1, len(parts), 2) if parts[i + 1].strip()]
    return [name for name in BRIEF_SECTIONS if not any(heading.startswith(name.lower()) for heading in filled)]


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


def ask_now(job, question, options, command=None, gate=None):
    """Ask the owner and wait; the answer, or why it failed, goes to the lead's inbox.
    A gate always asks FLEET_ASK_CMD itself, with the question made from its own record, and its yes (exit 0, a yes or
    nothing on stdout) is recorded for gate-ok, only while the record is still the one asked about."""
    asked = load_gate(job, gate) if gate else None
    if asked:
        if asked['route'] != 'local':
            raise PermissionError(f'gate {gate} goes to {asked["route"]}, not to the phone')
        question, options = gate_question(asked), []
    argv = shlex.split(ASK_CMD if gate else command or ASK_CMD)
    for option in options:
        argv += ['--option', option]
    yes = False
    try:
        result = subprocess.run([*argv, '--', question], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        yes = result.returncode == 0 and result.stdout.strip().lower() in ('', 'yes')
        if result.returncode == 0 and result.stdout.strip():
            status, answer = 'ANSWER', line(result.stdout)
        elif result.returncode == 1:
            status, answer = 'ANSWER', 'no (denied or cancelled)'
        else:
            status, answer = 'ASK FAILED', 'exit ' + str(result.returncode) + ': ' + line(result.stderr or result.stdout)
    except OSError as error:
        status, answer = 'ASK FAILED', 'exit 127: ' + line(error)
    if gate and yes:
        try:
            record_yes(job, gate, asked['sha'], 'owner, through ' + Path(argv[0]).name, asked)
            return 0
        except PermissionError as error:
            status, answer = 'GATE NOT RECORDED', line(error)
    tell(job, 'lead', status + ' ' + line(question) + ': ' + answer)
    return 0 if status == 'ANSWER' else 1


def ask_background(job, question, options, command=None, gate=None):
    """Detach the question in its own process group, so cancel stops it and its child card together."""
    job = Path(job).absolute()
    folder = job / 'asks'
    folder.mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex[:12]
    argv = [sys.executable, '-I', str(SCRIPTS / 'fleet_job.py'), '_ask', str(job), '--command', command or ASK_CMD,
            *(['--gate', gate] if gate else []), *['--option=' + option for option in options], '--', question]
    with (folder / (ident + '.log')).open('a') as output:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    (folder / (ident + '.pid')).write_text(str(process.pid) + '\n')
    (folder / (ident + '.txt')).write_text(line(question) + '\n')
    print('ASKED ' + ident + ' (the answer goes to the lead inbox; cancel with: fleet-job cancel ' + str(job) + ' ' + ident + ')')
    return ident


def cancel(job, ident):
    """Stop an answered or unwanted question: its waiter and its card, as one process group."""
    if not GATE.fullmatch(ident) or not (Path(job) / 'asks' / (ident + '.pid')).is_file():
        raise ValueError('no phone card ' + line(ident) + ' waiting in this job (a question sent to a bot is answered in its chat)')
    pid = int((Path(job) / 'asks' / (ident + '.pid')).read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    (Path(job) / 'asks' / (ident + '.pid')).unlink()
    print('CANCELLED ' + ident)


def job_owner(job):
    """The bot that started the job (fleet-job new wrote it), or '' for a job started locally."""
    path = Path(job) / 'owner'
    owner = path.read_text().strip() if path.is_file() else ''
    if owner and not OWNER.fullmatch(owner):
        raise ValueError('the owner file of this job holds no bot slug: ' + line(owner))
    return owner


def starter(workspace):
    """At fleet-job new: HERDR_EVENTS_OWNER, else the workspace's owner tag (herdr-events-owner); '' when local.
    A slug that is set but malformed is refused: it must never turn a bot's job into a local one."""
    owner, source = os.environ.get('HERDR_EVENTS_OWNER', '').strip(), 'HERDR_EVENTS_OWNER'
    tag = Path.home() / '.config/herdr-events/owners' / str(workspace)
    if not owner and workspace and tag.is_file():
        owner = next((row[len('owner='):].strip() for row in tag.read_text().splitlines() if row.startswith('owner=')), '')
        source = 'the owner tag of ' + str(workspace)
    if owner and not OWNER.fullmatch(owner):
        raise ValueError(f'{source} holds no bot slug ({line(owner)}): fix it with herdr-events-owner, then start again')
    return owner


def post_event(job, owner, fields):
    """One event to the bot that started the job, queued by the relay in strict mode: only the bot's own route with a
    URL (never the default route, perhaps another bot's), or a refusal. No `pane`: the flusher keeps only a pane's
    newest event after an outage, and a question or a gate must never be dropped for a later turn end."""
    event = {'source': 'stampede', 'owner': owner, 'job': str(Path(job).absolute()), 'agent': roster(job)[1], **fields}
    for key, name in (('workspace', 'HERDR_WORKSPACE_ID'), ('lead_pane', 'HERDR_PANE_ID')):
        if os.environ.get(name):
            event[key] = os.environ[name]
    result = subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'), '--strict', json.dumps(event)],
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'the relay did not queue this for {owner} ({line(result.stderr) or "exit " + str(result.returncode)}), '
                         'so the bot would never hear it: fix its route (herdr-doctor --relay), or ask the owner in your own pane')


def ask(job, question, options):
    """A question for the owner: to the bot that started the job, as a question event it answers with tell;
    else FLEET_ASK_CMD in the background."""
    owner = job_owner(job)
    if not owner:
        return ask_background(job, question, options)
    ident = uuid.uuid4().hex[:12]
    post_event(job, owner, {'state': 'question', 'ask': ident, 'question': line(question), 'options': options,
                            'answer': shlex.join(['fleet-job', 'tell', str(Path(job).absolute()), 'lead',
                                                  f"ANSWER {ident} {line(question)}: <the owner's words>"])})
    print(f'ASKED {ident} sent to {owner}, which asks the owner in chat; the answer comes to your inbox')
    return ident


def ask_gate(job, action, sha, pr=None):
    """A gate is one exact action at one commit, answered yes or no. A bot-started job sends it to that bot as a gate
    event, and the bot records the owner's yes with approve-gate; a local job asks FLEET_ASK_CMD in the background."""
    job = Path(job).absolute()
    if not SHA.fullmatch(sha):
        raise ValueError('--sha takes the full commit id the gate is about (git rev-parse HEAD)')
    owner = job_owner(job)
    ident = uuid.uuid4().hex[:12]
    gate = {'gate': ident, 'action': line(action), 'pr': pr, 'sha': sha, 'route': owner or 'local',
            'asked': datetime.now().strftime('%Y-%m-%d %H:%M')}
    (job / 'gates').mkdir(exist_ok=True)
    (job / 'gates' / (ident + '.json')).write_text(json.dumps(gate) + '\n')
    check = f'fleet-job gate-ok {job} {ident} --sha <the commit you act on>'
    if not owner:
        ask_background(job, gate_question(gate), [], gate=ident)
        return print(f'GATE {ident} on the phone; act after {check} prints APPROVED, or on the owner\'s yes typed in your pane')
    try:
        post_event(job, owner, {'state': 'gate', **gate, 'options': ['yes', 'no'],
                                'approve': shlex.join(['fleet-job', 'approve-gate', str(job), ident, '--sha', sha, '--by', 'owner in ' + owner + ' chat']),
                                'deny': shlex.join(['fleet-job', 'tell', str(job), 'lead', f"GATE {ident} NO: <the owner's words>"])})
    except ValueError:
        (job / 'gates' / (ident + '.json')).unlink()  # a gate its bot never hears is no gate
        raise
    print(f'GATE {ident} queued for {owner}, which asks the owner in chat; act after {check} prints APPROVED, '
          'or on the owner\'s yes typed in your pane')


def gate_question(gate):
    return f'Gate {gate["gate"]}: {gate["action"]}' + (f' (PR #{gate["pr"]})' if gate['pr'] else '') + f' at {gate["sha"][:12]}?'


def load_gate(job, ident):
    path = Path(job) / 'gates' / (str(ident) + '.json')
    if not GATE.fullmatch(str(ident)) or not path.is_file():
        raise ValueError('no gate ' + line(ident) + ' in this job')
    return json.loads(path.read_text())


def record_yes(job, ident, sha, by, asked=None):
    """The owner's yes for one gate at one commit, then wake the lead. asked: the gate as it was when asked."""
    gate = load_gate(job, ident)
    if asked is not None and gate != asked:
        raise PermissionError(f'gate {ident} changed while the owner was asked: ask again')
    if sha != gate['sha']:
        raise PermissionError(f'gate {ident} asked about {gate["sha"]}, not {sha}: a stale yes; ask again')
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    (Path(job) / 'gates' / (ident + '.approved')).write_text(json.dumps({'gate': ident, 'sha': sha, 'by': line(by), 'at': when}) + '\n')
    tell(job, 'lead', f'GATE {ident} APPROVED by {line(by)} at {when}: {gate["action"]} at {sha}. '
                      f'Run fleet-job gate-ok {Path(job).absolute()} {ident} --sha <the commit you act on>, then act.')


def inside_herdr(env=None, pid=None):
    """True for a command run in a Herdr pane, or anywhere under the Herdr server: an agent's own command.
    ponytail: same Unix user, so a determined agent could still write the record or reach this over ssh; the boundary
    is auto mode plus this refusal. Upgrade: an approval signed on the bot's own computer."""
    env = os.environ if env is None else env
    if env.get('HERDR_ENV') or env.get('HERDR_PANE_ID'):
        return True
    ps = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True)
    if ps.returncode:
        return True  # cannot tell: refuse
    tree = {}
    for row in ps.stdout.splitlines():
        cells = row.split(None, 2)
        if len(cells) == 3 and cells[0].isdigit() and cells[1].isdigit():
            tree[int(cells[0])] = (int(cells[1]), os.path.basename(cells[2].strip()))
    pid, seen = os.getpid() if pid is None else pid, set()
    while pid > 1 and pid in tree and pid not in seen:
        seen.add(pid)
        if tree[pid][1] == 'herdr':
            return True
        pid = tree[pid][0]
    return False


def approve_gate(job, ident, sha, by):
    """The starting bot's command, run outside Herdr: the owner said yes in its chat to this gate at this commit."""
    if inside_herdr():
        raise PermissionError('approve-gate runs only outside Herdr, from the bot that started the job: an agent\'s own '
                              'say-so never counts. The owner answers the bot in chat, or types yes in the lead\'s pane')
    if load_gate(job, ident)['route'] == 'local':
        raise PermissionError(f'gate {ident} belongs to a job started locally: the owner answers on the phone or in Herdr')
    if not line(by):
        raise ValueError('--by says who said yes and where, e.g. "owner in Grok Bot chat"')
    record_yes(job, ident, sha, by)
    print(f'APPROVED {ident} at {sha}')


def gate_ok(job, ident, sha):
    """The lead's check before it acts: the owner's recorded yes for this gate, at this very commit."""
    gate = load_gate(job, ident)
    path = Path(job) / 'gates' / (ident + '.approved')
    if not path.is_file():
        raise PermissionError(f'gate {ident} has no recorded yes: wait for it, or the owner\'s yes typed in your pane')
    record = json.loads(path.read_text())
    if record.get('gate') != ident:
        raise PermissionError(f'the yes recorded under gate {ident} is for gate {record.get("gate")}: ask again')
    if not record.get('sha') == gate['sha'] == sha:
        raise PermissionError(f'gate {ident} was approved for {record.get("sha")}, not {sha}: a push after the yes '
                              'withdraws it; ask again')
    print(f'APPROVED {ident} by {record["by"]} at {record["at"]}: {gate["action"]} at {sha}')


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
    if not lead:
        if not Path(brief).is_file():
            raise ValueError(f'brief {brief} does not exist')
        missing = missing_sections(Path(brief).read_text())
        if missing:
            raise ValueError(f'brief {brief} is missing: {", ".join(missing)}; '
                             'fill them in on skills/herdr-fleet/references/brief.md and start again')
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
    owner = starter(info.get('workspace_id', pane.split(':')[0]) if info else workspace)
    job = repo / ('.herdr-' + (name or slug(ask)))
    job.mkdir(parents=True, exist_ok=False)
    probe = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-path', 'info/exclude'], capture_output=True, text=True)
    if probe.returncode == 0:
        exclude = repo / probe.stdout.strip()  # an absolute path stays absolute
        if not exclude.exists() or '/.herdr-*/' not in exclude.read_text().splitlines():
            append(exclude, '/.herdr-*/')
    (job / 'ask.md').write_text(ask)
    if owner:
        (job / 'owner').write_text(owner + '\n')
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
    ask_gate_cmd = f'fleet-job ask {job} --gate --sha <commit> [--pr <n>] "<the exact action>"'
    gate_ok_cmd = f'fleet-job gate-ok {job} <gate> --sha <the commit you act on>'
    gate_route = (f'ask it with {ask_gate_cmd}; it goes back to {owner}, which asks the owner in chat. ' if owner else
                  f'ask it with your own question card, or with {ask_gate_cmd} (a phone card). ')
    gate_route += (f'Act only on the owner\'s yes typed in your pane{"" if owner else " or card"}, or after {gate_ok_cmd} '
                   'prints APPROVED; a merge uses --match-head-commit <that commit>. An agent\'s word or a relayed yes never counts.')
    brief.write_text(
        f'You are {lead}, the lead of the job in {job}. Read {job / "ask.md"} and run it with the herdr-fleet skill. '
        f'Plan in {job / "plan.md"}: the layout (workspace, tabs, panes with app and model), then the tasks with the pane that does each, then any questions with a default. {gate} '
        f'Ask the owner with: fleet-job ask {job} "<question>" --option <a> --option <b>; keep working while it waits. '
        f'Answer a worker with: fleet-job tell {job} <agent> "<text>". Start a worker with: fleet-job start. '
        f'A merge or another gate (the herdr-fleet list): {gate_route} '
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
    p.add_argument('--gate', action='store_true', help='a gate: one exact action at one commit, yes or no')
    p.add_argument('--sha', help='with --gate: the full commit id it is about'); p.add_argument('--pr', type=int, help='with --gate: the PR number')
    p = sub.add_parser('approve-gate'); p.add_argument('job'); p.add_argument('gate'); p.add_argument('--sha', required=True)
    p.add_argument('--by', required=True)
    p = sub.add_parser('gate-ok'); p.add_argument('job'); p.add_argument('gate'); p.add_argument('--sha', required=True)
    p = sub.add_parser('cancel'); p.add_argument('job'); p.add_argument('ident')
    p = sub.add_parser('approve'); p.add_argument('job'); p.add_argument('--by', required=True)
    p = sub.add_parser('hook'); p.add_argument('action'); p.add_argument('job'); p.add_argument('--agent', required=True)
    p.add_argument('payload', nargs='?', help="Codex's notify JSON, passed as the last argument; other hooks read stdin")
    p = sub.add_parser('_ask'); p.add_argument('job'); p.add_argument('--command'); p.add_argument('--option', action='append', default=[])
    p.add_argument('--gate')
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
    if a.cmd == 'ask' and a.gate:
        if a.option or not a.sha:
            raise ValueError('a gate takes --sha and no --option: one exact action, yes or no; ask each choice as its own gate')
        return ask_gate(a.job, ' '.join(a.question), a.sha, a.pr)
    if a.cmd == 'ask':
        return ask(a.job, ' '.join(a.question), a.option) and 0
    if a.cmd == 'approve-gate':
        return approve_gate(a.job, a.gate, a.sha, a.by)
    if a.cmd == 'gate-ok':
        return gate_ok(a.job, a.gate, a.sha)
    if a.cmd == 'cancel':
        return cancel(a.job, a.ident)
    if a.cmd == 'approve':
        return approve(a.job, a.by)
    if a.cmd == '_ask':
        return ask_now(a.job, ' '.join(a.question), a.option, a.command, a.gate)
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
