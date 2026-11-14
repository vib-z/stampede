"""stampede check: this checkout's unit tests, the fast part by default, each module in its own process, in a scratch
HOME with no herdr or hc on PATH (the tests bring their own fakes), so nothing reaches a live job on this machine."""
import json, os, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import base as base_

ROOT = base_.SCRIPTS.parents[2]
# the fast part: the repo's shape and contracts, then pure-unit classes. Each must be there, but OPTIONAL
FAST = ('test_shape', 'test_version', 'test_hc_contract', 'test_layers', 'test_settings', 'test_routes', 'test_herdr_trust',
        'test_herdr_send', 'test_platform', 'test_install',
        'test_fleet_job.Messages', 'test_fleet_job.Briefs', 'test_fleet_job.Command')
RAN = re.compile(r'^Ran (\d+) tests? in', re.M)


def run(name, env):
    """(name, ok, tests, seconds, output) for one module or class. A run of no tests is no pass: Python 3.9's unittest
    exits 0 for one, so the count decides, not the exit code alone."""
    began = time.monotonic()
    done = subprocess.run([sys.executable, '-m', 'unittest', 'tests.' + name], cwd=ROOT, env=env, capture_output=True, text=True)
    found = RAN.search(done.stderr)
    count, output = int(found.group(1)) if found else 0, done.stdout + done.stderr
    if not count:
        output += f'\nstampede check: tests.{name} ran no tests\n'
    return name, done.returncode == 0 and count > 0, count, time.monotonic() - began, output


def main(full=False, as_json=False):
    tests = ROOT / 'tests'
    if not tests.is_dir():
        raise ValueError(f'no tests folder in {ROOT}: stampede check runs from a git checkout (git clone the repo, then run it there)')
    if full:  # none at all is a broken checkout, never a pass
        names = sorted(p.stem for p in tests.glob('test_*.py'))
        missing = [] if names else [('tests', 'no test_*.py in this checkout\'s tests folder: run git status there')]
    else:
        names = [n for n in FAST if (tests / (n.split('.')[0] + '.py')).is_file()]
        missing = [(n, f'tests/{n.split(".")[0]}.py is missing from this checkout') for n in FAST if n not in names]
    home = tempfile.mkdtemp(prefix='stampede-check-')
    try:
        os.mkdir(os.path.join(home, 'bin'))
        os.symlink(sys.executable, os.path.join(home, 'bin', 'python3'))
        env = {'HOME': home, 'PATH': os.path.join(home, 'bin') + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
               'STAMPEDE_NO_UPDATE_CHECK': '1'}
        began, results = time.monotonic(), [{'name': n, 'ok': False, 'tests': 0, 'seconds': 0.0, 'output': why} for n, why in missing]
        if not as_json:
            for r in results:
                print(f'FAIL {r["name"]:<32} {r["output"]}', flush=True)
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
            for future in as_completed([pool.submit(run, name, env) for name in names]):
                name, ok, count, seconds, output = future.result()
                results.append({'name': name, 'ok': ok, 'tests': count, 'seconds': round(seconds, 1), 'output': '' if ok else output})
                if not as_json:
                    print(f'{"ok  " if ok else "FAIL"} {name:<32} {count:>4} tests {seconds:6.1f} s', flush=True)
                    if not ok:
                        print(output.rstrip() + '\n')
        seconds, count = time.monotonic() - began, sum(r['tests'] for r in results)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    failed = [r['name'] for r in results if not r['ok']] or ([] if count else ['(no tests ran)'])
    if as_json:
        print(json.dumps({'ok': not failed, 'tests': count, 'seconds': round(seconds, 1),
                          'modules': sorted(results, key=lambda r: r['name'])}, indent=1))
    elif failed:
        print(f'FAILED {len(failed)} of {len(results)}: {", ".join(sorted(failed))} ({count} tests in {seconds:.1f} s)')
    else:
        print(f'ok {count} tests in {seconds:.1f} s' + ('' if full else ' (the fast part; stampede check --full runs all)'))
    return 1 if failed else 0
