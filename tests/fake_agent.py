"""A fake agent that speaks OSC 7501 like Claude or Codex: idle at start, then working and done for each line it reads.
core_smoke.py runs it in a real Herdr Core terminal, as an agent and as a stand-in `claude` for stampede new --core."""
import os, sys, time


def status(word):
    os.write(1, ('\x1b]7501;state=' + word + ':app=fake-agent\x1b\\').encode())


status('idle')
for _ in sys.stdin:
    status('working')
    time.sleep(0.3)
    status('done')
