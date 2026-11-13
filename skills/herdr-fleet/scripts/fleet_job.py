"""fleet-job: a Herdr job's messages, background owner questions, plan approval and per-CLI hooks. The entry script:
the commands live in the stampede package beside this file (stampede/cli.py has the parser)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I puts no script folder on sys.path
from stampede import cli  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(cli.main(sys.argv[1:]) or 0)
