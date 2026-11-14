"""stampede doctor: this checkout's own checks (Python, VERSION and the package, the commands on PATH), then
herdr-doctor's lines passed through. Each check is {name, level, text, fix}; level is ok, warn or PROBLEM."""
import importlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

from . import base as base_

ROOT = base_.SCRIPTS.parents[2]  # the checkout: skills/herdr-fleet/scripts -> the repo
HELPERS = base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts'


def shown(text):
    """Text as doctor prints it: the home folder, by either spelling (HOME, and where it resolves to when it is a link),
    as ~, wherever it stands, so a pasted report carries no home path. main runs every line and JSON string through it."""
    text = str(text)
    homes = {os.path.expanduser('~').rstrip('/'), os.path.realpath(os.path.expanduser('~')).rstrip('/')} - {''}
    for home in sorted(homes, key=len, reverse=True):  # the longer first, so one spelling inside the other still goes
        text = re.sub(re.escape(home) + r'(?![^/\s\'"():;,\]])', '~', text)
    return text


def check(name, level, text, fix=''):
    return {'name': name, 'level': level, 'text': text, 'fix': fix}


def python():
    version = '.'.join(map(str, sys.version_info[:3]))
    if sys.version_info[:2] < base_.MIN_PYTHON:  # fleet_job.py stops first; this is for a doctor run some other way
        return [check('python', 'PROBLEM', f'python3 is {version}', 'put Python %d.%d or later first on PATH' % base_.MIN_PYTHON)]
    return [check('python', 'ok', f'python3 {version} ({sys.executable})')]


def checkout():
    try:
        version = (ROOT / 'VERSION').read_text().strip()
    except OSError:
        return [check('checkout', 'PROBLEM', f'no VERSION in {ROOT}', 'run stampede from a whole stampede checkout (git clone it again)')]
    modules = sorted(p.stem for p in Path(__file__).parent.glob('*.py') if p.stem != '__init__')
    for module in modules:  # relay and handed load lazily: import them all here, so a broken file shows now, not mid-job
        try:
            importlib.import_module(__package__ + '.' + module)
        except Exception as error:  # noqa: BLE001: any failure to import is the finding
            return [check('checkout', 'PROBLEM', f'stampede.{module} does not import ({base_.line(error)})',
                          f'git -C {ROOT} status, then restore the file or run stampede update')]
    return [check('checkout', 'ok', f'stampede {version} in {ROOT}, all {len(modules)} modules import')]


def commands():
    """stampede, fleet-job and every herdr-* helper install.sh links into ~/.local/bin, each resolving into this checkout."""
    wanted = {'stampede': ROOT / 'scripts/stampede', 'fleet-job': ROOT / 'scripts/stampede'}
    wanted.update((p.name, p) for p in sorted(HELPERS.iterdir()) if p.is_file() and not p.name.startswith('test-'))
    found = {name: shutil.which(name) for name in wanted}
    missing = [name for name, path in found.items() if not path]
    elsewhere = [f'{name} ({os.path.realpath(path)})' for name, path in found.items()
                 if path and os.path.realpath(path) != os.path.realpath(wanted[name])]
    fix = f'run {ROOT}/install.sh and put ~/.local/bin first on PATH'
    out = ([check('commands', 'PROBLEM', 'not on PATH: ' + ', '.join(missing), fix)] if missing else []) + \
          ([check('commands', 'PROBLEM', 'on PATH from another checkout: ' + ', '.join(elsewhere), fix)] if elsewhere else [])
    return out or [check('commands', 'ok', f'stampede, fleet-job and {len(wanted) - 2} herdr helpers on PATH point into this checkout')]


CHECKS = (python, checkout, commands)  # each returns its lines; a new check is one more function here


def herdr_doctor(core, tui):
    flags = (['--core'] if core else []) + (['--tui'] if tui else [])
    try:
        done = subprocess.run([str(HELPERS / 'herdr-doctor'), *flags], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return [check('herdr-doctor', 'PROBLEM', f'herdr-doctor did not run ({base_.line(error)})', f'bash {HELPERS}/herdr-doctor')]
    out = []
    for row in done.stdout.splitlines():
        level, _, rest = row.partition(' ')
        if level in ('ok', 'warn', 'PROBLEM'):
            text, _, fix = rest.partition(': ') if level != 'ok' else (rest, '', '')
            out.append(check('herdr-doctor', level, text, fix))
    if done.returncode and not any(c['level'] == 'PROBLEM' for c in out) or done.returncode and done.stderr.strip():
        said = base_.line(done.stderr) or 'no PROBLEM line before it'  # a crash after ok lines must not read as healthy
        out.append(check('herdr-doctor', 'PROBLEM', f'herdr-doctor exited {done.returncode} ({said})',
                         f'run herdr-doctor{"".join(" " + f for f in flags)} alone to see the whole of it'))
    return out


def main(core=False, tui=False, as_json=False):
    if core and tui:
        raise ValueError('doctor takes --core or --tui, not both (with neither it checks each backend installed)')
    found = [c for step in CHECKS for c in step()] + herdr_doctor(core, tui)
    checks = [{**c, 'text': shown(c['text']), 'fix': shown(c['fix'])} for c in found]  # the one place output is redacted
    ok = not any(c['level'] == 'PROBLEM' for c in checks)
    if as_json:
        print(json.dumps({'ok': ok, 'checks': checks}, indent=1))
    else:
        for c in checks:
            print(c['level'] + ' ' + c['text'] + (': ' + c['fix'] if c['fix'] else ''))
    return 0 if ok else 1
