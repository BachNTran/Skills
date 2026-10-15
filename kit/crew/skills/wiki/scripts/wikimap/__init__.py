"""wikimap: the Systems and Code maps and doc checks of the wiki skill (spec §6).

`open_map(root)` builds the map incrementally (cache under the data dir, never inside the repo) and, when
`wikimap.fresh` imports, annotates it with findings. It never writes the doc baseline and never raises on
repo content. Stdlib only; repo text is data.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["Map", "build_map", "open_map", "default_data_dir"]

_LAZY = ("Map", "build_map", "default_data_dir")


def __getattr__(name: str):
    """Load the graph on first use (PEP 562), so the hook's opt-in gate stays cheap."""
    if name in _LAZY:
        from . import graph
        return getattr(graph, name)
    raise AttributeError(name)


def open_map(root: Path, data: Path | None = None, *, exact: bool = False, annotate: bool = True) -> "Map":
    """Build (incremental via the cache) and annotate the map of `root`.

    exact=False walks up to the project root (`tree.find_root`); exact=True uses `root` as given.
    data defaults to `<root>/.wiki` when that dir exists or is git-ignored, else the user cache dir.
    """
    from . import tree
    from .graph import build_map, default_data_dir

    root = Path(root).resolve()
    if not exact:
        root = tree.find_root(root)[0]
    try:
        config = tree.load_config(root)
    except tree.ConfigError:
        config = dict(tree.DEFAULT_CONFIG)
    m = build_map(root, Path(data) if data else default_data_dir(root), exact=True, config=config)
    try:
        from . import fresh
    except Exception:  # noqa: BLE001 - the map works without findings
        fresh = None
    if not annotate:
        m.findings = []
    if fresh is not None and annotate:
        try:
            fresh.annotate(m)  # sets findings and badges; never writes the baseline
        except Exception:  # noqa: BLE001
            m.findings = []
    return m
