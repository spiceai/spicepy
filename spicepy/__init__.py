"""
spicepy
=====
Spice.ai client library.
"""

# flake8: noqa
from . import functions
from ._active_query import ActiveQuery
from ._client import Client
from ._dataframe import SpiceDataFrame
from ._expr import Expr, WindowFrame, case, col, lit
from ._http import RefreshOpts
from ._search import SearchMatch, SearchResult
from ._status import ComponentStatus, ConnectionDetails

__all__ = [
    "ActiveQuery",
    "Client",
    "ComponentStatus",
    "ConnectionDetails",
    "Expr",
    "RefreshOpts",
    "SearchMatch",
    "SearchResult",
    "SpiceDataFrame",
    "WindowFrame",
    "case",
    "col",
    "functions",
    "lit",
]
