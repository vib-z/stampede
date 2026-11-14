"""stampede (also fleet-job): the entry script. The commands live in the stampede package beside this file
(stampede/cli.py has the parser); base.py is plain enough to load on any Python 3 and holds the minimum."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I puts no script folder on sys.path
from stampede import base  # noqa: E402

if sys.version_info[:2] < base.MIN_PYTHON:
    print('stampede needs Python %d.%d or later (this is %s): put a newer python3 first on PATH, since stampede runs the '
             'first python3 there' % (*base.MIN_PYTHON, sys.version.split()[0]), file=sys.stderr)
    sys.exit(2)
from stampede import cli  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(cli.main(sys.argv[1:]) or 0)
