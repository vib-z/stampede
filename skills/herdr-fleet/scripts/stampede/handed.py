"""Handed panes: an agent Herdr Core cannot run, started in a Herdr TUI pane of a relay job. Deleted in v0.3.0."""
import contextlib, fcntl, json, os, re, shlex, subprocess, time, uuid
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, agents as agents_, tui as tui_, out as out_


def live_terminal(job, agent):
    """This job's live terminal for the agent: its bound address, else one the job's and the agent's labels name,
    which is adopted (bound). None when no live terminal runs it; a shell Core put in a lost agent's place is not one."""
    key = job_.core_key(job)
    address = job_.core_entries(job).get(agent, {}).get('address')
    if address:
        try:
            terminal = hcapi_.hc('get', address, job=job)
        except hcapi_.HcError as error:
            if error.kind != 'not_found':
                raise
            terminal = {}
        labels = terminal.get('labels') or {}
        if terminal.get('state') == 'live' and labels.get('stampede.job') == key and labels.get('stampede.agent') == agent \
                and not hcapi_.shelled(terminal):
            return terminal
    for found in hcapi_.hc('ls', '--label', 'stampede.job=' + key, '--label', 'stampede.agent=' + agent, job=job).get('terminals', []):
        if found.get('state', 'live') != 'live':
            continue
        try:  # hc ls shows no labels and no argv; the terminal's own record says which Claude session it runs
            shown = hcapi_.hc('get', found['address'], job=job)
        except hcapi_.HcError:
            shown = {}
        if hcapi_.shelled(shown):
            continue
        job_.bind(job, agent, {'state': 'live', 'address': found['address'], 'name': found.get('name') or agent})
        session = (shown.get('labels') or {}).get('stampede.session')
        if session:
            prove(job, agent, session, 'ran')
        return found
    return None


def prove(job, agent, session, proof):
    """Record whether one Claude session of an agent ran: 'ran', 'never' or 'unknown' (core.json, per session). 'ran' is
    for good: a later attempt that did not launch says nothing about the session itself."""
    launches = dict(job_.core_entries(job).get(agent, {}).get('launches', {}))
    launch = launches.get(session, {'at': int(time.time())})
    launches[session] = {**launch, 'proof': 'ran' if launch.get('proof') == 'ran' else proof}
    job_.bind(job, agent, {'launches': launches})


# Kinds stampede does not start on Herdr Core, so a Core job hands them to a TUI pane. Cursor and Hermes report no OSC 7501
# status. Kimi 2.5.3 does (seen at its trust dialog on hc 0.1.20, 11 Nov 2026), but has no turn hook, and its empty prompt
# is unchecked, so it stays handed until a signed-in run proves both.
HANDED = ('cursor', 'hermes', 'kimi')


def session_of(shown):
    """The agent session Herdr shows for an agent ({kind: id, value}), or None: not shown yet, or malformed."""
    session = shown.get('agent_session')
    value = session.get('value') if isinstance(session, dict) and session.get('kind') == 'id' else None
    return value if isinstance(value, str) and value else None


def replaced(entry, shown):
    """True when the agent Herdr shows under a handed agent's name is another process: a new agent session, or no
    finished turn (completion_seq null) where the entry recorded one.
    ponytail: a restart by hand under the same name, before its first turn and before Herdr shows its session, is not
    told apart; upgrade: a process id from Herdr."""
    session = session_of(shown)
    return (bool(entry.get('session')) and session is not None and session != entry['session']
            or isinstance(entry.get('completion'), int) and 'completion_seq' in shown and shown['completion_seq'] is None)


def counted(value):
    """A completion_seq Herdr showed: an int, or None (null: the agent has finished no turn). Anything else is not one."""
    return value is None or isinstance(value, int) and not isinstance(value, bool)


def briefing(job, agent, brief):
    """The exact tell that sends a handed agent its brief pointer, for the lead to run by hand."""
    return shlex.join(['fleet-job', 'tell', str(Path(job).absolute()), agent, agents_.pointer(agent, brief)])


def start_handed(job, agent, kind, pane, brief, model, effort, reports, yolo_in, cwd, lead):
    """An agent Herdr Core cannot run, handed to a Herdr TUI pane at its shell prompt inside a Core job: the TUI start,
    under the same launch lock and one-live-launch rule as a Core start. The pane is claimed (its mark) and the entry
    written (starting, a new launch id, the exact start) before Herdr starts it; it is live only once Herdr shows its
    identity there. A Herdr error other than a startup dialog is settled by a whole agent list: its agent there is
    adopted, none is failed (its CLI may still run there, undetected), anything unclear is UNKNOWN (entry and mark
    kept: reopen settles it, never a second launch)."""
    if kind not in HANDED:
        raise ValueError(f'Herdr Core runs {kind}: start it with --cwd <dir>, never --pane' if kind in ('claude', 'codex')
                         else f'a Core job hands cursor, hermes or kimi to a pane, not {kind}')
    if cwd:
        raise ValueError('a handed agent starts in the folder of its --pane; --cwd is for an agent Herdr Core runs')
    if lead:
        raise ValueError('the lead runs on Herdr Core, never in a pane')
    if not base_.PANE_ID.fullmatch(pane):
        raise ValueError(f'--pane takes a Herdr pane id such as w1:p2, not {pane!r}')
    job, brief = Path(job).absolute(), Path(brief).expanduser().absolute()
    hcapi_.target(job)
    with job_.launching(job, agent):
        try:
            running = live_terminal(job, agent)
        except hcapi_.HcError as error:
            raise ValueError(f'Herdr Core did not answer ({base_.line(error)}): cannot tell whether {agent} runs, so nothing started') from None
        if running:
            raise ValueError(f'{agent} is already running at {running["address"]}')
        refuse_handed(job, agent)
        yolo = tui_.pane_yolo(pane, yolo_in, lead)
        args = agents_.cli_args(job, agent, kind, model, effort, list(reports), yolo_in=yolo)
        again = ['fleet-job', 'start', str(job), agent, '--kind', kind, '--pane', pane, '--brief', str(brief)]
        again += [*(['--model', model] if model else []), *(['--effort', effort] if effort else []),
                  *[part for report in reports for part in ('--report', report)], *(['--yolo-in', str(yolo)] if yolo else [])]
        ident = uuid.uuid4().hex[:12]
        claim_pane(job, agent, pane, {'state': 'starting', 'role': 'worker', 'backend': 'tui', 'pane': pane, 'kind': kind,
                                      'launch': ident, 'brief': str(brief), 'briefed': False, 'start': shlex.join(again)})
        job_.record(job, agent, kind, brief, args)

        def failed(error, note=''):
            job_.bind(job, agent, {'state': 'failed', 'reason': base_.line(error)})
            release_pane(job, agent)
            job_.snapshot(job)
            out_.emit('FAILED', f'FAILED {agent} ({base_.line(error)}){note}', agent=agent, pane=pane, reason=base_.line(error))
            return 1
        try:
            herdrapi_.herdr('pane', 'rename', pane, agent)
        except (herdrapi_.HerdrError, ValueError) as error:  # nothing was started
            return failed(error)
        try:
            blocked = tui_.launch(agent, kind, pane, args)
        except (herdrapi_.HerdrError, ValueError) as error:
            try:
                found = herdrapi_.herdr_agents().get(pane)
            except ValueError as lookup:
                job_.snapshot(job)
                out_.emit('UNKNOWN', f'UNKNOWN {agent}: {base_.line(error)}, and Herdr could not tell whether it started ({base_.line(lookup)}). Nothing was '
                          f'taken back: once Herdr answers, bash {job / "reopen.sh"} adopts it or names the start, never a second copy',
                          agent=agent, pane=pane, reason=base_.line(error), retry='bash ' + str(job / 'reopen.sh'))
                return 1
            if not found or found.get('name') != agent or found.get('agent') != kind:
                return failed(error, f': Herdr did not see {kind} start in pane {pane}, but its CLI may still run there: read it '
                                     f'with herdr pane read {pane} --source visible --lines 30, and end it there with /exit')
            blocked = found.get('agent_status') == 'blocked'  # it started all the same
        why = commit_handed(job, agent, pane)
        job_.snapshot(job)
        if why:
            out_.emit('UNKNOWN', f'UNKNOWN {agent}: {why}, so it is not settled as this job\'s launch and gets no brief. Nothing was taken back: '
                      f'once Herdr shows it, bash {job / "reopen.sh"} settles it',
                      agent=agent, pane=pane, reason=why, retry='bash ' + str(job / 'reopen.sh'))
            return 1
    if blocked:
        out_.emit('BLOCKED', f'BLOCKED {agent}: clear the startup dialog in pane {pane}, then stampede tell {job} {agent} "Read {brief}"',
                  agent=agent, pane=pane, retry=f'stampede tell {job} {agent} "Read {brief}"')
        return 1
    why = prompt_handed(job, agent, agents_.pointer(agent, brief))
    if why:
        out_.emit('NOT BRIEFED', f'NOT BRIEFED {agent} (pane {pane}): {why}. It runs as this job\'s {agent}, so never start a second one: '
                  f'read its screen, and only once its prompt is empty and idle: {briefing(job, agent, brief)}',
                  agent=agent, pane=pane, reason=why, retry=briefing(job, agent, brief))
        return 1
    out_.emit('STARTED', f'STARTED {agent} (pane {pane})', agent=agent, pane=pane)
    return 0


def commit_handed(job, agent, pane):
    """Settle a handed launch as live once Herdr shows its name in its pane: the identity of a handed agent is its name
    and pane (Herdr names are unique, and only a start gives one), with its agent session once Herdr shows one. Records
    its completion_seq as its turn baseline, null included (a fresh agent's). Else why not, and it stays starting."""
    try:
        shown = herdrapi_.herdr_shown(pane)
    except ValueError as error:
        return f'Herdr did not show it in pane {pane} ({base_.line(error)})'
    seq = shown.get('completion_seq')
    if shown['name'] != agent or not counted(seq):
        return f'Herdr shows no clear identity for {agent} in pane {pane} (name {shown["name"]!r}, completion_seq {seq!r})'
    session = session_of(shown)
    job_.bind(job, agent, {'state': 'live', 'completion': seq, **({'session': session} if session else {})})
    return None


def known(job, agent):
    """A handed agent's entry with what the job's follower learned about this launch (its record tui:<pane>|<launch> in
    relay-state.json, which it replaces whole): the agent session and completion_seq it saw, and 'ended', the reason,
    when it saw the launch end or be replaced. Without a readable record, the entry as it is."""
    entry = dict(job_.core_entries(job).get(agent, {}))
    path = Path(job) / 'relay-state.json'
    try:
        records = json.loads(path.read_text()).get('terminals', {}) if path.is_file() else {}
    except (OSError, ValueError, AttributeError):
        records = {}
    seen = records.get(f'tui:{entry.get("pane")}|{entry.get("launch")}') if entry.get('backend') == 'tui' else None
    if isinstance(seen, dict):
        entry['session'] = entry.get('session') or seen.get('session')
        entry['completion'] = seen['completion'] if isinstance(seen.get('completion'), int) else entry.get('completion')
        if seen.get('finished'):
            entry['ended'] = seen.get('ended') or 'ended'
    return entry


def handed_state(job, agent):
    """Whether this job's handed agent runs: ('live', row) when its recorded pane runs its name and kind, as its live
    launch (its agent session, once both are known, the same) or its unsettled one; ('other', row) when that pane runs its
    name otherwise (ambiguous); ('missing', None) when a whole list shows no agent of its name there; ('none', None) for an
    agent never handed (no Herdr call). What the follower learned counts too: a launch it saw end, or one whose session or
    completion differs from Herdr's now, is not this launch. Anything Herdr does not show clearly is a ValueError."""
    entry = known(job, agent)
    if entry.get('backend') != 'tui':
        return 'none', None
    pane = entry.get('pane')
    row = herdrapi_.herdr_agents().get(pane)
    if row is None:
        return 'missing', None
    if not isinstance(row.get('name'), str):
        raise ValueError(f'pane {pane} runs an agent Herdr shows no name for')
    if row['name'] != agent:
        return 'missing', None
    if row.get('agent') != entry.get('kind') or entry.get('state') not in ('live', 'starting') or entry.get('ended'):
        return 'other', row
    if entry.get('state') == 'live' and replaced(entry, row):
        return 'other', row
    return 'live', row  # its live launch, or its own unsettled one (commit_handed settles it)


def refuse_handed(job, agent):
    """One live launch per agent across both backends: refuse while a Herdr pane runs this job's agent, or may."""
    try:
        state, _ = handed_state(job, agent)
    except ValueError as error:
        raise ValueError(f'Herdr did not answer clearly ({base_.line(error)}): cannot tell whether {agent} runs in its pane, so '
                         'nothing started') from None
    pane = job_.core_entries(job).get(agent, {}).get('pane')
    if state == 'live':
        raise ValueError(f'{agent} is already running in pane {pane}')
    if state == 'other':
        raise ValueError(f'pane {pane} runs {agent}, but not as the launch this job recorded: read it with herdr agent get '
                         f'{pane}, then end it or use another name; nothing started')


@contextlib.contextmanager
def marks():
    """The handed marks' folder, held for one claim or removal at a time (<events>/handed/.lock)."""
    folder = job_.events_dir() / 'handed'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield folder


def claim_pane(job, agent, pane, fields):
    """Reserve a pane for one launch, before anything else changes: refuse while its mark names another launch, of any
    job, that is unsettled or live with an agent in the pane; else create the mark (O_EXCL: the job and the launch) and
    write the agent's starting entry. While the mark is there the relay keeps every event about that pane home but the
    follower's, and the TUI watchdog leaves the pane alone; finish removes the job's marks."""
    with marks() as folder:
        path = folder / pane
        if path.exists():
            holder = pane_holder(job, agent, path)
            if holder:
                raise ValueError(f'pane {pane} is handed to {holder}: pick another pane; nothing started')
            fields = {**fields, 'took': path.read_text()}  # a stale mark: put back if this start fails
            path.unlink()
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as mark:
            mark.write(f'{Path(job).absolute()}\n{fields["launch"]}\n')
        job_.bind(job, agent, fields, fresh=True)


def release_pane(job, agent):
    """A start that failed gives its pane back: its own mark goes, and a stale mark it took over comes back as it was,
    so late events about that ended launch stay home until its job's finish."""
    entry = job_.core_entries(job).get(agent, {})
    with marks() as folder:
        path = folder / entry['pane']
        if path.is_file() and path.read_text().splitlines()[:2] == [str(Path(job).absolute()), entry.get('launch')]:
            if entry.get('took'):
                path.write_text(entry['took'])
            else:
                path.unlink()


def pane_holder(job, agent, path):
    """Who holds a pane's mark: its launch while unsettled (another caller may be starting it), or live while an agent
    runs in the pane (Herdr not answering clearly counts as one). '' for a stale mark: its job finished or gone, its
    launch failed or replaced, or this caller's own agent's launch, whose lock it holds, with the pane empty."""
    owner, launch = (path.read_text().splitlines() + ['', ''])[:2]
    other = Path(owner)
    if not owner or not (other / 'core.json').is_file() or (other / 'finished').exists():
        return ''
    try:
        entries = job_.core_entries(other)
    except ValueError:
        return f'a launch of {other} (its core.json is unreadable)'
    name, entry = next(((n, e) for n, e in entries.items() if e.get('launch') == launch), (None, {}))
    if entry.get('state') not in ('live', 'starting'):
        return ''
    held = f'{name} of {other}'
    if entry['state'] == 'starting' and not (other == Path(job).absolute() and name == agent):
        return held + ', still starting'
    try:
        return held if path.name in herdrapi_.herdr_agents() else ''
    except ValueError:
        return held + ' (Herdr did not answer clearly)'


def unmark_handed(job):
    """Remove this job's marks (finish)."""
    with marks() as folder:
        for path in folder.glob('*'):
            rows = path.read_text().splitlines() if path.is_file() and path.name != '.lock' else []
            if rows[:1] == [str(Path(job).absolute())]:
                path.unlink()


def prompt_handed(job, name, text):
    """Prompt a handed agent with one herdr agent prompt, never a key: only while its recorded pane runs this live launch
    (its name, and the session and completion this job or its follower saw; not one the follower saw end), idle or done,
    the owner not in it and its prompt shown empty (a start's own pointer too). None once Herdr took the prompt, else
    why not; anything Herdr does not show clearly refuses. A delivered prompt naming the agent's brief marks it briefed.
    ponytail: Herdr has no prompt --if idle, so an agent that turns working between the check and the prompt takes it as
    a message during its turn; upgrade: a status-guarded Herdr prompt."""
    entry = known(job, name)
    pane = entry.get('pane')
    if entry.get('ended'):
        return f'its follower saw this launch end ({entry["ended"]}); bash {Path(job).absolute() / "reopen.sh"} says what runs'
    try:
        shown = herdrapi_.herdr_shown(pane)
    except ValueError as error:
        return f'not running in pane {pane}, or Herdr did not answer clearly: {base_.line(error)}'
    word = shown.get('agent_status')
    if shown['name'] != name:
        return f'pane {pane} runs {shown["name"] or "an unnamed agent"}, not {name}'
    if entry.get('state') != 'live':
        return f'its start is not settled ({entry.get("state")}): bash {Path(job).absolute() / "reopen.sh"} settles it'
    if replaced(entry, shown):
        return f'pane {pane} runs {name}, but not as the launch this job recorded'
    if shown.get('focused'):
        return 'focused: the owner is in that pane; retry later'
    if word in ('working', 'blocked'):
        return {'working': 'working: tell it after its turn', 'blocked': f'blocked: read it with herdr agent read {pane}'}[word]
    if word not in ('idle', 'done'):
        return 'not ready'
    try:
        screen = subprocess.run([os.environ.get('HERDR', 'herdr'), 'agent', 'read', pane, '--source', 'visible', '--lines', '8'],
                                capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        screen = None
    if screen is None or screen.returncode or typed(screen.stdout, EMPTY_HANDED):
        return (f'text may be typed in its prompt, or its empty prompt is not one stampede knows: read it with herdr agent '
                f'read {pane} --source visible --lines 8, clear it there only when it is idle, then tell again')
    try:
        herdrapi_.herdr('agent', 'prompt', pane, text, '--wait', '--until', 'working', '--until', 'blocked', '--timeout', '15000')
    except (herdrapi_.HerdrError, ValueError) as error:
        return f'{base_.line(error)}; read its screen with herdr agent read {pane} before any resend'
    if entry.get('brief') and entry['brief'] in text:
        job_.bind(job, name, {'briefed': True})
    return None


def tell_handed(job, name, text):
    """tell to a handed agent: one SUBMITTED or FAILED line (exit 2), as tell_core."""
    why = prompt_handed(job, name, text)
    if why:
        out_.emit('FAILED', f'FAILED {name} ({why})', agent=name, reason=why)
        raise SystemExit(2)
    out_.emit('SUBMITTED', f'SUBMITTED {name} (pane {job_.core_entries(job)[name]["pane"]})',
              agent=name, pane=job_.core_entries(job)[name]['pane'])


def reopen_handed(job, agent):
    """A handed agent never starts in a Core terminal, and reopen never types into it. Under the agent's launch lock (the
    caller's): 'live' when its pane runs this launch, briefed (an unsettled one Herdr now shows is settled); 'unbriefed'
    when it runs but its brief pointer was never confirmed sent, with the tell to send after reading its screen; 'missing'
    with the exact start that runs it again (an unsettled launch not in its pane is failed and its mark removed); or
    'unknown'."""
    entry = job_.core_entries(job)[agent]
    pane = entry.get('pane')
    try:
        state, _ = handed_state(job, agent)
    except ValueError as error:
        print(f'UNKNOWN {agent}: Herdr did not show clearly whether pane {pane} runs it ({base_.line(error)}); nothing was started')
        return 'unknown'
    if state == 'other':
        print(f'UNKNOWN {agent}: pane {pane} runs {agent}, but not as the launch this job recorded: read it with herdr agent '
              f'get {pane}; nothing was started')
        return 'unknown'
    if state == 'live' and entry.get('state') != 'live':
        why = commit_handed(job, agent, pane)
        if why:
            print(f'UNKNOWN {agent}: {why}; nothing was started')
            return 'unknown'
        entry = job_.core_entries(job)[agent]
    if state == 'live' and entry.get('briefed'):
        print(f'LIVE {agent} (pane {pane})')
        return 'live'
    if state == 'live':
        print(f'NOT BRIEFED {agent} (pane {pane}): it runs, but its brief was never confirmed sent: read its screen with '
              f'herdr agent read {pane} --source visible --lines 30, and only if it has not got it: '
              f'{briefing(job, agent, entry.get("brief"))}')
        return 'unbriefed'
    if entry.get('state') == 'starting':  # an unsettled launch a whole list shows is not in its pane: it never ran, or ended
        job_.bind(job, agent, {'state': 'failed', 'reason': 'not in its pane at reopen'})
        release_pane(job, agent)
    print(f'NOT RUNNING {agent} (pane {pane}): start it again in a pane at its shell prompt: {entry["start"]}')
    return 'missing'


EMPTY_PROMPT = re.compile(r'Ask Codex to do anything|for shortcuts|To get started|describe a task|Try "|^ *(>|❯|›) *$',
                          re.IGNORECASE | re.MULTILINE)  # herdr-send's markers of an empty prompt


def typed(screen, empty=EMPTY_PROMPT):
    """True when a screen's last 8 non-empty lines show no empty-prompt marker: text already typed in the prompt."""
    return not empty.search('\n'.join([line for line in screen.splitlines() if line.strip()][-8:]))


# A handed agent's empty prompt: Cursor's placeholder too (Herdr 0.9.5, 30 Oct 2026), wrapped over lines in a narrow
# pane, with nothing after it. Hermes shows a rotating placeholder after its prompt and Kimi is unchecked, so a prompt to
# either fails closed until their markers are known.
EMPTY_HANDED = re.compile(EMPTY_PROMPT.pattern + r'|Plan,\s+search,\s+build\s+anything[ \t]*$', re.IGNORECASE | re.MULTILINE)
