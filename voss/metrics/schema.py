"""Logged tables (doc 06 §2). Analysis reads these tables only."""

from __future__ import annotations

from enum import StrEnum


class Table(StrEnum):
    INVOCATIONS = "invocations"
    EVENTS = "events"
    PLANS = "plans"
    SOLVER = "solver"
    CACHE = "cache"
    SAMPLES = "samples"
    MESSAGES = "messages"
    RECEIPTS = "receipts"
