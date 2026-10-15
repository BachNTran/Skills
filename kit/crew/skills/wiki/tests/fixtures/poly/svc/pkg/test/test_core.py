"""Tests for pkg.core."""
import pytest

from pkg.core import Engine, Store


@pytest.mark.req("REQ-PKG-001")
def test_engine_runs():
    eng = Engine(Store())
    assert eng.run(2, True) == 2
