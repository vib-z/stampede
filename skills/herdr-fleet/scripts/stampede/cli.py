"""The parser (main), the dispatch (run) and the two commands that start agents on every backend: new and start."""
import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path

from . import base as base_, job as job_, hcapi as hcapi_, herdrapi as herdrapi_, agents as agents_, owner as owner_, hooks as hooks_, tui as tui_, native as native_


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
        model, effort = agents_.lead_model(kind, model, effort)
    if not lead:
        if not Path(brief).is_file():
            raise ValueError(f'brief {brief} does not exist')
        missing = agents_.missing_sections(Path(brief).read_text())
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
        print(f'BLOCKED {agent}: clear the startup dialog, then fleet-job tell {job} {agent} "Read {brief}"')
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
    kind = kind or os.environ.get('FLEET_LEAD_KIND') or 'claude'
    if kind not in agents_.LEAD:
        raise ValueError(f'the lead runs on claude or codex, not {kind!r} (--lead, or FLEET_LEAD_KIND)')
    if kind != 'claude' and fork:
        raise ValueError('--fork forks a Claude chat, so it takes a Claude lead: drop --lead codex, or start without --fork')
    if core and kind == 'codex' and hcapi_.typing_unsafe():
        raise ValueError('a Codex lead on Herdr Core gets its inbox typed into its terminal, and ' + hcapi_.typing_unsafe())
    if core:
        if workspace or pane:
            raise ValueError('new --core takes --cwd <repo>, never --pane or --workspace: a Herdr Core job has no Herdr pane')
        if front:
            raise ValueError('--front-door is for a Herdr TUI job: the front door reads the lead\'s pane, and a Herdr Core job has none')
        if not relay:
            return native_.new(ask_file, name, review, fork, cwd, kind, space, max_helpers)
        return relay_.new_core(ask_file, name, review, fork, cwd, kind, app or os.environ.get('STAMPEDE_APP_SPACE') == '1')
    if app:
        raise ValueError('--app-space is for new --core: it shows a Herdr Core job in the Herdr app; a Herdr TUI job has its panes')
    if not (workspace or pane):
        raise ValueError('new needs --workspace or --pane, or run it inside Herdr' + relay_.core_hint())
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
    if info:
        herdrapi_.herdr('tab', 'rename', info['tab_id'], 'lead')
    else:
        pane = herdrapi_.herdr('tab', 'create', '--workspace', workspace, '--cwd', str(repo), '--label', 'lead', '--no-focus')['root_pane']['pane_id']
    brief = job / 'briefs' / (lead + '.md')
    brief.parent.mkdir()
    brief.write_text(agents_.lead_brief(job, lead, owner, review, fork, front=front, kind=kind))
    args = agents_.cli_args(job, lead, kind, *agents_.lead_model(kind), [], lead=True)
    herdrapi_.herdr('pane', 'rename', pane, lead)
    blocked = tui_.launch(lead, kind, pane, (['--resume', fork, '--fork-session'] if fork else []) + args)
    # the reopen record leaves the fork out: a reopen resumes the lead's own session, not the planning chat
    subprocess.run([str(base_.SCRIPTS.parent.parent / 'grokbot-herdr/scripts/herdr-reopen-snapshot'), 'record', str(job), lead,
                    kind, str(brief), '--', *args], check=True)
    job_.mark_job(ws_id, job)
    if blocked:
        return print(f'BLOCKED {lead}: clear the startup dialog, then fleet-job tell {job} lead "Read {brief}"')
    pointer = f'You are {lead}. Read {brief} and do everything it says.'
    if kind == 'codex' and tui_.type_pointer(job, lead, 'lead', brief, pointer):
        return 1
    if kind == 'claude':
        owner_.tell(job, lead, pointer)
    print(lead + ' ' + str(job))


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='fleet-job')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('new'); p.add_argument('--file', required=True)
    p.add_argument('--workspace', help='default: $HERDR_WORKSPACE_ID (Herdr TUI only)')
    p.add_argument('--core', action='store_true', help='run the job on Herdr Core (hc), in --cwd; start --pane still hands '
                   'cursor, hermes or kimi to Herdr TUI panes')
    p.add_argument('--cwd', help='with --core: the repo (default: the git root of the current folder)')
    p.add_argument('--name'); p.add_argument('--review', action='store_true')
    p.add_argument('--pane', help="an existing empty pane for the lead (a fresh workspace's root pane); its tab becomes lead")
    p.add_argument('--fork', metavar='SESSION_ID', help='start the lead as a fork of this Claude session (the chat that planned the job)')
    p.add_argument('--front-door', action='store_true', help='a chat outside Herdr stays the owner\'s only contact: the lead posts to <job>/outbox')
    p.add_argument('--lead', choices=sorted(agents_.LEAD), help='the lead\'s CLI: claude (claude-opus-5-5) or codex (gpt-6-astra); default '
                   '$FLEET_LEAD_KIND, else claude. --fork takes claude only')
    p.add_argument('--app-space', action='store_true', help='with --core --relay: label the lead and workers for the Herdr app '
                   '(herdr.space, herdr.tab), so it shows the job in a space; a native job always carries them')
    p.add_argument('--relay', action='store_true', help='with --core: the earlier Core job (a follower, inbox files, hooks)')
    p.add_argument('--space', help='with --core: the space\'s name (default: the job\'s name)')
    p.add_argument('--max-helpers', type=int, help=f'with --core: helpers running at once (default $STAMPEDE_MAX_HELPERS, else 12)')
    p = sub.add_parser('post'); p.add_argument('job'); p.add_argument('text', nargs='+'); p.add_argument('--file', action='append', default=[])
    p = sub.add_parser('wait'); p.add_argument('job'); p.add_argument('--timeout', type=int, default=3600, help='seconds; exit 3 when nothing came')
    p = start_parser = sub.add_parser('start'); p.add_argument('job'); p.add_argument('agent'); p.add_argument('--kind')
    p.add_argument('--pane', help='the Herdr TUI pane (required on the TUI; in a Core job, the pane a cursor, hermes or kimi '
                   'agent is handed to)'); p.add_argument('--brief')
    p.add_argument('--tab', help='a native job: the workstream tab (default main)')
    p.add_argument('--parent', help='a native job: the agent it runs under (default: the caller, else the lead)')
    p.add_argument('--outlive-parent', action='store_true', help='a native job: keep it running when its parent ends')
    p.add_argument('--cwd', help='a Herdr Core job: the folder an agent Core runs starts in (default: the repo)')
    p.add_argument('--model'); p.add_argument('--effort')
    p.add_argument('--report', action='append', default=[]); p.add_argument('--yolo-in', help='a worker in its own git worktree: no-checks mode')
    for verb in ('next', 'snapshot'):
        sub.add_parser(verb, help='a native job').add_argument('job')
    p = sub.add_parser('reopen', help='a native job: start what is not live, parents first'); p.add_argument('job')
    p.add_argument('--fresh', action='store_true', help='every Claude agent starts a new session with its brief')
    p.add_argument('--prompt', action='store_true', help='each resumed helper is told its parent\'s new address')
    p.add_argument('--rerun-programs', action='store_true', help='run programs that did not exit 0 again')
    p = sub.add_parser('close', help='a native job: end an agent\'s subtree, or the whole job'); p.add_argument('job')
    p.add_argument('agent', nargs='?')
    p = sub.add_parser('tree', help='a native job: its tree as Core holds it'); p.add_argument('job'); p.add_argument('--json', action='store_true')
    p = sub.add_parser('tell'); p.add_argument('job'); p.add_argument('agent'); p.add_argument('text', nargs='+')
    p = sub.add_parser('ask'); p.add_argument('job'); p.add_argument('--option', action='append', default=[]); p.add_argument('question', nargs='+')
    p.add_argument('--gate', action='store_true', help='a gate: one exact action at one commit, yes or no')
    p.add_argument('--sha', help='with --gate: the full commit id it is about'); p.add_argument('--pr', type=int, help='with --gate: the PR number')
    p = sub.add_parser('approve-gate'); p.add_argument('job'); p.add_argument('gate'); p.add_argument('--sha', required=True)
    p.add_argument('--by', required=True)
    p.add_argument('--digest', help='the gate as it was asked, from the approve command the bot was handed')
    p = sub.add_parser('gate-ok'); p.add_argument('job'); p.add_argument('gate'); p.add_argument('--sha', required=True)
    p = sub.add_parser('cancel'); p.add_argument('job'); p.add_argument('ident')
    p = sub.add_parser('approve'); p.add_argument('job'); p.add_argument('--by', required=True)
    p = sub.add_parser('finish'); p.add_argument('job'); p.add_argument('summary', nargs='+')
    p = sub.add_parser('hook'); p.add_argument('action'); p.add_argument('job'); p.add_argument('--agent', required=True)
    p.add_argument('payload', nargs='?', help="Codex's notify JSON, passed as the last argument; other hooks read stdin")
    p = sub.add_parser('_reopen', help='a Herdr Core job: start what is missing (reopen.sh runs it)'); p.add_argument('job')
    p.add_argument('--lead', action='store_true', help='only the follower and the lead')
    p.add_argument('--prompt', action='store_true', help='a restarted Codex worker gets its brief pointer again')
    p.add_argument('--fresh', action='store_true', help='each agent it starts begins a new session with its brief')
    p = sub.add_parser('_deliver', help='type a Codex lead\'s unread inbox lines into its pane once it is idle'); p.add_argument('job')
    p = sub.add_parser('_wake', help='start a _deliver in the background (a Claude lead needs none)'); p.add_argument('job')
    p = sub.add_parser('_ask'); p.add_argument('job'); p.add_argument('--command'); p.add_argument('--option', action='append', default=[])
    p.add_argument('--gate')
    p.add_argument('--ident', help='this question\'s id: names its waiter, so cancel signals only that process')
    p.add_argument('question', nargs='+')
    program = []
    if argv[:1] == ['start'] and '--' in argv:  # a native job: a program after --; cut here, since argparse before 3.13
        cut = argv.index('--')                    # loses it when a flag stands between the name and the --
        argv, program = argv[:cut], argv[cut + 1:]
    a = parser.parse_args(argv)
    a.program = program
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
        print('fleet-job ' + a.cmd + ': ' + base_.line(error), file=sys.stderr)
        return 2
    except (hcapi_.HcError, herdrapi_.HerdrError, OSError) as error:  # Herdr, Herdr Core or a program failed: one line, never a traceback
        print('fleet-job ' + a.cmd + ': ' + base_.line(error), file=sys.stderr)
        return 1


NATIVE_ONLY = ('next', 'tree', 'snapshot', 'reopen', 'close')


def run(a):
    from . import relay as relay_
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
