"""Per-language extractors for the wiki code map (spec §3). Entry point: `extract.extract`."""
from .extract import ADAPTER_VERSION, LANG_BY_EXT, extract, lang_of

__all__ = ["ADAPTER_VERSION", "LANG_BY_EXT", "extract", "lang_of"]
