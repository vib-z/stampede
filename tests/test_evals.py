"""The eval dataset and its recorder: every case well formed and implemented by its runner, and a run scrubbed."""
import json, re, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / 'tests/evals'
sys.path.insert(0, str(EVALS))
import record  # noqa: E402

AREAS = {'G': 'gate', 'S': 'side-effects', 'L': 'lifecycle', 'P': 'portability', 'D': 'dependencies', 'V': 'versions',
         'I': 'linux-install', 'T': 'tui-live', 'C': 'core-live'}
BACKENDS = {'fixture': 'tests/evals/run.py', 'linux-install': 'tests/evals/linux/run.sh',
            'tui-live': 'tests/evals/live/tui_e2e.py', 'core-live': 'tests/evals/live/core_e2e.py'}


class Dataset(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((EVALS / 'cases.json').read_text())['cases']

    def test_cases_are_well_formed(self):
        ids = [c['id'] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), 'duplicate case ids')
        for case in self.cases:
            self.assertRegex(case['id'], r'^[GSLPDVITC][0-9]{2}$')
            self.assertEqual(case['area'], AREAS[case['id'][0]], case['id'])
            self.assertEqual(case['runner'], BACKENDS[case['backend']], case['id'])
            for key in ('title', 'expect'):
                self.assertTrue(case[key].strip(), f'{case["id"]} has no {key}')
            self.assertLessEqual(set(case), {'id', 'area', 'backend', 'runner', 'title', 'expect', 'known_gap'}, case['id'])

    def test_every_fixture_case_is_implemented(self):
        import run
        fixture = {c['id'] for c in self.cases if c['backend'] == 'fixture'}
        self.assertEqual(fixture, set(run.CASES), 'cases.json and run.CASES differ')

    def test_each_existing_runner_names_its_cases(self):
        for backend, runner in BACKENDS.items():
            path = ROOT / runner
            if backend == 'fixture' or not path.is_file():
                continue
            text = path.read_text()
            missing = [c['id'] for c in self.cases if c['backend'] == backend and not re.search(rf"\b{c['id']}\b", text)]
            self.assertEqual(missing, [], f'{runner} does not implement {missing}')


class Recorder(unittest.TestCase):
    def test_a_run_is_scrubbed_and_counted(self):
        with tempfile.TemporaryDirectory() as out:
            run = record.Run('unit', backend='fixture', out_root=out)
            home, other = str(Path.home()), '/ho' 'me/somebody'  # split, so this file holds no home path itself
            run.case('G01', 'pass', 'x', f'ok in {home}/job and {other}/x', commands=[f'cd {record.ROOT}'])
            run.case('G02', 'fail', 'y', 'no')
            self.assertEqual(run.close(), 1)
            written = ''.join(p.read_text() for p in run.dir.iterdir())
            self.assertNotIn(home + '/', written)
            self.assertNotIn(other, written)
            self.assertNotIn(str(record.ROOT), written)
            self.assertIn('| pass | 1 |', (run.dir / 'summary.md').read_text())
            self.assertEqual([json.loads(r)['id'] for r in (run.dir / 'results.jsonl').read_text().splitlines()], ['G01', 'G02'])

    def test_a_bad_status_is_refused(self):
        with tempfile.TemporaryDirectory() as out:
            run = record.Run('unit', backend='fixture', out_root=out)
            with self.assertRaises(ValueError):
                run.case('G01', 'ok', 'x', 'y')


if __name__ == '__main__':
    unittest.main()
