"""Errors the API turns into HTTP responses."""

from __future__ import annotations


class ClientError(ValueError):
    """The request cannot be done as given (bad file, invalid edit): HTTP 422."""


class Conflict(Exception):
    """The request is valid but not allowed in this state (e.g. deleting a linked piece): HTTP 409."""
