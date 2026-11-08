#!/usr/bin/env python3
"""The linux-install cases I01 to I06, run inside the eval container (tests/evals/linux/run.sh starts it) against the
checkout at ~/stampede, a real herdr server and a real hc core in a scratch session that inside.sh has started, and the
pinned binaries install-pinned.sh put in ~/.local/bin. Records through record.py.

    python3 tests/evals/linux/install_checks.py --label baseline-linux-install --bot evalbot --repo ~/code/eval-repo

I01 the pinned installs (versions, digests, no root); I02 install.sh twice (links, the flock loop, nothing changes the
second time); I05 the plugin link and its event hook on a real status change; I03 herdr-doctor plain, --relay and
--core; I04 the unit suite; I06 moshi-hook 0.4.50 unpaired behind stampede ask and a gate. Order: I01, I02, I05, I03,
I04, I06 (the doctor's --relay check wants the plugin linked first)."""
import argparse, hashlib, json, os, re, shlex, subprocess, sys, time, traceback
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tests/evals'))
import record  # noqa: E402

HOME = Path.home()
BIN = HOME / '.local/bin'
EVENTS = Path(os.environ.get('HERDR_EVENTS_DIR') or HOME / '.config/herdr-events')
STATE = Path(os.environ.get('XDG_STATE_HOME') or HOME / '.local/state')
RELAY_LOG = STATE / 'herdr-events.log'
PINS = {row.split()[0]: row.split()[3] for row in (HERE / 'pins.txt').read_text().splitlines()
        if row.strip() and not row.startswith('#') and row.split()[1] == {'aarch64': 'arm64', 'x86_64': 'amd64'}.get(os.uname().machine, '')}
WANT = {'herdr': 'herdr 0.9.5', 'hc': 'hc 0.1.19', 'moshi-hook': 'moshi-hook version 0.4.50'}
SHA = 'a' * 40


class Ev:
    def __init__(self, ident):
        self.ident, self.cmds, self.log, self.started = ident, [], [], time.time()

    def sh(self, argv, env=None, timeout=300, cwd=None, stdin=None):
        argv = [str(a) for a in argv]
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd, input=stdin)
            code, out, err = done.returncode, done.stdout, done.stderr
        except subprocess.TimeoutExpired as error:
            code, out, err = 124, (error.stdout or b'').decode() if isinstance(error.stdout, bytes) else (error.stdout or ''), f'timed out after {timeout} s'
        except OSError as error:
            code, out, err = 127, '', str(error)
        self.cmds.append(shlex.join(argv) + f'  -> exit {code}')
        self.log.append(f'$ {shlex.join(argv)}\n[{code}] {out.strip()[-1500:]}\n{err.strip()[-800:]}'.rstrip())
        return code, out, err

    def note(self, text):
        self.log.append(text)

    def result(self, status, actual, notes=''):
        return status, actual, self.cmds, '\n'.join(self.log), time.time() - self.started, notes


def herdr(ev, *args):
    code, out, err = ev.sh(['herdr', *args], timeout=120)
    try:
        return json.loads(out).get('result', {})
    except ValueError:
        return {}


def wait(check, seconds, every=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = check()
        if found:
            return found
        time.sleep(every)
    return check()


def i01(ev, a):
    """The three pinned binaries: in ~/.local/bin, owned by this unprivileged user, the versions asked for, and the
    artefact digests install-pinned.sh checked equal to pins.txt."""
    rows = {}
    installed = HOME / '.local/share/stampede-eval/installed.tsv'
    recorded = {r.split('\t')[0]: r.split('\t') for r in installed.read_text().splitlines()} if installed.is_file() else {}
    for name, want in WANT.items():
        code, out, _ = ev.sh([name, '--version'])
        path = BIN / name
        real = path.resolve()
        owner_ok = path.exists() and real.stat().st_uid == os.getuid() and os.getuid() != 0
        digest_ok = name in recorded and recorded[name][2] == PINS.get(name)
        rows[name] = {'version': out.strip().splitlines()[0] if out.strip() else '', 'version_ok': out.strip().startswith(want),
                      'path': str(path), 'owner_ok': owner_ok, 'digest_ok': digest_ok, 'pinned_sha256': PINS.get(name)}
        if name == 'herdr' and path.exists():  # a plain binary: its own digest is the pin
            rows[name]['binary_sha256_ok'] = hashlib.sha256(real.read_bytes()).hexdigest() == PINS.get(name)
    ev.note(json.dumps(rows, indent=1))
    ev.sh(['ls', '-la', str(BIN)])
    ok = all(r['version_ok'] and r['owner_ok'] and r['digest_ok'] for r in rows.values()) and rows['herdr'].get('binary_sha256_ok')
    return ev.result('pass' if ok else 'fail', '; '.join(f'{k} {v["version"]} digest {"ok" if v["digest_ok"] else "MISMATCH"}' for k, v in rows.items())
                     + f'; uid {os.getuid()}, all in ~/.local/bin')


def i02(ev, a):
    """install.sh as the user in the login home: links, then the flock loop (no systemd here); a second run changes nothing."""
    env = {**os.environ}
    first = ev.sh(['bash', str(ROOT / 'install.sh')], env=env, cwd=ROOT)
    links = sorted(p.name for p in BIN.iterdir() if p.is_symlink() and str(p.resolve()).startswith(str(ROOT)))
    skills = {app: sorted(p.name for p in (HOME / app / 'skills').glob('*') if p.is_symlink()) for app in ('.claude', '.codex')}
    loop = ev.sh(['bash', '-c', f'. {shlex.quote(str(ROOT / "skills/grokbot-herdr/scripts/herdr-platform"))}; event_loop_running && '
                                f'echo "loop pid $(cat {shlex.quote(str(STATE / "herdr-events/supervise.pid"))})" || echo "no loop"'])
    second = ev.sh(['bash', str(ROOT / 'install.sh')], env=env, cwd=ROOT)
    changed = [row for row in second[1].splitlines() if row and not row.startswith(('ok ', 'Next,'))]
    ev.note(f'links into the checkout: {links}\nskills: {skills}')
    ok = (first[0] == 0 and 'started the event loop' in first[1] and 'linked' in first[1] and 'loop pid' in loop[1]
          and second[0] == 0 and not changed and 'ok event loop' in second[1]
          and {'stampede', 'fleet-job', 'herdr-doctor', 'herdr-send', 'herdr-event-post', 'herdr-event-flush', 'herdr-event-supervise'} <= set(links)
          and all(set(skills[app]) >= {'stampede', 'herdr-fleet', 'grokbot-herdr', 'share-plan'} for app in skills))
    systemd = 'systemctl answers' if subprocess.run(['bash', '-c', 'systemctl --user show-environment'], capture_output=True).returncode == 0 else 'no systemctl --user'
    return ev.result('pass' if ok else 'fail', f'first run: {len(links)} command links, skills linked for .claude and .codex, '
                     f'{"started the event loop" if "started the event loop" in first[1] else "no event loop"} ({systemd}); '
                     f'second run: {"nothing changed" if not changed else "changed: " + "; ".join(changed)[:200]}',
                     notes='The flock loop is the Linux path verified here. A systemd user manager cannot run in this container: systemd '
                           'as PID 1 in an unprivileged container (no --privileged, no host mount) exits 255 with "Failed to create '
                           '/init.scope control group: Read-only file system" (probed 8 Nov 2026), so the systemd timers stay a gap.')


def i05(ev, a):
    """herdr plugin link of this checkout, then a stand-in agent's status change makes Herdr run the event hook."""
    linked = ev.sh(['herdr', 'plugin', 'link', str(ROOT)])
    listed = ev.sh(['herdr', 'plugin', 'list'])
    enabled = bool(re.search(r'^- stampede .*enabled', listed[1], re.M)) or '"stampede"' in listed[1] and 'enabled' in listed[1]
    ws = herdr(ev, 'workspace', 'create', '--cwd', str(a.repo), '--label', 'eval-plugin', '--no-focus')
    pane, ws_id = ws.get('root_pane', {}).get('pane_id'), ws.get('workspace', {}).get('workspace_id')
    if not pane:
        return ev.result('error', 'herdr workspace create answered no pane')
    time.sleep(1)
    started = ev.sh(['herdr', 'agent', 'start', 'probe-plugin', '--kind', 'claude', '--pane', pane, '--timeout', '60000', '--',
                     '--permission-mode', 'auto', '-n', 'probe-plugin'], timeout=90)
    prompted = ev.sh(['herdr', 'agent', 'prompt', 'probe-plugin', 'one turn, please', '--wait', '--timeout', '30000'], timeout=60)
    state_file = STATE / 'herdr/plugins/stampede/panes' / pane.replace(':', '_')
    logged = wait(lambda: [r for r in herdr(ev, 'plugin', 'log', 'list', '--plugin', 'stampede').get('logs', [])
                           if r.get('event') == 'pane.agent_status_changed'], 30, every=2)
    relayed = wait(lambda: [row for row in (RELAY_LOG.read_text().splitlines() if RELAY_LOG.is_file() else [])
                            if f'pane={pane}' in row and 'herdr' in row], 10)
    states = state_file.read_text().strip() if state_file.is_file() else 'no state file'
    ev.note(f'plugin log entries: {json.dumps(logged[-3:], indent=1)[:1500]}\nstate file {state_file}: {states}\nrelay log: {relayed[-3:]}')
    herdr(ev, 'workspace', 'close', ws_id)
    finished = [r for r in logged if r.get('status') != 'running']  # a hook still running at this moment is no failure
    ok = linked[0] == 0 and enabled and started[0] == 0 and prompted[0] == 0 and finished and all(r.get('status') == 'succeeded' for r in finished) \
        and state_file.is_file() and relayed
    return ev.result('pass' if ok else 'fail', f'link exit {linked[0]}, listed enabled {enabled}, agent start exit {started[0]}, '
                     f'{len(logged)} hook runs logged ({", ".join(sorted({r.get("status", "?") for r in logged})) or "none"}), '
                     f'state file {"written: " + states if state_file.is_file() else "missing"}, relay log {"reached" if relayed else "not reached"}')


def i03(ev, a):
    """herdr-doctor plain, --relay and --core: no PROBLEM line (the --core run: none for the Core lines)."""
    results = {}
    core_env = {**os.environ}
    for name, argv, env in (('plain', ['herdr-doctor'], None), ('relay', ['herdr-doctor', '--relay'], None), ('core', ['herdr-doctor', '--core'], core_env)):
        code, out, err = ev.sh(argv, env=env, timeout=180)
        problems = [row for row in out.splitlines() if row.startswith('PROBLEM')]
        results[name] = (code, problems, [row for row in out.splitlines() if row.startswith('ok')])
    core_lines = results['core'][1]
    core_problems = [row for row in core_lines if re.search(r'\bhc\b|Herdr Core|claude|codex', row)]
    ok = not results['plain'][1] and not results['relay'][1] and not core_problems and results['plain'][0] == 0 and results['relay'][0] == 0
    text = '; '.join(f'{k}: exit {v[0]}, {len(v[2])} ok, {len(v[1])} PROBLEM' + (f' ({"; ".join(v[1])[:300]})' if v[1] else '') for k, v in results.items())
    return ev.result('pass' if ok else 'fail', text)


def i04(ev, a):
    """The whole unit suite in the container, from a copy of the checkout with a throwaway .git: run.sh copies no .git,
    and stampede's update check reads a checkout without one as a Herdr plugin install, which test_update does not
    expect. The full unittest output is kept beside the run as I04-unittest.log (scrubbed)."""
    copy = HOME / 'unit-suite'
    if not copy.exists():
        ev.sh(['cp', '-a', str(ROOT), str(copy)])
        ev.sh(['git', '-C', str(copy), 'init', '-q'])
        ev.sh(['git', '-C', str(copy), 'add', '-A'])
        ev.sh(['git', '-C', str(copy), 'commit', '-q', '-m', 'the checkout under test, for the unit suite'])
    code, out, err = ev.sh([sys.executable, '-m', 'unittest', 'discover', 'tests'], cwd=copy, timeout=2400)
    tail = [row for row in err.strip().splitlines()[-6:]]
    ran = next((row for row in tail if row.startswith('Ran ')), '')
    verdict = tail[-1] if tail else ''
    failed = re.findall(r'^(?:FAIL|ERROR): (\S+ \([^)]+\))', err, re.M)
    a.run_dir.joinpath('I04-unittest.log').write_text(record.scrub(err))
    ev.note('failed tests: ' + (', '.join(failed) if failed else 'none'))
    return ev.result('pass' if code == 0 and verdict.startswith('OK') else 'fail', f'exit {code}; {ran}; {verdict}'
                     + (f'; failed: {", ".join(failed)[:600]}' if failed else ''),
                     notes='Run from a copy with a throwaway .git (the copied checkout has none); the full output is I04-unittest.log in this run folder.')


def i06(ev, a):
    """moshi-hook 0.4.50 unpaired on Linux: stampede ask fails loudly and a gate asked through it is never approved.
    The job is a hand-made local job folder (lead, agents.tsv, inbox): the subject is the ask path, not Herdr."""
    probe = ev.sh(['moshi-hook', 'ask', '--require-remote', '--timeout', '10s', '--source', 'eval', '--', 'Is anyone there?'], timeout=60)
    status = ev.sh(['moshi-hook', 'status'], timeout=30)
    jobs = Path(os.environ.get('FLEET_JOBS_ROOT') or HOME / 'code/herdr-jobs') / 'jobs'
    job = jobs / f'{date.today():%Y-%m-%d}-local-moshi-eval'
    (job / 'inbox').mkdir(parents=True, exist_ok=True)
    (job / 'lead').write_text('lead-moshi\n')
    (job / 'agents.tsv').write_text('# herdr-reopen-snapshot: name\tkind\tsession\tbrief\targs\nlead-moshi\tclaude\t\t\t\n')
    (job / 'ask.md').write_text('moshi eval\n')
    env = {k: v for k, v in os.environ.items() if k != 'FLEET_ASK_CMD'}  # the default: moshi-hook ask --require-remote ...
    stampede = ROOT / 'scripts/stampede'
    asked = ev.sh([stampede, 'ask', str(job), 'Which colour?', '--option', 'red', '--option', 'blue'], env=env, timeout=60)
    inbox = job / 'inbox/lead-moshi.md'
    failed_q = wait(lambda: [row for row in (inbox.read_text().splitlines() if inbox.is_file() else []) if row.startswith('ASK FAILED')], 90)
    gated = ev.sh([stampede, 'ask', str(job), '--gate', '--sha', SHA, 'Deploy the thing'], env=env, timeout=60)
    ident = (re.search(r'GATE ([0-9a-f]{12})', gated[1]) or [None, None])[1]
    failed_g = wait(lambda: [row for row in (inbox.read_text().splitlines() if inbox.is_file() else []) if row.startswith('ASK FAILED Gate')], 90)
    approved = ident and (job / 'gates' / f'{ident}.approved').is_file()
    gate_ok = ev.sh([stampede, 'gate-ok', str(job), ident or '000000000000', '--sha', SHA], env=env)
    ev.note('inbox:\n' + (inbox.read_text() if inbox.is_file() else '(none)'))
    ok = probe[0] not in (0, 1) and asked[0] == 0 and failed_q and gated[0] == 0 and failed_g and not approved and gate_ok[0] != 0
    return ev.result('pass' if ok else 'fail', f'moshi-hook ask unpaired: exit {probe[0]} ({(probe[2] or probe[1]).strip()[:120]}); '
                     f'stampede ask -> inbox {failed_q[0][:100] if failed_q else "no ASK FAILED line"}; gate -> '
                     f'{failed_g[0][:100] if failed_g else "no ASK FAILED line"}; approved {bool(approved)}; gate-ok exit {gate_ok[0]}')


CASES = {'I01': i01, 'I02': i02, 'I05': i05, 'I03': i03, 'I04': i04, 'I06': i06}


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--label', required=True)
    p.add_argument('--bot', default='evalbot')
    p.add_argument('--repo', default=str(HOME / 'code/eval-repo'))
    p.add_argument('--cases', default='')
    p.add_argument('--out')
    p.add_argument('--extra', default='{}', help='JSON for env.json (the image digest and the host, from run.sh)')
    a = p.parse_args(argv)
    wanted = [c for c in a.cases.split(',') if c] or list(CASES)
    run = record.Run(a.label, backend='linux-install', cases=wanted, out_root=a.out, extra=json.loads(a.extra))
    a.run_dir = run.dir
    for ident in wanted:
        ev = Ev(ident)
        try:
            status, actual, cmds, log, seconds, notes = CASES[ident](ev, a)
        except Exception:
            status, actual, cmds, log, seconds, notes = 'error', 'harness error: ' + traceback.format_exc().strip().splitlines()[-1], ev.cmds, \
                '\n'.join(ev.log) + '\n' + traceback.format_exc(), time.time() - ev.started, ''
        run.case(ident, status, None, actual, cmds, log, seconds, notes)
    return run.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
