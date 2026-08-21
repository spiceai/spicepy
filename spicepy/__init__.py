"""
spicepy
=====
Spice.ai client library.
"""

# flake8: noqa
from . import functions
from ._active_query import ActiveQuery
from ._async_query import (
    ListQueriesResult,
    QueryJob,
    QueryJobError,
    QueryResult,
    QueryStatus,
    QuerySummary,
)
from ._client import Client
from ._dataframe import SpiceDataFrame
from ._expr import Expr, WindowFrame, case, col, lit
from ._http import RefreshOpts
from ._nsql import NsqlField, NsqlResult
from ._search import SearchMatch, SearchResult
from ._status import ComponentStatus, ConnectionDetails

__all__ = [
    "ActiveQuery",
    "Client",
    "ComponentStatus",
    "ConnectionDetails",
    "Expr",
    "ListQueriesResult",
    "NsqlField",
    "NsqlResult",
    "QueryJob",
    "QueryJobError",
    "QueryResult",
    "QueryStatus",
    "QuerySummary",
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
