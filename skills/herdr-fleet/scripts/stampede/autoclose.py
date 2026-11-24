"""Closing a finished job's own Herdr TUI workspace by itself, when the user's setting finish.auto_close is on.
At finish a detached closer waits until every agent in the workspace is idle, then finish.close_after seconds more, so
whoever started the job can read the lead's last screen. It closes only when nothing is left to lose or to answer:
every pane is one of the job's own agents, none is working or blocked, every git folder they use is clean, no gate
waits on the owner, no other job is open there, and the reopen record was written. Then it clears the owner tag and
closes the workspace. Each step goes to <job>/close.log, and one closed or kept event goes to whoever started the job."""
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, herdrapi as herdrapi_, settings as settings_

SCRIPTS = base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts'
QUIET_EVERY, QUIET_FOR = 10, 3600  # seconds between looks at the agents, seconds the closer waits for them to go idle
BUSY = ('working', 'blocked')


def log(text):
    print(f'{datetime.now():%Y-%m-%d %H:%M:%S} {text}', flush=True)


def workspace(job):
    path = Path(job) / 'workspace'
    found = path.read_text().strip() if path.is_file() else ''
    return found if base_.WS_ID.fullmatch(found) else ''


def enabled(job):
    """The workspace a closer would try for this job, or '' when the setting is off or the job has no Herdr TUI workspace."""
    if job_.backend(job) != 'tui' or settings_.current(job).get('finish.auto_close') is not True:
        return ''
    return workspace(job)


def start(job):
    """At finish: start the detached closer. Its output goes to <job>/close.log."""
    job = Path(job).absolute()
    base_.detach([sys.executable, '-I', base_.SCRIPTS / 'fleet_job.py', '_autoclose', job], job / 'close.log')


def panes(ws):
    """[(pane id, agent name or '', status, folders)] for each pane in the workspace; a ValueError or HerdrError when
    Herdr does not answer."""
    names = {a.get('pane_id'): a.get('name') or '' for a in herdrapi_.herdr('agent', 'list').get('agents', [])
             if a.get('workspace_id') == ws}
    out = []
    for pane in herdrapi_.herdr('pane', 'list', '--workspace', ws).get('panes', []):
        folders = {f for f in (pane.get('cwd'), pane.get('foreground_cwd')) if f}
        out.append((pane.get('pane_id', ''), names.get(pane.get('pane_id'), ''), pane.get('agent_status') or 'unknown', folders))
    return out


def busy(ws):
    return [name or pane for pane, name, status, _ in panes(ws) if status in BUSY]


def dirty(folder):
    """The git work tree holding folder when it has uncommitted or untracked files; '' when clean or not in git."""
    top = subprocess.run(['git', '-C', str(folder), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if top.returncode or not top.stdout.strip():
        return ''
    status = subprocess.run(['git', '-C', top.stdout.strip(), 'status', '--porcelain'], capture_output=True, text=True)
    return top.stdout.strip() if status.returncode or status.stdout.strip() else ''


def reasons(job, ws):
    """Why the workspace must stay open; [] when it may close."""
    job, why = Path(job).absolute(), []
    if not (job / 'finished').is_file():
        why.append('the job has not finished')
    marker = job_.job_marker(ws)
    if marker is not None and marker.is_file():
        why.append(f'another job is open in it ({base_.line(marker.read_text().splitlines()[0] if marker.read_text() else "")})')
    for gate in sorted((job / 'gates').glob('*.json')) if (job / 'gates').is_dir() else []:
        if not gate.with_suffix('.approved').exists():
            why.append(f'gate {gate.stem} waits on the owner')
    try:
        found = panes(ws)
    except (ValueError, herdrapi_.HerdrError) as error:
        return why + [f'Herdr did not list its panes ({base_.line(error)})']
    people = job_.roster(job)[0]
    folders = {job_.workdir(job)}
    for pane, name, status, cwd in found:
        if name not in people:
            why.append(f'pane {pane} is not one of this job\'s agents')
        elif status in BUSY:
            why.append(f'{name} is {status}')
        folders |= {Path(f) for f in cwd}
    for top in sorted({dirty(f) for f in folders if Path(f).is_dir()} - {''}):
        why.append(f'{top} has uncommitted changes')
    return why


def post(job, owner, ws, state, text):
    """One event for whoever started the job; the owner is named in it, since the tag may be cleared by then."""
    event = {'source': 'stampede', 'state': state, 'workspace': ws, 'job': str(Path(job).absolute()), 'summary': text,
             **({'owner': owner} if owner else {})}
    subprocess.run([str(SCRIPTS / 'herdr-event-post'), json.dumps(event)], stdin=subprocess.DEVNULL, capture_output=True)


def tag_owner(ws):
    path = job_.events_dir() / 'owners' / ws
    rows = path.read_text().splitlines() if path.is_file() else []
    return next((row[len('owner='):].strip() for row in rows if row.startswith('owner=')), '')


def keep(job, owner, ws, why):
    log(f'KEPT {ws}: {why}')
    post(job, owner, ws, 'kept', f'workspace {ws} left open: {why}')
    return 1


def run(job):
    """The closer: 0 when the workspace closed, 1 when it was kept (close.log and the event say why)."""
    job = Path(job).absolute()
    ws, owner = workspace(job), ''
    if not ws:
        log('KEPT: the job has no Herdr TUI workspace')
        return 1
    owner = tag_owner(ws)
    wait = settings_.current(job).get('finish.close_after')
    deadline = time.monotonic() + QUIET_FOR
    log(f'waiting for every agent in {ws} to be idle, then {wait} s')
    while True:
        try:
            working = busy(ws)
        except (ValueError, herdrapi_.HerdrError) as error:
            return keep(job, owner, ws, f'Herdr did not list its panes ({base_.line(error)})')
        if not working:
            time.sleep(wait)
            try:
                working = busy(ws)
            except (ValueError, herdrapi_.HerdrError) as error:
                return keep(job, owner, ws, f'Herdr did not list its panes ({base_.line(error)})')
            if not working:
                break
        if time.monotonic() > deadline:
            return keep(job, owner, ws, f'{", ".join(working)} still working after {QUIET_FOR // 60} minutes')
        time.sleep(QUIET_EVERY)
    why = reasons(job, ws)
    if why:
        return keep(job, owner, ws, '; '.join(why))
    snap = subprocess.run([str(SCRIPTS / 'herdr-reopen-snapshot'), ws, str(job)], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)
    if snap.returncode or not (job / 'reopen.sh').is_file():
        return keep(job, owner, ws, 'the reopen record was not written (' + base_.line(snap.stderr or snap.stdout or 'no reopen.sh') + ')')
    log(f'reopen record written: {job / "reopen.sh"}')
    if owner:
        cleared = subprocess.run([str(SCRIPTS / 'herdr-events-owner'), ws, '--clear'], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True)
        if cleared.returncode:
            return keep(job, owner, ws, 'the owner tag was not cleared (' + base_.line(cleared.stderr or cleared.stdout) + ')')
    try:
        herdrapi_.herdr('workspace', 'close', ws)
    except (ValueError, herdrapi_.HerdrError) as error:
        if owner:  # put the tag back, so its events still reach the bot
            subprocess.run([str(SCRIPTS / 'herdr-events-owner'), ws, owner], stdin=subprocess.DEVNULL, capture_output=True)
        return keep(job, owner, ws, f'herdr workspace close failed ({base_.line(error)})')
    log(f'CLOSED {ws}; reopen with {job / "reopen.sh"}')
    post(job, owner, ws, 'closed', f'workspace {ws} closed; reopen with {job / "reopen.sh"}')
    return 0
