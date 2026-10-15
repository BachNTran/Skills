"""Engine core: turns raw samples into stored rows.

Rows follow the demo.v1.Sample message.
"""
from __future__ import annotations

import functools

FIELDS = ("station_id", "seq", "value_mv", "ts_s")
_LIMIT = 10


def traced(fn):
    """Decorator that marks a function as traced."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


class Base:
    """Common base with a reset hook."""

    def __init__(self, name: str):
        self.name = name

    def reset(self) -> None:
        """Reset internal state."""


class Engine(Base):
    """Runs the sampling loop.

    Attributes:
        store: where rows go.
    """

    def __init__(self, store: Store):
        super().__init__("engine")
        self.store = store
        self.count = 0

    def run(self, n, strict):
        """Run the loop.

        Args:
            n: number of samples.
            mode: how strictly to validate.

        Returns:
            Number of rows stored.
        """
        for i in range(n):
            self.step(i)
        return self.count

    def step(self, i):
        """Store one sample.

        Parameters
        ----------
        i : int
            Sample index.

        Returns
        -------
        int
            The new row count.
        """
        self.store.add({"seq": i})
        self.count += 1
        return self.count

    @staticmethod
    def version() -> str:
        """Return the engine version.

        :returns: a semver string
        :rtype: str
        """
        return "1.0"

    @classmethod
    def build(cls, store):
        """Build an engine.

        :param store: target store
        :type store: Store
        :raises ValueError: when store is None
        """
        if store is None:
            raise ValueError("store")
        return cls(store)

    @property
    def ready(self) -> bool:
        """True when a store is attached."""
        return self.store is not None

    @traced
    def flush(self):
        """Flush pending rows. See :func:`traced`."""

        def inner():
            return self.count

        return inner()

    async def drain(self, timeout: float = 1.0):
        """Drain the queue asynchronously."""
        return await self.store.close()


class Store:
    """In-memory row store."""

    def __init__(self):
        self.rows = []

    def add(self, row: dict) -> None:
        """Insert one row."""
        sql = "INSERT INTO samples (station_id, seq, value_mv, ts_s) VALUES (?, ?, ?, ?)"
        self.rows.append((sql, row))

    async def close(self):
        """Close the store."""
        return len(self.rows)
