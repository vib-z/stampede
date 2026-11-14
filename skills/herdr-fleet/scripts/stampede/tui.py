"""The Herdr TUI path: typing into panes, the deliverer and launching agents in panes."""
import fcntl, json, os, re, signal, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, out as out_

HERDR_SEND = base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-send'


def herdr_send(job, name, text):
    """Type one prompt into an agent's pane with herdr-send: (submitted, its one line). A send that has not finished in
    DELIVER_SEND seconds is stopped with its children and counts as not submitted."""
    with subprocess.Popen([str(HERDR_SEND), name, text], env={**os.environ, 'FLEET_JOB_DIR': str(Path(job).absolute())},
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, start_new_session=True) as sent:
        try:
            said = sent.communicate(timeout=DELIVER_SEND)[0]
        except subprocess.TimeoutExpired:
            os.killpg(sent.pid, signal.SIGKILL)
            sent.communicate()
            return False, f'FAILED {name}: herdr-send did not finish in {DELIVER_SEND} s'
    return sent.returncode == 0, said.strip()


def type_pointer(job, agent, who, brief, pointer):
    """A Codex lead's brief pointer, typed now rather than left in its inbox for the deliverer, so a failure shows here:
    herdr-send's SUBMITTED line, or 1 and a BLOCKED line with the tell that hands the brief over."""
    submitted, said = herdr_send(job, agent, pointer)
    if submitted:
        return out_.said(said)
    out_.emit('BLOCKED', f'BLOCKED {agent}: its brief pointer did not go in ({base_.line(said)}); fix that, then stampede tell {job} {who} "Read {brief}"',
              agent=agent, reason=base_.line(said), retry=f'stampede tell {job} {who} "Read {brief}"')
    return 1


def deliver_soon(job):
    """Wake a Codex lead: a detached deliverer types its unread inbox lines into its pane once it is idle, then exits."""
    job = Path(job).absolute()
    (job / 'hooks').mkdir(exist_ok=True)
    with (job / 'hooks' / 'deliver.log').open('a') as out:
        subprocess.Popen([sys.executable, '-I', str(base_.SCRIPTS / 'fleet_job.py'), '_deliver', str(job)],
                         stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)


DELIVER_EVERY, DELIVER_FOR, DELIVER_MAX = 5, 4 * 3600, 1500  # seconds between looks, seconds one deliverer waits, characters per prompt
DELIVER_CALL, DELIVER_SEND = 15, 120  # seconds a Herdr look and a herdr-send may take before the deliverer stops waiting


def deliver(job):
    """Type a Codex lead's unread inbox lines (inbox/<lead>.md and inbox.log) into its pane while it is idle or done
    and not focused, until none is unread (a Herdr Core job: deliver_core, after typing_unsafe says it may type at all).
    One deliverer at a time: another one exits at once, and the one running looks
    again after letting go of its lock, so a line written meanwhile is never stranded. A read offset moves only after
    herdr-send says SUBMITTED. Exit 3 when the lead stayed busy, focused, drafting or gone for DELIVER_FOR seconds; exit 4
    at once when Herdr does not answer (a deliverer started inside a sandbox without network), so it never holds the lock.
    ponytail: polls Herdr every DELIVER_EVERY seconds while it waits; a Herdr event stream would replace the polling."""
    from . import relay as relay_
    job = Path(job).absolute()
    lead = job_.roster(job)[1]
    if job_.lead_kind(job) != 'codex':
        return 0
    if job_.backend(job) == 'core':
        hcapi_.target(job)
        return relay_.deliver_core(job, lead)
    deadline = time.monotonic() + DELIVER_FOR
    while True:
        with (job / 'hooks' / '.deliver.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0  # the deliverer running sees this line once it lets go
            while unread(job, lead):
                if time.monotonic() > deadline:
                    print(f'{datetime.now():%Y-%m-%d %H:%M} GAVE UP after {DELIVER_FOR}s: {lead} stayed busy, focused, drafting or gone')
                    return 3
                try:
                    if ready(lead) and type_unread(job, lead):
                        continue
                except ValueError as error:  # the next kick from outside the sandbox delivers the line
                    print(f'{datetime.now():%Y-%m-%d %H:%M} CANNOT REACH HERDR ({base_.line(error)}): left for the next deliverer')
                    return 4
                time.sleep(DELIVER_EVERY)
        if not unread(job, lead):
            return 0


def screen_of(agent):
    """The agent's visible screen; a ValueError when Herdr does not answer in DELIVER_CALL seconds."""
    try:
        return subprocess.run([os.environ.get('HERDR', 'herdr'), 'agent', 'read', agent, '--source', 'visible', '--lines', '30'],
                              capture_output=True, text=True, timeout=DELIVER_CALL).stdout
    except subprocess.TimeoutExpired:
        raise ValueError(f'herdr agent read did not answer in {DELIVER_CALL} s') from None


def composer_empty(screen):
    """True when a Codex screen's prompt holds no draft: below its last prompt line (», ›, ❯ or >) Codex's last row is
    a footer holding '? for shortcuts', which it hides while anything is typed. The row began with it on 3 Nov 2026 and
    reads '← for agents · ? for shortcuts' on Codex 0.167.1 (both checked live, the second on 11 Nov 2026), so the
    row need only contain it. Only the last row counts: a draft's own lines sit above Codex's status rows, so a draft
    that holds the phrase is still a draft. Text in the prompt line is never read, since a placeholder and a real
    draft look alike; any other screen is a draft."""
    rows = [row for row in screen.splitlines() if row.strip()][-8:]
    prompts = [i for i, row in enumerate(rows) if re.match(r' *[»›❯>]( |$)', row)]
    return bool(prompts) and prompts[-1] < len(rows) - 1 and '? for shortcuts' in rows[-1]


def ready(agent):
    """True when Herdr shows the agent idle or done, nobody focused on its pane and nothing typed in its prompt (herdr-send
    would clear a draft the owner left there). A ValueError when Herdr does not answer in DELIVER_CALL seconds; False when
    it has no such agent."""
    try:
        shown = herdrapi_.herdr('agent', 'get', agent, timeout=DELIVER_CALL).get('agent', {})
    except herdrapi_.HerdrError:
        return False
    return shown.get('agent_status') in ('idle', 'done') and not shown.get('focused') and composer_empty(screen_of(agent))


def unread(job, agent):
    """[(path, lines, offset after them)] for each watched file of the lead with complete lines it has not been given."""
    job = Path(job).absolute()
    with (job / 'hooks/.wake.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return [(path, *found) for path in watched(job, agent, True) for found in [new_lines(job, agent, path.resolve())]
                if found[0]]


def type_unread(job, lead, limit=None):
    """One prompt with every unread line, marked as from fleet-job; the offsets move only once herdr-send submitted it.
    On Herdr Core a send can end with no answer (None): the lines may have been typed or not, so they are never typed
    again. Their offsets move, with no acknowledgement of a reopen's line among them, and the lead is owed a pointer to
    them (point_owed), which says where to read them."""
    from . import relay as relay_
    found = unread(job, lead)
    text = f'[fleet-job inbox for {lead}, not typed by the owner] ' + ' '.join(
        f'{path.name}: ' + ' | '.join(lines) for path, lines, _ in found)
    if len(text) > DELIVER_MAX:
        text = text[:DELIVER_MAX - 120].rstrip() + ' ... (cut: read the rest at the end of ' + ' and '.join(
            str(path) for path, _, _ in found) + ')'
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)  # typed into a prompt: no control characters
    submitted, said = relay_.send_core(job, lead, text, limit) if job_.backend(job) == 'core' else herdr_send(job, lead, text)
    print(f'{datetime.now():%Y-%m-%d %H:%M} {said}')
    if submitted is not False:
        with (Path(job) / 'hooks/.wake.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if submitted is None:
                relay_.owe(job, lead, found)
            for path, lines, end in found:
                mark_read(job, lead, path.resolve(), end, lines, ack=submitted is True)
    return submitted


def watched(job, agent, lead):
    job = Path(job).absolute()
    return [job / 'inbox' / (agent + '.md')] + ([job / 'inbox.log'] if lead else [])


def new_lines(job, agent, path):
    """The complete lines written to a watched file since the agent's read offset, and the offset after them.
    The caller holds the wake lock."""
    state_path = Path(job) / 'hooks' / ('wake-' + agent + '.json')
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    content = path.read_bytes() if path.is_file() else b''
    offset = state.get(str(path), 0)
    offset = 0 if offset > len(content) else offset
    addition = content[offset:]
    complete = addition.rfind(b'\n') + 1
    return [base_.line(row.decode('utf-8', 'replace')) for row in addition[:complete].split(b'\n')[:-1] if row.strip()], offset + complete


def mark_read(job, agent, path, end, lines, ack=True):
    """Move the agent's read offset of a watched file to end; the caller holds the wake lock. ack: the lines were
    delivered, so a reopen's line among them is acknowledged; without it only the offset moves."""
    job = Path(job)
    state_path = job / 'hooks' / ('wake-' + agent + '.json')
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    state[str(path)] = end
    state_path.write_text(json.dumps(state) + '\n')
    attempts = [found.group(1) for found in (re.fullmatch('REOPENED ' + re.escape(agent) + ' ([0-9a-f]{12})', row)
                                              for row in lines) if found] if ack else []
    if attempts:  # this file's hook delivered a reopen's line: that reopen's proof the restarted agent reads this file
        ack_path = job / 'hooks' / ('ack-' + agent + '.json')
        acks = json.loads(ack_path.read_text()) if ack_path.is_file() else {}
        acks[str(path)] = (acks.get(str(path), []) + attempts)[-10:]
        temporary = ack_path.with_name('.' + ack_path.name + '.' + str(os.getpid()))
        temporary.write_text(json.dumps(acks) + '\n')
        os.replace(temporary, ack_path)  # reopen reads it without the wake lock


def launch(agent, kind, pane, args):
    """Start an agent in its pane; True when it is held at a startup dialog. Herdr answers agent_not_ready
    when a dialog is up during start (the name stays usable), or reports blocked once it is up."""
    try:
        herdrapi_.herdr('agent', 'start', agent, '--kind', kind, '--pane', pane, '--timeout', '90000', '--', *args)
    except herdrapi_.HerdrError as error:
        if error.code != 'agent_not_ready':
            raise
        return True
    ready = herdrapi_.herdr('agent', 'wait', agent, '--until', 'idle', '--until', 'done', '--until', 'blocked', '--timeout', '30000')
    return ready.get('agent', {}).get('agent_status') == 'blocked'


def pane_yolo(pane, yolo_in, lead):
    """The worktree a yolo worker runs in: the pane shell's live folder, which must be yolo_in (the stored cwd never
    qualifies). None without yolo."""
    if yolo_in is None:
        return None
    if lead:
        raise PermissionError('yolo is never for the lead')
    live = herdrapi_.herdr('pane', 'get', pane)['pane'].get('foreground_cwd')
    if not live or Path(live).resolve() != Path(yolo_in).expanduser().resolve():
        raise PermissionError(f'pane {pane}\'s shell is in {live or "an unknown folder"}, not {yolo_in}: '
                              'yolo only runs in a pane whose shell sits in the worker\'s own worktree')
    return Path(live).resolve()
