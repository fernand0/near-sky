#!/usr/bin/env python3

"""Utility module for OpenSky API authentication.
Provides a ``headers()`` function that returns the appropriate HTTP
Authorization header when the ``OPENSKY_TOKEN`` environment variable is
set. If the variable is absent, an empty dictionary is returned.
"""

import os


def headers() -> dict:
    """Return HTTP headers for OpenSky API calls.

    The original project expected a ``testingOpenskyToken`` module with a
    ``headers()`` function.  This refactored module keeps the same behaviour
    but uses a clearer name.
    """
    token = os.getenv("OPENSKY_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
