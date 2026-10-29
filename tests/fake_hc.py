#!/usr/bin/env python3
"""A fake Herdr Core `hc` for the tests: HC=<this file>, FAKE_HC=<a scratch folder>. Never starts a program.

State is FAKE_HC/state.json; every call is one JSON line in FAKE_HC/calls. A test shapes the answers with:
  on_run    {name: fields}       fields a new terminal starts with (status, state, exit_code, reason, screen)
  run_error {name: kind}         `run` fails with this error kind; with spawn_also, the terminal exists all the same
  after_get {address: fields}    fields applied right after the next `get` of that terminal (a race)
  send_error {address: kind}     `send` to it fails with this error kind
  get_error {address: kind}      `get` of it fails with this error kind
  ls_error  kind                 every `ls` fails with this error kind
  read_error {address: kind}     `read` of it fails with this error kind
A terminal's `draft` is what sits typed in its input: `keys` add to it (`ctrl+c` clears it, `enter` submits it), and
`send` submits the draft with the text after it, as Core pastes after whatever is there; `sent` keeps what arrived.
  lookup_error kind              after a `run` fails, every `ls` fails with this kind (a lost answer, then no lookup)
  slow      seconds              `run` holds the state lock this long (a launch in progress)
  streams   [[line, ...], ...]   `events`: connection n prints streams[n], one JSON line each, then ends
Exit codes and error shapes are Core's: usage 2, not_found 3, blocked 9, status_mismatch 10, finished 11, else 1.
Each HC_SESSION other than the default is a core of its own: its state and calls live in FAKE_HC/<session>/."""
import fcntl, json, os, sys, time
from pathlib import Path

SESSION = (os.environ.get('HC_SESSION') or '').strip()
HOME = Path(os.environ['FAKE_HC']) / ('' if SESSION in ('', 'default') else SESSION)
CODES = {'usage': 2, 'not_found': 3, 'blocked': 9, 'status_mismatch': 10, 'finished': 11}


def fail(kind, message):
    print(json.dumps({'error': {'kind': kind, 'message': message, 'hint': ''}}), file=sys.stderr)
    raise SystemExit(CODES.get(kind, 1))


def word(t):
    return (t.get('status') or {}).get('state')


def view(t):
    """`hc ls`: the CLI view, status as one word."""
    return {**{k: t.get(k) for k in ('address', 'name', 'cwd', 'state', 'turn', 'parent', 'exit_code', 'reason', 'labels')},
            'status': word(t)}


def find(state, ref):
    terminals = state['terminals']
    if ref in terminals:
        return terminals[ref]
    named = [t for t in terminals.values() if t.get('name') == ref]
    live = [t for t in named if t['state'] == 'live']
    if live or named:
        return (live or named)[-1]
    fail('not_found', f'no terminal {ref}')


def options(args, flags, valued):
    """Split leading options from the positional rest; `--` ends options."""
    found, rest, i = {'label': []}, [], 0
    while i < len(args):
        a = args[i]
        if a == '--':
            rest += args[i + 1:]
            break
        if a in flags:
            found[a[2:]] = True
        elif a in valued:
            if a == '--label':
                found['label'].append(args[i + 1])
            else:
                found[a[2:]] = args[i + 1]
            i += 1
        elif a.startswith('--'):
            fail('usage', 'unknown option ' + a)
        else:
            rest.append(a)
        i += 1
    return found, rest


def labelled(t, wanted):
    return all(t.get('labels', {}).get(k) == v for k, v in (w.split('=', 1) for w in wanted))


def command(state, argv):
    cmd, args = argv[0], argv[1:]
    if cmd in ('--version', '-V'):
        return print('hc 0.1.13')
    if cmd == 'run':
        o, program = options(args, {'--bg', '--no-parent', '--no-notify', '--outlive-parent', '--json', '--rm', '--keep'},
                             {'--name', '--cwd', '--label', '--parent', '--timeout', '--on'})
        name = o.get('name')
        if name and any(t.get('name') == name and t['state'] == 'live' for t in state['terminals'].values()):
            fail('name_taken', f'a live terminal is named {name}')
        error = state.get('run_error', {}).get(name)
        address = 't' + str(state['next'])
        state['next'] += 1
        if error and state.get('lookup_error'):
            state['ls_error'] = state['lookup_error']
        if error and not state.get('spawn_also'):
            fail(error, f'cannot start {program[:1]}')
        t = {'address': address, 'name': name, 'cwd': o.get('cwd'), 'argv': program, 'state': 'live', 'turn': 0,
             'labels': dict(w.split('=', 1) for w in o['label']), 'status': {'state': 'idle'}, 'reported': True,
             'exit_code': None, 'reason': None, 'parent': None, 'sent': [], **state.get('on_run', {}).get(name, {})}
        state['terminals'][address] = t
        if error:
            fail(error, 'timed out, but it started')
        time.sleep(state.get('slow', 0))
        return print(json.dumps(t))
    if cmd == 'ls':
        if state.get('ls_error'):
            fail(state['ls_error'], 'no answer')
        o, _ = options(args, {'--all', '--json'}, {'--label'})
        found = [view(t) for t in state['terminals'].values() if (o.get('all') or t['state'] == 'live') and labelled(t, o['label'])]
        return print(json.dumps({'terminals': found, 'machines': [], 'hidden_finished': 0}))
    if cmd in ('get', 'wait', 'kill', 'rm', 'read', 'keys', 'interrupt'):
        o, rest = options(args, {'--json'}, {'--timeout', '--lines', '--children', '--output'})
        t = find(state, rest[0])
        if cmd == 'get' and state.get('get_error', {}).get(t['address']):
            fail(state['get_error'][t['address']], 'no answer')
        if cmd == 'get':
            print(json.dumps(t))
            t.update(state.get('after_get', {}).pop(t['address'], {}))
            return
        if cmd == 'wait':
            ended = 'exit' if t['state'] == 'finished' else 'status'
            return print(json.dumps({'terminal': t['address'], 'ended': True, 'reason': ended, 'status': word(t),
                                     'exit_code': t.get('exit_code'), 'turn': t['turn']}))
        if cmd == 'kill':
            t.update(state='finished', reason='killed', status=None, signal=1)
            return print(json.dumps(t))
        if cmd == 'rm':
            if t['state'] == 'live':
                fail('live', f'{t["address"]} is live')
            del state['terminals'][t['address']]
            return print(json.dumps({'removed': t['address']}))
        if cmd == 'read':
            if state.get('read_error', {}).get(t['address']):
                fail(state['read_error'][t['address']], 'no answer')
            return print(json.dumps({'text': t.get('screen', 'last screen line'), 'complete': True, 'how': 'screen'}))
        if cmd == 'keys':
            t.setdefault('keys', []).append(rest[1:])
            for key in rest[1:]:
                if key == 'ctrl+c':
                    t['draft'] = ''
                elif key == 'enter':
                    t['sent'].append(t.pop('draft', ''))
                else:
                    t['draft'] = t.get('draft', '') + (' ' if key == 'space' else key)
        return print(json.dumps({'turn': t['turn'], 'status': word(t)}))
    if cmd == 'send':
        o, rest = options(args, {'--json', '--force', '--wait'}, {'--if', '--timeout'})
        t = find(state, rest[0])
        if t['state'] != 'live':
            fail('finished', f'{t["address"]} has finished')
        if word(t) == 'blocked' and not o.get('force'):
            fail('blocked', f'{t["address"]} is blocked')
        if state.get('send_error', {}).get(t['address']):
            fail(state['send_error'][t['address']], 'refused')
        if o.get('if') and word(t) != o['if']:
            fail('status_mismatch', f'{t["address"]} is {word(t)}, not {o["if"]}')
        t['sent'].append(t.pop('draft', '') + rest[1])
        return print(json.dumps({'started': True, 'status': word(t), 'turn': t['turn']}))
    if cmd == 'events':
        n = state.get('connections', 0)
        state['connections'] = n + 1
        streams = state.get('streams', [])
        for row in streams[n] if n < len(streams) else []:
            print(json.dumps(row), flush=True)
        return
    fail('usage', 'the fake hc has no ' + cmd)


def main(argv):
    HOME.mkdir(parents=True, exist_ok=True)
    with (HOME / 'calls').open('a') as calls:
        calls.write(json.dumps(argv) + '\n')
    with (HOME / 'state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = HOME / 'state.json'
        state = {'next': 1, 'terminals': {}, **(json.loads(path.read_text()) if path.is_file() else {})}
        try:
            command(state, [a for a in argv if a != '--json'] if argv[:1] != ['run'] else argv)
        finally:
            path.write_text(json.dumps(state, indent=1))


if __name__ == '__main__':
    main(sys.argv[1:])
