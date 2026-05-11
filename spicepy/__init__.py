"""
spicepy
=====
Spice.ai client library.
"""

# flake8: noqa
from . import functions
from ._client import Client
from ._dataframe import SpiceDataFrame
from ._expr import Expr, case, col, lit
from ._http import RefreshOpts

__all__ = [
    "Client",
    "Expr",
    "RefreshOpts",
    "SpiceDataFrame",
    "case",
    "col",
    "functions",
    "lit",
]
