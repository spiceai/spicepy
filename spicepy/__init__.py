"""
spicepy
=====
Spice.ai client library.
"""

# flake8: noqa
from . import functions
from ._client import Client
from ._dataframe import SpiceDataFrame
from ._expr import Expr, WindowFrame, case, col, lit
from ._http import RefreshOpts
from ._search import SearchMatch, SearchResponse

__all__ = [
    "Client",
    "Expr",
    "RefreshOpts",
    "SearchMatch",
    "SearchResponse",
    "SpiceDataFrame",
    "WindowFrame",
    "case",
    "col",
    "functions",
    "lit",
]
