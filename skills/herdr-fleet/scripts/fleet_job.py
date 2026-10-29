"""fleet-job: a Herdr job's messages, background owner questions, plan approval and per-CLI hooks.
Ported from stampede (scripts/stampede_hooks.py at 0871ae3) and cut down."""
import contextlib, fcntl, glob, hashlib, json, os, re, shlex, shutil, signal, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')
OWNER = re.compile(r'[a-z0-9][a-z0-9_-]{0,40}')  # a bot slug, as herdr-events-owner takes it
SHA = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?')
GATE = re.compile(r'[0-9a-f]{12}')
WS_ID = re.compile(r'w[0-9A-Za-z]+')
KEY = re.compile(r'hc-[0-9a-f]{12}')  # a Herdr Core job's key, where a TUI job has its workspace id
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
    if backend(job) == 'core':
        return tell_core(job, name, text)
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


def events_dir():
    """Owner tags, job markers and the default routes folder: HERDR_EVENTS_DIR, else ~/.config/herdr-events."""
    return Path(os.environ.get('HERDR_EVENTS_DIR') or Path.home() / '.config/herdr-events').expanduser()


def starter(workspace):
    """At fleet-job new: HERDR_EVENTS_OWNER, else the workspace's owner tag (herdr-events-owner); '' when local.
    A slug that is set but malformed is refused: it must never turn a bot's job into a local one."""
    owner, source = os.environ.get('HERDR_EVENTS_OWNER', '').strip(), 'HERDR_EVENTS_OWNER'
    tag = events_dir() / 'owners' / str(workspace)
    if not owner and workspace and tag.is_file():
        owner = next((row[len('owner='):].strip() for row in tag.read_text().splitlines() if row.startswith('owner=')), '')
        source = 'the owner tag of ' + str(workspace)
    if owner and not OWNER.fullmatch(owner):
        raise ValueError(f'{source} holds no bot slug ({line(owner)}): fix it with herdr-events-owner, then start again')
    return owner


def job_marker(workspace):
    """File whose presence means this workspace (or Core job key) has an open job. None for any other id."""
    if not workspace or not (WS_ID.fullmatch(str(workspace)) or KEY.fullmatch(str(workspace))):
        return None
    return events_dir() / 'jobs' / str(workspace)


def mark_job(workspace, job):
    path = job_marker(workspace)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(Path(job).absolute()) + '\n')
    (Path(job) / 'workspace').write_text(str(workspace) + '\n')


def clear_job_marker(workspace, job):
    path = job_marker(workspace)
    if path is None or not path.is_file():
        return
    if path.read_text().strip() == str(Path(job).absolute()):
        path.unlink()


def post_local(job, fields):
    """Ordinary relay, not strict: a local job's finish. Logged when no route has a URL."""
    event = {'source': 'stampede', 'job': str(Path(job).absolute()), 'agent': roster(job)[1], **fields, **caller_ids(job)}
    script = SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'
    result = subprocess.run([str(script), json.dumps(event)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('the relay did not accept the finish event ('
                         + (line(result.stderr) or 'exit ' + str(result.returncode)) + ')')


def finish(job, summary):
    """One done event, then drop the workspace marker. A second call does not post again.
    A job a bot started uses the strict route; a local job uses the ordinary relay."""
    job = Path(job).absolute()
    summary = line(summary)
    if not summary:
        raise ValueError('finish needs one line on where the job ended')
    stamp = job / 'finished'
    if not stamp.is_file():
        fields = {'state': 'done', 'summary': summary}
        workspace = (job / 'workspace').read_text().strip() if (job / 'workspace').is_file() else ''
        if workspace:
            fields['workspace'] = workspace
        owner = job_owner(job)
        if owner:
            post_event(job, owner, fields)
        else:
            post_local(job, fields)
        stamp.write_text(summary + '\n')
    if (job / 'workspace').is_file():
        clear_job_marker((job / 'workspace').read_text().strip(), job)
    print('FINISHED ' + str(job))


def post_event(job, owner, fields):
    """One event to the bot that started the job, queued by the relay in strict mode: only the bot's own route with a
    URL (never the default route, perhaps another bot's), or a refusal. No `pane`: the flusher keeps only a pane's
    newest event after an outage, and a question or a gate must never be dropped for a later turn end."""
    event = {'source': 'stampede', 'owner': owner, 'job': str(Path(job).absolute()), 'agent': roster(job)[1], **fields,
             **caller_ids(job)}
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
    typed = '' if backend(job) == 'core' else ', or on the owner\'s yes typed in your pane'  # on Core, anything can type
    if not owner:
        ask_background(job, gate_question(gate), [], gate=ident)
        return print(f'GATE {ident} on the phone; act after {check} prints APPROVED{typed}')
    try:
        post_event(job, owner, {'state': 'gate', **gate, 'options': ['yes', 'no'],
                                'approve': shlex.join(['fleet-job', 'approve-gate', str(job), ident, '--sha', sha, '--by', 'owner in ' + owner + ' chat']),
                                'deny': shlex.join(['fleet-job', 'tell', str(job), 'lead', f"GATE {ident} NO: <the owner's words>"])})
    except ValueError:
        (job / 'gates' / (ident + '.json')).unlink()  # a gate its bot never hears is no gate
        raise
    print(f'GATE {ident} queued for {owner}, which asks the owner in chat; act after {check} prints APPROVED{typed}')


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


CORE_TERMINAL = ('HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE')  # set by Herdr Core in each of its terminals
AGENT_HOSTS = ('herdr', 'herdr-core', 'hc')  # the Herdr server, and Herdr Core's core, holder and CLI


def inside_herdr(env=None, pid=None):
    """True for a command run in a Herdr pane or a Herdr Core terminal, or anywhere under the Herdr server or a Core
    process (hc exec included): an agent's own command.
    ponytail: same Unix user, so a determined agent could still write the record or reach this over ssh; the boundary
    is auto mode plus this refusal. Upgrade: an approval signed on the bot's own computer."""
    env = os.environ if env is None else env
    if env.get('HERDR_ENV') or env.get('HERDR_PANE_ID') or any(env.get(name) for name in CORE_TERMINAL):
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
        if tree[pid][1] in AGENT_HOSTS:
            return True
        pid = tree[pid][0]
    return False


def approve_gate(job, ident, sha, by):
    """The starting bot's command, run outside Herdr: the owner said yes in its chat to this gate at this commit."""
    core = backend(job) == 'core'
    if inside_herdr():
        if core:
            raise PermissionError('approve-gate runs only outside Herdr and Herdr Core (over plain ssh, never hc exec), from '
                                  'the bot that started the job: an agent\'s own say-so never counts. The owner answers the bot in chat')
        raise PermissionError('approve-gate runs only outside Herdr, from the bot that started the job: an agent\'s own '
                              'say-so never counts. The owner answers the bot in chat, or types yes in the lead\'s pane')
    if load_gate(job, ident)['route'] == 'local':
        raise PermissionError(f'gate {ident} belongs to a job started locally: the owner answers on the phone'
                              + ('' if core else ' or in Herdr'))
    if not line(by):
        raise ValueError('--by says who said yes and where, e.g. "owner in Grok Bot chat"')
    record_yes(job, ident, sha, by)
    print(f'APPROVED {ident} at {sha}')


def gate_ok(job, ident, sha):
    """The lead's check before it acts: the owner's recorded yes for this gate, at this very commit."""
    gate = load_gate(job, ident)
    path = Path(job) / 'gates' / (ident + '.approved')
    if not path.is_file():
        raise PermissionError(f'gate {ident} has no recorded yes: wait for it'
                              + ('' if backend(job) == 'core' else ', or the owner\'s yes typed in your pane'))
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
        lines = [line(row.decode('utf-8', 'replace')) for row in addition[:complete].split(b'\n')[:-1] if row.strip()]
        attempts = [found.group(1) for found in (re.fullmatch('REOPENED ' + re.escape(agent) + ' ([0-9a-f]{12})', row)
                                                  for row in lines) if found]
        if attempts:  # this file's hook delivered a reopen's line: that reopen's proof the restarted agent reads this file
            ack_path = job / 'hooks' / ('ack-' + agent + '.json')
            acks = json.loads(ack_path.read_text()) if ack_path.is_file() else {}
            acks[str(changed)] = (acks.get(str(changed), []) + attempts)[-10:]
            temporary = ack_path.with_name('.' + ack_path.name + '.' + str(os.getpid()))
            temporary.write_text(json.dumps(acks) + '\n')
            os.replace(temporary, ack_path)  # reopen reads it without the wake lock
    return lines


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
    """A worker's session ended (exit, crash, closed pane): tell the lead. Never for the lead itself, and never on Herdr
    Core, where the job's follower reports every exit, a hard kill that runs no hook included."""
    if agent != roster(job)[1] and backend(job) != 'core':
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


def backend(job):
    """'core' for a job stampede new --core made; 'tui' for every other job, those made before Core included."""
    path = Path(job) / 'backend'
    return 'core' if path.is_file() and path.read_text().strip() == 'core' else 'tui'


def job_key(job):
    """A new Core job's key: hc- and the first 12 hex of the SHA-256 of the job folder's absolute path."""
    return 'hc-' + hashlib.sha256(str(Path(job).absolute()).encode()).hexdigest()[:12]


def core_key(job):
    """The key a Core job recorded at new, in its workspace file."""
    path = Path(job) / 'workspace'
    key = path.read_text().strip() if path.is_file() else ''
    if not KEY.fullmatch(key):
        raise ValueError(f'{job} is no Herdr Core job: its workspace file holds no hc- key')
    return key


def endpoint(job):
    """The Herdr Core a job was made on: HC_SESSION and HC_SOCKET as they were at new; '' is Core's default."""
    path = Path(job) / 'endpoint'
    return json.loads(path.read_text()) if path.is_file() else {'session': '', 'socket': ''}


def target(job):
    """Point every hc call of this process, and every terminal it starts, at the job's own core. A caller whose
    HC_SESSION or HC_SOCKET names another core is refused, never retargeted: there the job would start a second time."""
    recorded = endpoint(job)
    for name, key, default in (('HC_SESSION', 'session', 'default'), ('HC_SOCKET', 'socket', '')):
        mine, want = (os.environ.get(name) or '').strip(), recorded.get(key) or ''
        if mine and mine != (want or default):
            raise ValueError(f'{Path(job).absolute()} runs on Herdr Core {name}={want or "(default)"}, but {name} here is '
                             f'{mine}: unset it or set it to the job\'s, so the job never starts a second time on another core')
        if want:
            os.environ[name] = want
        else:
            os.environ.pop(name, None)


class HcError(RuntimeError):
    def __init__(self, message, kind='', code=1):
        super().__init__(message)
        self.kind, self.code = kind, code


def hc(*args):
    """One Herdr Core command (HC names the binary) and its JSON answer; on failure Core's error kind and exit code."""
    try:
        result = subprocess.run([os.environ.get('HC') or 'hc', args[0], '--json', *args[1:]], capture_output=True, text=True)
    except OSError as error:
        raise ValueError('Herdr Core is not installed (' + line(error) + '): install hc 0.1.13 or later, or set HC') from None
    if result.returncode:
        try:
            error = json.loads(result.stderr or '{}').get('error') or {}
        except (ValueError, AttributeError):
            error = {}
        raise HcError('hc ' + args[0] + ': ' + line(error.get('message') or result.stderr or 'exit ' + str(result.returncode)),
                      error.get('kind', ''), result.returncode)
    return json.loads(result.stdout or '{}')


class CoreUnknown(RuntimeError):
    """An hc call failed where its answer decides whether an agent started, so nothing may be taken back."""
    def __init__(self, agent, message):
        super().__init__(message)
        self.agent = agent


def unknown(job, error):
    print(f'UNKNOWN {error.agent}: {line(error)}. Nothing was taken back: once Herdr Core answers, run bash '
          f'{Path(job).absolute() / "reopen.sh"}, which adopts it by its labels or starts it, never a second copy')
    return 1


def core_entries(job):
    path = Path(job) / 'core.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def bind(job, agent, fields, fresh=False):
    """Update one agent's entry in core.json ({state, address, name, role, session, socket, reason}): under core.json.lock
    only for this write, by a temporary file and os.replace, so no writer clobbers another's. fresh: a new launch's entry."""
    job = Path(job)
    with (job / 'core.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = core_entries(job)
        entries[agent] = dict(fields) if fresh else {**entries.get(agent, {}), **fields}
        temporary = job / ('.core.json.' + str(os.getpid()))
        temporary.write_text(json.dumps(entries, indent=1) + '\n')
        os.replace(temporary, job / 'core.json')
    return entries[agent]


@contextlib.contextmanager
def launching(job, agent):
    """Own this agent's launch: an exclusive lock on <job>/locks/<agent>.lock, held until its entry is live or failed.
    The kernel drops it when the caller dies, so a lock nobody holds means no launch is in flight, whatever core.json says."""
    path = Path(job) / 'locks' / (agent + '.lock')
    path.parent.mkdir(exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = os.read(fd, 32).decode(errors='replace').strip() or 'unknown'
            raise ValueError(f'{agent} is being started by another caller (pid {holder})') from None
        os.ftruncate(fd, 0)
        os.pwrite(fd, str(os.getpid()).encode(), 0)
        yield
    finally:
        os.close(fd)


CONFIG_KEYS = ('FLEET_LEAD_MODEL', 'FLEET_LEAD_EFFORT', 'FLEET_ASK_CMD', 'FLEET_TRUST_ROOT', 'FLEET_WATCH_INTERVAL',
               'FLEET_WATCH_PASSES', 'FLEET_WATCH_NOTIFY', 'HERDR_EVENTS_MACHINE', 'HERDR_EVENTS_HOME', 'HERDR_EVENTS_ROUTES_DIR',
               'HERDR_EVENTS_FLUSH_LOG', 'HERDR_EVENTS_DIR', 'HERDR_EVENTS_STALE_MINUTES', 'HC', 'HC_SESSION', 'HC_SOCKET',
               'STAMPEDE_NO_UPDATE_CHECK',
               'STAMPEDE_UPDATE_URL')  # every key in config.example; a test keeps them equal
HERDR_IDS = ('HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_EVENTS_OWNER')


def launch_env(job):
    """The front of every Core launch. A Core terminal gets the core's environment, not the caller's, and hc run has no
    --env: so the caller's PATH and settings, the job's key and the job's own owner, and never the caller's Herdr ids."""
    env = ['/usr/bin/env'] + [part for name in HERDR_IDS for part in ('-u', name)]
    env += ['PATH=' + os.environ.get('PATH', ''), 'STAMPEDE_JOB_KEY=' + core_key(job)]
    env += [name + '=' + os.environ[name] for name in CONFIG_KEYS if os.environ.get(name)]  # an empty one means unset
    owner = job_owner(job)
    return env + (['HERDR_EVENTS_OWNER=' + owner] if owner else [])


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


def start(job, agent, kind, pane, brief, model=None, effort=None, reports=(), yolo_in=None, cwd=None):
    """Start one agent and record it: in an existing pane at its shell prompt, then send its brief pointer (TUI); or in a
    Herdr Core terminal with its brief pointer as the first prompt (a Core job)."""
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
    if backend(job) == 'core':
        if pane:
            raise ValueError('this job runs on Herdr Core: start takes --cwd <dir>, never --pane')
        return start_core(job, agent, kind, brief, model, effort, reports, yolo_in, cwd, lead)
    if cwd:
        raise ValueError('--cwd is for a Herdr Core job; on the Herdr TUI the agent starts in its --pane')
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


CURSOR_ON_CORE = 'Cursor reports no OSC 7501 status, so stampede cannot tell when it is ready on Core; run it on the TUI'


def cli(kind):
    """The agent CLI's absolute path: a Core terminal runs it with the core's environment, not the caller's PATH."""
    path = shutil.which(kind)
    if not path:
        raise ValueError(kind + ' is not on PATH')
    return path


def record(job, agent, kind, brief, args, session=''):
    """How an agent was started, for reopen (agents.tsv); a Claude agent's session id is chosen by stampede on Core."""
    subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), agent, kind,
                    str(brief), *(['--session', session] if session else []), '--', *args], check=True, capture_output=True)


def core_status(terminal):
    """A terminal's own OSC 7501 word (idle, working, done, blocked, error), or None when it reports none."""
    return (terminal.get('status') or {}).get('state')


def live_terminal(job, agent):
    """This job's live terminal for the agent: its bound address, else one the job's and the agent's labels name,
    which is adopted (bound). None when no live terminal runs it."""
    key = core_key(job)
    address = core_entries(job).get(agent, {}).get('address')
    if address:
        try:
            terminal = hc('get', address)
        except HcError as error:
            if error.kind != 'not_found':
                raise
            terminal = {}
        labels = terminal.get('labels') or {}
        if terminal.get('state') == 'live' and labels.get('stampede.job') == key and labels.get('stampede.agent') == agent:
            return terminal
    found = [t for t in hc('ls', '--label', 'stampede.job=' + key, '--label', 'stampede.agent=' + agent).get('terminals', [])
             if t.get('state', 'live') == 'live']
    if found:
        bind(job, agent, {'state': 'live', 'address': found[0]['address'], 'name': found[0].get('name') or agent})
        try:  # hc ls shows no labels; the terminal's own record says which Claude session it runs
            session = (hc('get', found[0]['address']).get('labels') or {}).get('stampede.session')
        except HcError:
            session = None
        if session:
            prove(job, agent, session, 'ran')
        return found[0]
    return None


CORE_KEEPS = 86400  # seconds Herdr Core keeps a finished terminal's record (RETAIN_MS)


def prove(job, agent, session, proof):
    """Record whether one Claude session of an agent ran: 'ran', 'never' or 'unknown' (core.json, per session)."""
    launches = dict(core_entries(job).get(agent, {}).get('launches', {}))
    launches[session] = {**launches.get(session, {'at': int(time.time())}), 'proof': proof}
    bind(job, agent, {'launches': launches})


def claude_session_file(session):
    """Claude Code's own record of a session it ran, if this machine has one."""
    home = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser()
    return next(iter(sorted(home.glob('projects/*/' + session + '.jsonl'))), None)


def session_proof(job, agent, session):
    """Whether this Claude session of the agent ever ran. A recorded 'ran' or 'never' stands; an unknown launch is placed
    by a terminal of it in hc ls --all, or Claude's session file ('ran'), or, while Core still keeps a finished record
    (24 h), by finding neither ('never'). Anything else stays 'unknown': the caller refuses rather than guess."""
    launch = core_entries(job).get(agent, {}).get('launches', {}).get(session)
    if launch and launch.get('proof') in ('ran', 'never'):
        return launch['proof']
    try:
        found = hc('ls', '--all', '--label', 'stampede.job=' + core_key(job), '--label', 'stampede.agent=' + agent,
                   '--label', 'stampede.session=' + session).get('terminals', [])
    except HcError:
        return 'unknown'
    if found or claude_session_file(session):
        proof = 'ran'
    elif launch and time.time() - launch.get('at', 0) < CORE_KEEPS:
        proof = 'never'
    else:
        return 'unknown'
    prove(job, agent, session, proof)
    return proof


def core_run(job, agent, role, program, cwd, session=None):
    """Start one program of this job in its own Core terminal (no parent, no notes), the caller holding the agent's launch
    lock, and bind it. session: the Claude session it runs, labelled on the terminal and proved per session. A failed
    hc run that spawned all the same (a call that timed out) is adopted by its labels; otherwise the entry is failed
    and the error raised."""
    key = core_key(job)
    launches = dict(core_entries(job).get(agent, {}).get('launches', {}))
    if session and launches.get(session, {}).get('proof') != 'ran':
        launches[session] = {'proof': 'unknown', 'at': int(time.time())}  # a new launch has not run until shown
    bind(job, agent, {'state': 'starting', 'role': role, 'cwd': str(cwd), **endpoint(job), 'launches': launches}, fresh=True)
    labels = [part for k, v in (('job', key), ('agent', agent), ('role', role)) for part in ('--label', f'stampede.{k}={v}')]
    labels += ['--label', 'stampede.session=' + session] if session else []
    name = agent
    while True:
        try:
            terminal = hc('run', '--bg', '--no-parent', '--no-notify', '--name', name, '--cwd', str(cwd), *labels, '--',
                          *launch_env(job), *program)
            break
        except HcError as error:
            if error.kind == 'name_taken' and name == agent:
                name = agent[:27] + '-' + key[3:7]  # another job's terminal holds the name; identity is the address
                continue
            try:  # this launch's terminal, live or already finished
                spawned = hc('ls', '--all', *labels[:4], *labels[6:]).get('terminals', [])
            except HcError as lookup:  # the entry stays starting: a later start or reopen reconciles it by its labels
                raise CoreUnknown(agent, f'hc run answered {line(error)}, and hc ls could not tell whether it started '
                                         f'({line(lookup)})') from None
            live = [t for t in spawned if t.get('state', 'live') == 'live']
            if not live:
                if session:
                    prove(job, agent, session, 'ran' if spawned else 'never')
                bind(job, agent, {'state': 'failed', 'reason': line(error) + ('; it started, then ended' if spawned else '')})
                raise
            terminal = live[0]
            break
    if session:
        prove(job, agent, session, 'ran')
    bind(job, agent, {'state': 'live', 'address': terminal['address'], 'name': terminal.get('name') or name})
    return terminal['address']


def core_outcome(job, agent, address, who, brief, plain=False):
    """After a launch, from the agent's own status: 'started' (working, idle or done), 'not ready' (a live terminal that
    is blocked, at an error or silent after 30 s: it stays this job's agent), or 'failed' (its terminal finished).
    plain: a program with no status (the follower): live after 3 s is 'started'; Core not answering is 'unknown'."""
    try:
        hc('wait', address, '--timeout', '3' if plain else '30')
    except HcError:
        pass
    try:
        terminal = hc('get', address)
    except HcError as error:  # unconfirmed: it may run, so it stays this job's
        if plain:
            unknown(job, CoreUnknown(agent, f'started as {address}, then hc get failed ({line(error)})'))
            return 'unknown'
        print(f'NOT READY {agent}: {line(error)}; read it with hc read {address} once Herdr Core answers')
        return 'not ready'
    word = core_status(terminal)
    if terminal.get('state') != 'live':
        try:
            tail = hc('read', address, '--lines', '20').get('text', '')
        except HcError:
            tail = ''
        reason = f'{terminal.get("reason") or "ended"} exit {terminal.get("exit_code")}'
        bind(job, agent, {'state': 'failed', 'reason': reason})
        print(f'FAILED {agent} ({reason}): {line(tail)}')
        return 'failed'
    if plain:
        return 'started'
    if word in ('working', 'idle', 'done'):
        print(f'STARTED {agent} ({address})')
        return 'started'
    resend = f'then fleet-job tell {job} {who} "Read {brief}" if it went idle without its first prompt'
    if word == 'blocked':
        kind = (terminal.get('status') or {}).get('kind') or 'blocked'
        print(f'BLOCKED {agent}: {kind}; read it with hc read {address}, clear the dialog with hc keys {address} <keys>, {resend}')
    else:
        print(f'NOT READY {agent}: {word or "no status"}; read it with hc read {address}; it stays this job\'s {who}, '
              f'so never start a second one; {resend}')
    return 'not ready'


def start_core(job, agent, kind, brief, model, effort, reports, yolo_in, cwd, lead):
    """One live launch per agent: under its launch lock, refuse when a live terminal of this job runs it (adopting one its
    labels name), else start it with its hooks, its brief pointer as the first prompt, and Codex without its daemon."""
    if kind == 'cursor':
        raise ValueError(CURSOR_ON_CORE)
    job, brief = Path(job).absolute(), Path(brief).expanduser().absolute()  # the agent may start in another folder
    target(job)
    cwd = Path(cwd or job.parent).expanduser().resolve()
    if yolo_in is not None and Path(yolo_in).expanduser().resolve() != cwd:
        raise PermissionError(f'--yolo-in {yolo_in} must be the --cwd the worker starts in ({cwd}): its own worktree')
    with launching(job, agent):
        try:
            running = live_terminal(job, agent)
        except HcError as error:
            raise ValueError(f'Herdr Core did not answer ({line(error)}): cannot tell whether {agent} runs, so nothing started') from None
        if running:
            raise ValueError(f'{agent} is already running at {running["address"]}')
        args = cli_args(job, agent, kind, model, effort, list(reports), lead=lead, yolo_in=cwd if yolo_in is not None else None)
        args += ['--no-daemon'] if kind == 'codex' else []  # else Codex runs its commands outside the terminal
        session = str(uuid.uuid4()) if kind == 'claude' else ''
        program = [cli(kind)] + args + (['--session-id', session] if session else [])
        record(job, agent, kind, brief, args, session)
        pointer = f'You are {agent} in a herdr fleet. Read {brief} and do everything it says.'
        try:
            address = core_run(job, agent, 'lead' if lead else 'worker', program + [pointer], cwd, session or None)
        except CoreUnknown as error:
            snapshot(job)
            return unknown(job, error)
        except HcError as error:  # confirmed: no terminal of the job runs it, and its entry says failed
            snapshot(job)
            print(f'FAILED {agent} ({line(error)})')
            return 1
        snapshot(job)
        return 0 if core_outcome(job, agent, address, 'lead' if lead else agent, brief) == 'started' else 1


def snapshot(job):
    """Refresh a Core job's reopen record (REOPEN.md and reopen.sh, from agents.tsv and core.json)."""
    subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), core_key(job), str(job)],
                   check=True, capture_output=True)


FOLLOWER = SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-core'
REOPEN_EVERY, REOPEN_DEADLINE = 5, 90  # seconds between a reopen's REOPENED writes, and before it gives up


def agent_rows(job):
    """agents.tsv: name -> {kind, session, brief, args}."""
    path, rows = Path(job) / 'agents.tsv', {}
    for row in (path.read_text().splitlines() if path.is_file() else []):
        if row and not row.startswith('#'):
            cells = (row.split('\t') + [''] * 5)[:5]
            rows[cells[0]] = dict(zip(('kind', 'session', 'brief', 'args'), cells[1:]))
    return rows


def reopen(job, lead_only=False, prompt=False):
    """Start what is missing of a Core job, once each and never a second copy of a live one: for an open job its marker,
    owner tag and follower; its lead, resumed; with no lead_only, each worker that is not live (Claude resumed, Codex
    fresh, with its brief pointer only with prompt). A finished job resumes its agents for inspection only. A restarted
    lead of an open job must acknowledge both its inbox files (exit 3 when it does not)."""
    job = Path(job).absolute()
    key, (people, lead), rows = core_key(job), roster(job), agent_rows(job)
    finished, outcomes = (job / 'finished').is_file(), {}
    target(job)
    selected = [lead] + ([] if lead_only else [a for a in people if a != lead])
    folders = {}  # every folder this reopen may start something in, checked before anything starts
    for agent in selected + ([] if finished else ['relay-' + key[3:]]):
        folders.setdefault(str(core_entries(job).get(agent, {}).get('cwd') or job.parent), []).append(agent)
    gone = [f'{folder} ({", ".join(agents)})' for folder, agents in folders.items() if not Path(folder).is_dir()]
    if gone:
        raise ValueError('cwd gone: ' + '; '.join(gone) + ': git worktree add each back first; nothing was started')
    if not finished:
        mark_job(key, job)
        if job_owner(job):
            tag_owner(job, key, job_owner(job))
        relay = 'relay-' + key[3:]
        with launching(job, relay):
            if not live_terminal(job, relay):
                outcomes[relay] = reopen_run(job, relay, 'relay', [str(FOLLOWER), str(job)], job.parent, plain=True)
    pending = job / 'reopen-pending'  # a restarted lead that has not yet acknowledged both inbox files
    for agent in selected:
        outcomes[agent] = reopen_agent(job, agent, rows.get(agent, {}), prompt, agent == lead,
                                       pending if agent == lead and not finished else None)
    snapshot(job)
    if not [agent for agent, outcome in outcomes.items() if outcome != 'live']:
        print(f'LIVE {key}: no agent to restart')
    code = 1 if [outcome for outcome in outcomes.values() if outcome in ('failed', 'unknown')] else 0
    if finished or not pending.exists() or outcomes.get(lead) not in ('started', 'live'):
        return code
    acked = acknowledged(job, lead)  # also on a retry with the lead live: an earlier reopen may have timed out
    if acked == 0:
        pending.unlink()
    return acked or code


def reopen_run(job, agent, role, program, cwd, plain=False, session=None):
    """One restart and what came of it: 'started', 'failed' (confirmed, said) or 'unknown' (kept, said)."""
    try:
        address = core_run(job, agent, role, program, cwd, session)
    except CoreUnknown as error:
        unknown(job, error)
        return 'unknown'
    except HcError as error:
        print(f'FAILED {agent} ({line(error)}): it did not start')
        return 'failed'
    print(f'RESTARTED {agent} ({address})')
    if plain and core_outcome(job, agent, address, agent, None, plain=True) != 'started':
        return 'failed' if core_entries(job).get(agent, {}).get('state') == 'failed' else 'unknown'
    return 'started'


def reopen_agent(job, agent, row, prompt, lead, pending=None):
    """Restart one agent unless a live terminal of the job runs it: 'live', 'started', 'failed' or 'unknown'.
    pending: written before the lead starts, so even an interrupted reopen leaves its acknowledgement owed."""
    with launching(job, agent):
        if live_terminal(job, agent):
            return 'live'
        kind, args, session = row.get('kind', 'claude'), shlex.split(row.get('args', '')), row.get('session', '')
        pointer = f'You are {agent} in a herdr fleet. Read {row.get("brief")} and do everything it says.'
        proof = session_proof(job, agent, session) if kind == 'claude' and session else 'never'
        if kind == 'claude' and proof == 'unknown':
            print(f'UNKNOWN {agent}: cannot tell whether its session {session} ever ran (no terminal of it in hc ls --all '
                  f'--label stampede.job={core_key(job)} --label stampede.agent={agent}, no Claude session file): check '
                  'there, then start it again with fleet-job start; nothing was restarted')
            return 'unknown'
        if kind == 'claude' and proof == 'ran':
            program = [cli(kind), '--resume', session] + args
        elif kind == 'claude':  # it never ran: its own session id, fresh, with its brief
            if not session:
                session = str(uuid.uuid4())
                record(job, agent, kind, row.get('brief') or '-', args, session)
            program = [cli(kind)] + args + ['--session-id', session, pointer]
        else:
            program = [cli(kind)] + args + ([pointer] if prompt else [])
        cwd = core_entries(job).get(agent, {}).get('cwd') or Path(job).parent
        if pending:
            pending.write_text(datetime.now().strftime('%Y-%m-%d %H:%M') + '\n')
        return reopen_run(job, agent, 'lead' if lead else 'worker', program, cwd, session=session if kind == 'claude' else None)


def acknowledged(job, lead):
    """A restarted lead reads its two inbox files once its own wake hook delivers them: write REOPENED <lead> <attempt>
    to each every REOPEN_EVERY seconds until that file's hook has acknowledged this attempt, or REOPEN_DEADLINE passes.
    Reopen never moves a read offset, so each delivery carries every line written there while the lead was down."""
    attempt, acks = uuid.uuid4().hex[:12], Path(job) / 'hooks' / ('ack-' + lead + '.json')
    pending, deadline = {str(p.resolve()) for p in watched(job, lead, True)}, time.time() + REOPEN_DEADLINE
    while pending and time.time() < deadline:
        for path in sorted(pending):
            append(path, f'REOPENED {lead} {attempt}')
        until = min(deadline, time.time() + REOPEN_EVERY)
        while pending and time.time() < until:
            try:
                seen = json.loads(acks.read_text())
            except (OSError, ValueError):  # none yet, or not whole: not acknowledged yet
                seen = {}
            pending = {path for path in pending if attempt not in seen.get(path, [])}
            time.sleep(min(0.5, REOPEN_EVERY / 10))
    if not pending:
        print(f'ACKNOWLEDGED {lead}: its wake delivered both inbox files')
        return 0
    for path in sorted(pending):
        print(f'NOT ACKNOWLEDGED {path}: once {lead} is up, run: echo "REOPENED {lead} {attempt}" >> {path}')
    return 3


def caller_ids(job):
    """Where a job's event comes from: on the TUI, the caller's Herdr workspace and pane; on Core, the job's key and its
    lead's terminal, never the caller's environment (a TUI pane may run a Core job's command)."""
    if backend(job) != 'core':
        return {key: os.environ[name] for key, name in (('workspace', 'HERDR_WORKSPACE_ID'), ('lead_pane', 'HERDR_PANE_ID'))
                if os.environ.get(name)}
    key = core_key(job)
    address = core_entries(job).get(roster(job)[1], {}).get('address')
    return {'workspace': key, **({'lead_pane': f'hc:{key}/{address}'} if address else {})}


def tell_core(job, name, text):
    """Prompt a Codex agent in its Core terminal by its status: idle types only while idle (atomic); done types at once,
    so a worker that turned working in between takes it as a message during its turn. One SUBMITTED or FAILED line."""
    target(job)
    address, lost = core_entries(job).get(name, {}).get('address'), None
    try:
        terminal = hc('get', address) if address else {}
    except HcError as error:
        terminal, lost = {}, None if error.kind == 'not_found' else error
    labels, word = terminal.get('labels') or {}, core_status(terminal)
    refused = {'working': 'working: tell it after its turn', 'blocked': f'blocked: hc read {address}', 'error': f'error: hc read {address}'}
    if lost:
        why = 'Herdr Core did not answer: ' + line(lost)
    elif labels.get('stampede.job') != core_key(job) or labels.get('stampede.agent') != name:
        why = "not this job's terminal"
    elif terminal.get('state') != 'live' or word not in ('idle', 'done', *refused):
        why = 'not ready'
    elif word in refused:
        why = refused[word]
    else:
        try:
            hc('send', *(['--if', 'idle'] if word == 'idle' else []), '--', address, text)
            return print(f'SUBMITTED {name} ({address})')
        except HcError as error:
            why = {9: refused['blocked'], 10: refused['working'], 11: 'not ready'}.get(error.code, line(error))
    print(f'FAILED {name} ({why})')
    raise SystemExit(2)


FILLER = {'a', 'an', 'the', 'on', 'in', 'of', 'to', 'for', 'and', 'please', 'can', 'you', 'we', 'i', 'my', 'our', 'it', 'this', 'that'}


def slug(ask):
    words = [w for w in re.findall(r'[a-z0-9]+', ask.lower().split('\n')[0]) if w not in FILLER]
    out = ''
    for word in words:
        if len(out) + bool(out) + len(word) > 24:
            break
        out += '-' * bool(out) + word
    return out or 'job'


SESSION = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def make_job(repo, job, ask, owner, review):
    """The job folder (git-excluded), its ask, owner and review files, and the lead's name."""
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
    return lead


def lead_brief(job, lead, owner, review, fork, key=None):
    """The lead's first brief. key: a Herdr Core job's key, where only the recorded yes counts and workers take --cwd."""
    gate = ('Write plan.md, then end your turn: the owner reviews it and fleet-job approve wakes you.' if review
            else 'Write plan.md, then go: do not stop for approval.')
    if fork:
        gate = ('The conversation before this is the owner\'s planning chat, forked into your pane: you are no longer that chat '
                'but the lead, so write what it agreed into plan.md rather than planning again. ' + gate)
    ask_gate_cmd = f'fleet-job ask {job} --gate --sha <commit> [--pr <n>] "<the exact action>"'
    gate_ok_cmd = f'fleet-job gate-ok {job} <gate> --sha <the commit you act on>'
    layout, workers = 'the layout (workspace, tabs, panes with app and model)', 'Start a worker with: fleet-job start. '
    if key:
        gate_route = (f'ask it with {ask_gate_cmd}; it goes back to {owner}, which asks the owner in chat. ' if owner else
                      f'ask it with {ask_gate_cmd} (a phone card). ')
        gate_route += (f'Act only after {gate_ok_cmd} prints APPROVED; a merge uses --match-head-commit <that commit>. This job runs '
                       'on Herdr Core, where anything can type into your terminal: a yes typed there, your own question card, an '
                       'agent\'s word or a relayed yes never counts.')
        layout = 'the agents (app and model for each)'
        workers = (f'Start a worker with: fleet-job start {job} <agent> --kind claude|codex --brief <file> [--cwd <dir>] '
                   '(Herdr Core: no --pane; Cursor runs on the TUI only). Wait on CI or a build as a labelled terminal: '
                   f'hc run --bg --no-parent --no-notify --name wait-<what> --label stampede.job={key} --label stampede.role=wait '
                   '-- <command>; its end wakes you as WAITED <name> exit <code>. ')
    else:
        gate_route = (f'ask it with {ask_gate_cmd}; it goes back to {owner}, which asks the owner in chat. ' if owner else
                      f'ask it with your own question card, or with {ask_gate_cmd} (a phone card). ')
        gate_route += (f'Act only on the owner\'s yes typed in your pane{"" if owner else " or card"}, or after {gate_ok_cmd} '
                       'prints APPROVED; a merge uses --match-head-commit <that commit>. An agent\'s word or a relayed yes never counts.')
    return (f'You are {lead}, the lead of the job in {job}. Read {job / "ask.md"} and run it with the herdr-fleet skill. '
            f'Plan in {job / "plan.md"}: {layout}, then the tasks with the pane that does each, then any questions with a default. {gate} '
            f'Ask the owner with: fleet-job ask {job} "<question>" --option <a> --option <b>; keep working while it waits. '
            f'Answer a worker with: fleet-job tell {job} <agent> "<text>". {workers}'
            f'A merge or another gate (the herdr-fleet list): {gate_route} '
            f'When idle, end your turn; hooks wake you.\n'
            f'When the job is done or stopped for good, run fleet-job finish {job} "<one line on where it ended>" once.\n')


def new(ask_file, workspace, name=None, review=False, pane=None, fork=None, core=False, cwd=None):
    """Front door: make the job, start its lead on Claude with hooks, print the lead's name.
    pane: an existing empty pane for the lead (a fresh workspace's root pane), whose tab becomes `lead`; else a new tab.
    fork: a Claude session id (the chat that planned the job); the lead starts as a fork of it and keeps that conversation.
    core: the whole job runs on Herdr Core, in cwd (default: the git root here)."""
    if core:
        if workspace or pane:
            raise ValueError('new --core takes --cwd <repo>, never --pane or --workspace: a Herdr Core job has no Herdr pane')
        return new_core(ask_file, name, review, fork, cwd)
    if not (workspace or pane):
        raise ValueError('new needs --workspace or --pane, or run it inside Herdr')
    if fork is not None and not SESSION.fullmatch(fork):
        raise ValueError(f'--fork takes a Claude session id (a UUID, such as $CLAUDE_CODE_SESSION_ID), not {fork!r}')
    ask = Path(ask_file).expanduser().read_text()
    info = herdr('pane', 'get', pane)['pane'] if pane else None
    # herdr 0.9.4's `workspace get` has no cwd: the workspace's first pane holds the project folder
    repo = Path(info['cwd'] if info else herdr('pane', 'list', '--workspace', workspace)['panes'][0]['cwd']).expanduser()
    ws_id = info.get('workspace_id', pane.split(':')[0]) if info else workspace
    owner = starter(ws_id)
    job = repo / ('.herdr-' + (name or slug(ask)))
    lead = make_job(repo, job, ask, owner, review)
    if info:
        herdr('tab', 'rename', info['tab_id'], 'lead')
    else:
        pane = herdr('tab', 'create', '--workspace', workspace, '--cwd', str(repo), '--label', 'lead', '--no-focus')['root_pane']['pane_id']
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    brief.write_text(lead_brief(job, lead, owner, review, fork))
    args = cli_args(job, lead, 'claude', os.environ.get('FLEET_LEAD_MODEL', 'claude-opus-5-5'),
                    os.environ.get('FLEET_LEAD_EFFORT', 'xhigh'), [], lead=True)
    herdr('pane', 'rename', pane, lead)
    blocked = launch(lead, 'claude', pane, (['--resume', fork, '--fork-session'] if fork else []) + args)
    # the reopen record leaves the fork out: a reopen resumes the lead's own session, not the planning chat
    subprocess.run([str(SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), lead,
                    'claude', str(brief), '--', *args], check=True)
    mark_job(ws_id, job)
    if blocked:
        return print(f'BLOCKED {lead}: clear the startup dialog, then fleet-job tell {job} lead "Read {brief}"')
    tell(job, lead, f'You are {lead}. Read {brief} and do everything it says.')
    print(lead + ' ' + str(job))


def core_repo(cwd):
    """A Core job's repo: --cwd, else the git root of the current folder; under FLEET_TRUST_ROOT, as herdr-trust requires."""
    if cwd is None:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if top.returncode:
            raise ValueError('new --core needs --cwd <repo>, or run it inside a git repo')
        cwd = top.stdout.strip()
    repo = Path(cwd).expanduser().resolve()
    root = Path(os.environ.get('FLEET_TRUST_ROOT') or '~/code').expanduser().resolve()
    if not repo.is_dir() or (repo != root and root not in repo.parents):
        raise ValueError(f'{repo} is not a folder under FLEET_TRUST_ROOT ({root}): run herdr-trust on a repo there first')
    return repo


def new_core(ask_file, name, review, fork, cwd):
    """A whole job on Herdr Core. The record first (folder, backend, key, owner and its tag, marker, the lead's row), then
    the follower, then the lead with its brief pointer as the first prompt. Only a confirmed failure (the relay or the lead
    never ran, or its terminal already finished) takes the start back; a live lead that is not ready stays one job."""
    if fork is not None and not SESSION.fullmatch(fork):
        raise ValueError(f'--fork takes a Claude session id (a UUID, such as $CLAUDE_CODE_SESSION_ID), not {fork!r}')
    repo, claude = core_repo(cwd), cli('claude')
    ask = Path(ask_file).expanduser().read_text()
    owner = starter(os.environ.get('HERDR_WORKSPACE_ID'))
    job = repo / ('.herdr-' + (name or slug(ask)))
    if job.exists():
        raise ValueError(f'{job} already exists: a job folder is used once; start another job with --name')
    key = job_key(job)  # the path's hash: a folder made again at this path has the same key
    try:
        earlier = hc('ls', '--label', 'stampede.job=' + key).get('terminals', [])
    except HcError as error:
        raise ValueError(f'Herdr Core did not answer ({line(error)}): nothing was made') from None
    if earlier:
        raise ValueError('terminals of an earlier job at this path still run: kill them '
                         f'(hc ls --all --label stampede.job={key}) or use another --name')
    lead = make_job(repo, job, ask, owner, review)
    (job / 'backend').write_text('core\n')
    (job / 'endpoint').write_text(json.dumps({'session': (os.environ.get('HC_SESSION') or '').strip(),
                                              'socket': os.environ.get('HC_SOCKET') or ''}) + '\n')
    target(job)
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    brief.write_text(lead_brief(job, lead, owner, review, fork, key))
    args = cli_args(job, lead, 'claude', os.environ.get('FLEET_LEAD_MODEL', 'claude-opus-5-5'),
                    os.environ.get('FLEET_LEAD_EFFORT', 'xhigh'), [], lead=True)
    session = str(uuid.uuid4())
    record(job, lead, 'claude', brief, args, session)  # the fork stays out: a reopen resumes the lead's own session
    mark_job(key, job)
    (events_dir() / 'owners' / key).unlink(missing_ok=True)  # a folder used before (same path, same key) had its own
    if owner:
        tag_owner(job, key, owner)
    snapshot(job)  # reopen.sh exists before anything starts
    relay = 'relay-' + key[3:]
    try:
        with launching(job, relay):
            follower = core_outcome(job, relay, core_run(job, relay, 'relay', [str(FOLLOWER), str(job)], repo), relay, None, plain=True)
        if follower == 'failed':  # confirmed: the job would run with no one reporting its workers' exits
            return start_failed(job, key, relay, core_entries(job)[relay].get('reason', 'the follower ended'))
        if follower == 'unknown':
            snapshot(job)
            return 1
        with launching(job, lead):
            program = [claude] + (['--resume', fork, '--fork-session'] if fork else []) + args + ['--session-id', session]
            address = core_run(job, lead, 'lead', program + [f'You are {lead}. Read {brief} and do everything it says.'], repo, session)
            outcome = core_outcome(job, lead, address, 'lead', brief)
    except CoreUnknown as error:
        snapshot(job)
        return unknown(job, error)
    except HcError as error:
        return start_failed(job, key, relay, line(error))
    if outcome == 'failed':
        return start_failed(job, key, relay, core_entries(job)[lead].get('reason', 'the lead ended'))
    snapshot(job)
    if outcome == 'started':
        print(lead + ' ' + str(job))
        return 0
    return 1


def tag_owner(job, key, owner):
    """A Core job's owner tag: its bot, and the core it runs on (when not the default), which the watchdog asks."""
    point = endpoint(job)
    (events_dir() / 'owners').mkdir(parents=True, exist_ok=True)
    (events_dir() / 'owners' / key).write_text(f'owner={owner}\n' + ''.join(f'{k}={point[k]}\n' for k in ('session', 'socket') if point.get(k)))


def start_failed(job, key, relay, reason):
    """A confirmed failed start: kill and remove the follower, mark what is not failed yet as failed, take back the marker
    and owner tag, and leave start-failed (the follower exits on it). The folder stays; a retry is a new job."""
    address = core_entries(job).get(relay, {}).get('address')
    for verb in ('kill', 'rm'):
        try:
            hc(verb, address) if address else None
        except HcError:
            pass
    for agent, entry in core_entries(job).items():
        if entry.get('state') != 'failed':
            bind(job, agent, {'state': 'failed', 'reason': reason})
    clear_job_marker(key, job)
    if job_owner(job):
        (events_dir() / 'owners' / key).unlink(missing_ok=True)
    (job / 'start-failed').write_text(reason + '\n')
    print(f'FAILED {roster(job)[1]} ({reason}): nothing of {job} runs; the folder stays as a record, and a retry is a new job')
    return 1


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='fleet-job')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('new'); p.add_argument('--file', required=True)
    p.add_argument('--workspace', help='default: $HERDR_WORKSPACE_ID (Herdr TUI only)')
    p.add_argument('--core', action='store_true', help='run the whole job on Herdr Core (hc), in --cwd')
    p.add_argument('--cwd', help='with --core: the repo (default: the git root of the current folder)')
    p.add_argument('--name'); p.add_argument('--review', action='store_true')
    p.add_argument('--pane', help="an existing empty pane for the lead (a fresh workspace's root pane); its tab becomes lead")
    p.add_argument('--fork', metavar='SESSION_ID', help='start the lead as a fork of this Claude session (the chat that planned the job)')
    p = start_parser = sub.add_parser('start'); p.add_argument('job'); p.add_argument('agent'); p.add_argument('--kind', required=True)
    p.add_argument('--pane', help='the Herdr TUI pane (required on the TUI)'); p.add_argument('--brief', required=True)
    p.add_argument('--cwd', help='a Herdr Core job: the folder it starts in (default: the repo)')
    p.add_argument('--model'); p.add_argument('--effort')
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
    p = sub.add_parser('finish'); p.add_argument('job'); p.add_argument('summary', nargs='+')
    p = sub.add_parser('hook'); p.add_argument('action'); p.add_argument('job'); p.add_argument('--agent', required=True)
    p.add_argument('payload', nargs='?', help="Codex's notify JSON, passed as the last argument; other hooks read stdin")
    p = sub.add_parser('_reopen', help='a Herdr Core job: start what is missing (reopen.sh runs it)'); p.add_argument('job')
    p.add_argument('--lead', action='store_true', help='only the follower and the lead')
    p.add_argument('--prompt', action='store_true', help='a restarted Codex worker gets its brief pointer again')
    p = sub.add_parser('_ask'); p.add_argument('job'); p.add_argument('--command'); p.add_argument('--option', action='append', default=[])
    p.add_argument('--gate')
    p.add_argument('question', nargs='+')
    a = parser.parse_args(argv)
    if a.cmd == 'new' and a.cwd and not a.core:
        parser.error('--cwd is for new --core')
    if a.cmd == 'start' and not a.pane and backend(a.job) != 'core':
        start_parser.error('the following arguments are required: --pane')
    try:
        return run(a)
    except (ValueError, PermissionError) as error:
        if a.cmd == 'hook':  # a hook's exit 2 blocks or wakes Claude; keep a hook's error a plain failure
            raise
        print('fleet-job ' + a.cmd + ': ' + line(error), file=sys.stderr)
        return 2
    except HcError as error:  # Herdr Core failed: one line, never a traceback (a TUI job never calls hc)
        print('fleet-job ' + a.cmd + ': ' + line(error), file=sys.stderr)
        return 1


def run(a):
    if a.cmd == 'new':
        if a.core:
            return new(a.file, a.workspace, a.name, a.review, a.pane, a.fork, core=True, cwd=a.cwd)
        return new(a.file, a.workspace or os.environ.get('HERDR_WORKSPACE_ID'), a.name, a.review, a.pane, a.fork)
    if a.cmd == 'start':
        return start(a.job, a.agent, a.kind, a.pane, a.brief, a.model, a.effort, a.report, a.yolo_in, a.cwd)
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
    if a.cmd == 'finish':
        return finish(a.job, ' '.join(a.summary))
    if a.cmd == '_reopen':
        return reopen(a.job, a.lead, a.prompt)
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
