"""The patterns, the scripts folder and the helpers with no dependency."""
import fcntl, re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')
OWNER = re.compile(r'[a-z0-9][a-z0-9_-]{0,40}')  # a bot slug, as herdr-events-owner takes it
SHA = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?')
GATE = re.compile(r'[0-9a-f]{12}')
WS_ID = re.compile(r'w[0-9A-Za-z]+')
KEY = re.compile(r'hc-[0-9a-f]{12}')  # a Herdr Core job's key, where a TUI job has its workspace id


def line(value):
    return ' '.join(str(value).split())


def append(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(text.rstrip('\n') + '\n')
PANE_ID = re.compile(r'[A-Za-z0-9_-]+:[A-Za-z0-9_-]+')  # a Herdr pane id, such as w1:p2


FOLLOWER = SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-event-core'


SESSION = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
MIN_PYTHON = (3, 9)  # the oldest Python the unit suite passes on (CI runs it); fleet_job.py refuses an older one
