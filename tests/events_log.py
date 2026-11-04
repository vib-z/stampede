"""Relay log path. Same rule as herdr-platform: Library/Logs on macOS, state dir on Linux."""
import platform
from pathlib import Path


def events_log(home) -> Path:
    home = Path(home)
    if platform.system() == 'Darwin':
        return home / 'Library/Logs/herdr-events.log'
    return home / '.local/state/herdr-events.log'
