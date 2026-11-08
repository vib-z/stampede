#!/usr/bin/env python3
"""The fixture evals: each case in cases.json with backend fixture, run through the real `stampede` command against the
repo's fake herdr and hc, in a scratch HOME of its own. Records through record.py; exits 0 when nothing failed or broke.

    python3 tests/evals/run.py --label baseline-macos [--cases G01,G02] [--out <dir>]
"""
import argparse, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import record  # noqa: E402

CASES = {}  # id -> function(): (status, expected, actual, commands, log)


def case(ident):
    def register(fn):
        CASES[ident] = fn
        return fn
    return register


def stub(ident):
    CASES[ident] = lambda: ('blocked', record.cases()[ident]['expect'], 'not implemented yet', [], '')


for _ident in ('G01 G02 G03 G04 G05 G06 G07 G08 G09 G10 G11 G12 G13 G14 G15 G16 S01 S02 L01 L02 L03 L04 L05 L06 L07 L08 '
               'L09 L10 P01 P02 P03 P04 P05 P06 D01 D02 D03 D04 D05 D06 D07 V01 V02').split():
    stub(_ident)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--label', required=True)
    p.add_argument('--cases', default='')
    p.add_argument('--out')
    a = p.parse_args(argv)
    wanted = [c for c in a.cases.split(',') if c] or sorted(CASES)
    unknown = [c for c in wanted if c not in CASES]
    if unknown:
        p.error('no fixture case ' + ', '.join(unknown))
    run = record.Run(a.label, backend='fixture', out_root=a.out)
    dataset = record.cases()
    for ident in wanted:
        started = time.time()
        try:
            status, expected, actual, commands, log = CASES[ident]()
        except Exception:  # the harness broke: nothing is known about the case
            status, expected, actual, commands, log = 'error', dataset[ident]['expect'], 'harness error', [], traceback.format_exc()
        if dataset[ident].get('known_gap') and status in ('pass', 'fail'):
            actual = ('holds here: ' if status == 'pass' else 'does not hold: ') + actual
            status = 'gap'  # a known ceiling: recorded as it is, never counted as a pass or a regression
        run.case(ident, status, expected, actual, commands, log, time.time() - started)
    return run.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
