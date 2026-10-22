"""grokbot-herdr's relay scripts (B1 one event per turn, B2 Codex helper turns, B3 owner tags, B10 outage) on sample
payloads: runs scripts/test-relay.sh, which uses a throwaway HOME with fake herdr and curl (stdlib)."""
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/grokbot-herdr/scripts/test-relay.sh'


class HerdrRelay(unittest.TestCase):
    def test_relay_sample_payloads(self):
        r = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True, timeout=120)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'PASS'), r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
