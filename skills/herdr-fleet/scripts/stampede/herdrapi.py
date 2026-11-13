"""The herdr call to the Herdr TUI server."""
import json, os, subprocess

from . import base as base_

CORE_TERMINAL = ('HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE')  # set by Herdr Core in each of its terminals
AGENT_HOSTS = ('herdr', 'herdr-core', 'hc')  # the Herdr server, and Herdr Core's core, holder and CLI


def inside_herdr(env=None, pid=None):
    """True for a command run in a Herdr pane or a Herdr Core terminal, or anywhere under the Herdr server or a Core
    process (hc exec included): an agent's own command.
    ponytail: same Unix user, so a determined agent could still write the record or reach this over ssh; the boundary
    is auto mode plus this refusal. Upgrade: an approval signed on the bot's own computer."""
    env = os.environ if env is None else env
    if env.get('HERDR_ENV') or env.get('HERDR_PANE_ID') or any(env.get(name) for name in CORE_TERMINAL):
        return True
    try:
        ps = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True)
    except OSError:
        return True  # no ps: cannot tell, so refuse
    if ps.returncode:
        return True  # cannot tell: refuse
    tree = {}
    for row in ps.stdout.splitlines():
        cells = row.split(None, 2)
        if len(cells) == 3 and cells[0].isdigit() and cells[1].isdigit():
            tree[int(cells[0])] = (int(cells[1]), os.path.basename(cells[2].strip()))
    pid, seen = os.getpid() if pid is None else pid, set()
    while pid > 1:
        if pid not in tree or pid in seen:
            return True  # a command or an ancestor the table does not show, or a loop: cannot tell, so refuse
        seen.add(pid)
        if tree[pid][1] in AGENT_HOSTS:
            return True
        pid = tree[pid][0]
    return False


class HerdrError(RuntimeError):
    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


def herdr(*args, timeout=None):
    """One Herdr command's result; HerdrError when it answers an error. A Herdr that is missing, answers no JSON, or does
    not answer within timeout seconds is a ValueError: nothing can be told from it."""
    try:
        result = subprocess.run([os.environ.get('HERDR', 'herdr'), *args], capture_output=True, text=True, timeout=timeout)
        data = json.loads(result.stdout or result.stderr or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise ValueError('herdr ' + ' '.join(args[:2]) + ' did not answer (' + base_.line(error) + ')') from None
    if not isinstance(data, dict):
        raise ValueError('herdr ' + ' '.join(args[:2]) + ' answered no JSON object')
    if result.returncode or data.get('error'):
        error = data.get('error')
        raise HerdrError('herdr ' + ' '.join(args[:2]) + ': ' + base_.line(error or result.stderr),
                         error.get('code', '') if isinstance(error, dict) else '')
    return data.get('result', {})


def herdr_shown(pane):
    """The agent Herdr shows in a pane (herdr agent get), or a ValueError when it shows none clearly."""
    try:
        shown = herdr('agent', 'get', pane).get('agent')
    except HerdrError as error:
        raise ValueError(base_.line(error)) from None
    if not isinstance(shown, dict) or shown.get('pane_id') != pane or not isinstance(shown.get('name'), str):
        raise ValueError(f'herdr agent get {pane} showed no well-formed agent')
    return shown


def herdr_agents():
    """pane id -> agent, from one herdr agent list answered in full: a list of agents, each with its pane id. Any other
    answer is a ValueError: only a whole, well-formed list is evidence that an agent is absent."""
    try:
        listed = herdr('agent', 'list')
    except HerdrError as error:
        raise ValueError(base_.line(error)) from None
    rows = listed.get('agents') if isinstance(listed, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get('pane_id'), str) and row['pane_id']
                                             for row in rows):
        raise ValueError('herdr agent list gave no well-formed list of agents')
    return {row['pane_id']: row for row in rows}
