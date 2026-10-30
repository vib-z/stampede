#!/usr/bin/env python3
"""A smoke run on a real Herdr Core (hc 0.1.13) in a scratch session of its own (HC_SESSION and XDG folders under a
temporary folder), never the machine's own core. CI runs it after installing hc; it prints PASS or the first FAIL.
The stampede part (new --core, tell, finish, the follower's exit) runs once herdr-event-core is in the checkout."""
import json, os, queue, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
AGENT = SRC / 'tests/fake_agent.py'
T = Path(tempfile.mkdtemp(prefix='hc-smoke.', dir='/tmp'))  # short: a Unix socket path holds at most 103 bytes
ENV = {k: v for k, v in os.environ.items() if not k.startswith(('HC_', 'HERDR_', 'STAMPEDE_'))}
ENV.update(HC_SESSION='smoke', XDG_STATE_HOME=str(T / 'state'), XDG_RUNTIME_DIR=str(T / 'run'), XDG_CONFIG_HOME=str(T / 'config'))


def fail(text):
    raise SystemExit('FAIL: ' + text)


def hc(*args, env=None):
    result = subprocess.run(['hc', *args], capture_output=True, text=True, env=env or ENV, timeout=90)
    if result.returncode:
        fail(f'hc {" ".join(args)}: exit {result.returncode}: {result.stderr.strip()}')
    return json.loads(result.stdout)


def until(what, check, seconds=45):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return
        time.sleep(0.5)
    fail(what)


def core_basics():
    hc('run', '--bg', '--json', '--name', 'smoke-agent', '--label', 'smoke=1', '--', sys.executable, '-I', str(AGENT))
    waited = hc('wait', '--json', '--timeout', '20', 'smoke-agent')
    if waited.get('status') != 'idle':
        fail(f'the fake agent is {waited.get("status")}, not idle')
    lines = queue.Queue()
    events = subprocess.Popen(['hc', 'events', '--json', '--label', 'smoke=1'], stdout=subprocess.PIPE, text=True, env=ENV)
    threading.Thread(target=lambda: [lines.put(json.loads(row)) for row in events.stdout], daemon=True).start()
    try:
        snapshot = lines.get(timeout=20)
        if [t.get('name') for t in snapshot.get('terminals', [])] != ['smoke-agent']:
            fail(f'the event snapshot is {snapshot}')
        sent = hc('send', '--json', '--if', 'idle', '--wait', '--timeout', '20', 'smoke-agent', 'work')
        if (sent.get('wait') or {}).get('status') != 'done':
            fail(f'the turn did not end in done: {sent}')
        seen, deadline = set(), time.time() + 20
        while {'status', 'turn'} - seen and time.time() < deadline:
            try:
                seen.add(((lines.get(timeout=1).get('params') or {}).get('type')))
            except queue.Empty:
                pass
        if {'status', 'turn'} - seen:
            fail(f'no status and turn events on the stream, only {seen}')
    finally:
        events.kill()
    record = hc('get', '--json', 'smoke-agent')
    if (record['status'] or {}).get('state') != 'done' or record['turn'] < 1 or record['labels'] != {'smoke': '1'}:
        fail(f'the record is {record}')
    print('ok hc run, wait, send --if idle --wait, events, get')


def stampede_core():
    repo, fake = T / 'code/repo', T / 'bin'
    repo.mkdir(parents=True)
    fake.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (fake / 'claude').write_text(f'#!/bin/sh\nexec {sys.executable} -I {AGENT}\n')
    (fake / 'claude').chmod(0o755)
    env = {**ENV, 'PATH': f'{fake}:{ENV["PATH"]}', 'FLEET_TRUST_ROOT': str(T / 'code'), 'HERDR_EVENTS_DIR': str(T / 'events'),
           'HERDR_EVENTS_HOME': str(T / 'queue'), 'HERDR_EVENTS_ROUTES_DIR': str(T / 'routes'), 'FLEET_ASK_CMD': 'false'}
    ask = T / 'ask.md'
    ask.write_text('Smoke test the Core path\n')
    stampede = [str(SRC / 'scripts/stampede')]
    made = subprocess.run(stampede + ['new', '--core', '--file', str(ask), '--cwd', str(repo)], capture_output=True, text=True,
                          env=env, timeout=120)
    if made.returncode:
        fail(f'stampede new --core: exit {made.returncode}: {made.stdout} {made.stderr}')
    lead, job = made.stdout.strip().splitlines()[-1].split(' ', 1)
    key = (Path(job) / 'workspace').read_text().strip()
    names = sorted(t['name'] for t in hc('ls', '--json', '--label', 'stampede.job=' + key, env=env)['terminals'])
    if names != sorted([lead, 'relay-' + key[3:]]):
        fail(f'the job runs {names}')
    subprocess.run(stampede + ['tell', job, 'lead', 'hello from the smoke run'], check=True, env=env, capture_output=True)
    if 'hello from the smoke run' not in (Path(job) / 'inbox' / (lead + '.md')).read_text():
        fail('tell lead did not reach its inbox')
    subprocess.run(stampede + ['finish', job, 'smoke done'], check=True, env=env, capture_output=True)
    until('the follower did not exit after finish',
          lambda: hc('get', '--json', 'relay-' + key[3:], env=env)['state'] == 'finished')
    for terminal in hc('ls', '--all', '--json', '--label', 'stampede.job=' + key, env=env)['terminals']:
        if terminal['state'] == 'live':
            hc('kill', '--json', terminal['address'], env=env)
        hc('rm', '--json', terminal['address'], env=env)
    if hc('ls', '--all', '--json', '--label', 'stampede.job=' + key, env=env)['terminals']:
        fail('terminals of the job are left over')
    print('ok stampede new --core, tell, finish, the follower exits, cleanup')


def main():
    try:
        core_basics()
        if (SRC / 'skills/grokbot-herdr/scripts/herdr-event-core').exists():
            stampede_core()
        print('PASS')
    finally:
        try:
            for terminal in hc('ls', '--all', '--json')['terminals']:
                subprocess.run(['hc', 'kill', '--json', terminal['address']], capture_output=True, env=ENV)
            subprocess.run(['hc', 'server', 'stop', '--json'], capture_output=True, env=ENV, timeout=60)
        finally:
            shutil.rmtree(T, ignore_errors=True)


if __name__ == '__main__':
    main()
