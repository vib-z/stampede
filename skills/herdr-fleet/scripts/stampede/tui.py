"""The Herdr TUI path: typing into panes, the deliverer and launching agents in panes."""
import fcntl, json, os, re, signal, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, out as out_, send as send_

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
    """Wake the lead: a detached deliverer types its unread inbox lines into its pane once it is idle, then exits. For a
    Claude lead on the Herdr TUI it is the backstop to its file hook (see deliver)."""
    job = Path(job).absolute()
    (job / 'hooks').mkdir(exist_ok=True)
    base_.detach([sys.executable, '-I', base_.SCRIPTS / 'fleet_job.py', '_deliver', job], job / 'hooks' / 'deliver.log')


DELIVER_EVERY, DELIVER_FOR, DELIVER_MAX = 5, 4 * 3600, 1500  # seconds between looks, seconds one deliverer waits, characters per prompt
DELIVER_CALL, DELIVER_SEND = 15, 120  # seconds a Herdr look and a herdr-send may take before the deliverer stops waiting
HOOK_GRACE = 30  # seconds a Claude lead's own file hook has to take a line before the deliverer types it


def wakes(job):
    """True when a deliverer serves this job's lead: a Codex lead (it has no file hook), and a Claude lead on the Herdr
    TUI, whose file hook can miss a change (Claude Code's file watcher dropped two in one live job on 24 Nov 2026)."""
    kind = job_.lead_kind(job)
    return kind == 'codex' or (kind == 'claude' and job_.backend(job) == 'tui')


def wake_lead(job):
    """After a line for the lead is written: start a deliverer when one serves it."""
    if wakes(job):
        deliver_soon(job)


def deliver(job):
    """Type a Codex lead's unread inbox lines (inbox/<lead>.md and inbox.log) into its pane while it is idle or done
    and not focused, until none is unread (a Herdr Core job: deliver_core, after typing_unsafe says it may type at all).
    A Claude lead on the Herdr TUI: its file hook reads the lines and moves the same offsets, so the deliverer first
    gives it HOOK_GRACE seconds and then types only what the hook did not take, once the lead is idle with an empty prompt;
    it exits at once when Herdr shows no Claude agent in the lead's name. A prompt that holds only the deliverer's own
    earlier text (pending) counts as empty: herdr-send clears it and types the unread lines again.
    One deliverer at a time: another one exits at once, and the one running looks
    again after letting go of its lock, so a line written meanwhile is never stranded. A read offset moves only after
    herdr-send says SUBMITTED. Exit 3 when the lead stayed busy, focused, drafting or gone for DELIVER_FOR seconds; exit 4
    at once when Herdr does not answer (a deliverer started inside a sandbox without network), so it never holds the lock.
    ponytail: polls Herdr every DELIVER_EVERY seconds while it waits; a Herdr event stream would replace the polling."""
    from . import relay as relay_
    job = Path(job).absolute()
    lead = job_.roster(job)[1]
    kind = job_.lead_kind(job)
    if not wakes(job):
        return 0
    if job_.backend(job) == 'core':
        hcapi_.target(job)
        return relay_.deliver_core(job, lead)
    if kind == 'claude':  # only a live Claude agent in the lead's name: anything else is not this deliverer's to type into
        try:
            if herdrapi_.herdr('agent', 'get', lead, timeout=DELIVER_CALL).get('agent', {}).get('agent') != 'claude':
                return 0
        except herdrapi_.HerdrError:
            return 0
        except ValueError as error:
            print(f'{datetime.now():%Y-%m-%d %H:%M} CANNOT REACH HERDR ({base_.line(error)}): left for the next deliverer')
            return 4
        time.sleep(HOOK_GRACE)  # the hook usually takes the line within a second; the deliverer is for one it missed
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
                    gave_up(job, lead)
                    return 3
                try:
                    if ready(lead, kind, ours=pending(job, lead)) and type_unread(job, lead):
                        continue
                except ValueError as error:  # the next kick from outside the sandbox delivers the line
                    print(f'{datetime.now():%Y-%m-%d %H:%M} CANNOT REACH HERDR ({base_.line(error)}): left for the next deliverer')
                    return 4
                time.sleep(DELIVER_EVERY)
        if not unread(job, lead):
            return 0


def gave_up(job, lead):
    """Tell whoever started the job, once, that the lead's lines stayed unread: a blocked event through the relay (a job
    marker never holds it back), so the bot or the owner can look. A relay that fails is only logged here."""
    workspace = (Path(job) / 'workspace').read_text().strip() if (Path(job) / 'workspace').is_file() else ''
    event = {'source': 'stampede', 'state': 'blocked', 'kind': 'undelivered', 'job': str(Path(job).absolute()), 'agent': lead,
             'msg': f'{lead} has unread inbox lines that could not be typed for {DELIVER_FOR // 60} minutes: it stayed busy, '
                    f'focused, drafting or gone. Read its pane, then stampede tell {Path(job).absolute()} lead "<text>".',
             **({'workspace': workspace} if base_.WS_ID.fullmatch(workspace) else {})}
    try:
        subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'), json.dumps(event)],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=DELIVER_CALL)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f'{datetime.now():%Y-%m-%d %H:%M} NOT POSTED: {base_.line(error)}')


def screen_of(agent):
    """The agent's visible screen with its text styles (ANSI), or as plain text from a Herdr that cannot give styles;
    a ValueError when Herdr does not answer in DELIVER_CALL seconds."""
    read = [os.environ.get('HERDR', 'herdr'), 'agent', 'read', agent, '--source', 'visible', '--lines', '30']
    try:
        styled = subprocess.run(read + ['--format', 'ansi'], capture_output=True, text=True, timeout=DELIVER_CALL)
        if styled.returncode == 0:
            return styled.stdout
        return subprocess.run(read, capture_output=True, text=True, timeout=DELIVER_CALL).stdout
    except subprocess.TimeoutExpired:
        raise ValueError(f'herdr agent read did not answer in {DELIVER_CALL} s') from None


# Codex's footer of hints, whole or cut to fit a narrow pane, with or without its warnings count: the row it hides
# behind a draft, keeping only the count.
CODEX_FOOTER = re.compile(r' *(← for agents( ·( \?( for( [a-z]*)?)?)?)?|\? for shortcuts)( +⚠ .*)?')
SPARKLE = re.compile('[' + chr(0x2800) + '-' + chr(0x28ff) + ']')  # Codex's startup sparkles, braille dots: not text


def composer_empty(screen):
    """True when a Codex screen's prompt holds no draft. An empty Codex composer is its prompt line (», ›, ❯ or > in
    column 0) holding a dim placeholder, one blank row, its status rows, and a footer of hints as the last row. While anything is
    typed Codex hides the hints and keeps only a warnings count ('⚠ 2 warnings · f2 to view') on that row, and a
    composer taller than the pane scrolls, with ↑ and ↓ at its right edge. The footer began with '? for shortcuts'
    on 3 Nov 2026 and reads '← for agents · ? for shortcuts' on Codex 0.167.1 (11 Nov 2026). Codex 0.170.0, checked
    live on Linux in Herdr 0.9.5 panes 24 to 131 columns wide on 20 Nov 2026, cuts it to fit a narrow pane:
    '← for agents · ? for short', '← for agents   ⚠ 2 warnings · f2 to view', '← for agents ⚠ 2 · f2', or
    '← for agents' alone. So the last row must be such a footer and nothing else, the row under the prompt line must
    be blank (a draft's next line sits there), and the prompt line must hold no scroll arrow. In a screen read with
    its styles (screen_of), the prompt line must also hold Codex's dim placeholder: typed text is never dim, so a
    draft that quotes the footer in a pane too short for the status rows is still a draft. Any other screen is a
    draft. Live tests: tests/fixtures/codex-0.170."""
    lines = [[(SPARKLE.sub(' ', char), dim) for char, dim in send_.cells(row)] for row in screen.splitlines()]
    rows = [''.join(char for char, _ in line).rstrip() for line in lines]
    while rows and not rows[-1]:
        rows.pop()
    prompts = [i for i, row in enumerate(rows) if re.match(r'[»›❯>]( |$)', row)]  # column 0: a draft's lines are indented
    if not prompts or prompts[-1] >= len(rows) - 2 or len([row for row in rows[prompts[-1]:] if row]) > 8:
        return False
    prompt = rows[prompts[-1]]
    if rows[prompts[-1] + 1] or '↑' in prompt or '↓' in prompt or not CODEX_FOOTER.fullmatch(rows[-1]):
        return False
    if '\x1b[' not in screen:  # plain text: a placeholder and a draft look alike
        return True
    shown = [(char, dim) for char, dim in lines[prompts[-1]][len(prompt) - len(prompt.lstrip()) + 1:] if char.strip()]
    return bool(shown) and all(dim for _, dim in shown) and any(char.isalpha() for char, _ in shown)


def claude_prompt_empty(screen):
    """True when a Claude screen's prompt holds no draft: its last prompt line (❯ in column 0) shows nothing after the
    marker but Claude's dim placeholder, if anything, and the next row is the box's lower border. Any other screen is a
    draft. Read live from Claude Code 2.1.331 in a Herdr 0.9.5 pane on 24 Nov 2026: '❯' and a no-break space, or that
    and a dim 'Try "..."'."""
    lines = [send_.cells(row) for row in screen.splitlines()]
    rows = [''.join(char for char, _ in line).rstrip() for line in lines]
    prompts = [i for i, row in enumerate(rows) if row.startswith('❯')]
    if not prompts or prompts[-1] + 1 >= len(rows) or not rows[prompts[-1] + 1].lstrip().startswith('─'):
        return False
    shown = [(char, dim) for char, dim in lines[prompts[-1]][1:] if char.strip()]
    return not shown or ('\x1b[' in screen and all(dim for _, dim in shown))


def ready(agent, kind='codex', ours=((), False, None)):
    """True when Herdr shows the agent idle or done, nobody focused on its pane, and nothing typed in its prompt but,
    at most, text of ours (pending), which herdr-send clears before it types. Anything else in the prompt is a draft,
    which herdr-send would clear too, so it waits. A ValueError when Herdr does not answer in DELIVER_CALL seconds;
    False when it has no such agent."""
    try:
        shown = herdrapi_.herdr('agent', 'get', agent, timeout=DELIVER_CALL).get('agent', {})
    except herdrapi_.HerdrError:
        return False
    if shown.get('agent_status') not in ('idle', 'done') or shown.get('focused'):
        return False
    screen = screen_of(agent)
    empty = claude_prompt_empty if kind == 'claude' else composer_empty
    texts, lone, marker = ours
    return (empty(screen) or send_.holds(screen, texts, lone)
            or bool(marker) and re.sub(r'\s+', '', send_.box(screen)).startswith(re.sub(r'\s+', '', marker)))


LONE_FOR = 1800  # seconds after a send of ours that a lone paste placeholder in the lead's prompt counts as ours


def pending(job, lead):
    """(texts, lone, marker) for ready: the deliverer's own text that may still sit in the lead's prompt. texts: the
    last texts it typed there (typed-<lead>.json) and the text it would type now. Clearing one loses nothing: its lines
    are unread and typed again, or were delivered, and a copy Claude left in the prompt after a slow submit would be a
    second one. lone: a paste placeholder alone is ours only within LONE_FOR seconds of a send of ours that typed the
    text and that herdr-send did not confirm; otherwise it may be the owner's paste. marker: before any record (a prompt left by
    stampede 0.2.5), a prompt that starts with our mark, [fleet-job inbox for <lead>, not typed by the owner], is ours.
    An owner's draft, or our text with a word of theirs added, is never ours."""
    typed = typed_record(job, lead)
    found = unread(job, lead)
    texts = (typed or {}).get('texts', []) + ([inbox_text(lead, found)] if found else [])
    lone = (bool(typed) and typed['confirmed'] is not True and typed['typed'] is not False
            and time.time() - typed['at'] < LONE_FOR)
    return texts, lone, None if typed else mark(lead)


def remember(job, lead, text, submitted=None, typed=None):
    """Note a text the deliverer types into the lead's prompt (its last 5), when, whether herdr-send confirmed the last
    one, and whether it typed anything (False when it refused first: the owner in the pane, a dialog); None before it
    answers."""
    texts = [t for t in (typed_record(job, lead) or {}).get('texts', []) if t != text] + [text]
    record = {'texts': texts[-5:], 'at': time.time(), 'confirmed': submitted, 'typed': typed}
    (Path(job) / 'hooks' / ('typed-' + lead + '.json')).write_text(json.dumps(record) + '\n')


def typed_record(job, lead):
    """typed-<lead>.json, or None when there is none or it does not parse (then only our mark tells our text)."""
    try:
        typed = json.loads((Path(job) / 'hooks' / ('typed-' + lead + '.json')).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(typed, dict) or not isinstance(typed.get('texts'), list):
        return None
    at = typed.get('at') if isinstance(typed.get('at'), (int, float)) else 0
    return {'texts': [t for t in typed['texts'] if isinstance(t, str)], 'at': at, 'confirmed': typed.get('confirmed'),
            'typed': typed.get('typed')}


def mark(lead):
    return f'[fleet-job inbox for {lead}, not typed by the owner]'


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
    text = inbox_text(lead, found)
    if job_.backend(job) == 'core':
        submitted, said = relay_.send_core(job, lead, text, limit)
    else:
        remember(job, lead, text)
        submitted, said = herdr_send(job, lead, text)
        remember(job, lead, text, submitted, typed=submitted or not send_.refused(said))
    print(f'{datetime.now():%Y-%m-%d %H:%M} {said}')
    if submitted is not False:
        with (Path(job) / 'hooks/.wake.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if submitted is None:
                relay_.owe(job, lead, found)
            for path, lines, end in found:
                mark_read(job, lead, path.resolve(), end, lines, ack=submitted is True)
    return submitted


def inbox_text(lead, found):
    """The one prompt that carries unread lines ([(path, lines, end)]), marked as from fleet-job, cut to DELIVER_MAX."""
    text = mark(lead) + ' ' + ' '.join(
        f'{path.name}: ' + ' | '.join(lines) for path, lines, _ in found)
    if len(text) > DELIVER_MAX:
        text = text[:DELIVER_MAX - 120].rstrip() + ' ... (cut: read the rest at the end of ' + ' and '.join(
            str(path) for path, _, _ in found) + ')'
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)  # typed into a prompt: no control characters


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
