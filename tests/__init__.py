"""Adds src/ to sys.path so tests can `import imgmeta` from a plain
checkout without requiring `pip install -e .` first.
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
