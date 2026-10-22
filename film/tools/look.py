"""Run the pinned critique, omitting only contact-sheet labels on this host.

The local ffmpeg lacks drawtext. Gate analysis and thresholds stay unchanged.
"""
import importlib.util
from pathlib import Path

source = Path(__file__).parent / 'motionmaxxing/look.py'
spec = importlib.util.spec_from_file_location('motionmaxxing_look', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.drawtext_filter = lambda font: ''
if __name__ == '__main__':
    module.main()
