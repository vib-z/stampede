#!/usr/bin/env python3
"""A fake Herdr TUI `herdr` for the mixed-job tests: HERDR=<this file>, or a `herdr` on PATH linked to it (herdr-send
takes the one on PATH), and FAKE_HERDR=<a scratch folder>. Never starts a program.

State is FAKE_HERDR/state.json: panes {pane id: {cwd, foreground_cwd, label, screen, agent}}, where an agent is {name,
agent (its kind), agent_status, focused, terminal_id, completion_seq, args, prompts, keys}; every call is one JSON line in
FAKE_HERDR/calls. `agent get` shows terminal_id and completion_seq (as Herdr 0.9.5 does); `agent list` leaves them out.
A test shapes the answers with:
  on_start    {name: fields}   fields an agent starts with (agent_status, focused, ...)
  start_error {name: code}     `agent start` fails with this code; agent_not_ready leaves the agent up and blocked
  spawns      [name, ...]      with a start_error, the agent starts all the same (an answer lost after the spawn)
  list_error  code             `agent list` fails with this code
A prompt turns the agent working, as Herdr's prompt --wait --until working does. Errors are Herdr's shape, exit 1."""
import fcntl, json, os, sys
from pathlib import Path

HOME = Path(os.environ['FAKE_HERDR'])


def fail(code):
    print(json.dumps({'error': {'code': code, 'message': code}}))
    raise SystemExit(1)


def ok(result):
    print(json.dumps({'result': result}))


def view(pane_id, pane, full=False):
    agent = pane['agent']
    return {'pane_id': pane_id, 'workspace_id': pane_id.split(':')[0], 'tab_id': pane_id.split(':')[0] + ':t1',
            **{k: agent.get(k) for k in ('name', 'agent', 'agent_status')}, 'focused': agent.get('focused', False),
            **({k: agent.get(k) for k in ('terminal_id', 'completion_seq')} if full else {})}


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
        return ok({'agents': [view(i, p) for i, p in panes.items() if p.get('agent')]})
    if verb == 'agent get':
        return ok({'agent': view(*find(state, args[0]), full=True)})
    if verb == 'agent start':
        name, kind, pane_id = args[0], args[args.index('--kind') + 1], args[args.index('--pane') + 1]
        if pane_id not in panes:
            fail('pane_not_found')
        error = state.get('start_error', {}).get(name)
        rest = args[args.index('--') + 1:] if '--' in args else []
        state['terminals'] = state.get('terminals', 0) + 1
        spawned = error in (None, 'agent_not_ready') or name in state.get('spawns', [])
        panes[pane_id]['agent'] = {'name': name, 'agent': kind, 'agent_status': 'blocked' if error == 'agent_not_ready' else 'idle',
                                   'terminal_id': 'term' + str(state['terminals']), 'completion_seq': 0, 'args': rest,
                                   'prompts': [], **state.get('on_start', {}).get(name, {})} if spawned else None
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
