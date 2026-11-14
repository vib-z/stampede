"""--json: a command's result lines, each with its facts. Without --json, emit prints the line as it always did; with it,
the facts are kept and as_json prints one object at the end, and nothing else reaches stdout: a subprocess's output
goes to stderr, and any other line this process prints goes under "notes"."""
import contextlib, io, json, os, sys

RESULTS = []
FACTS = {}
SINK = None  # the buffer stdout points at while as_json runs; a line printed anywhere else is no result
LISTS = ('next', 'reopen', 'close', 'wait')  # their results are always the list under "results"


def emit(status, text, /, end='\n', **facts):
    """One result line: status is its first word (or words, NOT READY), facts what it names."""
    if SINK is None or sys.stdout is not SINK:
        return print(text, end=end)
    RESULTS.append({'status': status, **facts})


def said(text, /, end='\n', **facts):
    """A line another program wrote, such as herdr-send's SUBMITTED or FAILED <agent> (...)."""
    words = text.split()
    emit(words[0] if words else None, text, end, agent=words[1].rstrip(':') if len(words) > 1 else None, **facts)


ERROR = []  # [line, retry]: the refusal main would print on stderr


def refuse(line, retry=None):
    if SINK is None:
        print(line, file=sys.stderr)
        if retry:
            print(retry, file=sys.stderr)
    else:
        ERROR[:] = [line, retry]


def as_json(command, body):
    """Run body() with --json: return its exit code, having printed one object on the real stdout."""
    global SINK
    sys.stdout.flush()
    real = os.dup(1)
    os.dup2(2, 1)  # a subprocess's stdout goes to stderr, never into the object
    SINK, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(SINK), contextlib.redirect_stderr(err):
            try:
                code = body()
            except SystemExit as stop:  # argparse's usage error, or a SystemExit(2) after a FAILED line
                code = stop.code
    finally:
        notes = [line for line in (SINK.getvalue() + err.getvalue()).splitlines() if line.strip()]
        SINK = None
        os.dup2(real, 1)
        os.close(real)
    code = code if isinstance(code, int) else 0 if code is None else 1
    obj = {'ok': code == 0, 'command': command, 'status': None, **FACTS}
    if RESULTS:
        obj.update(RESULTS[-1])
    if len(RESULTS) > 1 or command in LISTS:
        obj['results'] = RESULTS
    if ERROR or (code and not RESULTS):  # a refusal, or argparse's: its last line is the reason
        line = ERROR[0] if ERROR else (notes[-1] if notes else f'exit {code}')
        obj.update(error=line, retry=ERROR[1] if ERROR else None)
        notes = [n for n in notes if n != line]
    if notes:
        obj['notes'] = notes
    print(json.dumps(obj))
    return code


def wants(argv):
    """True when argv asks for --json before any -- (a program's own flags come after it)."""
    return '--json' in (argv[:argv.index('--')] if '--' in argv else argv)

