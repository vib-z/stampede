"""The hc call to Herdr Core and what it needs: errors, endpoint, environment, draft hold and typing guard."""
import json, math, os, re, subprocess
from pathlib import Path

from . import base as base_, job as job_, settings as settings_


def default_socket(session):
    """The socket path Core uses for a session when HC_SOCKET is unset (the follower holds Core's rule)."""
    env = {**os.environ, 'HC_SESSION': session, 'HC_SOCKET': ''}
    found = subprocess.run([str(base_.FOLLOWER), '--socket'], capture_output=True, text=True, env=env)
    return os.path.normpath(found.stdout.strip()) if found.returncode == 0 and found.stdout.strip() else None


def target(job):
    """Point every hc call of this process, and every terminal it starts, at the job's own core. A caller whose
    HC_SESSION or HC_SOCKET names another core is refused, never retargeted: there the job would start a second time."""
    recorded = job_.endpoint(job)
    for name, key, default in (('HC_SESSION', 'session', 'default'), ('HC_SOCKET', 'socket', '')):
        mine, want = (os.environ.get(name) or '').strip(), recorded.get(key) or ''
        if name == 'HC_SOCKET' and mine and not want and os.path.normpath(mine) == default_socket(recorded.get('session') or ''):
            mine = ''  # the default socket's own path is the default core
        if mine and mine != (want or default):
            raise ValueError(f'{Path(job).absolute()} runs on Herdr Core {name}={want or "(default)"}, but {name} here is '
                             f'{mine}: unset it or set it to the job\'s, so the job never starts a second time on another core')
        if want:
            os.environ[name] = want
        else:
            os.environ.pop(name, None)
    TARGET[:] = [job]


class HcError(RuntimeError):
    def __init__(self, message, kind='', code=1):
        super().__init__(message)
        self.kind, self.code = kind, code


TARGET = []  # the job target() pointed this process at: its saved settings time every hc call


def hc_call(job=None):
    """Seconds one hc call may take on top of what the command itself waits for: that job's timeouts.hc_call (else the
    job target() last pointed this process at, else the live layers). Every call for a job passes its job."""
    return settings_.current(job if job is not None else TARGET[-1] if TARGET else None).get('timeouts.hc_call')


# A send is stopped SEND_MARGIN seconds before Core's draft hold could run out, so it never goes in after a draft someone
# began after stampede looked at the prompt and then left: Core types after a draft only once its hold is over, and a
# send stopped while held types nothing. SEND_FLOOR is what a send needs with no draft (Core's quiet pause, then its
# look for a started turn), so a shorter hold than their sum leaves no safe limit.
SEND_MARGIN, SEND_FLOOR = 10, 15
HOLD_SINCE = (0, 1, 20)  # the Herdr Core that holds a send while a person has an unsent draft


DRAFT_DEFAULT = 60.0  # Core's own draft_wait


def draft_config(env=None):
    """Herdr Core's draft_wait as its config.toml gives it, read as Core reads it: ('set', seconds) for a number there (a
    negative one is 0); ('default', 60.0) when the file does not set it, is missing, or is no valid TOML (Core then uses
    its defaults); ('unknown', None) when what it sets cannot be established here: not a finite number of seconds that
    fits a duration, or a file that names draft_wait on a Python with no TOML parser (3.11 has one). env: the
    environment whose config folder it is, the running core's own (core_env); this process's when none is given."""
    env = os.environ if env is None else env
    config = Path(env.get('XDG_CONFIG_HOME') or Path(env.get('HOME') or Path.home()) / '.config') / 'herdr-core/config.toml'
    try:
        text = config.read_text()
    except (OSError, ValueError):  # no file, or not text: nothing Core could read a setting from
        return 'default', DRAFT_DEFAULT
    try:
        import tomllib
    except ImportError:
        return ('unknown', None) if 'draft_wait' in text else ('default', DRAFT_DEFAULT)
    try:
        settings = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return 'default', DRAFT_DEFAULT
    if 'draft_wait' not in settings:
        return 'default', DRAFT_DEFAULT
    value = settings['draft_wait']
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value > 1e9:
        return 'unknown', None
    return 'set', max(0.0, float(value))


def core_hold():
    """(seconds, where it is set): how long the running Herdr Core (0.1.20 on) holds a send while a person's draft sits
    unsent, resolved as Core resolves it, from the core's own environment (core_env): draft_wait in the config.toml
    that environment names, else its HC_DRAFT_MS (a setting for Core's tests, and still what it would use), else
    Core's 60. (None, why) when that cannot be established. The one value both decides whether lines may be typed
    unattended and limits every send, so the two never disagree. An older core holds nothing."""
    env = core_env()
    if env is None:
        return None, 'the running core\'s environment cannot be read (hc exec), so how long it holds a message for a draft is not known'
    kind, seconds = draft_config(env)
    if kind == 'set':
        return seconds, 'in Herdr Core\'s config.toml'
    if kind == 'unknown':
        return None, ('draft_wait in Herdr Core\'s config.toml cannot be read here as Core reads it (not a plain number of seconds, '
                      'or this Python has no TOML parser)')
    if 'HC_DRAFT_MS' in env:
        try:
            fallback = float(env['HC_DRAFT_MS'])
        except ValueError:
            fallback = math.nan
        if not math.isfinite(fallback):
            return None, 'HC_DRAFT_MS in the running core\'s environment is no number'
        return max(0.0, fallback) / 1000, 'by HC_DRAFT_MS in the running core\'s environment'
    return seconds, 'by Herdr Core\'s default'


def core_env():
    """The running core's own environment, as a program it runs sees it (hc exec, read only, as herdr-doctor reads it):
    {name: value}, or None when it cannot be read. Core reads its config from the folders this names, which need not
    be this process's."""
    try:
        shown = subprocess.run([os.environ.get('HC') or 'hc', 'exec', '--', '/usr/bin/env'], capture_output=True, text=True, timeout=hc_call())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if shown.returncode:
        return None
    return dict(row.split('=', 1) for row in shown.stdout.splitlines() if '=' in row)


def send_limit(seconds=None):
    """Seconds a send may take, for a hold of that many seconds (default: core_hold's): up to SEND_MARGIN before the
    hold could run out, and never under SEND_FLOOR, which is also the limit when the hold cannot be established."""
    seconds = core_hold()[0] if seconds is None else seconds
    return SEND_FLOOR if seconds is None else max(seconds - SEND_MARGIN, SEND_FLOOR)


def hc_version():
    """Herdr Core's version as a tuple: the running core's own, asked on its socket (never started), since it is the core
    that holds a send and an hc on PATH may be newer than it; with no core up, what hc --version prints. None when
    neither says."""
    try:
        shown = subprocess.run([str(base_.FOLLOWER), '--core-version'], capture_output=True, text=True, timeout=hc_call()).stdout.strip()
        shown = shown or subprocess.run([os.environ.get('HC') or 'hc', '--version'], capture_output=True, text=True, timeout=hc_call()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r'(\d+)\.(\d+)\.(\d+)', shown)
    return tuple(int(n) for n in found.groups()) if found else None


def typing_guard():
    """(why, seconds): why lines must not be typed into a Codex lead's Core terminal on their own ('' when they may),
    and the hold that was resolved for it, which the send that follows is limited by. Only Core's draft hold keeps a
    person's typing apart from a typed line, so it has to be there (0.1.20 on) and long enough for a send to end
    before it runs out."""
    version = hc_version()
    if version is None or version < HOLD_SINCE:
        return ('Herdr Core ' + ('.'.join(map(str, version)) if version else 'of an unknown version') + ' does not hold a message while '
                'a person is typing (0.1.20 on does): hc update, or run the lead on Claude'), None
    need = SEND_FLOOR + SEND_MARGIN + 5
    seconds, where = core_hold()
    if seconds is None:
        return f'{where}: set draft_wait to a number of {need} or more in Herdr Core\'s config.toml, or run the lead on Claude', None
    if seconds < need:
        return (f'draft_wait is {seconds:g} s {where}, too short to keep a draft you leave apart from a typed line: set it to '
                f'{need} or more (60 is the default), or run the lead on Claude'), seconds
    return '', seconds


def typing_unsafe():
    """typing_guard's reason alone: '' when lines may be typed into a Codex lead's Core terminal on their own."""
    return typing_guard()[0]


def hc(*args, wait=0, limit=None, job=None):
    """One Herdr Core command (HC names the binary) and its JSON answer; on failure Core's error kind and exit code.
    wait: seconds the command itself may wait (hc wait --timeout). A call with no answer hc_call(job) seconds after that
    (or after limit seconds, when given) is stopped, kind 'timeout': a hung hc never holds a lock or a lead. Core
    cancels a send whose caller is gone before it typed anything."""
    limit = limit or hc_call(job) + wait
    try:
        result = subprocess.run([os.environ.get('HC') or 'hc', args[0], '--json', *args[1:]], capture_output=True, text=True,
                                timeout=limit)
    except subprocess.TimeoutExpired:
        raise HcError(f'hc {args[0]}: no answer in {limit:g} s, so it was stopped', 'timeout', 124) from None
    except OSError as error:
        raise ValueError('Herdr Core is not installed (' + base_.line(error) + '): install hc 0.1.13 or later, or set HC') from None
    if result.returncode:
        try:
            error = json.loads(result.stderr or '{}').get('error') or {}
        except (ValueError, AttributeError):
            error = {}
        raise HcError('hc ' + args[0] + ': ' + base_.line(error.get('message') or result.stderr or 'exit ' + str(result.returncode)),
                      error.get('kind', ''), result.returncode)
    return json.loads(result.stdout or '{}')


class CoreUnknown(RuntimeError):
    """An hc call failed where its answer decides whether an agent started, so nothing may be taken back."""
    def __init__(self, agent, message):
        super().__init__(message)
        self.agent = agent


def unknown(job, error):
    print(f'UNKNOWN {error.agent}: {base_.line(error)}. Nothing was taken back: once Herdr Core answers, run bash '
          f'{Path(job).absolute() / "reopen.sh"}, which adopts it by its labels or starts it, never a second copy')
    return 1


CONFIG_KEYS = ('FLEET_LEAD_KIND', 'FLEET_LEAD_MODEL', 'FLEET_LEAD_EFFORT', 'FLEET_ASK_CMD', 'FLEET_TRUST_ROOT', 'FLEET_JOBS_ROOT', 'FLEET_WATCH_INTERVAL',
               'FLEET_WATCH_PASSES', 'FLEET_WATCH_NOTIFY', 'HERDR_EVENTS_MACHINE', 'HERDR_EVENTS_HOME', 'HERDR_EVENTS_ROUTES_DIR',
               'HERDR_EVENTS_FLUSH_LOG', 'HERDR_EVENTS_DIR', 'HERDR_EVENTS_STALE_MINUTES', 'HC', 'HC_SESSION', 'HC_SOCKET',
               'STAMPEDE_NO_UPDATE_CHECK', 'STAMPEDE_APP_SPACE', 'STAMPEDE_MAX_HELPERS', 'STAMPEDE_TAB_PANES',
               'STAMPEDE_UPDATE_URL')  # every key in config.example; a test keeps them equal
HERDR_IDS = ('HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_EVENTS_OWNER')


def launch_env(job):
    """The front of every Core launch. A Core terminal gets the core's environment, not the caller's, and hc run has no
    --env: so the caller's PATH and settings, the job's key and the job's own owner, and never the caller's Herdr ids."""
    env = ['/usr/bin/env'] + [part for name in HERDR_IDS for part in ('-u', name)]
    env += ['PATH=' + os.environ.get('PATH', ''), 'STAMPEDE_JOB_KEY=' + job_.core_key(job)]
    env += [name + '=' + os.environ[name] for name in CONFIG_KEYS if os.environ.get(name)]  # an empty one means unset
    owner = job_.job_owner(job)
    return env + (['HERDR_EVENTS_OWNER=' + owner] if owner else [])


def core_status(terminal):
    """A terminal's own OSC 7501 word (idle, working, done, blocked, error), or None when it reports none."""
    return (terminal.get('status') or {}).get('state')


def shelled(terminal):
    """True when a terminal that carries an agent's labels no longer runs the job's launch: a kept terminal lost its
    program and Core put a shell in its place (the Herdr app turns keep on for a terminal it shows), live at the same
    address with the same name and labels. Every launch of stampede's names STAMPEDE_JOB_KEY in its argv, and Core
    shows a terminal's argv as what it runs now, so one without it is that shell, whether keep is still on or was
    turned off since. Core never runs the original command again, so the agent is gone. A record with no argv is not
    judged."""
    argv = terminal.get('argv') or []
    return bool(argv) and not any(str(a).startswith('STAMPEDE_JOB_KEY=') for a in argv)


def start_failed(job, key, relay, reason):
    """A confirmed failed start: kill and remove the follower, mark what is not failed yet as failed, take back the marker
    and owner tag, and leave start-failed (the follower exits on it). The folder stays; a retry is a new job."""
    address = job_.core_entries(job).get(relay, {}).get('address')
    for verb in ('kill', 'rm'):
        try:
            hc(verb, address, job=job) if address else None
        except HcError:
            pass
    for agent, entry in job_.core_entries(job).items():
        if entry.get('state') != 'failed':
            job_.bind(job, agent, {'state': 'failed', 'reason': reason})
    job_.clear_job_marker(key, job)
    if job_.job_owner(job):
        (job_.events_dir() / 'owners' / key).unlink(missing_ok=True)
    (job / 'start-failed').write_text(reason + '\n')
    print(f'FAILED {job_.roster(job)[1]} ({reason}): nothing of {job} runs; the folder stays as a record, and a retry is a new job')
    return 1
