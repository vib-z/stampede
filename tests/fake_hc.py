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
  send_slow {address: seconds}   `send` to it answers only after this long, typing nothing before (a hung hc)
  send_started {address: value}  the `started` a `send` to it answers (true by default; false: it did not go working)
A terminal's `draft` is what sits typed in its input by `keys` (`ctrl+c` clears it, `enter` submits it): `send` submits
it with the text after it, as Core pastes after text no person is typing. A terminal's `person` is a person's unsent
draft, typed through an attach: {"draft": text, "then": "clear" | "send" | "stay", "after": seconds}. As Core 0.1.20
does, `send` waits `after` seconds for the person, then types the text alone when they cleared the draft, after their
own message when they sent it, and after the draft when it stayed past the limit; `sent` keeps what arrived. A draft
that stays holds the send for `after` seconds, by default the state's `draft_wait` (60, Core's own): a send killed
before that has typed nothing, and the draft is still there.
  version   string               what `hc --version` prints after "hc " (0.1.20 by default)
  core_env  {name: value}        added to the core's own environment, which `exec -- /usr/bin/env` prints: HOME and
                                 XDG_CONFIG_HOME as this fake was called with them, so its config.toml is the test's
  exec_error kind                `exec` fails with this error kind
`keep <t> [--off]` and `label <t> k=v...` (`k=` removes) change the terminal as Core's do; a test plays a lost program
under keep by setting the terminal's argv to a shell's and its status to null, as Core's restarted event leaves it.
  lookup_error kind              after a `run` fails, every `ls` fails with this kind (a lost answer, then no lookup)
  slow      seconds              `run` holds the state lock this long (a launch in progress)
  streams   [[line, ...], ...]   `events`: connection n prints streams[n], one JSON line each, then ends
  hold      [seconds, ...]       `events`: connection n then stays open and quiet this long (the state lock released)
Exit codes and error shapes are Core's: usage 2, not_found 3, blocked 9, status_mismatch 10, finished 11, else 1
(cancelled, a send Core dropped before typing, among them). tests/test_hc_contract.py holds this fake to hc's own schema.
Each HC_SESSION other than the default is a core of its own: its state and calls live in FAKE_HC/<session>/."""
import fcntl, json, os, sys, time
from pathlib import Path

SESSION = (os.environ.get('HC_SESSION') or '').strip()
HOME = Path(os.environ['FAKE_HC']) / ('' if SESSION in ('', 'default') else SESSION)
CODES = {'usage': 2, 'not_found': 3, 'blocked': 9, 'status_mismatch': 10, 'finished': 11}
HOLD = [0]  # seconds an `events` connection stays quiet before it ends


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
        return print('hc ' + state.get('version', '0.1.20'))
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
        t = {'address': address, 'name': name, 'cwd': o.get('cwd'), 'argv': program, 'state': 'live', 'turn': 0, 'keep': bool(o.get('keep')),
             'labels': dict(w.split('=', 1) for w in o['label']), 'status': {'state': 'idle'}, 'status_ms': 1, 'reported': True,
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
    if cmd == 'exec':  # one program without a terminal: only the core's environment is modelled
        if state.get('exec_error'):
            fail(state['exec_error'], 'cannot run it')
        env = {k: os.environ[k] for k in ('HOME', 'XDG_CONFIG_HOME') if os.environ.get(k)}
        return print('\n'.join(f'{k}={v}' for k, v in {**env, **state.get('core_env', {})}.items()))
    if cmd == 'keep':
        o, rest = options(args, {'--json', '--off'}, set())
        t = find(state, rest[0])
        t['keep'] = not o.get('off')
        return print(json.dumps({'terminal': t['address'], 'keep': t['keep']}))
    if cmd == 'label':
        o, rest = options(args, {'--json'}, set())
        t = find(state, rest[0])
        for k, v in (w.split('=', 1) for w in rest[1:]):
            t['labels'].pop(k, None) if v == '' else t['labels'].__setitem__(k, v)
        return print(json.dumps({'terminal': t['address'], 'labels': t['labels']}))
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
            return print(json.dumps({'text': t.get('screen', '\u203a '), 'complete': True, 'how': 'screen'}))  # an empty prompt
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
        time.sleep(state.get('send_slow', {}).get(t['address'], 0))  # killed here, nothing was typed
        person = t.pop('person', None)
        if person:  # a person's unsent draft holds the send: until they send or clear it, or the limit passes
            time.sleep(person.get('after', state.get('draft_wait', 60) if person.get('then', 'stay') == 'stay' else 0))
            if person.get('then') == 'send':
                t['sent'].append(person['draft'])
            elif person.get('then') != 'clear':
                t['draft'] = person['draft'] + t.get('draft', '')
        t['sent'].append(t.pop('draft', '') + rest[1])
        return print(json.dumps({'started': state.get('send_started', {}).get(t['address'], True), 'status': word(t), 'turn': t['turn']}))
    if cmd == 'events':
        n = state.get('connections', 0)
        state['connections'] = n + 1
        streams = state.get('streams', [])
        for row in streams[n] if n < len(streams) else []:
            print(json.dumps(row), flush=True)
        HOLD[0] = state.get('hold', [])[n] if n < len(state.get('hold', [])) else 0
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
    time.sleep(HOLD[0])


if __name__ == '__main__':
    main(sys.argv[1:])
