"""Sibling module that reaches back up the package."""
from ..core import Engine


def make_engine(store):
    """Build an engine for `store`."""
    return Engine(store)
