"""pstack for coding jobs (the setting dev.pstack): whether the lead's CLI can load pstack on this machine, the sentence
the lead's brief gets when it can, and the one line for the user when it cannot. pstack reaches a machine as a plugin
of the CLI or as plain skill folders; either way it carries the entry skill poteto-mode, so that is what find looks for."""
import json, os, re
from collections import namedtuple
from pathlib import Path

from . import base as base_, job as job_, settings as settings_

RULES = base_.SCRIPTS.parent / 'references' / 'pstack.md'  # what a fleet changes in pstack's playbooks
Found = namedtuple('Found', 'how command')  # how it is installed, in a few words, and what the lead types to load it
PLUGIN = re.compile(r'pstack@[A-Za-z0-9._-]+')  # the plugin pstack of any marketplace: the port's, or upstream's own
VERSION = re.compile(r'[0-9A-Za-z.+_-]{1,32}')
NAMES = {'claude': 'Claude', 'codex': 'Codex'}
INSTALL = {'claude': 'claude plugin marketplace add michael-denyer/pstack-claude && claude plugin install pstack@pstack-claude',
           'codex': 'codex plugin marketplace add michael-denyer/pstack-claude && codex plugin add pstack@pstack-claude'}


def claude_home(env, home):
    return Path(env.get('CLAUDE_CONFIG_DIR') or home / '.claude').expanduser()


def codex_home(env, home):
    return Path(env.get('CODEX_HOME') or home / '.codex').expanduser()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):  # no file, not UTF-8 or not JSON: nothing is known from it
        return None


def claude_plugin(env, home, repo):
    """Claude Code's record of installed plugins: a pstack plugin installed for the user, or for this repo, and not
    switched off in settings.json."""
    root = claude_home(env, home)
    record, switches = read_json(root / 'plugins/installed_plugins.json'), read_json(root / 'settings.json')
    plugins = record.get('plugins') if isinstance(record, dict) else None
    off = switches.get('enabledPlugins') if isinstance(switches, dict) else None
    for name, entries in (plugins.items() if isinstance(plugins, dict) else ()):
        if not PLUGIN.fullmatch(name) or (isinstance(off, dict) and off.get(name) is False):
            continue
        for entry in (entries if isinstance(entries, list) else ()):
            if not isinstance(entry, dict):
                continue
            where = entry.get('projectPath')
            if entry.get('scope') not in ('project', 'local') or (repo and isinstance(where, str) and Path(where).expanduser().resolve() == repo):
                version = entry.get('version')  # the plugin's own word: only a plain version reaches the lead's brief
                plain = isinstance(version, str) and VERSION.fullmatch(version)
                return Found(' '.join(('the Claude Code plugin', name) + ((version,) if plain else ())), '/pstack:poteto-mode')


def codex_plugin(env, home, repo):
    """Codex's config.toml: a [plugins."pstack@<marketplace>"] table that does not say enabled = false."""
    try:
        text = (codex_home(env, home) / 'config.toml').read_text()
    except (OSError, ValueError):
        return None
    for table in re.finditer(r'(?m)^[ \t]*\[plugins\."(pstack@[A-Za-z0-9._-]+)"\][ \t]*(?:#.*)?$', text):
        body = re.split(r'(?m)^[ \t]*\[', text[table.end():], maxsplit=1)[0]
        if not re.search(r'(?m)^[ \t]*enabled[ \t]*=[ \t]*false\b', body):
            return Found('the Codex plugin ' + table.group(1), '$pstack:poteto-mode')


def skills(command, folders):
    """A finder for plain skill folders (npx skills add, or links made by hand): the first that holds poteto-mode."""
    def look(env, home, repo):
        for folder in folders(env, home, repo):
            if (folder / 'poteto-mode' / 'SKILL.md').is_file():
                return Found(f'the skill folder {folder / "poteto-mode"}', command)
    return look


SOURCES = {  # for each CLI that leads a job, where it loads pstack from, the first hit wins
    'claude': (claude_plugin, skills('/poteto-mode', lambda env, home, repo: [claude_home(env, home) / 'skills']
                                     + ([repo / '.claude/skills'] if repo else []))),
    'codex': (codex_plugin, skills('$poteto-mode', lambda env, home, repo: [home / '.agents/skills', codex_home(env, home) / 'skills']
                                   + ([repo / '.agents/skills'] if repo else []))),
}


def lead_env(core):
    """The environment the lead's CLI finds its config folder in. On the Herdr TUI, the caller's. On Herdr Core a terminal
    gets the core's own environment, with none of the caller's CLAUDE_CONFIG_DIR or CODEX_HOME (hcapi.launch_env), and
    stampede cannot read it: so the default folders, which is where the lead looks unless the core itself moved them."""
    return {} if core else os.environ


def find(kind, repo=None, env=None, home=None):
    """How the lead's CLI (kind) has pstack on this machine, for a job in repo, or None."""
    env, home = os.environ if env is None else env, Path(home or Path.home())
    repo = Path(repo).expanduser().resolve() if repo else None
    return next(filter(None, (look(env, home, repo) for look in SOURCES.get(kind, ()))), None)


def brief_text(job, kind=None, end=' '):
    """The sentence the lead's brief gets: only with dev.pstack on and pstack found for the lead's CLI (kind, else the
    job's lead.kind). The lead decides whether its job is coding work; stampede cannot know that from an ask."""
    settings = settings_.current(job)
    found = settings.get('dev.pstack') and find(kind or settings.get('lead.kind'), job_.workdir(job),
                                                 lead_env(job_.backend(job) != 'tui'))
    if not found:
        return ''
    return (f'pstack is installed ({found.how}). If this job is coding work (a feature, a fix, a refactor or a code review), '
            f'load it first with {found.command} and work its way, under the fleet\'s rules in {RULES}, which win over '
            'pstack\'s own. For any other job, leave pstack alone.' + end)


def missing(settings, kind, repo=None, core=False):
    """stampede new's one line when dev.pstack is on and the lead's CLI has no pstack: the job runs without it."""
    if not settings.get('dev.pstack') or find(kind, repo, lead_env(core)):
        return ''
    return (f'note: pstack is not installed for a {NAMES[kind]} lead, so this job runs without it. To use it for coding jobs: '
            f'{INSTALL[kind]}. To stop this line: stampede setup --pstack no')
