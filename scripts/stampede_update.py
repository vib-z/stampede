"""stampede update: the daily check for a newer release, and the update of a git checkout. Python 3 stdlib only.
  stampede update --check   one line: a newer release (exit 1), or this is the latest (exit 0); nothing when unknown or off
  stampede update           fast-forward a clean checkout on main, then rerun install.sh; never overwrites a local file.
                            A Herdr plugin install names herdr plugin update instead"""
import json, os, re, subprocess, sys, threading, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = 24 * 3600
DEADLINE = 3  # seconds for the whole fetch: DNS, connect and the reply
X_Y_Z = re.compile(r'v?(\d+)\.(\d+)\.(\d+)')


def parse(version):
    """'v0.10.0' -> (0, 10, 0), so versions compare as numbers; None when it is not X.Y.Z."""
    m = X_Y_Z.fullmatch(str(version).strip())
    return tuple(map(int, m.groups())) if m else None


def fetch(url, got):
    """Append the reply's tag_name to got. Runs in a thread, so a slow server cannot outlast DEADLINE."""
    try:
        with urllib.request.urlopen(url, timeout=2) as reply:
            got.append(str(json.loads(reply.read(65536))['tag_name']))  # a release reply is a few KB
    except Exception:
        pass


def latest():
    """The latest release's tag, cached for 24 h under $XDG_CACHE_HOME/stampede; '' when offline, limited or malformed."""
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'stampede' / 'latest-release'
    try:
        if 0 <= time.time() - cache.stat().st_mtime < DAY:
            return cache.read_text().strip()
    except OSError:
        pass
    got = []
    url = os.environ.get('STAMPEDE_UPDATE_URL') or 'https://api.github.com/repos/vib-z/stampede/releases/latest'
    worker = threading.Thread(target=fetch, args=(url, got), daemon=True)
    worker.start()
    worker.join(DEADLINE)  # past it the daemon thread is abandoned and the check counts as failed
    tag = got[0] if got else ''
    try:  # a failure is cached too, so an offline machine waits a day, not 3 s on every command
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(tag + '\n')
    except OSError:
        pass
    return tag


def check():
    """(1, the warning) when a newer release is out, (0, an ok line) when not, (0, '') when off or unknown."""
    try:
        if os.environ.get('STAMPEDE_NO_UPDATE_CHECK', '0') not in ('', '0'):
            return 0, ''
        mine, tag = (ROOT / 'VERSION').read_text().strip(), latest()
        if not (parse(mine) and parse(tag)):
            return 0, ''
        if parse(tag) > parse(mine):
            how = 'herdr plugin update stampede --yes' if plugin_install() else 'stampede update'
            return 1, f'stampede {tag.lstrip("v")} is out, this is {mine}: run {how}'
        return 0, f'stampede {mine}, the latest release is {tag.lstrip("v")}'
    except Exception:
        return 0, ''


def plugin_install():
    """Herdr's managed checkout keeps .git on a detached HEAD, so its folder says it, not .git; a copy without .git too."""
    return 'github-installations' in ROOT.parts or not (ROOT / '.git').exists()


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def in_the_way(path):
    """Something already on disk where an incoming file goes, or a file where it needs a folder. After a clean
    git status that can only be an ignored file, and a fast-forward would overwrite it."""
    rel = Path(path)
    return os.path.lexists(ROOT / rel) or any(
        os.path.lexists(ROOT / d) and not (ROOT / d).is_dir() for d in list(rel.parents)[:-1])


def update():
    if plugin_install():
        print(f'{ROOT} is a Herdr plugin install: run herdr plugin update stampede --yes')
        return 1
    branch = git('symbolic-ref', '-q', '--short', 'HEAD')
    if branch != 'main':
        print(f'refused: {ROOT} is on {branch or "a detached HEAD"}, not main: git switch main, then rerun', file=sys.stderr)
        return 1
    if git('status', '--porcelain'):
        print(f'refused: {ROOT} has local changes or untracked files: commit, stash or move them, then rerun', file=sys.stderr)
        return 1
    if subprocess.run(['git', '-C', str(ROOT), 'fetch']).returncode:
        print('refused: git fetch failed (above); your files are as they were', file=sys.stderr)
        return 1
    added = subprocess.run(['git', '-C', str(ROOT), 'diff', '-z', '--name-only', '--no-renames', '--diff-filter=A',
                            'HEAD', '@{u}'], capture_output=True).stdout  # raw bytes: a path may start or end with a space
    clash = [p for p in map(os.fsdecode, added.split(b'\0')) if p and in_the_way(p)]
    if clash:
        print(f'refused: the update adds {", ".join(clash)}, already in {ROOT} (ignored by git, so it would be '
              'overwritten): move it away, then rerun', file=sys.stderr)
        return 1
    before = (ROOT / 'VERSION').read_text().strip()
    if subprocess.run(['git', '-C', str(ROOT), 'merge', '--ff-only', '@{u}']).returncode:
        print('refused: git merge --ff-only failed (above); your files are as they were', file=sys.stderr)
        return 1
    if subprocess.run(['bash', str(ROOT / 'install.sh')]).returncode:
        return 1
    after = (ROOT / 'VERSION').read_text().strip()
    print('stampede ' + (after if after == before else f'{before} -> {after}'))
    return 0


def main(argv):
    if argv == ['--check']:
        code, text = check()
        if text:
            print(text)
        return code
    if argv:
        print('usage: stampede update [--check]', file=sys.stderr)
        return 2
    return update()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
