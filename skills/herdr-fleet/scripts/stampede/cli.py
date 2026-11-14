"""The parser (main) with every command's help, the dispatch (run) and the two commands that start agents on every
backend: new and start."""
import json, os, shlex, subprocess, sys
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, agents as agents_, owner as owner_, hooks as hooks_, tui as tui_, native as native_, \
    doctor as doctor_, check as check_, settings as settings_


def start(job, agent, kind, pane, brief, model=None, effort=None, reports=(), yolo_in=None, cwd=None, tab=None, parent=None,
          outlive=False, program=()):
    """Start one agent and record it: in an existing pane at its shell prompt, then send its brief pointer (TUI); or in a
    Herdr Core terminal with its brief pointer as the first prompt (a Core job). A native job: core_native.start."""
    from . import handed as handed_, relay as relay_
    if job_.backend(job) == 'native':
        return native_.start(job, agent, kind, pane, brief, model, effort, reports, yolo_in, cwd, tab, parent, outlive, program)
    if tab or parent or outlive or program:
        raise ValueError('--tab, --parent, --outlive-parent and a program after -- are for a native job (new --core)')
    owner_.require_approval(job)
    if not base_.NAME.fullmatch(agent):
        raise ValueError('agent names are <role>-<scope>, lowercase')
    lead = agent == job_.roster(job)[1]  # a restarted lead keeps the lead's hooks
    if lead and kind not in agents_.LEAD:
        raise ValueError('the lead runs on claude or codex')
    if lead:  # a restarted lead keeps the lead model and effort of its CLI unless told otherwise
        model, effort = agents_.lead_model(kind, model, effort, job)
    if not lead:
        if not Path(brief).is_file():
            raise ValueError(f'brief {brief} does not exist')
        missing = agents_.missing_sections(Path(brief).read_text(), job)
        if missing:
            raise ValueError(f'brief {brief} is missing: {", ".join(missing)}; '
                             'fill them in on skills/herdr-fleet/references/brief.md and start again')
    if job_.backend(job) == 'core':
        if pane:
            return handed_.start_handed(job, agent, kind, pane, brief, model, effort, reports, yolo_in, cwd, lead)
        if lead and kind == 'codex':
            hcapi_.target(job)
            if hcapi_.typing_unsafe():
                raise ValueError('a Codex lead on Herdr Core gets its inbox typed into its terminal, and ' + hcapi_.typing_unsafe())
        previous = agents_.lead_brief_for(job, agent, kind, brief) if lead else None
        try:
            return relay_.start_core(job, agent, kind, brief, model, effort, reports, yolo_in, cwd, lead)
        except BaseException:
            if previous is not None:  # nothing was recorded for the other CLI: its brief goes back
                Path(brief).write_text(previous)
            raise
    if cwd:
        raise ValueError('--cwd is for a Herdr Core job; on the Herdr TUI the agent starts in its --pane')
    if kind in ('hermes', 'kimi'):
        raise ValueError(f'{kind} runs only as a handed agent of a Herdr Core job (start --pane in a job made with new --core), '
                         'whose follower tells its turns; on a Herdr TUI job start it by hand')
    yolo_in = tui_.pane_yolo(pane, yolo_in, lead)
    previous = agents_.lead_brief_for(job, agent, kind, brief) if lead else None  # only once every check passed
    try:
        args = agents_.cli_args(job, agent, kind, model, effort, list(reports), lead=lead, yolo_in=yolo_in)
        herdrapi_.herdr('pane', 'rename', pane, agent)
        blocked = tui_.launch(agent, kind, pane, args)
    except BaseException:
        if previous is not None:  # the switch never happened: the brief goes back to the CLI agents.tsv and reopen.sh name
            Path(brief).write_text(previous)
        raise
    snapshot = str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot')
    subprocess.run([snapshot, 'record', str(job), agent, kind, str(brief), '--', *args], check=True)
    if blocked:
        print(f'BLOCKED {agent}: clear the startup dialog, then stampede tell {job} {agent} "Read {brief}"')
        return
    pointer = f'You are {agent} in a herdr fleet. Read {brief} and do everything it says.'
    if lead and kind == 'codex':
        return tui_.type_pointer(job, agent, agent, brief, pointer)
    owner_.tell(job, agent, pointer)


def new(ask_file, workspace, name=None, review=False, pane=None, fork=None, core=False, cwd=None, front=False, kind=None, app=False,
        relay=False, space=None, max_helpers=None):
    """Front door: make the job, start its lead with its hooks, print the lead's name.
    kind: the lead's CLI, claude (on claude-opus-5-5) or codex (on gpt-6-astra); with none, FLEET_LEAD_KIND, else claude.
    A fork of a Claude chat takes a Claude lead only.
    The job folder is <jobs root>/jobs/<date>-<owner or local>-<slug>; the repo stays the agents' cwd, recorded in `workdir`.
    pane: an existing empty pane for the lead (a fresh workspace's root pane), whose tab becomes `lead`; else a new tab.
    fork: a Claude session id (the chat that planned the job); the lead starts as a fork of it and keeps that conversation.
    core: the whole job runs on Herdr Core, in cwd (default: the git root here). app: its lead and workers also carry
    the Herdr app's space and tab labels, so the app shows them (STAMPEDE_APP_SPACE=1 is the standing choice).
    front: the chat that runs this, outside Herdr, stays the owner's only contact; the lead posts to <job>/outbox for it.
    relay: a core job of the earlier kind (follower, inbox, hooks); else a core job is native (core_native.new), where
    space and max_helpers apply."""
    from . import relay as relay_
    if (space or max_helpers) and (relay or not core):
        raise ValueError('--space and --max-helpers are for a native job: new --core without --relay')
    flags = {'lead.kind': kind, 'helpers.max': max_helpers}

    def check(kind):
        if kind not in agents_.LEAD:
            raise ValueError(f'the lead runs on claude or codex, not {kind!r} (--lead, or the setting lead.kind)')
        if kind != 'claude' and fork:
            raise ValueError('--fork forks a Claude chat, so it takes a Claude lead: drop --lead codex, or start without --fork')
        if core and kind == 'codex' and hcapi_.typing_unsafe():
            raise ValueError('a Codex lead on Herdr Core gets its inbox typed into its terminal, and ' + hcapi_.typing_unsafe())
        return kind
    if core:
        settings = settings_.for_new(repo_of(cwd), flags)  # every layer first: a repo's .stampede.toml may name the lead
        kind = check(settings.get('lead.kind'))
        if workspace or pane:
            raise ValueError('new --core takes --cwd <repo>, never --pane or --workspace: a Herdr Core job has no Herdr pane')
        if front and relay:
            raise ValueError('--front-door on Herdr Core is for a native job: drop --relay (a --core --relay job has no front door)')
        if not relay:
            return native_.new(ask_file, name, review, fork, cwd, kind, space, max_helpers, front, settings)
        return relay_.new_core(ask_file, name, review, fork, cwd, kind, app or os.environ.get('STAMPEDE_APP_SPACE') == '1', settings)
    if app:
        raise ValueError('--app-space is for new --core: it shows a Herdr Core job in the Herdr app; a Herdr TUI job has its panes')
    if not (workspace or pane):
        raise base_.Retry('new needs --workspace or --pane, or run it inside Herdr' + relay_.core_hint()
                    + '; to run it here on Herdr Core, run the next line',
                    ' '.join(['stampede', 'new', '--core', '--file', shlex.quote(str(ask_file)), '--cwd', git_root()]))
    if fork is not None and not base_.SESSION.fullmatch(fork):
        raise ValueError(f'--fork takes a Claude session id (a UUID, such as $CLAUDE_CODE_SESSION_ID), not {fork!r}')
    ask = Path(ask_file).expanduser().read_text()
    try:  # the first words with Herdr: when it is not there, say so before anything is made, and name Core if it answers
        info = herdrapi_.herdr('pane', 'get', pane)['pane'] if pane else None
        # herdr 0.9.4's `workspace get` has no cwd: the workspace's first pane holds the project folder
        repo = Path(info['cwd'] if info else herdrapi_.herdr('pane', 'list', '--workspace', workspace)['panes'][0]['cwd']).expanduser()
    except herdrapi_.HerdrError as error:
        if error.code != 'server_not_running':
            raise
        raise herdrapi_.HerdrError(base_.line(error) + relay_.core_hint(), error.code) from None
    except ValueError as error:  # no herdr on PATH, or one that gave no answer
        raise ValueError(base_.line(error) + relay_.core_hint()) from None
    settings = settings_.for_new(repo, flags)
    kind = check(settings.get('lead.kind'))
    ws_id = info.get('workspace_id', pane.split(':')[0]) if info else workspace
    owner = job_.starter(ws_id)
    if front and owner:
        raise ValueError(f'--front-door is for a chat outside Herdr, but workspace {ws_id} is owned by the bot {owner}: '
                         'a bot relays its own jobs (drop --front-door, or clear the tag with herdr-events-owner)')
    base = name or job_.slug(ask)
    for n in range(1, 100):  # the same ask in another repo the same day: -2, -3, and the lead's name with it
        name = base if n == 1 else f'{base[:26 - len(str(n))].rstrip("-")}-{n}'  # lead-<name> stays a valid 32-char NAME
        job = job_.jobs_root() / 'jobs' / f'{datetime.now():%Y-%m-%d}-{owner or "local"}-{name}'
        if not job.exists():
            break
    else:
        raise ValueError(f'99 jobs named {base} today: pass --name')
    lead = job_.make_job(repo, job, ask, owner, review, name, front)
    settings_.save(job, settings)
    if info:
        herdrapi_.herdr('tab', 'rename', info['tab_id'], 'lead')
    else:
        pane = herdrapi_.herdr('tab', 'create', '--workspace', workspace, '--cwd', str(repo), '--label', 'lead', '--no-focus')['root_pane']['pane_id']
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    brief.write_text(agents_.lead_brief(job, lead, owner, review, fork, front=front, kind=kind))
    args = agents_.cli_args(job, lead, kind, *agents_.lead_model(kind, job=job), [], lead=True)
    herdrapi_.herdr('pane', 'rename', pane, lead)
    blocked = tui_.launch(lead, kind, pane, (['--resume', fork, '--fork-session'] if fork else []) + args)
    # the reopen record leaves the fork out: a reopen resumes the lead's own session, not the planning chat
    subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), lead,
                    kind, str(brief), '--', *args], check=True)
    job_.mark_job(ws_id, job)
    if blocked:
        return print(f'BLOCKED {lead}: clear the startup dialog, then stampede tell {job} lead "Read {brief}"')
    pointer = f'You are {lead}. Read {brief} and do everything it says.'
    if kind == 'codex' and tui_.type_pointer(job, lead, 'lead', brief, pointer):
        return 1
    if kind == 'claude':
        owner_.tell(job, lead, pointer)
    print(lead + ' ' + str(job))


GROUPS = (  # the top-level help, in the order an agent meets the commands; hook and the _ commands stay out of it
    ('start a job', (('new', 'make a job folder and start its lead'),)),
    ('work in it', (('start', 'start a worker (or a restarted lead) in the job'),
                    ('tell', 'send a message to an agent of the job'),
                    ('ask', 'ask the owner a question, or a gate: one exact action, yes or no'),
                    ('post', "put an item for the owner in the job's outbox"),
                    ('wait', 'a front door: wait for the next outbox item'),
                    ('next', 'a native job: start what waits in the queue'),
                    ('tree', 'a native job: its agents as Herdr Core holds them'))),
    ('gates', (('approve', "record the owner's yes to the plan"),
               ('approve-gate', "a bot: record the owner's yes to one gate"),
               ('gate-ok', 'exit 0 only when a gate has the owner\'s yes at this commit'),
               ('cancel', 'stop a question still waiting on the phone'))),
    ('end and return', (('finish', 'tell the owner where the job ended, in one line'),
                        ('snapshot', 'a native job: save how to reopen it'),
                        ('reopen', 'a native job: start again what is not live'),
                        ('close', "a native job: end an agent's subtree, or the whole job"))),
    ('settings', (('config', 'config show: every setting, and the layer that set it'),)),
    ('the machine', (('doctor', 'check this machine and this checkout, with the fix for each problem'),
                     ('check', "run this checkout's fast tests (--full: all of them)"),
                     ('update', 'update this checkout to the latest release'))),
)
SUMMARY = {name: text for _, commands in GROUPS for name, text in commands}
TOP = ('Run a team of AI agents on one job: a lead plans, workers build in their own panes or terminals, a reviewer\n'
       'checks, and the owner answers questions and gates from a chat or a phone.\n\ncommands:\n'
       + '\n'.join(f'  {group}:\n' + '\n'.join(f'    {name:<13} {text}' for name, text in commands) for group, commands in GROUPS))
TOP_EPILOG = '''start a job:
  stampede new --file ask.md                    inside Herdr: the lead gets a tab of this workspace
  stampede new --core --file ask.md --cwd .     anywhere: the job runs on Herdr Core
Each command takes the job folder new prints. `stampede <command> --help` has its flags and examples;
USING.md in the stampede checkout has the whole flow.'''
EXAMPLES = {
    'new': '''examples:
  stampede new --file ask.md
  stampede new --core --file ask.md --cwd ~/code/app --lead codex
  stampede new --core --file ask.md --cwd ~/code/app --front-door     # a chat outside Herdr runs it''',
    'start': '''examples:
  stampede start <job> build-api --kind claude --brief <job>/briefs/build-api.md --pane w1:p3
  stampede start <job> build-api --kind codex --brief <job>/briefs/build-api.md --model gpt-6-astra
  stampede start <job> lint-web -- npm run lint     # a native job: any program''',
    'tell': '''examples:
  stampede tell <job> lead "the owner says: ship it"
  stampede tell <job> build-api "Read <job>/briefs/build-api.md again: the Done when changed"''',
    'ask': '''examples:
  stampede ask <job> "Which database?" --option Postgres --option SQLite
  sha=$(gh pr view 12 --json headRefOid -q .headRefOid)     # the PR's head: the commit the owner says yes to
  stampede ask <job> --gate "merge PR 12" --sha "$sha" --pr 12''',
    'post': '''examples:
  stampede post <job> "PLAN READY" --file <job>/plan.md
  stampede post <job> "the login page, before and after" --file before.png --file after.png''',
    'wait': '''example:
  stampede wait <job> --timeout 600     # run it in the background; it returns with each new item''',
    'next': 'example:\n  stampede next <job>',
    'tree': 'examples:\n  stampede tree <job>\n  stampede tree <job> --json',
    'approve': 'example:\n  stampede approve <job> --by owner',
    'approve-gate': '''example (run the approve line the gate event carries, as given):
  stampede approve-gate <job> 0123456789ab --sha <40 hex> --by owner --digest <digest>''',
    'gate-ok': '''example (one commit for the check and the act, so a later push cannot slip in):
  sha=$(gh pr view 12 --json headRefOid -q .headRefOid)
  stampede gate-ok <job> 0123456789ab --sha "$sha" && gh pr merge 12 --squash --match-head-commit "$sha"''',
    'cancel': 'example:\n  stampede cancel <job> 0123456789ab',
    'finish': 'example:\n  stampede finish <job> "PR 12 merged; the report is <job>/reports/lead.md"',
    'snapshot': 'example:\n  stampede snapshot <job>',
    'reopen': 'examples:\n  stampede reopen <job>\n  stampede reopen <job> --fresh',
    'close': 'examples:\n  stampede close <job> build-api\n  stampede close <job>     # the whole job',
    'doctor': 'examples:\n  stampede doctor\n  stampede doctor --core --json',
    'check': 'examples:\n  stampede check\n  stampede check --full',
    'config': '''examples:
  stampede config show
  stampede config show --json
  stampede config show --job <job>''',
}
JOB = 'the job folder (new prints it)'
def repo_of(cwd=None):
    """The folder whose .stampede.toml applies: cwd, else the git root of the current folder; None outside a repo."""
    if cwd:
        return Path(cwd).expanduser().resolve()
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    return Path(top.stdout.strip()) if top.returncode == 0 else None


def main(argv):
    import argparse
    form = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(prog='stampede', usage='stampede <command> [<args>]', description=TOP, epilog=TOP_EPILOG,
                                     formatter_class=form)
    sub = parser.add_subparsers(dest='cmd', metavar='<command>', help=argparse.SUPPRESS)
    sub.required = True

    def command(name, description=None):
        return sub.add_parser(name, description=description or SUMMARY[name][0].upper() + SUMMARY[name][1:] + '.',
                              epilog=EXAMPLES.get(name), formatter_class=form)

    p = command('new', 'Make a job folder and start its lead. Inside Herdr the lead gets a tab of this workspace (or --pane);\n'
                       'anywhere else, --core runs the whole job on Herdr Core. Prints the lead\'s name and the job folder.')
    p.add_argument('--file', required=True, help='the ask: a file with what the job is for')
    p.add_argument('--workspace', help='the Herdr workspace for the lead\'s tab (default: $HERDR_WORKSPACE_ID; Herdr TUI only)')
    p.add_argument('--core', action='store_true', help='run the job on Herdr Core (hc) in --cwd: every agent is a Core terminal and '
                   'nothing is handed to a Herdr TUI pane (that is --core --relay)')
    p.add_argument('--cwd', help='with --core: the repo the agents work in (default: the git root of the current folder)')
    p.add_argument('--name', help='the job\'s short name (default: made from the ask); the lead is lead-<name>')
    p.add_argument('--review', action='store_true', help='the owner sees the plan first: no worker starts before stampede approve')
    p.add_argument('--pane', help="an existing empty pane for the lead (a fresh workspace's root pane); its tab becomes lead")
    p.add_argument('--fork', metavar='SESSION_ID', help='start the lead as a fork of this Claude session (the chat that planned the job)')
    p.add_argument('--front-door', action='store_true', help='a chat outside Herdr stays the owner\'s only contact: the lead posts to <job>/outbox '
                   'and the chat reads it with stampede wait (with --core: a native job only, not --relay)')
    p.add_argument('--lead', choices=sorted(agents_.LEAD), help='the lead\'s CLI: claude (claude-opus-5-5) or codex (gpt-6-astra); default '
                   '$FLEET_LEAD_KIND, else claude. --fork takes claude only')
    p.add_argument('--app-space', action='store_true', help='with --core --relay: label the lead and workers for the Herdr app '
                   '(herdr.space, herdr.tab), so it shows the job in a space; a native job always carries them')
    p.add_argument('--relay', action='store_true', help='with --core: the earlier Core job (a follower, inbox files, hooks), which hands '
                   'cursor, hermes or kimi to Herdr TUI panes with start --pane')
    p.add_argument('--space', help='with --core: the space\'s name (default: the job\'s name)')
    p.add_argument('--max-helpers', type=int, help='with --core: helpers running at once (default: the setting helpers.max, 12)')
    p.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='a setting for this job, above every '
                   'other layer, such as helpers.max=6 (repeatable; saved in <job>/settings.json; stampede config show lists them)')
    p = start_parser = command('start', 'Start a worker in the job, or restart its lead: its brief pointer is its first message.\n'
                                        'Kinds: on a Herdr TUI job claude, codex or cursor; on a --core --relay job claude or codex in a\n'
                                        'Core terminal, and cursor, hermes or kimi handed to a Herdr TUI --pane; on a native job\n'
                                        '(new --core) claude or codex, and any other CLI or program after --.')
    p.add_argument('job', help=JOB)
    p.add_argument('agent', help='its name, <role>-<scope> in lowercase, such as build-api')
    p.add_argument('--kind', help='its CLI: claude, codex, cursor, hermes or kimi (see above for where each runs)')
    p.add_argument('--pane', help='the Herdr TUI pane (required on the TUI; in a --core --relay job, the pane a cursor, hermes or kimi '
                   'agent is handed to)')
    p.add_argument('--brief', help='its brief file (a worker\'s needs the sections of skills/herdr-fleet/references/brief.md)')
    p.add_argument('--tab', help='a native job: the workstream tab (default main)')
    p.add_argument('--parent', help='a native job: the agent it runs under (default: the caller, else the lead)')
    p.add_argument('--outlive-parent', action='store_true', help='a native job: keep it running when its parent ends')
    p.add_argument('--cwd', help='a Herdr Core job: the folder the agent starts in (default: the repo)')
    p.add_argument('--model', help='its model (default: the CLI\'s own; a restarted lead keeps the lead\'s)')
    p.add_argument('--effort', help='its reasoning effort, where the CLI takes one')
    p.add_argument('--report', action='append', default=[], help='a report it must write before it may stop, such as reports/build-api.md in the job folder (repeatable: any one will do)')
    p.add_argument('--yolo-in', metavar='WORKTREE', help='a worker in its own git worktree: no-checks mode, never the lead')
    p.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='a setting for this start only, such as '
                   'lead.codex.effort=high (repeatable)')
    p = command('tell', 'Send a message to an agent of the job (lead names the lead). A Claude agent or the lead of a Herdr TUI\n'
                        'or --relay job reads it from its inbox file; every other agent gets it typed into its pane or terminal.')
    p.add_argument('job', help=JOB); p.add_argument('agent', help='the agent\'s name, or lead')
    p.add_argument('text', nargs='+', help='the message')
    p = command('ask', 'Ask the owner a question and return at once: the answer comes to the lead\'s inbox (a native job:\n'
                       'its terminal). With --gate, ask for a yes or no to one exact action at one commit.')
    p.add_argument('job', help=JOB)
    p.add_argument('--option', action='append', default=[], help='one answer to choose from (repeatable; not with --gate)')
    p.add_argument('question', nargs='+', help='the question, or with --gate the action')
    p.add_argument('--gate', action='store_true', help='a gate: one exact action at one commit, yes or no')
    p.add_argument('--sha', help='with --gate: the full commit id it is about'); p.add_argument('--pr', type=int, help='with --gate: the PR number')
    p = command('post', 'Put an item for the owner in <job>/outbox/<n>.md, with its files copied beside it. A job a bot\n'
                        'started also sends that bot the item; a front door reads it with stampede wait.')
    p.add_argument('job', help=JOB); p.add_argument('text', nargs='+', help='the item\'s text')
    p.add_argument('--file', action='append', default=[], help='a file to send with it (repeatable)')
    p = command('wait', 'A front door\'s wait: return with every outbox item not shown yet, or when the lead sits at a\n'
                        'question card (a native job: BLOCKED when Core says it waits at a dialog), or LEAD_GONE.\n'
                        'Exit 0 with output, 3 when nothing came in --timeout seconds.')
    p.add_argument('job', help=JOB)
    p.add_argument('--timeout', type=int, help='seconds (default: the setting timeouts.wait, 3600); exit 3 when nothing came')
    for verb in ('next', 'snapshot'):
        command(verb).add_argument('job', help=JOB)
    p = command('tree'); p.add_argument('job', help=JOB); p.add_argument('--json', action='store_true', help='one JSON document')
    p = command('reopen', 'A native job: start what is not live, parents first. A finished job reopens for reading only.')
    p.add_argument('job', help=JOB)
    p.add_argument('--fresh', action='store_true', help='every Claude agent starts a new session with its brief')
    p.add_argument('--prompt', action='store_true', help='each resumed helper is told its parent\'s new address')
    p.add_argument('--rerun-programs', action='store_true', help='run programs that did not exit 0 again')
    p = command('close'); p.add_argument('job', help=JOB)
    p.add_argument('agent', nargs='?', help='the agent whose subtree ends (default: the whole job)')
    p = command('approve', 'Record the owner\'s yes to the plan as it stands (plan.md), then wake the lead. Run it after the\n'
                           'owner said yes, and again after any change to the plan.')
    p.add_argument('job', help=JOB); p.add_argument('--by', required=True, help='who said yes')
    p = command('approve-gate', 'A bot, outside Herdr: record the owner\'s yes, said in its chat, to one gate at one commit.')
    p.add_argument('job', help=JOB); p.add_argument('gate', help='the gate\'s id (12 hex)')
    p.add_argument('--sha', required=True, help='the full commit id the yes is for'); p.add_argument('--by', required=True, help='who said yes')
    p.add_argument('--digest', help='the gate as it was asked, from the approve command the bot was handed')
    p = command('gate-ok', 'The lead\'s check before it acts: exit 0 only when the owner\'s yes to this gate is recorded at\n'
                           'this very commit.')
    p.add_argument('job', help=JOB); p.add_argument('gate', help='the gate\'s id (12 hex)')
    p.add_argument('--sha', required=True, help='the full commit id about to be acted on')
    p = command('cancel'); p.add_argument('job', help=JOB); p.add_argument('ident', help='the question\'s id (ASKED prints it)')
    p = command('finish', 'Tell the owner where the job ended, in one line: one done event, sent once. Questions still\n'
                          'waiting on the phone are cancelled.')
    p.add_argument('job', help=JOB); p.add_argument('summary', nargs='+', help='one line on where the job ended')
    p = command('doctor', 'Check this machine and this checkout: one line per check, ok, warn or PROBLEM with its fix.\n'
                          'Exit 1 when any line is a PROBLEM.')
    p.add_argument('--core', action='store_true', help='check Herdr Core only (passed to herdr-doctor)')
    p.add_argument('--tui', action='store_true', help='check the Herdr TUI only (passed to herdr-doctor)')
    p.add_argument('--json', action='store_true', help='{"ok": bool, "checks": [{"name", "level", "text", "fix"}]}')
    p = command('check', 'Run the fast part of this checkout\'s unit tests (under 15 seconds) in a scratch HOME, with no herdr or hc\n'
                         'on PATH, so nothing reaches a live job. One line per test module, then the total. Exit 0 or 1.')
    p.add_argument('--full', action='store_true', help='run the whole suite (minutes)')
    p.add_argument('--json', action='store_true', help='{"ok": bool, "tests": n, "seconds": s, "modules": [...]}')
    p = command('config', 'The settings: config show prints every setting as key = value (source), the source being the layer\n'
                          'that set it (default, user, repo, env:<NAME>, flag or set), then the environment-only variables,\n'
                          'then any problems. Exit 1 when the config has problems.')
    p = p.add_subparsers(dest='action', metavar='show')
    p.required = True
    p = p.add_parser('show', description='Every setting and the layer that set it; exit 1 when the config has problems.',
                     epilog=EXAMPLES['config'], formatter_class=form)
    p.add_argument('--json', action='store_true', help='{"values", "sources", "files", "environment", "problems"}')
    p.add_argument('--job', help='a job folder: the settings it saved at new (else the repo is the git root here)')
    p = sub.add_parser('hook'); p.add_argument('action'); p.add_argument('job'); p.add_argument('--agent', required=True)
    p.add_argument('payload', nargs='?', help="Codex's notify JSON, passed as the last argument; other hooks read stdin")
    p = sub.add_parser('_reopen'); p.add_argument('job')
    p.add_argument('--lead', action='store_true', help='only the follower and the lead')
    p.add_argument('--prompt', action='store_true', help='a restarted Codex worker gets its brief pointer again')
    p.add_argument('--fresh', action='store_true', help='each agent it starts begins a new session with its brief')
    sub.add_parser('_deliver').add_argument('job')
    sub.add_parser('_wake').add_argument('job')
    p = sub.add_parser('_ask'); p.add_argument('job'); p.add_argument('--command'); p.add_argument('--option', action='append', default=[])
    p.add_argument('--gate')
    p.add_argument('--ident', help='this question\'s id: names its waiter, so cancel signals only that process')
    p.add_argument('question', nargs='+')
    if not argv:
        parser.print_help(sys.stderr)
        return 2
    if argv[0] == 'update':  # scripts/stampede runs it first; this is the same command under fleet-job's own entry
        return subprocess.run([sys.executable, '-I', str(base_.SCRIPTS.parents[2] / 'scripts/stampede_update.py'), *argv[1:]]).returncode
    if not argv[0].startswith('-') and argv[0] not in sub.choices:  # argparse would list hook and the _ commands too
        parser.error(f'{argv[0]!r} is no stampede command: stampede --help lists them')
    program = []
    if argv[:1] == ['start'] and '--' in argv:  # a native job: a program after --; cut here, since argparse before 3.13
        cut = argv.index('--')                    # loses it when a flag stands between the name and the --
        argv, program = argv[:cut], argv[cut + 1:]
    a = parser.parse_args(argv)
    a.program = program
    try:
        if a.cmd == 'new':
            ask = Path(a.file).expanduser()
            if not ask.is_file():
                raise ValueError(f'the ask file {a.file} does not exist: write what the job is for in it, then run new again')
        elif a.cmd != 'hook' and getattr(a, 'job', None) is not None:
            require_job(a.job)
    except ValueError as error:
        print('stampede ' + a.cmd + ': ' + base_.line(error), file=sys.stderr)
        return 2
    if a.cmd == 'new' and a.cwd and not a.core:
        parser.error('--cwd is for new --core')
    if a.cmd == 'start' and job_.backend(a.job) != 'native':
        missing = [flag for flag, value in (('--kind', a.kind), ('--brief', a.brief), ('--pane', a.pane or job_.backend(a.job) == 'core'))
                   if not value]
        if missing:
            start_parser.error('the following arguments are required: ' + ', '.join(missing))
    try:
        return run(a)
    except (ValueError, PermissionError) as error:
        if a.cmd == 'hook':  # a hook's exit 2 blocks or wakes Claude; keep a hook's error a plain failure
            raise
        print('stampede ' + a.cmd + ': ' + base_.line(error), file=sys.stderr)
        if isinstance(error, base_.Retry):
            print(error.command, file=sys.stderr)
        return 2
    except (hcapi_.HcError, herdrapi_.HerdrError, OSError) as error:  # Herdr, Herdr Core or a program failed: one line, never a traceback
        print('stampede ' + a.cmd + ': ' + base_.line(error), file=sys.stderr)
        return 1


def git_root():
    done = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    return shlex.quote(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else '<repo>'  # printed in a command


def require_job(job):
    """Every command but new and hook: the job folder exists and is one (new writes lead and ask.md; either will do, so a
    job that lost one can still be finished or reopened), before anything reads its backend."""
    path = Path(job).expanduser()
    if not path.is_dir():
        raise ValueError(f'job folder not found: {job}')
    if not ((path / 'lead').is_file() or (path / 'ask.md').is_file()):
        raise ValueError(f'not a job folder, it has no lead or ask.md file: {job}')


NATIVE_ONLY = ('next', 'tree', 'snapshot', 'reopen', 'close')


def run(a):
    from . import relay as relay_
    if a.cmd == 'doctor':
        return doctor_.main(a.core, a.tui, a.json)
    if a.cmd == 'check':
        return check_.main(a.full, a.json)
    for pair in getattr(a, 'set', None) or []:
        settings_.parse_set(pair)  # a bad pair is refused before anything runs
    settings_.SETS[:] = getattr(a, 'set', None) or []
    if a.cmd == 'config':
        found = settings_.current(a.job) if a.job else settings_.load(repo=repo_of())
        print(settings_.show(found, a.json).rstrip('\n'))
        return 1 if found.problems else 0
    if a.cmd == 'new':
        if a.core:
            return new(a.file, a.workspace, a.name, a.review, a.pane, a.fork, core=True, cwd=a.cwd, front=a.front_door, kind=a.lead,
                       app=a.app_space, relay=a.relay, space=a.space, max_helpers=a.max_helpers)
        if a.relay:
            raise ValueError('--relay is for new --core')
        return new(a.file, a.workspace or os.environ.get('HERDR_WORKSPACE_ID'), a.name, a.review, a.pane, a.fork, front=a.front_door,
                   kind=a.lead, app=a.app_space, space=a.space, max_helpers=a.max_helpers)
    job = getattr(a, 'job', None)
    if a.cmd in NATIVE_ONLY and job_.backend(job) != 'native':
        raise ValueError(f'{a.cmd} is for a native job (new --core); {job} is a {job_.backend(job)} job')
    if a.cmd in ('hook', '_deliver', '_wake') and job_.backend(job) == 'native':
        return 0  # no hooks, no inbox and no deliverer on a native job: Core carries every message
    if a.cmd == '_reopen' and job_.backend(job) == 'native':
        raise ValueError('_reopen is for a relay job; a native job reopens with stampede reopen')
    if a.cmd == 'next':
        return native_.next_(job)
    if a.cmd == 'tree':
        return native_.tree(job, a.json)
    if a.cmd == 'snapshot':
        return native_.snapshot(job)
    if a.cmd == 'reopen':
        return native_.reopen(job, a.fresh, a.prompt, a.rerun_programs)
    if a.cmd == 'close':
        return native_.close(job, a.agent)
    if a.cmd == 'post':
        return owner_.post(a.job, ' '.join(a.text), a.file)
    if a.cmd == 'wait':
        return owner_.wait(a.job, a.timeout)
    if a.cmd == 'start':
        return start(a.job, a.agent, a.kind, a.pane, a.brief, a.model, a.effort, a.report, a.yolo_in, a.cwd, a.tab, a.parent,
                     a.outlive_parent, a.program)
    if a.cmd == 'tell':
        return owner_.tell(a.job, a.agent, ' '.join(a.text)) or 0
    if a.cmd == 'ask' and a.gate:
        if a.option or not a.sha:
            raise ValueError('a gate takes --sha and no --option: one exact action, yes or no; ask each choice as its own gate')
        return owner_.ask_gate(a.job, ' '.join(a.question), a.sha, a.pr)
    if a.cmd == 'ask':
        return owner_.ask(a.job, ' '.join(a.question), a.option) and 0
    if a.cmd == 'approve-gate':
        return owner_.approve_gate(a.job, a.gate, a.sha, a.by, a.digest)
    if a.cmd == 'gate-ok':
        return owner_.gate_ok(a.job, a.gate, a.sha)
    if a.cmd == 'cancel':
        return owner_.cancel(a.job, a.ident)
    if a.cmd == 'approve':
        return owner_.approve(a.job, a.by)
    if a.cmd == 'finish':
        return owner_.finish(a.job, ' '.join(a.summary))
    if a.cmd == '_reopen':
        return relay_.reopen(a.job, a.lead, a.prompt, a.fresh)
    if a.cmd == '_deliver':
        return tui_.deliver(a.job)
    if a.cmd == '_wake':
        return tui_.deliver_soon(a.job) if job_.lead_kind(a.job) == 'codex' else 0
    if a.cmd == '_ask':
        return owner_.ask_now(a.job, ' '.join(a.question), a.option, a.command, a.gate)
    raw = a.payload if a.payload is not None else sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    lead = a.agent == job_.roster(a.job)[1]
    if a.action == 'watch-paths':
        event = 'CwdChanged' if payload.get('hook_event_name') == 'CwdChanged' else 'SessionStart'
        print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'watchPaths': hooks_.watch_paths(a.job, a.agent, lead)}}))
        return 0
    if a.action == 'wake':
        lines = hooks_.wake(a.job, a.agent, payload)
        if lines:
            print('\n'.join(lines), file=sys.stderr)
            return 2
        return 0
    out = {'ask-lead': lambda: hooks_.ask_lead(a.job, a.agent, payload), 'claude-stop': lambda: hooks_.claude_stop(a.job, a.agent, payload),
           'codex-notify': lambda: hooks_.codex_notify(a.job, a.agent, payload) or '', 'cursor-stop': lambda: hooks_.cursor_stop(a.job, a.agent, payload),
           'send-file': lambda: hooks_.send_file(a.job, a.agent, payload),
           'session-end': lambda: hooks_.session_end(a.job, a.agent, payload)}[a.action]()
    if out:
        print(out)
    return 0
