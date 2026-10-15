"""Helpers that use the sibling module."""
from . import sibling
from .sibling import make_engine as build


def twice(store):
    """Build two engines."""
    return [build(store), sibling.make_engine(store)]
