#!/usr/bin/env python3
"""A fake Herdr TUI `herdr` for the mixed-job tests: HERDR=<this file>, or a `herdr` on PATH linked to it (herdr-send
takes the one on PATH), and FAKE_HERDR=<a scratch folder>. Never starts a program.

State is FAKE_HERDR/state.json: panes {pane id: {cwd, foreground_cwd, label, screen, agent}}, where an agent is {name,
agent (its kind), agent_status, focused, terminal_id, completion_seq, agent_session, args, prompts, keys}; every call is
one JSON line in FAKE_HERDR/calls. As Herdr 0.9.5 does (live, 30 Oct 2026): `agent list` rows and `agent get` show the
same fields; terminal_id belongs to the pane (term_<pane>, the same for every launch there); completion_seq is null on a
fresh agent and after its first turn a Herdr-wide counter (`seq` in the state); agent_session is null until set. A test
shapes the answers with:
  on_start    {name: fields}   fields an agent starts with (agent_status, focused, ...)
  start_error {name: code}     `agent start` fails with this code; agent_not_ready leaves the agent up and blocked
  spawns      [name, ...]      with a start_error, the agent starts all the same (an answer lost after the spawn)
  list_error  code             `agent list` fails with this code
  list_answer result           `agent list` answers this result as it is (a malformed list)
  get_error   {pane: code}     `agent get` of that pane fails with this code
  get_answer  {pane: result}   `agent get` of that pane answers this result as it is
  hang        seconds          every call waits this long first (a hung Herdr)
A prompt turns the agent working, as Herdr's prompt --wait --until working does. Errors are Herdr's shape, exit 1."""
import fcntl, json, os, sys, time
from pathlib import Path

HOME = Path(os.environ['FAKE_HERDR'])


def fail(code):
    print(json.dumps({'error': {'code': code, 'message': code}}))
    raise SystemExit(1)


def ok(result):
    print(json.dumps({'result': result}))


def view(pane_id, pane):
    agent = pane['agent']
    return {'pane_id': pane_id, 'workspace_id': pane_id.split(':')[0], 'tab_id': pane_id.split(':')[0] + ':t1',
            'focused': False, **{k: v for k, v in agent.items() if k not in ('args', 'prompts', 'keys')}}


def find(state, target):
    """An agent by its pane id or its name: (pane id, pane), or not found."""
    for pane_id, pane in state['panes'].items():
        if pane.get('agent') and target in (pane_id, pane['agent'].get('name')):
            return pane_id, pane
    fail('agent_not_found')


def command(state, argv):
    verb, args = ' '.join(argv[:2]), argv[2:]
    panes = state['panes']
    if verb == 'pane get':
        if args[0] not in panes:
            fail('pane_not_found')
        pane = panes[args[0]]
        return ok({'pane': {'pane_id': args[0], 'cwd': pane.get('cwd'), 'foreground_cwd': pane.get('foreground_cwd', pane.get('cwd')),
                            'workspace_id': args[0].split(':')[0], 'tab_id': args[0].split(':')[0] + ':t1'}})
    if verb == 'pane rename':
        if args[0] not in panes:
            fail('pane_not_found')
        panes[args[0]]['label'] = args[1]
        return ok({})
    if verb in ('pane read', 'agent read'):
        pane = panes.get(args[0]) or find(state, args[0])[1]
        return print(pane.get('screen', '❯ '))
    if verb == 'agent list':
        if state.get('list_error'):
            fail(state['list_error'])
        if state.get('list_answer') is not None:
            return ok(state['list_answer'])
        return ok({'agents': [view(i, p) for i, p in panes.items() if p.get('agent')]})
    if verb == 'agent get':
        if state.get('get_error', {}).get(args[0]):
            fail(state['get_error'][args[0]])
        if args[0] in state.get('get_answer', {}):
            return ok(state['get_answer'][args[0]])
        return ok({'agent': view(*find(state, args[0]))})
    if verb == 'agent start':
        name, kind, pane_id = args[0], args[args.index('--kind') + 1], args[args.index('--pane') + 1]
        if pane_id not in panes:
            fail('pane_not_found')
        error = state.get('start_error', {}).get(name)
        rest = args[args.index('--') + 1:] if '--' in args else []
        spawned = error in (None, 'agent_not_ready') or name in state.get('spawns', [])
        panes[pane_id]['agent'] = {'name': name, 'agent': kind, 'agent_status': 'blocked' if error == 'agent_not_ready' else 'idle',
                                   'terminal_id': 'term_' + pane_id, 'completion_seq': None, 'agent_session': None,
                                   'args': rest, 'prompts': [], **state.get('on_start', {}).get(name, {})} if spawned else None
        if error:
            fail(error)
        return ok({'agent': view(pane_id, panes[pane_id])})
    if verb == 'agent wait':
        return ok({'agent': view(*find(state, args[0]))})
    if verb == 'agent prompt':
        pane_id, pane = find(state, args[0])
        pane['agent']['prompts'].append(args[1])
        pane['agent']['agent_status'] = 'working'
        return ok({'type': 'agent_prompted'})
    if verb == 'agent send-keys':
        find(state, args[0])[1]['agent'].setdefault('keys', []).append(args[1:])
        return ok({})
    fail('unknown_command')


def main(argv):
    HOME.mkdir(parents=True, exist_ok=True)
    path = HOME / 'state.json'
    time.sleep((json.loads(path.read_text()) if path.is_file() else {}).get('hang', 0))
    with (HOME / 'calls').open('a') as calls:
        calls.write(json.dumps(argv) + '\n')
    with (HOME / 'state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = HOME / 'state.json'
        state = {'panes': {}, **(json.loads(path.read_text()) if path.is_file() else {})}
        try:
            command(state, argv)
        finally:
            path.write_text(json.dumps(state, indent=1))


if __name__ == '__main__':
    main(sys.argv[1:])
