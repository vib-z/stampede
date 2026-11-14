"""Reaching the owner and the lead: questions, gates, plan approval, posts, tell, wait and finish."""
import contextlib, fcntl, hashlib, json, os, shlex, shutil, signal, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, herdrapi as herdrapi_, tui as tui_, settings as settings_, out as out_

ASK_CMD = None  # a test's stand-in for the setting ask.command


def ask_command(job):
    return ASK_CMD or settings_.current(job).get('ask.command')


def require_ask_command(command):
    """A local job's question or gate is answered only through ask.command: refuse it when that program is not installed,
    so a gate never looks asked when no one can ever answer it. A command that runs and fails later stays an ASK FAILED."""
    argv = shlex.split(command or '')
    if not argv or not shutil.which(argv[0]):
        raise ValueError(f'the ask command is not installed ({base_.line(argv[0] if argv else "empty")} is not on PATH), so the owner '
                         'could never answer: install it, or set ask.command in your config (stampede config show names '
                         'the file; env FLEET_ASK_CMD) to a command that asks the owner and prints their answer')


def tell(job, name, text):
    from . import handed as handed_, native as native_, relay as relay_
    if job_.backend(job) == 'native':
        return native_.tell(job, name, text)
    people, lead = job_.roster(job)
    name = lead if name == 'lead' else name
    if not base_.NAME.fullmatch(name or '') or name not in people:
        raise ValueError(f'agent {name} is not in this job (it has: {", ".join(["lead"] + sorted(set(people) - {lead}))})')
    if people[name] == 'claude' or name == lead:  # the lead always gets its inbox file, so no answer or yes is ever lost
        base_.append(Path(job) / 'inbox' / (name + '.md'), base_.line(text))
        if people[name] != 'claude':  # a Codex lead has no file hook: the line is typed into its pane once it is idle
            tui_.deliver_soon(job)
            where = 'terminal' if job_.backend(job) == 'core' else 'pane'
            return out_.emit('DELIVERED', f'DELIVERED {name} (inbox file; typed into its {where} once it is idle)', agent=name)
        # a pending card holds the turn: the inbox is read only once the card is answered (a Core agent has no pane to read)
        if job_.backend(job) != 'core' and agent_card(name):
            out_.emit('BLOCKED_ON_CARD', f'BLOCKED_ON_CARD {name}: queued in its inbox, but it waits at a question card and reads '
                      f'nothing until that is answered; read it with: herdr agent read {name} --source visible --lines 40', agent=name)
            return 3
        return out_.emit('DELIVERED', 'DELIVERED ' + name + ' (inbox file)', agent=name)
    if job_.backend(job) == 'core':
        return (handed_.tell_handed if job_.core_entries(job).get(name, {}).get('backend') == 'tui' else relay_.tell_core)(job, name, text)
    sent = subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-send'), name, text], stdout=subprocess.PIPE,
                          text=True, env={**os.environ, 'FLEET_JOB_DIR': str(Path(job).absolute())})
    out_.said(sent.stdout, end='')
    if sent.returncode:
        raise SystemExit(2)  # herdr-send printed its one FAILED line (focused, blocked or gone); never a traceback


def notify_lead(job, text, kept=None):
    """One line for the lead in inbox.log, where a Claude lead's file hook sees it; a Codex lead gets it typed. On a native
    job Core types it: 0, or 2 when it was not typed (kept names the file that holds it, in the FAILED line)."""
    from . import native as native_
    if job_.backend(job) == 'native':
        return native_.notify_lead(job, text, kept)
    base_.append(Path(job) / 'inbox.log', text)
    if job_.lead_kind(job) == 'codex':
        tui_.deliver_soon(job)


def ask_now(job, question, options, command=None, gate=None, ident=None):
    """Ask the owner and wait; the answer, or why it failed, goes to the lead's inbox. On a native job Core types it in,
    and a line hc send refuses (the lead is blocked or gone) stays in asks/<ident>.answer, mode 0600, and the ask fails.
    A gate always asks FLEET_ASK_CMD itself, with the question made from its own record, and its yes (exit 0, a yes or
    nothing on stdout) is recorded for gate-ok, only while the record is still the one asked about."""
    if ident is not None and not base_.GATE.fullmatch(ident):
        raise ValueError(f'--ident takes a question id as ask makes it (12 hex), not {base_.line(ident)!r}')
    asked = load_gate(job, gate) if gate else None
    if asked:
        if asked['route'] != 'local':
            raise PermissionError(f'gate {gate} goes to {asked["route"]}, not to the phone')
        question, options = gate_question(asked), []
    argv = shlex.split(ask_command(job) if gate else command or ask_command(job))
    for option in options:
        argv += ['--option', option]
    yes = False
    try:
        result = subprocess.run([*argv, '--', question], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        yes = result.returncode == 0 and result.stdout.strip().lower() in ('', 'yes')
        if result.returncode == 0 and result.stdout.strip():
            status, answer = 'ANSWER', base_.line(result.stdout)
        elif result.returncode == 1:
            status, answer = 'ANSWER', 'no (denied or cancelled)'
        else:
            status, answer = 'ASK FAILED', 'exit ' + str(result.returncode) + ': ' + base_.line(result.stderr or result.stdout)
    except OSError as error:
        status, answer = 'ASK FAILED', 'exit 127: ' + base_.line(error)
    if gate and yes:
        try:
            record_yes(job, gate, asked['sha'], 'owner, through ' + Path(argv[0]).name, asked)
            return 0
        except PermissionError as error:
            status, answer = 'GATE NOT RECORDED', base_.line(error)
    line = status + ' ' + base_.line(question) + ': ' + answer
    if job_.backend(job) == 'native':
        kept = asks_folder(job) / ((ident or uuid.uuid4().hex[:12]) + '.answer')
        keep(kept, line + '\n')  # first, so the answer outlives a send that fails or never returns
        if notify_lead(job, line, kept):
            return 1
        kept.unlink()
    else:
        tell(job, 'lead', line)
    return 0 if status == 'ANSWER' else 1


def asks_folder(job):
    """<job>/asks, private (0700) whatever the umask, and made so when it is more open: a kept answer is the owner's words."""
    folder = Path(job).absolute() / 'asks'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def keep(path, text):
    """Write text to path whole and private: a new 0600 file of its own beside it, then os.replace onto path, so a reader
    of the old file sees only the old text and a crash leaves one of the two whole."""
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def ask_background(job, question, options, command=None, gate=None):
    """Detach the question in its own process group, so cancel stops it and its child card together."""
    job = Path(job).absolute()
    command = command or ask_command(job)
    require_ask_command(command)
    folder = asks_folder(job)
    ident = uuid.uuid4().hex[:12]
    argv = [sys.executable, '-I', str(base_.SCRIPTS / 'fleet_job.py'), '_ask', str(job), '--ident', ident, '--command', command,
            *(['--gate', gate] if gate else []), *['--option=' + option for option in options], '--', question]
    with (folder / (ident + '.log')).open('a') as output:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    (folder / (ident + '.pid')).write_text(str(process.pid) + '\n')
    (folder / (ident + '.txt')).write_text(base_.line(question) + '\n')
    where = 'Core types the answer into the lead\'s terminal' if job_.backend(job) == 'native' else 'the answer goes to the lead inbox'
    out_.emit('ASKED', 'ASKED ' + ident + ' (' + where + '; cancel with: stampede cancel ' + str(job) + ' ' + ident + ')', id=ident)
    return ident


def own_waiter(job, pid, ident):
    """True when pid still runs this very question's _ask: its argv names this job and this question's id, word for word
    (a pid file can outlive its waiter, and its pid be reused, by another job's waiter too)."""
    try:
        args = subprocess.run(['ps', '-o', 'args=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    except OSError:
        return False
    return 'fleet_job.py _ask ' in args and f' _ask {Path(job).absolute()} --ident {ident} ' in args + ' '


def cancel(job, ident, waiting_only=False):
    """Stop an answered or unwanted question: its waiter and its card, as one process group. A record whose pid no
    longer runs this job's waiter (it answered, or the pid was reused) is dropped without a signal, and with
    waiting_only (finish) without a line."""
    path = Path(job) / 'asks' / (str(ident) + '.pid')
    if not base_.GATE.fullmatch(str(ident)) or not path.is_file():
        raise ValueError('no phone card ' + base_.line(ident) + ' waiting in this job (a question sent to a bot is answered in its chat)')
    text = path.read_text().strip()
    if text.isdigit() and own_waiter(job, int(text), ident):
        try:
            os.killpg(int(text), signal.SIGTERM)
        except ProcessLookupError:
            pass
        out_.emit('CANCELLED', 'CANCELLED ' + ident, id=ident)
    elif not waiting_only:
        out_.emit('CANCELLED', 'CANCELLED ' + ident + ' (its waiter had already gone)', id=ident)
    path.unlink()


def outbox_post(job, kind, text, files=(), answer=None):
    """One item for the front door to relay: <job>/outbox/<n>.md, its files copied into outbox/<n>/, a line in outbox.log."""
    job = Path(job).absolute()
    box = job / 'outbox'
    box.mkdir(exist_ok=True)
    with (box / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        n = f'{len(list(box.glob("[0-9]*.md"))) + 1:03d}'
        body = [f'# {n} {kind}', '', str(text).strip()]
        if files:
            (box / n).mkdir()
            for f in files:
                source = Path(f).expanduser().absolute()
                if not source.is_file():
                    raise ValueError(f'no file {source} to post')
                shutil.copy2(source, box / n / source.name)
            body += ['', 'Files:'] + [f'- {box / n / Path(f).name}' for f in files]
        if answer:
            body += ['', 'Answer with: ' + answer]
        (box / (n + '.md')).write_text('\n'.join(body) + '\n')
        base_.append(job / 'outbox.log', f'{n} {kind} {base_.line(text)[:200]}')
    return n


def post(job, text, files=()):
    """One item for the owner. outbox/<n>.md is always the record; a job a bot started (and no front door) also sends that
    bot one post event on the strict route, since only a front door's wait reads the outbox."""
    owner = '' if job_.front_door(job) else job_.job_owner(job)
    n = outbox_post(job, 'post', text, files)
    item = Path(job).absolute() / 'outbox' / (n + '.md')
    if not owner and job_.front_door(job):
        return out_.emit('POSTED', f'POSTED {n} for the front door to relay ({item})', outbox=n, path=str(item), to='front door')
    if not owner:  # a local job: the outbox is the only copy, and nothing reads it
        return out_.emit('POSTED', f'POSTED {n} to the outbox only ({item}): no bot or front door hears it. To have the owner told, a '
                         'job a bot starts sets HERDR_EVENTS_OWNER=<bot> at new, and a chat outside Herdr starts it with --front-door',
                         outbox=n, path=str(item), to=None)
    copies = [str(item.parent / n / Path(f).name) for f in files]
    post_event(job, owner, {'state': 'post', 'text': str(text).strip(), 'outbox': n, 'item': str(item), 'files': copies},
               refused=lambda why: f'outbox {n} is written but {owner} never heard it: the relay refused it ({why}). '
                                   'Fix the route (herdr-doctor --relay), then post again')
    out_.emit('POSTED', f'POSTED {n} to {owner} (and {item})', outbox=n, path=str(item), to=owner)


def lead_card(job):
    """The lead's screen when it is held at a question card (Claude's 'Enter to select'), else ''."""
    return agent_card(job_.roster(job)[1])


def agent_card(name):
    try:
        screen = subprocess.run([os.environ.get('HERDR', 'herdr'), 'agent', 'read', name, '--source', 'visible', '--lines', '40'],
                                capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    return screen if 'Enter to select' in screen else ''


def lead_alive(job):
    """False only when Herdr says the lead's agent is gone (agent_not_found); any other failure counts as alive."""
    from . import native as native_
    if job_.backend(job) == 'native':
        return native_.lead_alive(job)
    lead = job_.roster(job)[1]
    try:
        out = subprocess.run([os.environ.get('HERDR', 'herdr'), 'agent', 'get', lead], capture_output=True, text=True, timeout=10)
        return 'agent_not_found' not in out.stdout + out.stderr
    except (OSError, subprocess.SubprocessError):
        return True


def wait(job, timeout=None, every=5):
    """The front door's wait, run in the background: returns with every outbox item it has not shown yet, or when the
    lead sits at a question card (on a native job: when Core says the lead is blocked). Exit 0 with output, 3 on timeout.
    Marks what it printed as seen."""
    from . import native as native_
    job = Path(job).absolute()
    native = job_.backend(job) == 'native'
    seen_path, log = job / 'outbox' / '.seen', job / 'outbox.log'
    timeout = settings_.current(job).get('timeouts.wait') if timeout is None else timeout
    deadline, checks = time.monotonic() + timeout, 0
    while True:
        seen = int(seen_path.read_text() or 0) if seen_path.is_file() else 0
        rows = [r for r in (log.read_text().splitlines() if log.is_file() else []) if r[:3].isdigit() and int(r[:3]) > seen]
        if rows:
            for row in rows:
                item = job / 'outbox' / (row[:3] + '.md')
                out_.emit('ITEM', item.read_text().rstrip() + '\n', outbox=row[:3], path=str(item), kind=row[4:].split(' ')[0],
                          text=item.read_text().rstrip())
            seen_path.write_text(rows[-1][:3] + '\n')
            return 0
        if checks % 6 == 0:
            if not lead_alive(job):
                out_.emit('LEAD_GONE', f'LEAD_GONE {job_.roster(job)[1]}: ' + (
                    f'Herdr Core holds no live lead of this job (crash, close or restart). Look with stampede tree {job}, '
                    f'then reopen it (stampede reopen {job}) or tell the owner.' if native else
                    'its agent no longer exists in Herdr (crash, closed pane or restart). Look at the workspace, then restart '
                    'it or tell the owner.'), lead=job_.roster(job)[1])
                return 0
            blocked = native_.lead_blocked(job) if native else None
            if blocked:
                kind, address, screen = blocked
                shown = '\n'.join(r for r in screen.splitlines() if r.strip())[-1500:]
                out_.emit('BLOCKED', f'BLOCKED {job_.roster(job)[1]}: {kind}. Core says it waits at a dialog in its terminal {address} '
                          f'(hc read {address}). Its screen:\n' + shown,
                          lead=job_.roster(job)[1], reason=kind, address=address, screen=shown)
                return 0
            card = '' if native else lead_card(job)
            if card:
                shown = '\n'.join(r for r in card.splitlines() if r.strip())[-1500:]
                out_.emit('BLOCKED_ON_CARD', f'BLOCKED_ON_CARD {job_.roster(job)[1]}: it is waiting at a question card in its pane. Its '
                          'screen:\n' + shown, lead=job_.roster(job)[1], screen=shown)
                return 0
        if time.monotonic() > deadline:
            out_.emit('TIMEOUT', f'TIMEOUT nothing new in {job / "outbox"} after {timeout}s; run fleet-job wait again',
                      path=str(job / 'outbox'),
                      retry=f'fleet-job wait {job}')
            return 3
        checks += 1
        time.sleep(every)


def post_local(job, fields):
    """Ordinary relay, not strict: a local job's finish. Logged when no route has a URL."""
    event = {'source': 'stampede', 'job': str(Path(job).absolute()), 'agent': job_.roster(job)[1], **fields, **caller_ids(job)}
    script = base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'
    result = subprocess.run([str(script), json.dumps(event)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('the relay did not accept the finish event ('
                         + (base_.line(result.stderr) or 'exit ' + str(result.returncode)) + ')')


def finish(job, summary):
    """One done event, then drop the workspace marker. A second call does not post again.
    A job a bot started uses the strict route; a local job uses the ordinary relay. Every question still waiting on the
    phone is cancelled: its waiter runs in a session of its own, which outlives the lead's pane on the Herdr TUI and,
    since Herdr Core 0.1.19, a Core terminal too, so nothing else ends it."""
    from . import handed as handed_, native as native_, gates as gates_
    job = Path(job).absolute()
    summary = base_.line(summary)
    gone = gates_.off(job)
    if not summary:
        raise ValueError('finish needs one line on where the job ended')
    stamp = job / 'finished'
    if not stamp.is_file():
        fields = {'state': 'done', 'summary': summary, **({'gates_off': gone} if gone else {})}
        workspace = (job / 'workspace').read_text().strip() if (job / 'workspace').is_file() else ''
        if workspace:
            fields['workspace'] = workspace
        owner = job_.job_owner(job)
        if owner:
            post_event(job, owner, fields)
        elif job_.front_door(job):  # no bot hears a front-door job's end: the front door's wait does, from the outbox
            outbox_post(job, 'done', summary + (f'\ngates off: {", ".join(gone)}' if gone else ''))
        else:
            post_local(job, fields)
        stamp.write_text(summary + '\n')
    for waiter in sorted((job / 'asks').glob('*.pid')) if (job / 'asks').is_dir() else []:
        try:
            cancel(job, waiter.stem, waiting_only=True)
        except (ValueError, OSError) as error:  # one bad record never keeps the next waiter alive
            out_.emit('NOT CANCELLED', 'NOT CANCELLED ' + waiter.stem + ': ' + base_.line(error), id=waiter.stem, reason=base_.line(error))
    if (job / 'workspace').is_file():
        job_.clear_job_marker((job / 'workspace').read_text().strip(), job)
    handed_.unmark_handed(job)
    if gone:
        print('gates off: ' + ', '.join(gone))
    out_.emit('FINISHED', 'FINISHED ' + str(job), gates_off=gone)
    if job_.backend(job) == 'native':
        with contextlib.suppress(Exception):  # the record is a copy: a refresh that fails never fails finish
            native_.refresh(job)


def post_event(job, owner, fields, refused=None):
    """One event to the bot that started the job, queued by the relay in strict mode: only the bot's own route with a
    URL (never the default route, perhaps another bot's), or a refusal. No `pane`: the flusher keeps only a pane's
    newest event after an outage, and a question, a gate or a post must never be dropped for a later turn end.
    refused: the error for a refusal, given the relay's reason; by default the one for a question, a gate or finish."""
    event = {'source': 'stampede', 'owner': owner, 'job': str(Path(job).absolute()), 'agent': job_.roster(job)[1], **fields,
             **caller_ids(job)}
    result = subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-post'), '--strict', json.dumps(event)],
                            capture_output=True, text=True)
    if result.returncode and refused:
        raise ValueError(refused(base_.line(result.stderr) or 'exit ' + str(result.returncode)))
    if result.returncode:
        raise ValueError(f'the relay did not queue this for {owner} ({base_.line(result.stderr) or "exit " + str(result.returncode)}), '
                         'so the bot would never hear it: fix its route (herdr-doctor --relay)'
                         + (', or ask the owner in your own pane' if pane_yes(job) else ', then ask again'))


def ask(job, question, options):
    """A question for the owner: to the bot that started the job, as a question event it answers with tell;
    else FLEET_ASK_CMD in the background."""
    owner = job_.job_owner(job)
    if not owner and job_.front_door(job):
        ident = uuid.uuid4().hex[:12]
        n = outbox_post(job, 'question', base_.line(question) + ''.join('\n- ' + o for o in options),
                        answer=shlex.join(['fleet-job', 'tell', str(Path(job).absolute()), 'lead',
                                           f'ANSWER {ident} {base_.line(question)}: <their words>']))
        where = 'Core types the answer into your terminal' if job_.backend(job) == 'native' else 'it comes to your inbox'
        out_.emit('ASKED', f'ASKED {ident} posted to the front door as outbox {n}; the owner answers there and {where}', id=ident, outbox=n)
        return ident
    if not owner:
        return ask_background(job, question, options)
    ident = uuid.uuid4().hex[:12]
    post_event(job, owner, {'state': 'question', 'ask': ident, 'question': base_.line(question), 'options': options,
                            'answer': shlex.join(['fleet-job', 'tell', str(Path(job).absolute()), 'lead',
                                                  f"ANSWER {ident} {base_.line(question)}: <the owner's words>"])})
    where = 'Core types the answer into your terminal' if job_.backend(job) == 'native' else 'the answer comes to your inbox'
    out_.emit('ASKED', f'ASKED {ident} sent to {owner}, which asks the owner in chat; {where}', id=ident, to=owner)
    return ident


HELD = ('merge', 'push_default_branch')  # gates the code checks itself: only their recorded yes opens them (gates.py)


def ask_gate(job, action, sha, pr=None, kind=None):
    """A gate is one exact action at one commit, answered yes or no. A bot-started job sends it to that bot as a gate
    event, and the bot records the owner's yes with approve-gate; a local job asks FLEET_ASK_CMD in the background.
    kind: one of the [gates] names, covered by the digest; stampede merge and the pre-push hook take only their own kind."""
    job = Path(job).absolute()
    if not base_.SHA.fullmatch(sha):
        raise ValueError('--sha takes the full commit id the gate is about (git rev-parse HEAD)')
    owner = job_.job_owner(job)
    ident = uuid.uuid4().hex[:12]
    route = owner or ('front-door' if job_.front_door(job) else 'local')
    gate = {'gate': ident, 'action': base_.line(action), 'pr': pr, 'sha': sha, 'route': route,
            'asked': datetime.now().strftime('%Y-%m-%d %H:%M'), **({'kind': kind} if kind else {})}
    (job / 'gates').mkdir(exist_ok=True)
    (job / 'gates' / (ident + '.json')).write_text(json.dumps(gate) + '\n')
    check = f'stampede gate-ok {job} {ident} --sha <the commit you act on>'
    typed = ', or on the owner\'s yes typed in your pane' if pane_yes(job) and kind not in HELD else ''
    if route == 'front-door':
        n = outbox_post(job, 'gate', gate_question(gate) + '\nOne exact action, yes or no. Show the owner this action as written.',
                        answer=shlex.join(['fleet-job', 'approve-gate', str(job), ident, '--sha', sha, '--digest', gate_digest(gate)])
                        + ' --by "owner in <chat>: <their exact words>"   (a no: '
                        + shlex.join(['fleet-job', 'tell', str(job), 'lead', f'GATE {ident} NO: <their words>']) + ')')
        return out_.emit('GATE', f'GATE {ident} posted to the front door as outbox {n}; act after {check} prints APPROVED{typed}', id=ident,
                         sha=sha, pr=pr, kind=kind, outbox=n)
    if not owner:
        try:
            ask_background(job, gate_question(gate), [], gate=ident)
        except ValueError:
            (job / 'gates' / (ident + '.json')).unlink()  # a gate no one can answer is no gate
            raise
        return out_.emit('GATE', f'GATE {ident} on the phone; act after {check} prints APPROVED{typed}', id=ident, sha=sha, pr=pr, kind=kind)
    try:
        post_event(job, owner, {'state': 'gate', **gate, 'options': ['yes', 'no'],
                                'approve': shlex.join(['fleet-job', 'approve-gate', str(job), ident, '--sha', sha, '--digest',
                                                       gate_digest(gate), '--by', 'owner in ' + owner + ' chat']),
                                'deny': shlex.join(['fleet-job', 'tell', str(job), 'lead', f"GATE {ident} NO: <the owner's words>"])})
    except ValueError:
        (job / 'gates' / (ident + '.json')).unlink()  # a gate its bot never hears is no gate
        raise
    out_.emit('GATE', f'GATE {ident} queued for {owner}, which asks the owner in chat; act after {check} prints APPROVED{typed}', id=ident,
              sha=sha, pr=pr, kind=kind, to=owner)


def gate_digest(gate):
    """One fingerprint of a gate as asked: the yes recorded for it covers exactly this action, PR, commit and route."""
    return hashlib.sha256(json.dumps(gate, sort_keys=True).encode()).hexdigest()[:16]


def gate_question(gate):
    return f'Gate {gate["gate"]}' + (f' ({gate["kind"]})' if gate.get('kind') else '') + f': {gate["action"]}' + (f' (PR #{gate["pr"]})' if gate['pr'] else '') + f' at {gate["sha"][:12]}?'


def load_gate(job, ident):
    path = Path(job) / 'gates' / (str(ident) + '.json')
    if not base_.GATE.fullmatch(str(ident)) or not path.is_file():
        raise ValueError('no gate ' + base_.line(ident) + ' in this job')
    gate = json.loads(path.read_text())
    if not isinstance(gate, dict) or gate.get('gate') != ident or not base_.SHA.fullmatch(str(gate.get('sha', ''))) or 'route' not in gate:
        raise ValueError(f'gate {ident} is malformed: ask again')
    return gate


def record_yes(job, ident, sha, by, asked=None):
    """The owner's yes for one gate at one commit, then wake the lead. asked: the gate as it was when asked, or the
    digest the bot was handed with it."""
    gate = load_gate(job, ident)
    if asked is not None and (gate_digest(gate) != asked if isinstance(asked, str) else gate != asked):
        raise PermissionError(f'gate {ident} changed while the owner was asked: ask again')
    if sha != gate['sha']:
        raise PermissionError(f'gate {ident} asked about {gate["sha"]}, not {sha}: a stale yes; ask again')
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    (Path(job) / 'gates' / (ident + '.approved')).write_text(json.dumps({'gate': ident, 'sha': sha, 'by': base_.line(by), 'at': when,
                                                                         'digest': gate_digest(gate)}) + '\n')
    tell(job, 'lead', f'GATE {ident} APPROVED by {base_.line(by)} at {when}: {gate["action"]} at {sha}. '
                      f'Run fleet-job gate-ok {Path(job).absolute()} {ident} --sha <the commit you act on>, then act.')


def pane_yes(job):
    """True when a yes typed in the lead's pane can only be the owner's: a Claude lead on the Herdr TUI. fleet-job types
    inbox lines into a Codex lead's pane, and on Herdr Core anything can type, so there only gate-ok's recorded yes counts."""
    return job_.backend(job) == 'tui' and job_.lead_kind(job) == 'claude'


def approve_gate(job, ident, sha, by, digest=None):
    """The starting bot's command, run outside Herdr: the owner said yes in its chat to this gate at this commit.
    digest: the gate as the bot was handed it (its approve command carries it); a gate changed since then takes no yes."""
    core = job_.backend(job) != 'tui'
    if load_gate(job, ident)['route'] == 'local':  # what is wrong with the gate first, then where this runs
        raise PermissionError(f'gate {ident} belongs to a job started locally: the owner answers on the phone'
                              + (' or in Herdr' if pane_yes(job) else ''))
    if herdrapi_.inside_herdr():
        if core:
            raise PermissionError('approve-gate runs only outside Herdr and Herdr Core (over plain ssh, never hc exec), from '
                                  'the bot that started the job: an agent\'s own say-so never counts. The owner answers the bot in chat')
        raise PermissionError('approve-gate runs only outside Herdr, from the bot that started the job: an agent\'s own '
                              'say-so never counts. The owner answers the bot in chat'
                              + (', or types yes in the lead\'s pane' if pane_yes(job) else ''))
    if not base_.line(by):
        raise ValueError('--by says who said yes and where, e.g. "owner in Grok Bot chat"')
    if not digest:
        raise PermissionError(f'approve-gate needs --digest, the gate {ident} as it was asked: run the approve command the gate '
                              'event or the front-door post gave you, as written')
    record_yes(job, ident, sha, by, digest)
    out_.emit('APPROVED', f'APPROVED {ident} at {sha}', id=ident, sha=sha)


def gate_ok(job, ident, sha):
    """The lead's check before it acts: the owner's recorded yes for this gate, at this very commit."""
    gate = load_gate(job, ident)
    path = Path(job) / 'gates' / (ident + '.approved')
    if not path.is_file():
        raise PermissionError(f'gate {ident} has no recorded yes: wait for it'
                              + (', or the owner\'s yes typed in your pane' if pane_yes(job) and gate.get('kind') not in HELD else ''))
    record = json.loads(path.read_text())
    if not isinstance(record, dict) or not all(base_.line(record.get(k, '')) for k in ('gate', 'sha', 'by', 'at')):
        raise PermissionError(f'the yes recorded for gate {ident} is malformed: ask again')
    if record.get('gate') != ident:
        raise PermissionError(f'the yes recorded under gate {ident} is for gate {record.get("gate")}: ask again')
    if not record.get('sha') == gate['sha'] == sha:
        raise PermissionError(f'gate {ident} was approved for {record.get("sha")}, not {sha}: a push after the yes '
                              'withdraws it; ask again')
    if record.get('digest') != gate_digest(gate):
        raise PermissionError(f'gate {ident} changed after the yes (its action, PR or route), or the yes predates that check: '
                              'the yes covers only what was asked; ask again')
    out_.emit('APPROVED', f'APPROVED {ident} by {record["by"]} at {record["at"]}: {gate["action"]} at {sha}', id=ident, sha=sha,
              by=record['by'], at=record['at'], action=gate['action'], kind=gate.get('kind'))


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
    if job_.front_door(job):
        if herdrapi_.inside_herdr():  # the lead could otherwise post its own plan and approve it
            raise PermissionError('in a front-door job approve runs only from the chat outside Herdr, after the owner said yes '
                                  'to the plan: an agent\'s own say-so never counts')
        box = Path(job) / 'outbox'
        seen = int((box / '.seen').read_text() or 0) if (box / '.seen').is_file() else 0
        for name in ('plan.md', 'fleet-plan.md'):
            plan = Path(job) / name
            if not plan.is_file():
                continue
            posted = [int(copy.parent.name) for copy in box.glob('*/' + name) if copy.read_bytes() == plan.read_bytes()]
            if not posted:
                raise PermissionError(f'the owner has not been shown this {name}: the lead posts it (fleet-job post <job> "PLAN READY" '
                                      f'--file {name}), the front door sends it to the owner, and only their yes to it is approved')
            if min(posted) > seen:  # posted, but the front door has not had it: a yes now cannot be a yes to this plan
                raise PermissionError(f'the front door has not received this {name} yet: run fleet-job wait <job>, send the owner '
                                      'the file it names, and approve only their yes to that file')
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    (Path(job) / 'approved').write_text(f'Approved: {when} by {base_.line(by)}, plan {digest}\n')
    started = 'helpers' if job_.backend(job) == 'native' else 'panes'
    tell(job, 'lead', f'Approved by {base_.line(by)} at {when}. Start the {started} the plan names.')


def require_approval(job):
    """A review job may open panes only once the owner approved the plan as it stands."""
    job = Path(job)
    if not (job / 'review').is_file():
        return
    record = (job / 'approved').read_text() if (job / 'approved').is_file() else ''
    if not record.rstrip().endswith('plan ' + plan_digest(job)):
        raise PermissionError('the owner asked to see this plan: run fleet-job approve after their yes, '
                              'and again after any change to the plan')


def caller_ids(job):
    """Where a job's event comes from: on the TUI, the caller's Herdr workspace and pane; on Core, the job's key and its
    lead's terminal, never the caller's environment (a TUI pane may run a Core job's command)."""
    from . import native as native_
    if job_.backend(job) == 'native':
        return native_.caller_ids(job)
    if job_.backend(job) != 'core':
        return {key: os.environ[name] for key, name in (('workspace', 'HERDR_WORKSPACE_ID'), ('lead_pane', 'HERDR_PANE_ID'))
                if os.environ.get(name)}
    key = job_.core_key(job)
    address = job_.core_entries(job).get(job_.roster(job)[1], {}).get('address')
    return {'workspace': key, **({'lead_pane': f'hc:{key}/{address}'} if address else {})}
