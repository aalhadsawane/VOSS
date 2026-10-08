"""Core value types shared by world, observe, policy and runtime (doc 05 §3).

Views live here so that ``policy`` never needs ``observe`` or ``world``. Types are added phase by phase.
"""

from __future__ import annotations
