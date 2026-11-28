"""stampede setup: ask the default preferences for new jobs and save them in the user's own settings file. Each question
has a flag, so it runs with no prompt too. Only an answer that differs from what the settings already say is written,
so the file holds what the user changed and every other key keeps following its default; a question skipped (Enter,
--defaults, or no terminal) keeps what it was. A settings file that exists is changed only after the change was shown
and a yes came: typed at the prompt, or --yes on the command line."""
import difflib, json, os, sys
from collections import namedtuple

from . import agents as agents_, out as out_, pstack as pstack_, settings as settings_

HEADER = ('# stampede settings, written by `stampede setup`. Edit this file by hand, or run setup again.\n'
          '# Every key with its default: config.example in the stampede checkout. What applies now: stampede config show\n')
YES = {'yes': True, 'y': True, 'no': False, 'n': False}
EFFORTS = ', '.join(settings_.EFFORTS[:-1]) + ' or ' + settings_.EFFORTS[-1]


def one_of(answer, allowed):
    if answer not in allowed:
        raise ValueError(f'it takes {", ".join(allowed[:-1])} or {allowed[-1]}, not {answer!r}')
    return answer


def yes_no(answer):
    if answer.lower() not in YES:
        raise ValueError(f'it takes yes or no, not {answer!r}')
    return YES[answer.lower()]


def lead_model(answer, values, rules):
    if not answer.isprintable() or ' ' in answer:
        raise ValueError(f'a model is one word, such as {values["lead." + values["lead.kind"] + ".model"]}, not {answer!r}')
    return answer


def worker_effort(answer, values, rules):
    cap = rules.get('workers.max_effort')
    if cap and settings_.EFFORTS.index(one_of(answer, settings_.EFFORTS)) > settings_.EFFORTS.index(cap):
        raise ValueError(f'workers may not run at {answer} effort (workers.max_effort: {cap})')
    return one_of(answer, settings_.EFFORTS)


def roles(values):
    """Every role with an effort of its own: the built-in ones, and the user's."""
    return sorted(key.split('.')[1] for key in values if settings_.ROLE.fullmatch(key) and key.endswith('.effort'))


def shared(values):
    """The effort every role has, or 'mixed' when they differ."""
    efforts = {values[f'roles.{role}.effort'] for role in roles(values)}
    return efforts.pop() if len(efforts) == 1 else 'mixed'


# One row per question, in the order asked. name: its flag (--name) and its key in --json. ask: the prompt.
# shown: the answer in [brackets], from the values so far. keys: an answer as {setting: value}; it raises ValueError
# with the reason for an answer it does not take. takes: the answers, for --help.
Question = namedtuple('Question', 'name ask shown keys takes')
QUESTIONS = (
    Question('pstack', 'Use pstack for coding jobs? It is a set of working rules for a coding agent. yes or no',
             lambda v: 'yes' if v['dev.pstack'] else 'no', lambda a, v, r: {'dev.pstack': yes_no(a)}, 'yes or no'),
    Question('lead', 'Which agent leads a job? claude or codex',
             lambda v: v['lead.kind'], lambda a, v, r: {'lead.kind': one_of(a, settings_.CHOICES['lead.kind'])}, 'claude or codex'),
    Question('lead-model', "The lead's model",
             lambda v: v[f'lead.{v["lead.kind"]}.model'], lambda a, v, r: {f'lead.{v["lead.kind"]}.model': lead_model(a, v, r)},
             'a model of the lead\'s CLI, such as claude-opus-5-5'),
    Question('lead-effort', f"The lead's effort: {EFFORTS}",
             lambda v: v[f'lead.{v["lead.kind"]}.effort'],
             lambda a, v, r: {f'lead.{v["lead.kind"]}.effort': one_of(a, settings_.EFFORTS)}, EFFORTS),
    Question('worker-effort', "Every worker's effort", shared,
             lambda a, v, r: {f'roles.{role}.effort': worker_effort(a, v, r) for role in roles(v)}, EFFORTS),
    Question('backend', 'Where do jobs run? tui (the Herdr TUI), core (Herdr Core) or auto (the TUI inside Herdr, else Core)',
             lambda v: v['backend'], lambda a, v, r: {'backend': one_of(a, ('tui', 'core', 'auto'))}, 'tui, core or auto'),
    Question('review', 'When is the work reviewed? end (one pass at the end), each (every pull request or step) or none',
             lambda v: v['review.step'], lambda a, v, r: {'review.step': one_of(a, settings_.CHOICES['review.step'])}, 'end, each or none'),
)


def answers(given, ask, say):
    """{setting: value} for every answer that differs from what the user's file and the defaults say now. An answer comes
    from a flag (given: {question name: text}), else is typed when ask is there (ask(prompt) returns the line, '' for
    Enter, None at the end of input). A typed answer that is not taken is said and asked again; a flag's is a refusal.
    The lead's model must pass lead.forbid and lead.allow, kept or new."""
    rules = settings_.load()  # what stampede new enforces: your file and the environment
    mine = settings_.load(env={'XDG_CONFIG_HOME': os.environ.get('XDG_CONFIG_HOME', '')})  # your file over the defaults
    for problem in mine.problems:
        print('note: ' + problem, file=sys.stderr)
    values, changes = dict(mine.values), {}
    for number, q in enumerate(QUESTIONS, 1):
        while True:
            typed = q.name not in given and ask is not None
            raw = ask(f'{number} of {len(QUESTIONS)}  {q.ask} [{q.shown(values)}]: ') if typed else given.get(q.name)
            try:
                new = q.keys(raw.strip(), values, rules) if raw and raw.strip() else {}
                if q.name == 'lead-model':
                    agents_.check_lead_model(rules, {**values, **new}[f'lead.{values["lead.kind"]}.model'], suggest=False)
                break
            except ValueError as error:
                if not typed or raw is None:  # a flag, or a kept answer with no one left to ask
                    raise ValueError(f'--{q.name}: {error}' if q.name in given else f'{error}: name another with --{q.name}') from None
                say(f'        {error}')
        changes.update({key: value for key, value in new.items() if values[key] != value})
        values.update(new)
    return changes


def summary():
    """What new jobs use now, each with the layer that set it (the environment included), then pstack on this machine."""
    now = settings_.load()
    kind, effort = now.get('lead.kind'), shared(now.values)
    lines = ['What new jobs use now:']
    for key in ('dev.pstack', 'lead.kind', f'lead.{kind}.model', f'lead.{kind}.effort', 'backend', 'review.step'):
        lines.append(f'  {key} = {json.dumps(now.get(key))}  ({now.source(key)})')
    lines.append(f'  every worker\'s effort = {json.dumps(effort)}' if effort != 'mixed' else
                 '  the workers\' efforts differ by role: stampede config show')
    if now.get('dev.pstack'):
        found = pstack_.find(kind)
        lines.append(f'pstack: {found.how}' if found else
                     f'pstack is not installed for a {pstack_.NAMES[kind]} lead yet. Install it with: {pstack_.INSTALL[kind]}')
    return lines


def main(a, stdin=None):
    """Exit 0: saved, nothing to change, or the user said no. A refusal (a bad answer, a file that cannot be changed
    safely, or a change to an existing file with no yes) is a ValueError: cli prints it and exits 2."""
    stdin = sys.stdin if stdin is None else stdin
    prompts = not (a.defaults or a.json) and stdin.isatty()

    def say(text):
        print(text, flush=True)  # before a refusal on stderr, so the change shown stands above it

    def ask(prompt):
        print(prompt, end='', flush=True)
        line = stdin.readline()
        if not line:  # the end of input: keep what is there, and never save unasked
            print()
        return line.rstrip('\n') if line else None
    given = {q.name: getattr(a, q.name.replace('-', '_')) for q in QUESTIONS if getattr(a, q.name.replace('-', '_')) is not None}
    if prompts:
        say('stampede setup: your default preferences for new jobs.\n'
            'Press Enter to keep the answer in [brackets]. Nothing is saved before the end.\n')
    changes = answers(given, ask if prompts else None, say)
    path, old, new = settings_.edit_user(changes)
    exists = path.exists()
    if not exists:
        new = HEADER.encode() + (b'\n' if new else b'') + new
    facts = {'path': str(path), 'changed': changes}
    if new == old:
        out_.emit('UNCHANGED', f'UNCHANGED {path}: your answers are what it already says', **facts)
    else:
        if exists:
            say('\n'.join(difflib.unified_diff(old.decode().splitlines(), new.decode().splitlines(), 'now', 'with your answers', lineterm='')))
        else:
            say(f'New file {path}:\n' + ''.join('  ' + line + '\n' for line in new.decode().splitlines()).rstrip('\n'))
        if exists and not a.yes:
            if not prompts:
                raise ValueError(f'{path} would change as shown: run it again with --yes to save that; nothing was changed')
            reply = ask('Save this change? yes or no [yes]: ')
            if reply is None or reply.strip().lower() not in ('', 'yes', 'y'):
                out_.emit('NOT SAVED', f'NOT SAVED {path}: nothing was changed', **facts)
                return 0
        settings_.write_user(path, old, new)
        out_.emit('SAVED', f'SAVED {path}', **facts)
    say('\n'.join(summary()))
    return 0
