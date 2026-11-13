"""stampede's settings: each key resolved from layers, lowest first, the last one that sets it wins.
1 defaults.toml beside this file (the list of keys), 2 the user's config.toml, 3 <repo>/.stampede.toml, 4 the
environment (the variable names stampede always read), 5 a command's flags, then its --set key=value pairs.
A bad value, an unknown key or a file that does not parse is skipped and named in problems; it never stops a command."""
import difflib, json, os, re, socket
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.9 and 3.10
    tomllib = None

DEFAULTS_FILE = Path(__file__).resolve().parent / 'defaults.toml'
ENV = {'FLEET_LEAD_KIND': 'lead.kind', 'FLEET_ASK_CMD': 'ask.command', 'FLEET_JOBS_ROOT': 'jobs_root',
       'FLEET_TRUST_ROOT': 'trust_root', 'STAMPEDE_MAX_HELPERS': 'helpers.max', 'STAMPEDE_TAB_PANES': 'helpers.tab_panes'}
# FLEET_LEAD_MODEL and FLEET_LEAD_EFFORT set the pair of the CLI the model belongs to: see lead_env.
USER_ONLY = ('ask.command', 'jobs_root', 'trust_root', 'gates.')  # run a command or lower a safety rule: never from a repo
ENV_ONLY = (  # read by other programs too, so they stay environment variables: (name, default, what it does)
    ('FLEET_WATCH_INTERVAL', '30', 'seconds between passes of fleet-watch.sh'),
    ('FLEET_WATCH_PASSES', '0', 'fleet-watch.sh stops after this many passes; 0 runs until stopped'),
    ('FLEET_WATCH_NOTIFY', '1', '0 turns off the phone push for stalls and vanished agents'),
    ('HERDR_EVENTS_MACHINE', socket.gethostname().split('.')[0], 'short hostname sent with every event'),
    ('HERDR_EVENTS_HOME', '~/.herdr-events', 'the event queue and dead letters'),
    ('HERDR_EVENTS_ROUTES_DIR', '~/.config/herdr-events/routes', 'one file per route, holding URL= and KEY='),
    ('HERDR_EVENTS_FLUSH_LOG', '~/.herdr-events/flush.log', "the flusher's log"),
    ('HERDR_EVENTS_DIR', '~/.config/herdr-events', 'owner tags, job markers, handed panes'),
    ('HERDR_EVENTS_STALE_MINUTES', '30', "minutes a working terminal's screen may stay unchanged before stale"),
    ('HC', 'hc', 'the Herdr Core binary'),
    ('HC_SESSION', 'default', 'which core'),
    ('HC_SOCKET', '', "that core's socket; empty is Core's default path for the session"),
    ('STAMPEDE_APP_SPACE', '0', '1: every new --core --relay job labels its agents for the Herdr app'),
    ('STAMPEDE_NO_UPDATE_CHECK', '0', '1 turns the daily check for a newer release off'),
    ('STAMPEDE_UPDATE_URL', 'https://api.github.com/repos/vib-z/stampede/releases/latest', 'where it reads the latest release'))
KEY = re.compile(r'[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*')


def loads_subset(text):
    """The TOML these files use, for a Python without tomllib: comments, [table] and [a.b] headers, key = value (dotted keys
    too) with strings, integers, floats, booleans and arrays of those. Raises ValueError on anything else."""
    out, i, n = {}, 0, len(text)
    table = out

    def fail(why):
        raise ValueError(f'line {text.count(chr(10), 0, i) + 1}: {why}')

    def skip(newlines):
        nonlocal i
        while i < n:
            if text[i] in ' \t\r' or (newlines and text[i] == '\n'):
                i += 1
            elif text[i] == '#':
                while i < n and text[i] != '\n':
                    i += 1
            else:
                break

    def end_of_line():
        skip(False)
        if i < n and text[i] != '\n':
            fail('expected the end of the line')

    def name(stop):
        nonlocal i
        j = text.find(stop, i)
        key = text[i:j].strip() if j >= 0 else ''
        if not KEY.fullmatch(key):
            fail(f'bad key {key!r}')
        i = j + 1
        return [part.strip() for part in key.split('.')]

    def into(node, parts):
        for part in parts:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                fail(f'{part} is already a value')
        return node

    def value():
        nonlocal i
        c = text[i] if i < n else ''
        if c == '"':
            m = re.compile(r'"(?:[^"\\\n]|\\.)*"').match(text, i)
            if not m:
                fail('unclosed string')
            i = m.end()
            return json.loads(m.group(0))
        if c == "'":
            j = text.find("'", i + 1)
            if j < 0 or '\n' in text[i:j]:
                fail('unclosed string')
            word, i = text[i + 1:j], j + 1
            return word
        if c == '[':
            i, items = i + 1, []
            while True:
                skip(True)
                if i < n and text[i] == ']':
                    i += 1
                    return items
                items.append(value())
                skip(True)
                if i < n and text[i] == ',':
                    i += 1
                elif not (i < n and text[i] == ']'):
                    fail('expected , or ] in an array')
        m = re.compile(r'(true|false)\b|[+-]?\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?\b').match(text, i)
        if not m:
            fail('expected a value')
        i = m.end()
        word = m.group(0).replace('_', '')
        return word == 'true' if m.group(1) else float(word) if m.group(2) or m.group(3) else int(word)

    while True:
        skip(True)
        if i >= n:
            return out
        if text[i] == '[':
            i += 1
            table = into(out, name(']'))
        else:
            parts = name('=')
            skip(False)
            node = into(table, parts[:-1])
            if parts[-1] in node:
                fail(f'{parts[-1]} is set twice')
            node[parts[-1]] = value()
        end_of_line()



def parse(text):
    return tomllib.loads(text) if tomllib else loads_subset(text)


def flatten(tree, prefix=''):
    out = {}
    for key, value in tree.items():
        out.update(flatten(value, prefix + key + '.') if isinstance(value, dict) else {prefix + key: value})
    return out


DEFAULTS = flatten(parse(DEFAULTS_FILE.read_text(encoding='utf-8')))


def kind(value):
    return f'a list of {kind(value[0])}' if isinstance(value, list) and value else type(value).__name__


def fits(value, default):
    """The default's type is the key's type; a list's items take the type of the default's first item."""
    if isinstance(default, list):
        return isinstance(value, list) and all(type(item) is type(default[0]) for item in value)
    return type(value) is type(default)


def lead_env(env):
    """FLEET_LEAD_MODEL and FLEET_LEAD_EFFORT, as a pair, for the CLI the model belongs to: a gpt-... model is Codex's, any
    other (or none) Claude's. So a Claude lead's settings never reach a Codex one, nor the other way round."""
    model = env.get('FLEET_LEAD_MODEL') or ''
    cli = 'codex' if model.startswith('gpt') else 'claude'
    pairs = ((f'lead.{cli}.model', 'FLEET_LEAD_MODEL'), (f'lead.{cli}.effort', 'FLEET_LEAD_EFFORT'))
    return [(key, name) for key, name in pairs if env.get(name)]


class Settings:
    def __init__(self, values, sources, problems, files, environment):
        self.values, self.sources, self.problems, self.files, self.environment = values, sources, problems, files, environment

    def get(self, key):
        return self.values[key]

    def source(self, key):
        return self.sources[key]


def parse_set(pair):
    """--set key=value: the value read as a TOML value, else as the plain string it is."""
    key, eq, text = pair.partition('=')
    key, text = key.strip(), text.strip()
    if not eq or not KEY.fullmatch(key) or not text:
        raise ValueError(f'--set takes key=value, such as helpers.max=6; not {pair!r}')
    try:
        return key, parse('v = ' + text)['v']
    except ValueError:
        return key, text


def load(repo=None, env=None, flags=None, sets=(), home=None):
    """Every setting with the layer it came from. A job's saved, resolved values can later stand in for layers 1 to 4:
    start values and sources from them instead of the defaults, files and environment, then apply flags and sets."""
    env = os.environ if env is None else env
    user = Path(env.get('XDG_CONFIG_HOME') or Path(home or Path.home()) / '.config') / 'stampede' / 'config.toml'
    paths = {'user': user} if repo is None else {'user': user, 'repo': Path(repo) / '.stampede.toml'}
    values, sources, problems = dict(DEFAULTS), dict.fromkeys(DEFAULTS, 'default'), []

    def put(key, value, source, where):
        if source == 'repo' and key.startswith(USER_ONLY):
            problems.append(f'{where}: {key} is taken only from your own {user}, the environment or a flag, '
                            f'never from a repo; skipped')
        elif key not in DEFAULTS:
            close = difflib.get_close_matches(key, DEFAULTS, n=1)
            problems.append(f'{where}: {key} is not a setting' + (f' (did you mean {close[0]}?)' if close else '') + '; skipped')
        elif not fits(value, DEFAULTS[key]):
            problems.append(f'{where}: {key} must be {kind(DEFAULTS[key])}, not {value!r}; skipped')
        else:
            values[key], sources[key] = value, source

    for source, path in paths.items():
        if path.is_file():
            try:
                tree = parse(path.read_text(encoding='utf-8'))
            except (OSError, UnicodeDecodeError, ValueError) as error:
                problems.append(f'{path}: not readable TOML ({error}); the whole file is skipped')
                continue
            for key, value in flatten(tree).items():
                put(key, value, source, path)
    for key, name in [(key, name) for name, key in ENV.items() if env.get(name)] + lead_env(env):
        text = env[name]
        number = isinstance(DEFAULTS[key], int) and re.fullmatch(r'[+-]?\d+', text)
        put(key, int(text) if number else text, 'env:' + name, 'environment ' + name)
    for key, value in (flags or {}).items():
        if value is not None:  # a flag the command was not given
            put(key, value, 'flag', 'flag ' + key)
    for pair in sets:
        put(*parse_set(pair), 'set', '--set ' + pair)
    files = {source: {'path': str(path), 'exists': path.is_file()} for source, path in paths.items()}
    environment = {name: env.get(name) or default for name, default, _ in ENV_ONLY}  # an empty one means unset
    return Settings(values, sources, problems, files, environment)


def show(settings, as_json=False):
    """What every setting is and where it came from, then the environment-only variables, then the problems."""
    if as_json:
        return json.dumps({'values': settings.values, 'sources': settings.sources, 'files': settings.files,
                           'environment': settings.environment, 'problems': settings.problems}, indent=2)
    lines = [f"# {source} config: {f['path']} ({'found' if f['exists'] else 'none'})" for source, f in settings.files.items()]
    table = None
    for key, value in settings.values.items():
        if key.rpartition('.')[0] != table:
            table = key.rpartition('.')[0]
            lines.append('')
        lines.append(f'{key} = {json.dumps(value)}  ({settings.source(key)})')
    lines += ['', '# environment only: other programs read these too']
    lines += [f'{name} = {json.dumps(value)}  ({"env" if value != default else "default"})'
              for (name, default, _), value in zip(ENV_ONLY, settings.environment.values())]
    if settings.problems:
        lines += ['', '# problems'] + settings.problems
    return '\n'.join(lines) + '\n'
