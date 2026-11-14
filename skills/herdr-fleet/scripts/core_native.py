"""Moved to stampede/native.py: this name re-exports that module for one release."""
import sys; from stampede import native as _native  # noqa: E702
sys.modules[__name__] = _native
