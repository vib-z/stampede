"""One eval run on disk: env.json, results.jsonl (one line per case) and summary.md, under tests/evals/runs/<run>/.

Every runner (run.py for the fixture cases, live/tui_e2e.py and live/core_e2e.py for the live ones) records through
this file, so every run has the same shape. Everything written is scrubbed: the home folder becomes ~, the checkout
<repo>, this machine's name <host> and the user's name <user>, so a run can be committed.

    run = Run('baseline-fixture', backend='fixture', cases=['G01', 'G02'])
    run.case('G01', 'pass', None, actual='APPROVED ...', commands=[...], log='...')
    sys.exit(run.close())   # G02 got no result: recorded as error

Every selected case gets exactly one result; its expectation is always the dataset's own text. env.json names what
was measured (the product files' digest and commit) apart from what measured it (the dataset's and the harness's
digests), with the argv, the settings that matter and each tool's path and sha256. In a container with no .git, the
host passes STAMPEDE_EVAL_COMMIT and STAMPEDE_EVAL_DIRTY.
"""
from datetime import datetime, timezone
import getpass, hashlib, json, os, platform, re, shutil, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = HERE / 'runs'
STATUSES = ('pass', 'fail', 'error', 'blocked', 'skip', 'gap')
# pass and fail: the case ran and its expectation held or did not. error: the harness broke, so nothing is known.
# blocked: it could not run here (a missing tool or backend). skip: it does not apply here (the reason says why).
# gap: a known ceiling, documented; the actual behaviour is recorded and never counted as a pass.
LOG_TAIL = 4000  # characters of a case's log kept in results.jsonl
TOOLS = {'herdr': ['herdr', '--version'], 'hc': ['hc', '--version'], 'moshi-hook': ['moshi-hook', '--version'],
         'jq': ['jq', '--version'], 'git': ['git', '--version'], 'bash': ['bash', '--version'], 'python3': ['python3', '--version'],
         'claude': ['claude', '--version'], 'codex': ['codex', '--version'], 'systemctl': ['systemctl', '--version'],
         'flock': ['flock', '--version'], 'ps': ['ps', '--version']}


def _patterns():
    home = str(Path.home())
    pairs = [(str(ROOT), '<repo>'), (os.path.realpath(ROOT), '<repo>')]
    if home not in ('/', ''):
        pairs += [(os.path.realpath(home), '~'), (home, '~')]
    names = {socket.gethostname(), socket.gethostname().split('.')[0], platform.node()}
    user = getpass.getuser()
    return pairs, sorted({n for n in names if len(n) > 2}, key=len, reverse=True), user


PAIRS, HOSTS, USER = _patterns()


def scrub(text):
    """No home path, checkout path, host name or user name in anything a run writes."""
    text = str(text)
    for old, new in PAIRS:
        text = text.replace(old, new)
    text = re.sub(r'/' r'Users/[^/\s"\']+', '~', text)
    text = re.sub(r'/home/(?!you\b|user\b)[^/\s"\']+', '~', text)
    for name in HOSTS:
        text = re.sub(r'\b' + re.escape(name) + r'\b', '<host>', text)
    if len(USER) > 2:
        text = re.sub(r'\b' + re.escape(USER) + r'\b', '<user>', text)
    return text


def _version(argv):
    if not shutil.which(argv[0]):
        return None
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'
    first = (out.stdout or out.stderr).strip().splitlines()
    return first[0][:120] if first else 'unknown'


def os_name():
    if platform.system() == 'Linux' and Path('/etc/os-release').is_file():
        rows = dict(row.split('=', 1) for row in Path('/etc/os-release').read_text().splitlines() if '=' in row)
        return rows.get('PRETTY_NAME', 'Linux').strip('"')
    if platform.system() == 'Darwin':
        return 'macOS ' + platform.mac_ver()[0]
    return platform.system()


PRODUCT = ('skills', 'scripts', 'install.sh', 'herdr-plugin.toml', 'VERSION')
HARNESS = ('tests/evals', 'tests/clients_run.py', 'tests/fake_herdr.py', 'tests/fake_hc.py', 'tests/fake_agent.py',
           'tests/test_core.py', 'tests/test_clients.py', 'tests/test_fleet_job.py', 'tests/test_herdr_reopen_snapshot.py')
SETTINGS = re.compile(r'^(FLEET_|HERDR_|HC_|STAMPEDE_|XDG_|CODEX_HOME$|PATH$|HOME$|LANG$|LC_|TMPDIR$)')
SECRET = re.compile(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL', re.I)


def digest(parts, skip=('tests/evals/runs',)):
    """sha256 over each file's relative path and bytes, in order; works with or without .git."""
    h = hashlib.sha256()
    for part in parts:
        top = ROOT / part
        files = [top] if top.is_file() else sorted(f for f in top.rglob('*') if f.is_file()) if top.is_dir() else []
        for f in files:
            rel = f.relative_to(ROOT).as_posix()
            if any(rel.startswith(s) for s in skip) or '__pycache__' in rel:
                continue
            h.update(rel.encode() + b'\0' + f.read_bytes() + b'\0')
    return h.hexdigest()


def tool(name, argv):
    path = shutil.which(name)
    if not path:
        return None
    real = os.path.realpath(path)
    try:
        sha = hashlib.sha256(Path(real).read_bytes()).hexdigest()
    except OSError:
        sha = None
    return {'version': _version(argv), 'path': path, 'sha256': sha}


def environment(backend, extra=None):
    git = lambda *a: subprocess.run(['git', '-C', str(ROOT), *a], capture_output=True, text=True).stdout.strip() \
        if (ROOT / '.git').exists() else ''
    commit = git('rev-parse', 'HEAD') or os.environ.get('STAMPEDE_EVAL_COMMIT') or None
    dirty = bool(git('status', '--porcelain')) if git('rev-parse', 'HEAD') else os.environ.get('STAMPEDE_EVAL_DIRTY') == '1'
    return {'when': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'backend': backend, 'os': os_name(),
            'kernel': platform.release(), 'arch': platform.machine(), 'python': platform.python_version(),
            'commit': commit, 'dirty': dirty, 'product_sha256': digest(PRODUCT), 'harness_sha256': digest(HARNESS),
            'dataset_sha256': hashlib.sha256((HERE / 'cases.json').read_bytes()).hexdigest(),
            'argv': [sys.executable, *sys.argv], 'in_container': Path('/.dockerenv').exists(),
            'settings': {k: v for k, v in sorted(os.environ.items()) if SETTINGS.match(k) and not SECRET.search(k)},
            'tools': {name: tool(name, argv) for name, argv in TOOLS.items()}, **(extra or {})}


class Run:
    def __init__(self, label, backend, cases=None, out_root=None, extra=None):
        """cases: the ids this run will record, each exactly once (default: every case of this backend)."""
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,60}', label):
            raise ValueError('a run label is lowercase letters, digits and dashes')
        self.dataset = globals()['cases']()
        self.selected = list(cases) if cases is not None else [i for i, c in self.dataset.items() if c['backend'] == backend]
        unknown = [i for i in self.selected if i not in self.dataset]
        if unknown or len(set(self.selected)) != len(self.selected):
            raise ValueError(f'unknown or repeated case ids: {unknown or self.selected}')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.dir = Path(out_root or RUNS) / f'{stamp}-{label}'
        self.dir.mkdir(parents=True)
        self.label, self.backend, self.rows, self.started = label, backend, [], time.time()
        self.env = {**environment(backend, extra), 'label': label, 'selected': self.selected}
        (self.dir / 'env.json').write_text(scrub(json.dumps(self.env, indent=1)) + '\n')

    def case(self, case_id, status, expected=None, actual='', commands=(), log='', seconds=None, notes='', measured=None):
        """One result. expected is ignored: the dataset's text is the expectation. measured: for a known gap, whether
        its expectation held here (pass) or not (fail), so a later change shows."""
        if status not in STATUSES:
            raise ValueError(f'status {status} is not one of {STATUSES}')
        if case_id not in self.selected:
            raise ValueError(f'{case_id} is not a case this run selected')
        if any(r['id'] == case_id for r in self.rows):
            raise ValueError(f'{case_id} already has a result in this run')
        row = {'id': case_id, 'status': status, 'measured': measured, 'expected': scrub(self.dataset[case_id]['expect']), 'actual': scrub(actual),
               'commands': [scrub(c) for c in commands], 'log': scrub(str(log)[-LOG_TAIL:]),
               'seconds': None if seconds is None else round(seconds, 2), 'notes': scrub(notes)}
        self.rows.append(row)
        with (self.dir / 'results.jsonl').open('a') as out:
            out.write(json.dumps(row) + '\n')
        print(f'{status.upper():7} {case_id} {row["actual"][:150]}', flush=True)
        return row

    def close(self):
        """Write summary.md; 0 when nothing failed or broke. A selected case with no result is an error."""
        for case_id in [i for i in self.selected if not any(r['id'] == i for r in self.rows)]:
            self.case(case_id, 'error', actual='no result recorded: the runner never reached this case')
        counts = {s: sum(r['status'] == s for r in self.rows) for s in STATUSES}
        tools = ', '.join(f'{k} {v["version"]}' for k, v in self.env['tools'].items() if v)
        lines = [f'# Eval run {self.dir.name}', '',
                 f'Backend {self.backend}; {self.env["os"]} {self.env["arch"]}; Python {self.env["python"]}; '
                 f'commit {(self.env["commit"] or "none")[:12]}{" (dirty)" if self.env["dirty"] else ""}; '
                 f'{round(time.time() - self.started)} s.', '',
                 f'Product {self.env["product_sha256"][:12]}, harness {self.env["harness_sha256"][:12]}, dataset '
                 f'{self.env["dataset_sha256"][:12]}; {len(self.selected)} cases selected.', '', f'Tools: {tools}.', '',
                 '| status | count |', '|---|---|', *[f'| {s} | {counts[s]} |' for s in STATUSES], '',
                 '| case | status | expected | actual |', '|---|---|---|---|']
        cell = lambda t: scrub(t).replace('|', '\\|').replace('\n', ' ')[:200]
        lines += [f'| {r["id"]} | {r["status"]} | {cell(r["expected"])} | {cell(r["actual"])} |' for r in self.rows]
        (self.dir / 'summary.md').write_text('\n'.join(lines) + '\n')
        print(f'{self.dir}: ' + ', '.join(f'{counts[s]} {s}' for s in STATUSES if counts[s]), flush=True)
        return 1 if counts['fail'] or counts['error'] else 0


def cases():
    """The dataset: tests/evals/cases.json, by id."""
    data = json.loads((HERE / 'cases.json').read_text())
    return {c['id']: c for c in data['cases']}


if __name__ == '__main__':
    print(json.dumps(environment(sys.argv[1] if len(sys.argv) > 1 else 'none'), indent=1))
