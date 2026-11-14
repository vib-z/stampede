"""The earlier Core path (new --core --relay), whole: holds, sends, starts and reopen. Deleted in v0.3.0."""
import fcntl, json, os, shlex, subprocess, time, uuid
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, agents as agents_, tui as tui_, handed as handed_, settings as settings_


def deliver_core(job, lead):
    """deliver for a Codex lead in a Herdr Core terminal: its unread lines typed with hc send while it is idle or done,
    each line at most once. A send that got no answer may or may not have typed; most often a person's draft held it
    until it was stopped. Then the lines' offsets move with no acknowledgement, the lead is owed a pointer to them
    (point_owed), and nothing more is typed into that terminal until it has taken a turn, which only a submitted prompt
    gives, so the text someone may have left there is no longer in it. Until then every deliverer leaves (7) once the
    hold has its turn count, staying only for the settled look that gives it, and the owner is told once. Clearing the hold by hand, after a look at the lead's prompt, is removing
    <job>/hooks/deliver-held.json. Before every send, typing_guard says whether it may type at all and what Core's hold
    is, and that same hold limits the send. Exit 3 after DELIVER_FOR seconds of a busy or gone lead, 4 when Core does not
    answer, 6 when typing_guard refuses (nothing is typed where a person's draft could go in with it)."""
    deadline = time.monotonic() + tui_.DELIVER_FOR
    while True:
        with (job / 'hooks' / '.deliver.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0  # the deliverer running sees this line once it lets go
            while tui_.unread(job, lead) or owed(job):
                if time.monotonic() > deadline:
                    print(f'{datetime.now():%Y-%m-%d %H:%M} GAVE UP after {tui_.DELIVER_FOR}s: {lead} stayed busy, blocked, drafting or gone')
                    return 3
                try:
                    terminal = core_ready(job, lead)
                    if terminal and held(job, terminal) and hold_count(job) is not None:
                        print(f'{datetime.now():%Y-%m-%d %H:%M} HELD: a send to {lead} got no answer, so text may sit in its prompt at '
                              f'{terminal["address"]}; nothing more is typed there until it has taken a turn, or until '
                              f'{job / "hooks" / "deliver-held.json"} is removed by someone who looked')
                        return 7
                    if terminal and not held(job, terminal):
                        unsafe, seconds = hcapi_.typing_guard()
                        if unsafe:
                            print(f'{datetime.now():%Y-%m-%d %H:%M} NOT TYPED: {unsafe}; the lines stay in {job / "inbox.log"} and '
                                  f'{job / "inbox" / (lead + ".md")}')
                            return 6
                        limit = hcapi_.send_limit(seconds)
                        outcome = point_owed(job, lead, limit) if owed(job) else tui_.type_unread(job, lead, limit)
                        if outcome is None:
                            hold(job, lead, terminal['address'])
                        if outcome is not False:
                            continue
                except (ValueError, hcapi_.HcError) as error:  # the next kick from outside the sandbox delivers the line
                    print(f'{datetime.now():%Y-%m-%d %H:%M} CANNOT REACH HERDR ({base_.line(error)}): left for the next deliverer')
                    return 4
                time.sleep(tui_.DELIVER_EVERY)
        if not (tui_.unread(job, lead) or owed(job)):
            return 0


HOLD_SETTLE = None  # a test's stand-in for the setting timeouts.hold_settle


def settled(terminal):
    """The terminal's turn count when it is at rest (idle or done) and has been for timeouts.hold_settle seconds by Core's own
    clock (status_ms): no turn is under way, and none has only just ended whose count might not show yet. Else None."""
    since, settle = terminal.get('status_ms'), settings_.current().get('timeouts.hold_settle') if HOLD_SETTLE is None else HOLD_SETTLE
    if terminal.get('state') == 'live' and hcapi_.core_status(terminal) in ('idle', 'done') and isinstance(since, (int, float)) \
            and not isinstance(since, bool) and time.time() * 1000 - since >= settle * 1000:
        return terminal.get('turn') or 0
    return None


def held(job, terminal):
    """True while a send to this terminal that got no answer is unresolved. terminal: its record as core_ready gives it.
    The hold counts turns from a look taken after that send with the terminal settled at rest (settled): no turn was
    under way then, so a higher count now means a prompt was submitted since, and with it whatever sat in the prompt.
    A hold that has no such look yet takes this one if it is settled, and stands either way. Another terminal (a
    restarted lead, with a prompt of its own) ends the hold; so does removing its file."""
    path = Path(job) / 'hooks' / 'deliver-held.json'
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    if record.get('address') != terminal.get('address'):
        path.unlink(missing_ok=True)
        return False
    if not isinstance(record.get('turn'), int):
        if settled(terminal) is not None:
            save_hold(job, {**record, 'turn': settled(terminal)})
        return True
    if (terminal.get('turn') or 0) <= record['turn']:
        return True
    path.unlink(missing_ok=True)
    return False


def hold_count(job):
    """The turn count a hold stands on, or None while it has none yet (or there is no hold)."""
    try:
        turn = json.loads((Path(job) / 'hooks' / 'deliver-held.json').read_text()).get('turn')
    except (OSError, ValueError):
        return None
    return turn if isinstance(turn, int) else None


def save_hold(job, record):
    path = Path(job) / 'hooks' / 'deliver-held.json'
    temporary = path.with_name('.deliver-held.json.' + str(os.getpid()))
    temporary.write_text(json.dumps(record) + '\n')
    os.replace(temporary, path)


def hold(job, lead, address):
    """Start a hold on the lead's terminal after a send to it got no answer, and tell whoever started the job once (a
    blocked event through the relay, as the job's follower sends them; best effort). Its turn count is read now, after
    the send, and kept only when the terminal is settled at rest (settled): a count from before the send, or one taken
    while a turn is under way or has just ended, could be passed by a turn that began before the text in the prompt
    did. Without one the hold has no count yet, and held takes the first settled look."""
    key, turn = job_.core_key(job), None
    try:
        turn = settled(hcapi_.hc('get', address))
    except hcapi_.HcError:
        pass
    record = {'address': address, 'turn': turn, 'at': datetime.now().strftime('%Y-%m-%d %H:%M')}
    save_hold(job, record)
    owner = job_.job_owner(job)
    event = {'source': 'hc', 'workspace': key, 'job': str(Path(job).absolute()), 'agent': lead, 'state': 'blocked', 'kind': 'held',
             'msg': f'A message for {lead} got no answer from Herdr Core, so text may be left typed in its terminal ({address}). '
                    'Nothing more is typed there until it takes a turn: send or clear what is in its prompt.',
             'pane': f'hc:{key}/{address}', 'event_id': f'{key}/{address}|held|{uuid.uuid4().hex[:8]}', **({'owner': owner} if owner else {})}
    try:
        subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'), json.dumps(event)],
                       capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def core_ready(job, lead):
    """The lead's Core terminal (its record) when it is this job's, live, and idle or done by its own status. Whether a
    person is typing there is Core's to guard (its draft hold) and send_core's (text already in the prompt). An HcError
    when Core does not answer; None when the terminal is gone, another job's, or a shell Core put in the lead's place."""
    hcapi_.target(job)
    address = job_.core_entries(job).get(lead, {}).get('address')
    try:
        terminal = hcapi_.hc('get', address) if address else {}
    except hcapi_.HcError as error:
        if error.kind != 'not_found':
            raise
        return None
    labels = terminal.get('labels') or {}
    ready = (terminal.get('state') == 'live' and not hcapi_.shelled(terminal) and hcapi_.core_status(terminal) in ('idle', 'done')
             and labels.get('stampede.job') == job_.core_key(job) and labels.get('stampede.agent') == lead)
    return terminal if ready else None


def owed(job):
    """The line ranges a Codex lead on Herdr Core may or may not have been given: [[path, first line, last line], ...]."""
    path = Path(job) / 'hooks' / 'deliver-owed.json'
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return []


def owe(job, lead, found):
    """Record the lines of a delivery whose outcome is unknown, by their numbers in their files, before their offsets
    move; the caller holds the wake lock."""
    state_path = Path(job) / 'hooks' / ('wake-' + lead + '.json')
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    ranges = owed(job)
    for path, _, end in found:
        content, start = path.read_bytes(), state.get(str(path.resolve()), 0)
        start = 0 if start > len(content) else start
        ranges.append([str(path), content[:start].count(b'\n') + 1, content[:end].count(b'\n')])
    path = Path(job) / 'hooks' / 'deliver-owed.json'
    temporary = path.with_name('.deliver-owed.json.' + str(os.getpid()))
    temporary.write_text(json.dumps(ranges) + '\n')
    os.replace(temporary, path)


def point_owed(job, lead, limit=None):
    """Tell the lead where to read the lines it may have missed: True once that pointer was submitted, False when
    nothing was typed, None when that send got no answer either (the caller then holds the terminal again). The
    pointer is the same whoever reads it and however often, so unlike the lines themselves it may be sent again."""
    where = '; '.join(f'lines {first} to {last} of {path}' for path, first, last in owed(job))
    text = (f'[fleet-job inbox for {lead}, not typed by the owner] Herdr Core gave no answer to a delivery, so these lines '
            f'may not have reached you. Read them yourself, each once: {where}')
    submitted, said = send_core(job, lead, text, limit)
    print(f'{datetime.now():%Y-%m-%d %H:%M} {said}')
    if submitted:
        (Path(job) / 'hooks' / 'deliver-owed.json').unlink(missing_ok=True)
    return submitted


CORE_KEEPS = 86400  # seconds Herdr Core keeps a finished terminal's record (RETAIN_MS)


def session_proof(job, agent, session):
    """Whether this Claude session of the agent ever ran. A recorded 'ran' or 'never' stands; an unknown launch is placed
    by a terminal of it in hc ls --all, or Claude's session file ('ran'), or, while Core still keeps a finished record
    (24 h), by finding neither ('never'). Anything else stays 'unknown': the caller refuses rather than guess."""
    launch = job_.core_entries(job).get(agent, {}).get('launches', {}).get(session)
    if launch and launch.get('proof') == 'ran':
        return 'ran'
    if agents_.claude_session_file(session):  # every source of evidence before never
        handed_.prove(job, agent, session, 'ran')
        return 'ran'
    try:
        found = hcapi_.hc('ls', '--all', '--label', 'stampede.job=' + job_.core_key(job), '--label', 'stampede.agent=' + agent,
                   '--label', 'stampede.session=' + session).get('terminals', [])
    except hcapi_.HcError:
        return 'never' if launch and launch.get('proof') == 'never' else 'unknown'
    if found:
        proof = 'ran'
    elif launch and launch.get('proof') == 'never':
        return 'never'
    elif launch and time.time() - launch.get('at', 0) < CORE_KEEPS:
        proof = 'never'
    else:
        return 'unknown'
    handed_.prove(job, agent, session, proof)
    return proof


def app_space(job):
    """The Herdr app space a Core job asked to show in (new --core --app-space), or ''."""
    path = Path(job) / 'app-space'
    return path.read_text().strip() if path.is_file() else ''


def app_labels(job, agent, role):
    """The labels that make the Herdr app show a terminal: herdr.space=<the job's space> and herdr.tab=<the agent's
    name>, Herdr's own mechanism, only for a job that asked and only for its lead and workers (the follower and wait
    terminals stay out of the window). The tab id is the agent's name, never a terminal title."""
    space = app_space(job)
    if not space or role not in ('lead', 'worker'):
        return []
    return ['--label', 'herdr.space=' + space, '--label', 'herdr.tab=' + agent]


def core_run(job, agent, role, program, cwd, session=None):
    """Start one program of this job in its own Core terminal (no parent, no notes), the caller holding the agent's launch
    lock, and bind it. session: the Claude session it runs, labelled on the terminal and proved per session. A failed
    hc run that spawned all the same (a call that timed out) is adopted by its labels; otherwise the entry is failed
    and the error raised."""
    key = job_.core_key(job)
    launches = dict(job_.core_entries(job).get(agent, {}).get('launches', {}))
    if session and launches.get(session, {}).get('proof') != 'ran':
        launches[session] = {'proof': 'unknown', 'at': int(time.time())}  # a new launch has not run until shown
    launch = uuid.uuid4().hex[:8]  # this attempt's own label: after a lost answer, only its terminal is looked for
    job_.bind(job, agent, {'state': 'starting', 'role': role, 'cwd': str(cwd), **job_.endpoint(job), 'launches': launches, 'launch': launch},
         fresh=True)
    labels = [part for k, v in (('job', key), ('agent', agent), ('role', role)) for part in ('--label', f'stampede.{k}={v}')]
    labels += ['--label', 'stampede.session=' + session] if session else []
    labels += ['--label', 'stampede.launch=' + launch]
    shown = app_labels(job, agent, role)
    # a name is free or it is not: another job's terminal, or the shell Core left in a lost launch's place, may hold the
    # agent's own, and after a second loss the first spare too. Identity is the address, never the name.
    names = [agent, agent[:27] + '-' + key[3:7]] + [agent[:23] + '-' + uuid.uuid4().hex[:8] for _ in range(4)]
    for name in names:
        try:
            terminal = hcapi_.hc('run', '--bg', '--no-parent', '--no-notify', '--name', name, '--cwd', str(cwd), *labels, *shown, '--',
                          *hcapi_.launch_env(job), *program)
            break
        except hcapi_.HcError as error:
            if error.kind == 'name_taken' and name != names[-1]:
                continue
            try:  # this launch's own terminal, live or already finished: by its launch label, never an older one's
                spawned = hcapi_.hc('ls', '--all', *labels[:4], *labels[-2:]).get('terminals', [])
            except hcapi_.HcError as lookup:  # the entry stays starting: a later start or reopen reconciles it by its labels
                raise hcapi_.CoreUnknown(agent, f'hc run answered {base_.line(error)}, and hc ls could not tell whether it started '
                                         f'({base_.line(lookup)})') from None
            live = [t for t in spawned if t.get('state', 'live') == 'live']
            if not live:
                if session:
                    handed_.prove(job, agent, session, 'ran' if spawned else 'never')
                job_.bind(job, agent, {'state': 'failed', 'reason': base_.line(error) + ('; it started, then ended' if spawned else '')})
                raise
            terminal = live[0]
            break
    if session:
        handed_.prove(job, agent, session, 'ran')
    job_.bind(job, agent, {'state': 'live', 'address': terminal['address'], 'name': terminal.get('name') or name})
    return terminal['address']


def core_outcome(job, agent, address, who, brief, plain=False):
    """After a launch, from the agent's own status: 'started' (working, idle or done), 'not ready' (a live terminal that
    is blocked, at an error or silent after 30 s: it stays this job's agent), or 'failed' (its terminal finished).
    plain: a program with no status (the follower): live after 3 s is 'started'; Core not answering is 'unknown'."""
    try:
        hcapi_.hc('wait', address, '--timeout', '3' if plain else '30', wait=3 if plain else 30)
    except hcapi_.HcError:
        pass
    try:
        terminal = hcapi_.hc('get', address)
    except hcapi_.HcError as error:  # unconfirmed: it may run, so it stays this job's
        if plain:
            hcapi_.unknown(job, hcapi_.CoreUnknown(agent, f'started as {address}, then hc get failed ({base_.line(error)})'))
            return 'unknown'
        print(f'NOT READY {agent}: {base_.line(error)}; read it with hc read {address} once Herdr Core answers')
        return 'not ready'
    word = hcapi_.core_status(terminal)
    if terminal.get('state') != 'live':
        try:
            tail = hcapi_.hc('read', address, '--lines', '20').get('text', '')
        except hcapi_.HcError:
            tail = ''
        reason = f'{terminal.get("reason") or "ended"} exit {terminal.get("exit_code")}'
        job_.bind(job, agent, {'state': 'failed', 'reason': reason})
        print(f'FAILED {agent} ({reason}): {base_.line(tail)}')
        return 'failed'
    if plain:
        return 'started'
    if word in ('working', 'idle', 'done'):
        print(f'STARTED {agent} ({address})')
        return 'started'
    resend = f'then stampede tell {job} {who} "Read {brief}" if it went idle without its first prompt'
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
    if kind in handed_.HANDED:
        why = ('reports its status on Herdr Core, but stampede has no turn hook or empty-prompt check for it there yet'
               if kind == 'kimi' else 'reports no OSC 7501 status, so Herdr Core cannot run it')
        raise ValueError(f'{kind.capitalize()} {why}: hand it to a Herdr TUI pane at its shell prompt with --pane <pane>')
    job, brief = Path(job).absolute(), Path(brief).expanduser().absolute()  # the agent may start in another folder
    hcapi_.target(job)
    cwd = Path(cwd or job.parent).expanduser().resolve()
    if yolo_in is not None and Path(yolo_in).expanduser().resolve() != cwd:
        raise PermissionError(f'--yolo-in {yolo_in} must be the --cwd the worker starts in ({cwd}): its own worktree')
    with job_.launching(job, agent):
        try:
            running = handed_.live_terminal(job, agent)
        except hcapi_.HcError as error:
            raise ValueError(f'Herdr Core did not answer ({base_.line(error)}): cannot tell whether {agent} runs, so nothing started') from None
        if running:
            raise ValueError(f'{agent} is already running at {running["address"]}')
        handed_.refuse_handed(job, agent)
        args = agents_.cli_args(job, agent, kind, model, effort, list(reports), lead=lead, yolo_in=cwd if yolo_in is not None else None)
        args += ['--no-daemon'] if kind == 'codex' else []  # else Codex runs its commands outside the terminal
        session = str(uuid.uuid4()) if kind == 'claude' else ''
        program = [agents_.cli(kind)] + args + (['--session-id', session] if session else [])
        job_.record(job, agent, kind, brief, args, session)
        pointer = f'You are {agent} in a herdr fleet. Read {brief} and do everything it says.'
        try:
            address = core_run(job, agent, 'lead' if lead else 'worker', program + [pointer], cwd, session or None)
        except hcapi_.CoreUnknown as error:
            job_.snapshot(job)
            return hcapi_.unknown(job, error)
        except hcapi_.HcError as error:  # confirmed: no terminal of the job runs it, and its entry says failed
            job_.snapshot(job)
            print(f'FAILED {agent} ({base_.line(error)})')
            return 1
        job_.snapshot(job)
        return 0 if core_outcome(job, agent, address, 'lead' if lead else agent, brief) == 'started' else 1
REOPEN_EVERY, REOPEN_DEADLINE = 5, 90  # seconds between a reopen's REOPENED writes, and before it gives up


def reopen(job, lead_only=False, prompt=False, fresh=False):
    """Start what is missing of a Core job, once each and never a second copy of a live one: for an open job its marker,
    owner tag and follower; its lead, resumed; with no lead_only, each worker that is not live (Claude resumed, Codex
    fresh, with its brief pointer only with prompt). A finished job resumes its agents for inspection only. A restarted
    lead of an open job must acknowledge both its inbox files (exit 3 when it does not). fresh: every agent it starts
    begins a new session, with its recorded flags and its brief, and nothing is resumed."""
    job = Path(job).absolute()
    key, (people, lead) = job_.core_key(job), job_.roster(job)
    finished, outcomes = (job / 'finished').is_file(), {}
    hcapi_.target(job)
    selected = [lead] + ([] if lead_only else [a for a in people if a != lead])
    folders = {}  # every folder this reopen may start something in, checked before anything starts
    for agent in selected + ([] if finished else ['relay-' + key[3:]]):
        folders.setdefault(str(job_.core_entries(job).get(agent, {}).get('cwd') or job.parent), []).append(agent)
    gone = [f'{folder} ({", ".join(agents)})' for folder, agents in folders.items() if not Path(folder).is_dir()]
    if gone:
        raise ValueError('cwd gone: ' + '; '.join(gone) + ': git worktree add each back first; nothing was started')
    if not finished:
        job_.mark_job(key, job)
        if job_.job_owner(job):
            job_.tag_owner(job, key, job_.job_owner(job))
        relay = 'relay-' + key[3:]
        with job_.launching(job, relay):
            if not handed_.live_terminal(job, relay):
                outcomes[relay] = reopen_run(job, relay, 'relay', [str(base_.FOLLOWER), str(job)], job.parent, plain=True)
    pending = job / 'reopen-pending'  # a restarted lead that has not yet acknowledged both inbox files
    for agent in selected:
        with job_.launching(job, agent):  # the lock first, then its entry and row: a start that ran meanwhile is seen
            if job_.core_entries(job).get(agent, {}).get('backend') == 'tui':  # handed: never started on Core
                outcomes[agent] = handed_.reopen_handed(job, agent)
            else:
                outcomes[agent] = reopen_agent(job, agent, job_.agent_rows(job).get(agent, {}), prompt, agent == lead,
                                               pending if agent == lead and not finished else None, fresh)
    job_.snapshot(job)
    if not [agent for agent, outcome in outcomes.items() if outcome != 'live']:
        print(f'LIVE {key}: no agent to restart')
    code = 1 if [o for o in outcomes.values() if o in ('failed', 'unknown', 'not ready', 'missing', 'unbriefed')] else 0
    if finished or not pending.exists() or outcomes.get(lead) not in ('started', 'live'):
        return code
    acked = acknowledged(job, lead)  # also on a retry with the lead live: an earlier reopen may have timed out
    if acked == 0:
        pending.unlink()
    return acked or code


def reopen_run(job, agent, role, program, cwd, plain=False, session=None, brief=None):
    """One restart and what came of it, said by start's rule: 'started', 'not ready' (a live terminal blocked, at an
    error or silent: still the job's), 'failed' (confirmed) or 'unknown' (kept). plain: the follower, which has no status."""
    try:
        address = core_run(job, agent, role, program, cwd, session)
    except hcapi_.CoreUnknown as error:
        hcapi_.unknown(job, error)
        return 'unknown'
    except hcapi_.HcError as error:
        print(f'FAILED {agent} ({base_.line(error)}): it did not start')
        return 'failed'
    if not plain:
        return core_outcome(job, agent, address, 'lead' if role == 'lead' else agent, brief)
    print(f'RESTARTED {agent} ({address})')
    if core_outcome(job, agent, address, agent, None, plain=True) != 'started':
        return 'failed' if job_.core_entries(job).get(agent, {}).get('state') == 'failed' else 'unknown'
    return 'started'


def reopen_agent(job, agent, row, prompt, lead, pending=None, fresh=False):
    """Restart one agent unless a live terminal of the job runs it: 'live', 'started', 'failed' or 'unknown'. The caller
    holds its launch lock. pending: written before the lead starts, so even an interrupted reopen leaves its
    acknowledgement owed."""
    if handed_.live_terminal(job, agent):
        return 'live'
    kind, args, session = row.get('kind', 'claude'), shlex.split(row.get('args', '')), row.get('session', '')
    if kind in handed_.HANDED:  # never on Core, whatever its entry says
        print(f'UNKNOWN {agent}: Herdr Core cannot run {kind}, and it has no handed entry: start it with fleet-job start --pane')
        return 'unknown'
    pointer = f'You are {agent} in a herdr fleet. Read {row.get("brief")} and do everything it says.'
    if fresh:  # a new session, the recorded flags and the brief; nothing resumed
        if kind == 'claude':
            session = str(uuid.uuid4())
            job_.record(job, agent, kind, row.get('brief') or '-', args, session)
        program = [agents_.cli(kind)] + args + (['--session-id', session] if kind == 'claude' else []) + [pointer]
        cwd = job_.core_entries(job).get(agent, {}).get('cwd') or Path(job).parent
        if pending:
            pending.write_text(datetime.now().strftime('%Y-%m-%d %H:%M') + '\n')
        return reopen_run(job, agent, 'lead' if lead else 'worker', program, cwd, session=session if kind == 'claude' else None,
                          brief=row.get('brief'))
    proof = session_proof(job, agent, session) if kind == 'claude' and session else 'never'
    if kind == 'claude' and proof == 'unknown':
        print(f'UNKNOWN {agent}: cannot tell whether its session {session} ever ran (no terminal of it in hc ls --all '
              f'--label stampede.job={job_.core_key(job)} --label stampede.agent={agent}, no Claude session file): check '
              'there, then start it again with fleet-job start; nothing was restarted')
        return 'unknown'
    if kind == 'claude' and proof == 'ran':
        program = [agents_.cli(kind), '--resume', session] + args
    elif kind == 'claude':  # it never ran: its own session id, fresh, with its brief
        if not session:
            session = str(uuid.uuid4())
            job_.record(job, agent, kind, row.get('brief') or '-', args, session)
        program = [agents_.cli(kind)] + args + ['--session-id', session, pointer]
    elif session:  # Codex, with the session its own notify recorded: resumed, without its daemon as at start
        program = [agents_.cli(kind), 'resume'] + args + [session] + ([pointer] if prompt else [])
    else:  # a Codex lead that never ended a turn has no session to resume: it starts with its brief, as a fresh one
        program = [agents_.cli(kind)] + args + ([pointer] if prompt or lead else [])
    cwd = job_.core_entries(job).get(agent, {}).get('cwd') or Path(job).parent
    if pending:
        pending.write_text(datetime.now().strftime('%Y-%m-%d %H:%M') + '\n')
    return reopen_run(job, agent, 'lead' if lead else 'worker', program, cwd, session=session if kind == 'claude' else None,
                      brief=row.get('brief'))


def acknowledged(job, lead):
    """A restarted lead reads its two inbox files once its own wake hook delivers them: write REOPENED <lead> <attempt>
    to each every REOPEN_EVERY seconds until that file's hook has acknowledged this attempt, or REOPEN_DEADLINE passes.
    Reopen never moves a read offset, so each delivery carries every line written there while the lead was down."""
    attempt, acks = uuid.uuid4().hex[:12], Path(job) / 'hooks' / ('ack-' + lead + '.json')
    pending, deadline = {str(p.resolve()) for p in tui_.watched(job, lead, True)}, time.time() + REOPEN_DEADLINE
    while pending and time.time() < deadline:
        for path in sorted(pending):
            base_.append(path, f'REOPENED {lead} {attempt}')
        if job_.lead_kind(job) == 'codex':  # no file hook: its deliverer types the lines, and that is its acknowledgement
            tui_.deliver_soon(job)
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


def drafted(address):
    """True when the last 8 non-empty screen lines show no empty-prompt marker: text already typed, which Core would
    paste after. Core 0.1.20 holds a send only while a person is typing; a draft left alone past draft_wait, and text
    typed with hc keys, still gets the message pasted after it. Cut here, since hc read may give the whole screen, whose
    scrollback can hold a marker. A screen Core cannot read counts as empty."""
    try:
        screen = hcapi_.hc('read', address, '--lines', '8').get('text', '')
    except hcapi_.HcError:
        return False
    return handed_.typed(screen)


def tell_core(job, name, text):
    """Prompt a Codex agent in its Core terminal: send_core's one SUBMITTED or FAILED line, and exit 2 on FAILED."""
    submitted, said = send_core(job, name, text)
    print(said)
    if not submitted:
        raise SystemExit(2)


SEND_REFUSED = ('not_found', 'machine_unknown', 'finished', 'unavailable', 'blocked', 'status_mismatch', 'invalid_params', 'config',
                'cancelled')  # hc send's own error kinds (hc schema 0.1.20): each says nothing was typed


def send_core(job, name, text, limit=None):
    """Type one prompt into a Codex agent's Core terminal by its status: idle types only while idle (atomic); done types
    at once, so a worker that turned working in between takes it as a message during its turn. (submitted, its one
    SUBMITTED or FAILED line): True, False when nothing was typed, or None when nobody can tell (hc gave no answer, or
    failed in no way Core names), which the line says to read before any resend. It writes only through hc send, which
    refuses a blocked terminal and, from Core 0.1.20, waits while a person is typing there: no key is ever pressed,
    since Core cannot guard one. The send is stopped limit seconds in (default send_limit()), before Core's hold could
    run out and type it after a draft someone left. A slash command, or text already typed in the prompt, is refused
    with the step to do by hand."""
    hcapi_.target(job)
    address, lost = job_.core_entries(job).get(name, {}).get('address'), None
    try:
        terminal = hcapi_.hc('get', address) if address else {}
    except hcapi_.HcError as error:
        terminal, lost = {}, None if error.kind == 'not_found' else error
    labels, word = terminal.get('labels') or {}, hcapi_.core_status(terminal)
    refused = {'working': 'working: tell it after its turn', 'blocked': f'blocked: hc read {address}', 'error': f'error: hc read {address}'}
    if lost:
        why = 'Herdr Core did not answer: ' + base_.line(lost)
    elif labels.get('stampede.job') != job_.core_key(job) or labels.get('stampede.agent') != name:
        why = "not this job's terminal"
    elif terminal.get('state') == 'live' and hcapi_.shelled(terminal):
        why = (f'its program was lost and Herdr Core put a shell in its place at {address}: start it again with bash '
               f'{Path(job).absolute() / "reopen.sh"}')
    elif terminal.get('state') != 'live' or word not in ('idle', 'done', *refused):
        why = 'not ready'
    elif word in refused:
        why = refused[word]
    else:
        try:
            if text.startswith('/') and '\n' not in text:  # pasted, Codex takes a slash command as chat
                keys = ' '.join(['space' if c == ' ' else c for c in text] + ['enter'])
                why = (f'a slash command needs typed keys, which Core cannot guard: when hc get {address} shows idle, '
                       f'run hc keys {address} {keys}')
            elif drafted(address):  # Core pastes after it; clearing it could erase someone's own typing
                why = (f'text is already typed in its prompt; Core cannot clear it safely: read it with hc read {address}, '
                       f'clear it with hc keys {address} ctrl+c when hc get shows idle, then tell again')
            else:
                sent = hcapi_.hc('send', *(['--if', 'idle'] if word == 'idle' else []), '--', address, text, limit=limit or hcapi_.send_limit())
                quiet = ('' if sent.get('started') is not False else
                         f'; it has not gone working yet: read it with hc read {address} before any resend')
                return True, f'SUBMITTED {name} ({address}){quiet}'
        except hcapi_.HcError as error:
            if error.kind not in SEND_REFUSED and error.code not in (9, 10, 11):  # no answer, or a failure Core does not name
                return None, (f'FAILED {name} ({base_.line(error)}; a send still held by a draft types nothing once stopped, '
                              f'but read it with hc read {address} before any resend)')
            held = {'cancelled': 'Herdr Core cancelled the send before it typed anything: tell again if still needed'}
            why = {9: refused['blocked'], 10: refused['working'], 11: 'not ready'}.get(error.code) or held.get(error.kind, base_.line(error))
    return False, f'FAILED {name} ({why})'


def core_hint():
    """What new adds to its error when the Herdr TUI cannot take the job but a Herdr Core answers on its socket here
    (asked there, never started): the way to run the job on Core. The TUI stays the default backend, so nothing is
    switched for the caller. '' when no core answers."""
    if subprocess.run([str(base_.FOLLOWER), '--alive'], capture_output=True).returncode:
        return ''
    return '; Herdr Core answers here, so this job can run on it: new --core --file <ask.md> [--cwd <repo>]'


def new_core(ask_file, name, review, fork, cwd, kind='claude', app=False, settings=None):
    """A whole job on Herdr Core. The record first (folder, backend, key, owner and its tag, marker, the lead's row), then
    the follower, then the lead with its brief pointer as the first prompt. Only a confirmed failure (the relay or the lead
    never ran, or its terminal already finished) takes the start back; a live lead that is not ready stays one job.
    kind: the lead's CLI; a Codex lead runs without its daemon, as a Codex worker does. app: the job's lead and workers
    carry the Herdr app's labels (<job>/app-space holds the space id)."""
    if fork is not None and not base_.SESSION.fullmatch(fork):
        raise ValueError(f'--fork takes a Claude session id (a UUID, such as $CLAUDE_CODE_SESSION_ID), not {fork!r}')
    repo, program = job_.core_repo(cwd), agents_.cli(kind)
    settings = settings or settings_.for_new(repo, {'lead.kind': kind})
    ask = Path(ask_file).expanduser().read_text()
    owner = job_.starter(os.environ.get('HERDR_WORKSPACE_ID'))
    job = repo / ('.herdr-' + (name or job_.slug(ask)))
    if job.exists():
        raise ValueError(f'{job} already exists: a job folder is used once; start another job with --name')
    key = job_.job_key(job)  # the path's hash: a folder made again at this path has the same key
    try:
        earlier = hcapi_.hc('ls', '--label', 'stampede.job=' + key).get('terminals', [])
    except hcapi_.HcError as error:
        raise ValueError(f'Herdr Core did not answer ({base_.line(error)}): nothing was made') from None
    if earlier:
        raise ValueError('terminals of an earlier job at this path still run: kill them '
                         f'(hc ls --all --label stampede.job={key}) or use another --name')
    lead = job_.make_job(repo, job, ask, owner, review)
    settings_.save(job, settings)
    (job / 'backend').write_text('core\n')
    (job / 'endpoint').write_text(json.dumps({'session': (os.environ.get('HC_SESSION') or '').strip(),
                                              'socket': os.environ.get('HC_SOCKET') or ''}) + '\n')
    hcapi_.target(job)
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    if app:
        (job / 'app-space').write_text('stampede-' + key[3:] + '\n')
    brief.write_text(agents_.lead_brief(job, lead, owner, review, fork, key, kind=kind))
    args = agents_.cli_args(job, lead, kind, *agents_.lead_model(kind, job=job), [], lead=True)
    args += ['--no-daemon'] if kind == 'codex' else []  # else Codex runs its commands outside the terminal
    session = str(uuid.uuid4()) if kind == 'claude' else ''  # Codex names its own session, at its first turn end
    job_.record(job, lead, kind, brief, args, session)  # the fork stays out: a reopen resumes the lead's own session
    job_.mark_job(key, job)
    (job_.events_dir() / 'owners' / key).unlink(missing_ok=True)  # a folder used before (same path, same key) had its own
    if owner:
        job_.tag_owner(job, key, owner)
    job_.snapshot(job)  # reopen.sh exists before anything starts
    relay = 'relay-' + key[3:]
    try:
        with job_.launching(job, relay):
            follower = core_outcome(job, relay, core_run(job, relay, 'relay', [str(base_.FOLLOWER), str(job)], repo), relay, None, plain=True)
        if follower == 'failed':  # confirmed: the job would run with no one reporting its workers' exits
            return hcapi_.start_failed(job, key, relay, job_.core_entries(job)[relay].get('reason', 'the follower ended'))
        if follower == 'unknown':
            job_.snapshot(job)
            return 1
        with job_.launching(job, lead):
            program = [program] + (['--resume', fork, '--fork-session'] if fork else []) + args + (['--session-id', session] if session else [])
            address = core_run(job, lead, 'lead', program + [f'You are {lead}. Read {brief} and do everything it says.'], repo,
                               session or None)
            outcome = core_outcome(job, lead, address, 'lead', brief)
    except hcapi_.CoreUnknown as error:
        job_.snapshot(job)
        return hcapi_.unknown(job, error)
    except hcapi_.HcError as error:
        return hcapi_.start_failed(job, key, relay, base_.line(error))
    if outcome == 'failed':
        return hcapi_.start_failed(job, key, relay, job_.core_entries(job)[lead].get('reason', 'the lead ended'))
    job_.snapshot(job)
    if outcome == 'started':
        print(lead + ' ' + str(job))
        return 0
    return 1
