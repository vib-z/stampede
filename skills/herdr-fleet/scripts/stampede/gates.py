"""The gates the code holds: each job's gate settings (an owner-side record made at new), the opt-out log, stampede merge
(only a reviewed commit, only past the merge gate) and the pre-push hook (no push to the default branch without the gate).
This guards against a forgetful agent, not a hostile one: an agent runs as the same user, and git push --no-verify
skips any hook."""
import contextlib, io, json, os, re, shlex, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

from . import base as base_, job as job_, owner as owner_, settings as settings_

HOOK_MARK = '# stampede-hook'
HOOK = f'''#!/bin/sh
{HOOK_MARK}: a job's agent may not push to the default branch without the owner's gate (stampede prepush).
command -v stampede >/dev/null 2>&1 || exit 0
exec stampede prepush "$@"
'''
HOOK_LINE = 'command -v stampede >/dev/null 2>&1 && { stampede prepush "$@" || exit 1; }'
METHODS = ('squash', 'merge', 'rebase')


class GhError(OSError):
    """gh failed: cli prints its one line and exits 1."""


def names():
    return [key[len('gates.'):] for key in settings_.DEFAULTS if key.startswith('gates.')]


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def record_path(job):
    """Outside the job folder and the repo, which the job's agents write: <HERDR_EVENTS_DIR>/gates/<the job's key>.json."""
    return job_.events_dir() / 'gates' / (job_.job_key(job) + '.json')


def of(job):
    """name -> (on, source) for this job, from its record; every gate on for a job without one (made before gates)."""
    try:
        found = json.loads(record_path(job).read_text())
    except (OSError, ValueError):
        found = {}
    if not isinstance(found, dict) or found.get('job') != str(Path(job).absolute()):
        found = {}
    gates, sources = found.get('gates') or {}, found.get('sources') or {}
    return {name: (gates.get(name) is not False, str(sources.get(name, 'default'))) for name in names()}


def off(job):
    return [name for name, (on, _) in of(job).items() if not on]


def begin(job, settings, repo):
    """At new, on every backend: the job's record, one OFF line per gate switched off, and the pre-push hook."""
    job = Path(job).absolute()
    gates = {name: settings.get('gates.' + name) for name in names()}
    sources = {name: settings.source('gates.' + name) for name in names()}
    path = record_path(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'job': str(job), 'gates': gates, 'sources': sources}) + '\n')
    for name in names():
        if not gates[name]:
            base_.append(job / 'gates.log', f'{stamp()} OFF {name} ({sources[name]})')
    if gates['push_default_branch']:
        install_hook(repo)


def install_hook(repo):
    """git's own hooks folder of the repo, only when it has no pre-push and core.hooksPath is unset; else one line."""
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    found = git('rev-parse', '--path-format=absolute', '--git-common-dir')
    if found.returncode or not found.stdout.strip():
        return  # not a git repo: nothing to push
    hook = Path(found.stdout.strip()) / 'hooks' / 'pre-push'
    custom = git('config', '--get', 'core.hooksPath').stdout.strip()
    if not custom and hook.is_file() and HOOK_MARK in hook.read_text(errors='replace'):
        return  # an earlier job's
    if custom or hook.exists():
        where = f'core.hooksPath is {custom}' if custom else f'{hook} already exists'
        return print(f'stampede new: the pre-push hook was not installed ({where}); to hold the push gate, add this line '
                     f'to that pre-push hook: {HOOK_LINE}', file=sys.stderr)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK)
    hook.chmod(0o755)


def brief_text(job, cmd):
    """The lead's brief, on every backend: merge only with stampede merge, then which gates the owner switched off."""
    text = (f'Merge only with {cmd} merge {job} <pr> --sha <the reviewed commit> --review <the review report> --gate <gate>, never '
            'with gh pr merge: it checks that the report passes that commit and the PR head is still it. A merge and a push '
            'to the default branch need the recorded yes (gate-ok), never a typed one. ')
    gone = off(job)
    if gone:
        text += (f'The owner switched these gates off for this job: {", ".join(gone)}; those need no yes. Every other gate '
                 'still needs the owner\'s recorded yes. ')
    return text


def overlay(settings, job):
    """config show --job: the gates as the job's record holds them, with the layer that set each at new."""
    if not record_path(job).is_file():
        return settings
    values, sources = dict(settings.values), dict(settings.sources)
    for name, (on, source) in of(job).items():
        values['gates.' + name], sources['gates.' + name] = on, source + ', at new'
    return settings_.Settings(values, sources, settings.problems, settings.files, settings.environment, settings.exported)


def gh(job, *args):
    """Every gh call, in the job's repo (tests put a fake gh on PATH)."""
    done = subprocess.run(['gh', *args], cwd=str(job_.workdir(job)), capture_output=True, text=True)
    if done.returncode:
        raise GhError(f'gh {" ".join(args[:2])} failed: ' + base_.line(done.stderr or done.stdout or f'exit {done.returncode}'))
    return done.stdout


def review_says(report, sha):
    """Refuse unless the report's first 10 lines carry Status: PASS and Reviewed: <sha>."""
    path = Path(report).expanduser()
    if not path.is_file():
        raise PermissionError(f'no review report {report}: the reviewer writes one with Status: PASS and Reviewed: <full sha> '
                              'in its first 10 lines')
    head = path.read_text(errors='replace').splitlines()[:10]
    found = {}
    for row in head:
        m = re.match(r'\s*(Status|Reviewed):\s*(\S+)', row)
        if m:
            found.setdefault(m.group(1), m.group(2))
    if found.get('Status') != 'PASS':
        raise PermissionError(f'the review report {report} says Status: {found.get("Status", "(none)")}, not PASS, in its first '
                              '10 lines: fix the findings and review again')
    if 'Reviewed' not in found:
        raise PermissionError(f'the review report {report} names no Reviewed: <full sha> in its first 10 lines: the reviewer '
                              'adds the commit it reviewed')
    if found['Reviewed'] != sha:
        raise PermissionError(f'the review report passes {found["Reviewed"]}, not {sha}: merge the reviewed commit, or review {sha}')


def merge(job, pr, sha, review, gate=None):
    """stampede merge: whatever the settings, a passing review of sha and an open PR whose head is sha; with the merge gate
    on, the owner's recorded yes at sha. Then it merges with --match-head-commit sha. Returns the facts."""
    job = Path(job).absolute()
    if not base_.SHA.fullmatch(sha or ''):
        raise ValueError('--sha takes the full commit id that was reviewed (40 hex)')
    review_says(review, sha)
    pull = json.loads(gh(job, 'pr', 'view', str(pr), '--json', 'headRefOid,isDraft,state'))
    if pull.get('state') != 'OPEN':
        raise PermissionError(f'PR {pr} is {str(pull.get("state")).lower()}, not open: there is nothing to merge')
    if pull.get('headRefOid') != sha:
        raise PermissionError(f'the review report passes {sha} but the PR head is {pull.get("headRefOid")}: review the new commit')
    on, source = of(job)['merge']
    if on:
        ask = f'stampede ask {job} --gate --sha {sha} --pr {pr} ' + shlex.quote(f'merge PR {pr} at {sha}')
        if not gate:
            raise PermissionError(f'the merge gate is on: ask the owner with {ask}, then run this again with --gate <id>')
        if owner_.load_gate(job, gate).get('pr') != pr:
            raise PermissionError(f'gate {gate} is not about PR {pr}: ask with {ask}')
        with contextlib.redirect_stdout(io.StringIO()):
            owner_.gate_ok(job, gate, sha)
    else:
        base_.append(job / 'gates.log', f'{stamp()} MERGE {pr} {sha} without the merge gate (off: {source})')
    method = settings_.current(job).get('merge.method')
    if method not in METHODS:
        raise ValueError(f'the setting merge.method is {method!r}: it takes {", ".join(METHODS)}')
    if pull.get('isDraft'):
        gh(job, 'pr', 'ready', str(pr))
    gh(job, 'pr', 'merge', str(pr), '--' + method, '--match-head-commit', sha)
    commit = gh(job, 'pr', 'view', str(pr), '--json', 'mergeCommit', '-q', '.mergeCommit.oid').strip() or 'unknown'
    facts = {'pr': pr, 'sha': sha, 'merge_commit': commit, 'method': method, 'review': str(review), 'gate': gate if on else None}
    base_.append(job / 'merges.log', f'{stamp()} MERGED {pr} {sha} {commit} {method} review {review} gate {gate if on else "off"}')
    print(f'MERGED {pr} {commit}')
    return facts


def default_branches(remote):
    found = subprocess.run(['git', 'symbolic-ref', '--quiet', f'refs/remotes/{remote}/HEAD'], capture_output=True, text=True)
    head = found.stdout.strip()
    return [head.rpartition('/')[2]] if found.returncode == 0 and head else ['main', 'master']


def approved(job, sha):
    """True when the job holds a gate approved at sha."""
    for path in sorted((Path(job) / 'gates').glob('*.json')):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                owner_.gate_ok(job, path.stem, sha)
            return True
        except (ValueError, PermissionError, OSError):
            continue
    return False


def prepush(remote, lines, env=None):
    """The pre-push hook: 0 unless a job's agent (STAMPEDE_JOB_KEY on Core, HERDR_WORKSPACE_ID in a Herdr pane, naming an
    open job's marker) pushes to the remote's default branch with the gate on and no approved gate for the commit."""
    env = os.environ if env is None else env
    marker = None
    for name in ('STAMPEDE_JOB_KEY', 'HERDR_WORKSPACE_ID'):
        marker = marker or (job_.job_marker(env.get(name)) if env.get(name) else None)
    if marker is None or not marker.is_file():
        return 0
    job = Path((marker.read_text().splitlines() or [''])[0].strip())
    if not job.is_absolute() or not job.is_dir():
        return 0
    branches = default_branches(remote)
    on, source = of(job)['push_default_branch']
    logged = False
    for row in lines:
        cells = row.split()
        if len(cells) != 4 or not cells[2].startswith('refs/heads/') or cells[2][len('refs/heads/'):] not in branches:
            continue
        sha, branch = cells[1], cells[2][len('refs/heads/'):]
        if not on:
            if not logged:
                base_.append(job / 'gates.log', f'{stamp()} PUSH {sha} to {branch} without the push gate (off: {source})')
                logged = True
            continue
        if approved(job, sha):
            continue
        print(f'stampede prepush: a push of {sha} to {branch} needs the owner\'s yes. Ask with: stampede ask {job} --gate --sha '
              f'{sha} ' + shlex.quote(f'push {sha} to {branch}') + ', then push again once stampede gate-ok prints APPROVED',
              file=sys.stderr)
        return 1
    return 0
