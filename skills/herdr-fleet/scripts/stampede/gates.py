"""The gates the code holds: each job's gate settings (an owner-side record made at new), the opt-out log, stampede merge
(only a reviewed commit, only past the merge gate) and the pre-push hook (no push to the default branch without the gate).
This guards against a forgetful agent, not a hostile one: an agent runs as the same user, and git push --no-verify
skips any hook."""
import contextlib, io, json, os, re, shlex, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

from . import base as base_, job as job_, owner as owner_, settings as settings_, out as out_

REFUSED = 9  # stampede prepush's refusal: the one exit code that stops a push; anything else lets it through
HOOK_MARK = '# stampede-hook'
HOOK = f'''#!/bin/sh
{HOOK_MARK}: a job's agent may not push to the default branch without the owner's gate. stampede prepush
# decides whether the push is a job's; only its refusal ({REFUSED}) stops a push. No set -e: every status is tested in an if.
if [ -z "${{STAMPEDE_JOB_KEY:-}}" ] && [ -z "${{HERDR_WORKSPACE_ID:-}}" ]; then exit 0; fi
if ! command -v stampede >/dev/null 2>&1; then
  echo "stampede-hook: stampede is not on PATH, so the push gate was not checked: put it on PATH (./install.sh)" >&2
  exit 0
fi
if stampede prepush "$@"; then exit 0; else code=$?; fi
if [ "$code" = {REFUSED} ]; then exit 1; fi
echo "stampede-hook: stampede prepush failed (exit $code), so the push gate was not checked: run stampede update" >&2
exit 0
'''
METHODS = settings_.CHOICES['merge.method']


class GhError(OSError):
    """gh failed: cli prints its one line and exits 1."""


def names():
    return [key[len('gates.'):] for key in settings_.DEFAULTS if key.startswith('gates.')]


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def record_path(job):
    """Outside the job folder and the repo, which the job's agents write: <HERDR_EVENTS_DIR>/gates/<the job's key>.json."""
    return job_.events_dir() / 'gates' / (job_.job_key(job) + '.json')


def recorded(job):
    """The job's record as new wrote it, or {} (none, or one naming another folder)."""
    try:
        found = json.loads(record_path(job).read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) and found.get('job') == str(Path(job).absolute()) else {}


def of(job):
    """name -> (on, source) for this job, from its record; every gate on for a job without one (made before gates)."""
    found = recorded(job)
    if not found:
        return {name: (True, 'no record: all on') for name in names()}
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
    branches = default_branch(repo) if gates['push_default_branch'] else {}
    path.write_text(json.dumps({'job': str(job), 'gates': gates, 'sources': sources, 'default_branch': branches}) + '\n')
    for name in names():
        if not gates[name]:
            base_.append(job / 'gates.log', f'{stamp()} OFF {name} ({sources[name]})')
    if gates['push_default_branch']:
        install_hook(repo)


def default_branch(repo):
    """At new, once: {remote name and its URL: the default branch}, from the remote's HEAD symref, else git ls-remote
    --symref (5 s at most); a remote that answers neither is left out."""
    def git(*args, timeout=None):
        try:
            return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        except (OSError, subprocess.TimeoutExpired):
            return None
    found = {}
    listed = git('remote')
    for remote in (listed.stdout.split() if listed and listed.returncode == 0 else []):
        head, prefix = git('symbolic-ref', '--quiet', f'refs/remotes/{remote}/HEAD'), f'refs/remotes/{remote}/'
        branch = head.stdout.strip()[len(prefix):] if head and head.returncode == 0 and head.stdout.startswith(prefix) else ''
        if not branch:
            remote_head = git('ls-remote', '--symref', remote, 'HEAD', timeout=5)
            line = remote_head.stdout.splitlines()[0] if remote_head and remote_head.returncode == 0 and remote_head.stdout else ''
            m = re.match(r'ref: refs/heads/(\S+)\s+HEAD$', line)
            branch = m.group(1) if m else ''
        if branch:
            found[remote] = branch
            url = git('remote', 'get-url', remote)
            if url and url.returncode == 0 and url.stdout.strip():
                found[url.stdout.strip()] = branch
    return found


def install_hook(repo):
    """git's own hooks folder of the repo, only when it has no pre-push and core.hooksPath is unset; else one line."""
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    found = git('rev-parse', '--path-format=absolute', '--git-common-dir')
    if found.returncode or not found.stdout.strip():
        return  # not a git repo: nothing to push
    hook = Path(found.stdout.strip()) / 'hooks' / 'pre-push'
    custom = git('config', '--get', 'core.hooksPath')
    if custom.returncode == 0:  # set, even to the empty string
        return skipped(f'core.hooksPath is set ({custom.stdout.strip() or "empty"})')
    hook.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(hook, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)  # never through a symlink, never over another
    except FileExistsError:
        if hook.is_symlink() or not hook.is_file() or HOOK_MARK not in hook.read_text(errors='replace'):
            skipped(f'{hook} already exists')
        return  # else an earlier job's
    with os.fdopen(fd, 'w') as out:
        out.write(HOOK)
    hook.chmod(0o755)
    print(f'hook pre-push installed in {hook}: a job\'s agent cannot push to the default branch without the gate', file=sys.stderr)


def skipped(why):
    print(f'stampede new: the push gate is not enforced by a hook in this repo, because it has its own ({why}); '
          'stampede merge still holds the merge gate', file=sys.stderr)


def brief_text(job, cmd):
    """The lead's brief, on every backend: merge only with stampede merge, then which gates the owner switched off."""
    text = (f'Merge only with {cmd} merge {job} <pr> --sha <the reviewed commit> --review <the review report> --gate <gate>, never '
            'with gh pr merge: it checks that the report passes that commit and the PR head is still it. A merge and a push '
            'to the default branch open only with a gate asked with --kind merge or --kind push_default_branch and its '
            'recorded yes, never a typed one or your own card. Every review report, after every new commit (a rebase too), '
            'must carry Status: PASS or FINDINGS and Reviewed: <the full sha it reviewed> in its first 10 lines: put that in '
            'each review brief. ')
    gone = off(job)
    if gone:
        text += (f'The owner switched these gates off for this job: {", ".join(gone)}; those need no yes. Every other gate '
                 'still needs the owner\'s recorded yes. ')
    return text


def overlay(settings, job):
    """config show --job: the gates as the job's record holds them (with the layer that set each at new); a job with
    no record has every gate on, whatever the user's config says now."""
    values, sources = dict(settings.values), dict(settings.sources)
    for name, (on, source) in of(job).items():
        values['gates.' + name], sources['gates.' + name] = on, source if source.startswith('no record') else source + ', at new'
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
    lines = path.read_text(errors='replace').splitlines()[:10]
    found = {}
    for row in lines:
        m = re.match(r'(Status|Reviewed):[ \t]*(.*?)\s*$', row)  # a header starts the line
        if m:
            found.setdefault(m.group(1), []).append(m.group(2))
    last = max([n for n, row in enumerate(lines) if re.match(r'(Status|Reviewed):', row)] or [-1])
    for n, row in enumerate(lines[:last + 1]):  # the header comes before any code block, quote, comment or markup
        if re.match(r' *(```|~~~|<|>)', row) or row.startswith(('    ', '\t')):
            raise PermissionError(f'line {n + 1} of the review report {report} ({base_.line(row)[:40]}) comes before or inside '
                                  'its header: a title line, then Status: and Reviewed:, before any code block, quote or comment')
    for key, values in found.items():
        if len(values) > 1:
            raise PermissionError(f'the review report {report} has {len(values)} {key}: lines in its first 10 lines '
                                  f'({", ".join(values)}): it must have one; the reviewer fixes the header')
    found = {key: values[0] for key, values in found.items()}
    if found.get('Status') != 'PASS':
        raise PermissionError(f'the review report {report} says Status: {found.get("Status", "(none)")}, not PASS, in its first '
                              '10 lines: fix the findings and review again')
    if 'Reviewed' not in found:
        raise PermissionError(f'the review report {report} names no Reviewed: <full sha> in its first 10 lines: the reviewer '
                              'adds the commit it reviewed')
    if not base_.SHA.fullmatch(found['Reviewed']):
        raise PermissionError(f'the review report {report} says Reviewed: {found["Reviewed"]}: it takes one full sha and nothing '
                              'else')
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
    method = settings_.current(job).get('merge.method')
    if method not in METHODS:
        raise ValueError(f'the setting merge.method is {method!r}: it takes {", ".join(METHODS)}')
    if on:
        ask = ask_line(job, 'merge', sha, f'merge PR {pr}', pr)  # the gate adds the commit itself
        if not gate:
            raise base_.Retry('the merge gate is on: ask the owner with the next line, then run this again with --gate <id>', ask)
        asked = owner_.load_gate(job, gate)
        if asked.get('kind') != 'merge' or asked.get('pr') != pr:
            raise base_.Retry(f'gate {gate} is not a merge gate for PR {pr} (it is {asked.get("kind") or "of no kind"}, '
                              + (f'PR {asked["pr"]}' if asked.get('pr') else 'no PR') + '): ask one with the next line', ask)
        with contextlib.redirect_stdout(io.StringIO()):
            owner_.gate_ok(job, gate, sha)
    else:
        base_.append(job / 'gates.log', f'{stamp()} MERGE {pr} {sha} without the merge gate (off: {source})')
    how = f'{method} review {review} gate {gate if on else "off"}'
    try:  # the intent is on record before anything changes on GitHub, or nothing is merged
        base_.append(job / 'merges.log', f'{stamp()} MERGING {pr} {sha} {how}')
    except OSError as error:
        raise PermissionError(f'{job / "merges.log"} cannot be written ({base_.line(error)}): nothing was merged; fix it, '
                              'then merge again') from None
    try:
        if pull.get('isDraft'):
            gh(job, 'pr', 'ready', str(pr))
        gh(job, 'pr', 'merge', str(pr), '--' + method, '--match-head-commit', sha)
    except GhError as error:
        with contextlib.suppress(OSError):
            base_.append(job / 'merges.log', f'{stamp()} FAILED {pr} {sha} {how}: {base_.line(error)}')
        raise
    try:
        commit = gh(job, 'pr', 'view', str(pr), '--json', 'mergeCommit', '-q', '.mergeCommit.oid').strip()
    except GhError:
        commit = ''
    with contextlib.suppress(OSError):
        base_.append(job / 'merges.log', f'{stamp()} MERGED {pr} {sha} {commit or "(merge commit not read)"} {how}')
    out_.emit('MERGED', f'MERGED {pr} {commit}'.rstrip(),
              pr=pr, sha=sha, merge_commit=commit or None, method=method, gate=gate if on else None)
    return {'pr': pr, 'sha': sha, 'merge_commit': commit or None, 'method': method, 'review': str(review),
            'gate': gate if on else None}


def ask_line(job, kind, sha, action, pr=None):
    """The stampede ask a refusal hands back, as one runnable line."""
    return shlex.join(['stampede', 'ask', str(job), '--gate', '--kind', kind, '--sha', sha, *(['--pr', str(pr)] if pr else []),
                       action])


def default_branches(job, remote, url=None):
    """The job's record from new, else refs/remotes/<remote>/HEAD (the whole name after the prefix), else main and master."""
    saved = recorded(job).get('default_branch') or {}
    for name in (remote, url):
        if name and isinstance(saved.get(name), str):
            return [saved[name]]
    found = subprocess.run(['git', 'symbolic-ref', '--quiet', f'refs/remotes/{remote}/HEAD'], capture_output=True, text=True)
    head, prefix = found.stdout.strip(), f'refs/remotes/{remote}/'
    return [head[len(prefix):]] if found.returncode == 0 and head.startswith(prefix) and head != prefix else ['main', 'master']


def approved(job, sha, kind):
    """True when the job holds a gate of this kind approved at sha."""
    for path in sorted((Path(job) / 'gates').glob('*.json')):
        try:
            if owner_.load_gate(job, path.stem).get('kind') != kind:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                owner_.gate_ok(job, path.stem, sha)
            return True
        except (ValueError, PermissionError, OSError):
            continue
    return False


def job_of(env):
    """The open job a push comes from: the first of STAMPEDE_JOB_KEY and HERDR_WORKSPACE_ID naming a valid marker."""
    for name in ('STAMPEDE_JOB_KEY', 'HERDR_WORKSPACE_ID'):
        marker = job_.job_marker(env.get(name)) if env.get(name) else None
        try:
            job = Path((marker.read_text().splitlines() or [''])[0].strip()) if marker and marker.is_file() else None
        except OSError:
            job = None
        if job and job.is_absolute() and job.is_dir():
            return job
    return None


def prepush(remote, lines, env=None, url=None):
    """The pre-push hook: 0 unless a job's agent (STAMPEDE_JOB_KEY on Core, HERDR_WORKSPACE_ID in a Herdr pane, naming an
    open job's marker) pushes to the remote's default branch with the gate on and no approved gate for the commit."""
    job = job_of(os.environ if env is None else env)
    if job is None:
        return 0
    branches = default_branches(job, remote, url)
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
        if approved(job, sha, 'push_default_branch'):
            continue
        print(f'stampede prepush: a push of {sha} to {branch} needs the owner\'s yes. Ask it with the next line, then push '
              'again once stampede gate-ok prints APPROVED:\n' + ask_line(job, 'push_default_branch', sha, f'push {sha} to {branch}'),
              file=sys.stderr)
        return REFUSED
    return 0
