"""The job folder and its record: roster, backend, keys, markers, owner and core.json."""
import contextlib, fcntl, hashlib, json, os, re, subprocess
from pathlib import Path

from . import base as base_


def roster(job):
    """name -> kind from agents.tsv, and the lead's name from the `lead` file."""
    job = Path(job)
    people = {}
    tsv = job / 'agents.tsv'
    if tsv.is_file():
        for row in tsv.read_text().splitlines():
            if row and not row.startswith('#'):
                name, kind = row.split('\t')[:2]
                people[name] = kind
    lead = (job / 'lead').read_text().strip() if (job / 'lead').is_file() else ''
    return people, lead


def lead_kind(job):
    """The lead's CLI, from agents.tsv: 'claude' or 'codex'."""
    people, lead = roster(job)
    return people.get(lead, 'claude')


def job_owner(job):
    """The bot that started the job (fleet-job new wrote it), or '' for a job started locally."""
    path = Path(job) / 'owner'
    owner = path.read_text().strip() if path.is_file() else ''
    if owner and not base_.OWNER.fullmatch(owner):
        raise ValueError('the owner file of this job holds no bot slug: ' + base_.line(owner))
    return owner


def front_door(job):
    """True when a chat outside Herdr started the job and stays the owner's only contact (fleet-job new --front-door)."""
    return (Path(job) / 'front-door').is_file()


def events_dir():
    """Owner tags, job markers and the default routes folder: HERDR_EVENTS_DIR, else ~/.config/herdr-events."""
    return Path(os.environ.get('HERDR_EVENTS_DIR') or Path.home() / '.config/herdr-events').expanduser()


def starter(workspace):
    """At fleet-job new: HERDR_EVENTS_OWNER, else the workspace's owner tag (herdr-events-owner); '' when local.
    A slug that is set but malformed is refused: it must never turn a bot's job into a local one."""
    owner, source = os.environ.get('HERDR_EVENTS_OWNER', '').strip(), 'HERDR_EVENTS_OWNER'
    tag = events_dir() / 'owners' / str(workspace)
    if not owner and workspace and tag.is_file():
        owner = next((row[len('owner='):].strip() for row in tag.read_text().splitlines() if row.startswith('owner=')), '')
        source = 'the owner tag of ' + str(workspace)
    if owner and not base_.OWNER.fullmatch(owner):
        raise ValueError(f'{source} holds no bot slug ({base_.line(owner)}): fix it with herdr-events-owner, then start again')
    return owner


def job_marker(workspace):
    """File whose presence means this workspace (or Core job key) has an open job. None for any other id."""
    if not workspace or not (base_.WS_ID.fullmatch(str(workspace)) or base_.KEY.fullmatch(str(workspace))):
        return None
    return events_dir() / 'jobs' / str(workspace)


def mark_job(workspace, job):
    path = job_marker(workspace)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(Path(job).absolute()) + '\n')
    (Path(job) / 'workspace').write_text(str(workspace) + '\n')


def clear_job_marker(workspace, job):
    path = job_marker(workspace)
    if path is None or not path.is_file():
        return
    if path.read_text().strip() == str(Path(job).absolute()):
        path.unlink()


def backend(job):
    """'native' for a job stampede new --core made, 'core' for one new --core --relay made; 'tui' for every other job,
    those made before Core included."""
    path = Path(job) / 'backend'
    found = path.read_text().strip() if path.is_file() else ''
    return found if found in ('native', 'core') else 'tui'


def job_key(job):
    """A new Core job's key: hc- and the first 12 hex of the SHA-256 of the job folder's absolute path."""
    return 'hc-' + hashlib.sha256(str(Path(job).absolute()).encode()).hexdigest()[:12]


def core_key(job):
    """The key a Core job recorded at new, in its workspace file."""
    path = Path(job) / 'workspace'
    key = path.read_text().strip() if path.is_file() else ''
    if not base_.KEY.fullmatch(key):
        raise ValueError(f'{job} is no Herdr Core job: its workspace file holds no hc- key')
    return key


def endpoint(job):
    """The Herdr Core a job was made on: HC_SESSION and HC_SOCKET as they were at new; '' is Core's default."""
    path = Path(job) / 'endpoint'
    return json.loads(path.read_text()) if path.is_file() else {'session': '', 'socket': ''}


def core_entries(job):
    path = Path(job) / 'core.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def bind(job, agent, fields, fresh=False):
    """Update one agent's entry in core.json ({state, address, name, role, session, socket, reason}): under core.json.lock
    only for this write, by a temporary file and os.replace, so no writer clobbers another's. fresh: a new launch's entry."""
    job = Path(job)
    with (job / 'core.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = core_entries(job)
        entries[agent] = dict(fields) if fresh else {**entries.get(agent, {}), **fields}
        temporary = job / ('.core.json.' + str(os.getpid()))
        temporary.write_text(json.dumps(entries, indent=1) + '\n')
        os.replace(temporary, job / 'core.json')
    return entries[agent]


@contextlib.contextmanager
def launching(job, agent):
    """Own this agent's launch: an exclusive lock on <job>/locks/<agent>.lock, held until its entry is live or failed.
    The kernel drops it when the caller dies, so a lock nobody holds means no launch is in flight, whatever core.json says."""
    path = Path(job) / 'locks' / (agent + '.lock')
    path.parent.mkdir(exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = os.read(fd, 32).decode(errors='replace').strip() or 'unknown'
            raise ValueError(f'{agent} is being started by another caller (pid {holder})') from None
        os.ftruncate(fd, 0)
        os.pwrite(fd, str(os.getpid()).encode(), 0)
        yield
    finally:
        os.close(fd)


def record(job, agent, kind, brief, args, session=''):
    """How an agent was started, for reopen (agents.tsv); a Claude agent's session id is chosen by stampede on Core."""
    subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), agent, kind,
                    str(brief), *(['--session', session] if session else []), '--', *args], check=True, capture_output=True)


def snapshot(job):
    """Refresh a Core job's reopen record (REOPEN.md and reopen.sh, from agents.tsv and core.json)."""
    subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), core_key(job), str(job)],
                   check=True, capture_output=True)


def agent_rows(job):
    """agents.tsv: name -> {kind, session, brief, args}."""
    path, rows = Path(job) / 'agents.tsv', {}
    for row in (path.read_text().splitlines() if path.is_file() else []):
        if row and not row.startswith('#'):
            cells = (row.split('\t') + [''] * 5)[:5]
            rows[cells[0]] = dict(zip(('kind', 'session', 'brief', 'args'), cells[1:]))
    return rows


FILLER = {'a', 'an', 'the', 'on', 'in', 'of', 'to', 'for', 'and', 'please', 'can', 'you', 'we', 'i', 'my', 'our', 'it', 'this', 'that'}


def slug(ask):
    words = [w for w in re.findall(r'[a-z0-9]+', ask.lower().split('\n')[0]) if w not in FILLER]
    out = ''
    for word in words:
        if len(out) + bool(out) + len(word) > 24:
            break
        out += '-' * bool(out) + word
    return out or 'job'


def jobs_root():
    """Every job folder lives under <root>/jobs, never in the repo it works on (owner, 25 Oct 2026)."""
    return Path(os.environ.get('FLEET_JOBS_ROOT') or '~/code/herdr-jobs').expanduser().absolute()


def make_job(repo, job, ask, owner, review, name=None, front=False):
    """The job folder, its ask, owner, review and front-door files, and the lead's name. A folder inside the repo (a Herdr
    Core job's .herdr-<name>) is git-excluded; one under the jobs root records the repo it works on in `workdir`."""
    job.mkdir(parents=True, exist_ok=False)
    if repo in job.parents:
        probe = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-path', 'info/exclude'], capture_output=True, text=True)
        if probe.returncode == 0:
            exclude = repo / probe.stdout.strip()  # an absolute path stays absolute
            if not exclude.exists() or '/.herdr-*/' not in exclude.read_text().splitlines():
                base_.append(exclude, '/.herdr-*/')
    else:
        (job / 'workdir').write_text(str(repo) + '\n')
    (job / 'ask.md').write_text(ask)
    if owner:
        (job / 'owner').write_text(owner + '\n')
    if review:
        (job / 'review').write_text('The owner asked to see the plan before any pane opens.\n')
    if front:
        (job / 'front-door').write_text('The chat that started this job is the owner\'s only contact: it relays <job>/outbox.\n')
    lead = 'lead-' + (name or job.name[len('.herdr-'):])
    (job / 'lead').write_text(lead + '\n')
    return lead


def core_repo(cwd):
    """A Core job's repo: --cwd, else the git root of the current folder; under FLEET_TRUST_ROOT, as herdr-trust requires."""
    if cwd is None:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if top.returncode:
            raise ValueError('new --core needs --cwd <repo>, or run it inside a git repo')
        cwd = top.stdout.strip()
    repo = Path(cwd).expanduser().resolve()
    root = Path(os.environ.get('FLEET_TRUST_ROOT') or '~/code').expanduser().resolve()
    if not repo.is_dir() or (repo != root and root not in repo.parents):
        raise ValueError(f'{repo} is not a folder under FLEET_TRUST_ROOT ({root}): run herdr-trust on a repo there first')
    return repo


def tag_owner(job, key, owner):
    """A Core job's owner tag: its bot, and the core it runs on (when not the default), which the watchdog asks."""
    point = endpoint(job)
    (events_dir() / 'owners').mkdir(parents=True, exist_ok=True)
    (events_dir() / 'owners' / key).write_text(f'owner={owner}\n' + ''.join(f'{k}={point[k]}\n' for k in ('session', 'socket') if point.get(k)))
