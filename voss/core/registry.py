"""Registry of pluggable behaviors chosen by name in config (doc 05 §4).

``@register("planner", "milp")`` records a factory; ``create("planner", "milp", **kw)`` builds it. The registry is
the one sanctioned module-level table (it is append-only and populated at import time).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class Registry:
    """Maps ``(kind, name)`` to a factory."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], Callable[..., Any]] = {}

    def register(self, kind: str, name: str) -> Callable[[T], T]:
        def deco(obj: T) -> T:
            key = (kind, name)
            if key in self._entries and self._entries[key] is not obj:
                raise KeyError(f"duplicate registration {kind}/{name}")
            self._entries[key] = obj  # type: ignore[assignment]
            return obj

        return deco

    def get(self, kind: str, name: str) -> Callable[..., Any]:
        try:
            return self._entries[(kind, name)]
        except KeyError:
            known = ", ".join(self.names(kind)) or "none"
            raise KeyError(f"unknown {kind} '{name}' (known: {known})") from None

    def create(self, kind: str, name: str, *args: Any, **kwargs: Any) -> Any:
        return self.get(kind, name)(*args, **kwargs)

    def names(self, kind: str) -> list[str]:
        return sorted(n for k, n in self._entries if k == kind)


REGISTRY = Registry()
register = REGISTRY.register
create = REGISTRY.create
