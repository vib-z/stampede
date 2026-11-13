"""The per-CLI hook handlers: wake, stop, notify, session end, questions and files."""
import fcntl, glob, hashlib, json, os, re, shlex, subprocess
from pathlib import Path

from . import base as base_, job as job_, owner as owner_, tui as tui_


def report_done(path):
    path = Path(path)
    if not path.is_file():
        return False
    head = path.read_text(errors='replace').splitlines()[:10]
    return any(re.match(r'Status:\s*(DONE|PASS|FINDINGS)\b', row.strip()) for row in head)


def watch_paths(job, agent, lead):
    """The files Claude watches; creates only absent ones, since touching a watched file fires its hook again."""
    paths = tui_.watched(job, agent, lead)
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
    if str(changed) not in {str(p.resolve()) for p in tui_.watched(job, agent, agent == job_.roster(job)[1])}:
        return []
    with (job / 'hooks/.wake.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lines, end = tui_.new_lines(job, agent, changed)
        tui_.mark_read(job, agent, changed, end, lines)
    return lines


def claude_stop(job, agent, payload):
    """Announce each report whose content changed; send a worker with no done report back once."""
    job = Path(job)
    record = job / 'hooks' / (agent + '.json')
    reports = json.loads(record.read_text()).get('reports', []) if record.is_file() else []
    if not reports:
        owner_.notify_lead(job, 'TURN ' + agent)
        return ''
    state_path = job / 'hooks' / ('reported-' + agent + '.json')
    seen = json.loads(state_path.read_text()) if state_path.is_file() else {}
    done = [report for report in reports if report_done(job / report)]
    for report in done:
        digest = hashlib.sha256((job / report).read_bytes()).hexdigest()
        if seen.get(report) != digest:
            seen[report] = digest
            owner_.notify_lead(job, 'REPORT ' + report)
    state_path.write_text(json.dumps(seen) + '\n')
    if done:
        return ''
    if payload.get('hook_event_name') == 'Stop' and not payload.get('stop_hook_active'):
        return json.dumps({'decision': 'block', 'reason': 'Finish your lane and write ' + ' or '.join(reports)
                           + ' with Status: DONE (a review: PASS or FINDINGS) in its first 10 lines. If you need an answer, write it to '
                           + str(job / 'questions' / (agent + '.md')) + ' and end your turn.'})
    owner_.notify_lead(job, 'TURN ' + agent + ' ended without a report')
    return ''


def deny(reason):
    return json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                              'permissionDecisionReason': reason}})


def ask_lead(job, agent, payload):
    """A worker's question card becomes a file for the lead. The lead's own card goes ahead, except in a front-door job,
    where nobody watches its pane: there it becomes an outbox question for the front door to relay."""
    questions = payload.get('tool_input', {}).get('questions', [])
    if agent == job_.roster(job)[1]:
        if not job_.front_door(job):
            return '{}'
        text = []
        for question in questions:
            text += [str(question.get('question', 'Owner input needed'))]
            text += ['- ' + str(o.get('label', '')) + ': ' + str(o.get('description', '')) for o in question.get('options', [])]
            text += ['']
        n = owner_.outbox_post(job, 'question', '\n'.join(text) or 'Owner input needed',
                        answer=shlex.join(['fleet-job', 'tell', str(Path(job).absolute()), 'lead', 'ANSWER: <their words>']))
        return deny(f'The owner talks only to the front-door chat, so this card would reach no one. It was posted there as '
                    f'outbox {n}; end your turn, the answer arrives in your inbox. Ask a gate with fleet-job ask --gate, '
                    'one exact action each, and put undecided questions in a post, never on one card with a gate.')
    text = ['# Questions from ' + agent]
    for question in questions:
        text += ['', str(question.get('question', 'Owner input needed'))]
        text += ['- ' + str(o.get('label', '')) + ': ' + str(o.get('description', '')) for o in question.get('options', [])]
    base_.append(Path(job) / 'questions' / (agent + '.md'), '\n'.join(text))
    first = base_.line(questions[0].get('question', '')) if questions else 'needs input'
    owner_.notify_lead(job, 'QUESTION ' + agent + ': ' + first)
    return deny('Question saved for the lead. End your turn; the answer arrives in your inbox.')


def send_file(job, agent, payload):
    """In a front-door job the lead's SendUserFile reaches no one (its pane is a terminal): post the files instead."""
    if agent != job_.roster(job)[1] or not job_.front_door(job):
        return '{}'
    data = payload.get('tool_input', {})
    files = [f for f in data.get('files', []) if Path(str(f)).expanduser().is_file()]
    n = owner_.outbox_post(job, 'post', data.get('caption') or 'Files for the owner', files)
    return deny(f'SendUserFile reaches no one from this pane. The files were posted to the front door as outbox {n}, '
                'which sends them to the owner; next time use fleet-job post <job> "<text>" --file <path>.')


RELAY_CODEX = base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-codex-notify'


def codex_notify(job, agent, payload):
    """Only the agent's own turns reach the lead: a thread whose session file is missing, or starts with a parent
    or a sub-agent source, is Codex's background work (as stampede's codex_notify at 0871ae3).
    A Codex lead's own turn goes to the relay, as Codex's global notify would have sent it, never to inbox.log, and
    then lets the deliverer type what came in while it worked."""
    lead = agent == job_.roster(job)[1]
    if lead:
        subprocess.run([str(RELAY_CODEX), json.dumps(payload)], stdin=subprocess.DEVNULL, capture_output=True)
    if payload.get('type') != 'agent-turn-complete':
        return
    thread = own_thread(payload)
    row = job_.agent_rows(job).get(agent) if thread and job_.backend(job) == 'core' else None
    if row is not None and row.get('session') != thread:  # on Core no snapshot sees Codex's session: its own turn names it
        job_.record(job, agent, 'codex', row.get('brief') or '-', shlex.split(row.get('args', '')), thread)
    if lead:
        return tui_.deliver_soon(job)
    if thread:
        owner_.notify_lead(job, base_.line('TURN ' + agent + ' ' + payload.get('last-assistant-message', '')))


def own_thread(payload):
    """The thread id when a Codex turn end is the agent's own turn, else None (Codex's background work)."""
    thread = payload.get('thread-id')
    if not thread or payload.get('parent_thread_id') or isinstance(payload.get('source'), dict) and payload['source'].get('subagent'):
        return None
    home = os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex')
    files = glob.glob(os.path.join(home, 'sessions', '*', '*', '*', 'rollout-*' + thread + '.jsonl'))
    if not files:
        return None
    with open(files[0]) as source:
        first = json.loads(source.readline()).get('payload', {})
    if first.get('parent_thread_id') or isinstance(first.get('source'), dict) and first['source'].get('subagent'):
        return None
    return thread


def session_end(job, agent, payload):
    """A worker's session ended (exit, crash, closed pane): tell the lead. Never for the lead itself, and never on Herdr
    Core, where the job's follower reports every exit, a hard kill that runs no hook included."""
    if agent != job_.roster(job)[1] and job_.backend(job) != 'core':
        owner_.notify_lead(job, base_.line('GONE ' + agent + ' ' + payload.get('reason', '')))
    return ''


def cursor_stop(job, agent, payload):
    """Every stop reaches the lead with its status: completed, error or aborted."""
    owner_.notify_lead(job, base_.line('TURN ' + agent + ' ' + str(payload.get('status', ''))))
    return '{}'
