"""--json: a command's result lines, each with its facts. Without --json, emit prints the line as it always did; with it,
the facts are kept and as_json prints one object at the end, and nothing else reaches stdout: a subprocess's output
goes to stderr, and any other line this process prints goes under "notes". Whatever way the command ends (a refusal,
a usage error, an exception, an interrupt), stdout holds exactly one object."""
import contextlib, io, json, os, re, sys, traceback

LISTS = ('next', 'reopen', 'close', 'wait')  # their results are always the list under "results"
RUN = None  # the Run of the --json call under way, only while as_json runs it


class Run:
    """What one --json call collects: its results, the facts every result shares, its refusal."""
    def __init__(self):
        self.sink, self.results, self.facts, self.error = io.StringIO(), [], {}, None


def emit(status, text, /, end='\n', **facts):
    """One result line: status is its first word (or words, NOT READY), facts what it names. A line printed while stdout
    points elsewhere (merge's quiet gate-ok) is no result."""
    if RUN is None or sys.stdout is not RUN.sink:
        return print(text, end=end)
    RUN.results.append({'status': status, **facts})


SAID = re.compile(r'(?P<status>[A-Z][A-Z_]*) (?P<agent>[^\s(]*[^\s(:]):? ?(?:\((?P<inside>[^)]*)\))?(?P<rest>.*)', re.S)


def said(text, /, end='\n', **facts):
    """A line another program wrote: herdr-send's or send_core's `SUBMITTED <agent> [(<address>)]`, or
    `FAILED <agent> (<reason>)` or `FAILED <agent> <reason>`, with the same facts as a line printed here."""
    m = SAID.fullmatch(text.strip())
    if not m:
        return emit(text.split()[0] if text.split() else None, text, end, **facts)
    inside, rest = m.group('inside'), m.group('rest').strip()
    if m.group('status') == 'SUBMITTED':
        found = {'agent': m.group('agent'), 'address': inside if inside and ' ' not in inside else None}
    else:
        found = {'agent': m.group('agent'), 'reason': inside or rest.lstrip(': ') or None}
    emit(m.group('status'), text, end, **found, **facts)


def fact(**facts):
    """Facts of the whole call, such as job or backend; nothing without --json."""
    if RUN is not None:
        RUN.facts.update(facts)


def refuse(line, retry=None):
    """The refusal main prints on stderr: with --json, the object's error and retry."""
    if RUN is None:
        print(line, file=sys.stderr)
        if retry:
            print(retry, file=sys.stderr)
    else:
        RUN.error = (line, retry)


def as_json(command, body):
    """Run body() with --json: return its exit code, having printed one object on the real stdout."""
    global RUN
    run = RUN = Run()
    sys.stdout.flush()
    real = os.dup(1)
    os.dup2(2, 1)  # a subprocess's stdout goes to stderr, never into the object
    err, crash = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(run.sink), contextlib.redirect_stderr(err):
            try:
                code = body()
            except SystemExit as stop:  # argparse's usage error, or a SystemExit(2) after a FAILED line
                code = stop.code
            except KeyboardInterrupt:
                code, crash = 130, ('KeyboardInterrupt: interrupted', '')
            except Exception as error:  # a bug: the object says so, and its traceback goes to stderr as without --json
                code, crash = 1, (f'{type(error).__name__}: {error}', traceback.format_exc())
    finally:
        RUN = None
        sys.stdout.flush()
        os.dup2(real, 1)
        os.close(real)
    notes = [line for line in (run.sink.getvalue() + err.getvalue()).splitlines() if line.strip()]
    if isinstance(code, str):  # SystemExit('text'): Python prints the text and exits 1
        notes.append(code)
        code = 1
    code = 0 if code is None else code
    obj = {'ok': code == 0, 'command': command, 'status': None, **run.facts}
    if run.results:
        obj.update(run.results[-1])
    if len(run.results) > 1 or command in LISTS:
        obj['results'] = run.results
    if crash:
        obj.update(error=crash[0], retry=None)
        sys.stderr.write(crash[1])
    elif run.error or (code and not run.results):  # a refusal, or argparse's: its last line is the reason
        line = run.error[0] if run.error else (notes[-1] if notes else f'exit {code}')
        obj.update(error=line, retry=run.error[1] if run.error else None)
        notes = [n for n in notes if n != line]
    if notes:
        obj['notes'] = notes
    try:
        print(json.dumps(obj), flush=True)
    except BrokenPipeError:  # the reader went away: nothing more to say, and the exit code stands
        os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
    return code


def split(argv, commands):
    """(command, argv without --json) when argv asks for --json for one of commands, before or after the command's name
    and anywhere among its arguments up to a -- that starts a program (after it, the flag is the program's); else
    (None, argv)."""
    cut = argv.index('--') if '--' in argv else len(argv)
    head, tail = argv[:cut], argv[cut:]
    command = next((a for a in head if not a.startswith('-')), None)
    if '--json' not in head or command not in commands:
        return None, argv
    return command, [a for a in head if a != '--json'] + tail
