"""stampede update: the daily check for a newer release, and the update of a git checkout. Python 3 stdlib only.
  stampede update --check   one line: a newer release (exit 1), or this is the latest (exit 0); nothing when unknown or off
  stampede update           fast-forward a clean checkout on main, then rerun install.sh; never discards local changes"""
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = 24 * 3600
X_Y_Z = re.compile(r'v?(\d+)\.(\d+)\.(\d+)')


def parse(version):
    """'v0.10.0' -> (0, 10, 0), so versions compare as numbers; None when it is not X.Y.Z."""
    m = X_Y_Z.fullmatch(str(version).strip())
    return tuple(map(int, m.groups())) if m else None


def latest():
    """The latest release's tag, cached for 24 h under $XDG_CACHE_HOME/stampede; '' when offline, limited or malformed."""
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'stampede' / 'latest-release'
    try:
        if 0 <= time.time() - cache.stat().st_mtime < DAY:
            return cache.read_text().strip()
    except OSError:
        pass
    tag = ''
    try:
        url = os.environ.get('STAMPEDE_UPDATE_URL') or 'https://api.github.com/repos/vib-z/stampede/releases/latest'
        with urllib.request.urlopen(url, timeout=2) as reply:
            tag = str(json.load(reply)['tag_name'])
    except Exception:
        pass
    try:  # a failure is cached too, so an offline machine waits a day, not 2 s on every command
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
            how = 'stampede update' if (ROOT / '.git').exists() else 'herdr plugin update'
            return 1, f'stampede {tag.lstrip("v")} is out, this is {mine}: run {how}'
        return 0, f'stampede {mine}, the latest release is {tag.lstrip("v")}'
    except Exception:
        return 0, ''


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def update():
    if not (ROOT / '.git').exists():
        print(f'{ROOT} is not a git checkout (a Herdr plugin install): run herdr plugin update')
        return 1
    branch = git('symbolic-ref', '-q', '--short', 'HEAD')
    if branch != 'main':
        print(f'refused: {ROOT} is on {branch or "a detached HEAD"}, not main: git switch main, then rerun', file=sys.stderr)
        return 1
    if git('status', '--porcelain', '--untracked-files=no'):
        print(f'refused: {ROOT} has local changes: commit or stash them, then rerun', file=sys.stderr)
        return 1
    before = (ROOT / 'VERSION').read_text().strip()
    if subprocess.run(['git', '-C', str(ROOT), 'pull', '--ff-only']).returncode:
        print('refused: git pull --ff-only failed (above); your files are as they were', file=sys.stderr)
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
