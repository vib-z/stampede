#!/usr/bin/env python3
"""A probe of Herdr Core, not a test of stampede: does `hc wait --children any` return, run by a lead from inside its own
terminal, when a child sends it a line with hc send and then reports idle (or exits)?

    python3 tests/evals/live/wait_probe.py [--runs 5] [--keep]

On a scratch core of its own (the fleet test's harness), per run: a native job whose lead is the stand-in agent, one
stand-in Claude helper `kid`. The lead first drains news already there (`hc wait --children any --timeout 2`, twice),
then runs `hc wait --children any --timeout 120`; the kid sleeps 6 s, sends its parent one line, works 3 s more (so a
return on the message and a return on the idle are 3 s apart), then ends its turn idle. A last run has the kid exit then.
It prints, per run, when the wait returned after the send and its JSON."""
import argparse, json, sys
from datetime import datetime

from native_fleet import Fleet, Fail, own_core


def at(row):
    return datetime.strptime(row['at'], '%H:%M:%S.%f')


def probe(f, n, then):
    lead, job, key = f.new(f'probe{n}')
    f.helper(job, 'kid')
    f.done_turn(key, 'kid')
    address = f.by_name(key)[lead]['address']
    wait = 'hc wait --children any --timeout 2 ;; hc wait --children any --timeout 2 ;; hc wait --children any --timeout 120'
    for name, text in ((lead, wait), ('kid', f'sleep 6 ;; hc send {address} "kid: one line for my parent" ;; sleep 3 ;; {then}')):
        told = f.stampede('tell', job, name, text)
        if told.returncode:
            raise Fail(f'tell {name}: {told.stdout} {told.stderr}')
    hc_rows = lambda name: [r for r in f.standin(job, name) if r.get('action') == 'hc']
    seen = []  # the lead's status as Core shows it while it waits
    f.until('the lead\'s last wait ended', lambda: seen.append((f.by_name(key)[lead].get('status') or {}).get('state')) or len(hc_rows(lead)) >= 3, 150)
    drains, waited = hc_rows(lead)[:2], hc_rows(lead)[2]
    sent = hc_rows('kid')[0]
    began = at(waited).timestamp() - waited['seconds']
    after = at(waited).timestamp() - at(sent).timestamp()
    answer = json.loads(waited['stdout'] or '{}')
    typed = lambda: any(r.get('event') == 'prompt' and 'one line for my parent' in r.get('text', '') for r in f.standin(job, lead))
    typed = bool(f.until('the line typed into the lead', typed, 15))
    return (f'run {n} (kid {then}s): drains {[json.loads(d["stdout"] or "{}").get("reason") for d in drains]}; the wait began '
            f'{at(sent).timestamp() - began:.1f} s before the send and returned {after:.1f} s after it, exit {waited["exit"]}, '
            f'reason {answer.get("reason")!r}; the send exit {sent["exit"]} {(sent["stderr"] or sent["stdout"]).strip()[:200]!r}, typed into the lead {typed}, the lead\'s status meanwhile '
            f'{sorted(set(map(str, seen)))}: {json.dumps(answer)[:300]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    before, f = own_core(), Fleet(args.keep)
    try:
        f.prepare()
        for n, then in enumerate(['idle'] * args.runs + ['exit'], 1):
            try:
                print(probe(f, n, then), flush=True)
            except Fail as error:
                print(f'run {n} (kid {then}s): FAIL {error}', flush=True)
    finally:
        f.cleanup()
    print(f'the machine\'s own core: {"the same" if own_core() == before else "changed"} terminals before and after')


if __name__ == '__main__':
    sys.exit(main())
